from __future__ import annotations

import logging
import signal
import threading
import time
from pathlib import Path
from typing import Any

from ghostnode.collectors.rpc import _call
from ghostnode.config import Config
from ghostnode.intelligence.collectors import (apply_block_plan, prepare_block_plan,
                                                prepare_snapshot, save_snapshot_plan,
                                                StalePlan)
from ghostnode.intelligence.db import IntelligenceDB, utc_now
from ghostnode.intelligence.diagnostics import sanitize_error
from ghostnode.intelligence.process_identity import current_identity
from ghostnode.intelligence.lock import CollectorLock, InstanceLock

LOG = logging.getLogger("ghostnode.collector")


class CollectorRunner:
    """Read-only runner with independent monotonic schedules."""

    def __init__(self, config: Config, db_path: str | Path,
                 wallet_name: str = "ghostmain", lock_path: str | Path | None = None,
                 block_interval: float = 60.0, snapshot_interval: float = 900.0,
                 batch_size: int = 100):
        if block_interval <= 0 or snapshot_interval <= 0 or batch_size < 1:
            raise ValueError("intervals must be positive and batch_size must be positive")
        self.config = config
        self.db_path = Path(db_path).expanduser()
        self.wallet_name = wallet_name
        self.lock_path = Path(lock_path or str(self.db_path) + ".lock")
        self.instance_lock_path = self.lock_path.with_name(self.lock_path.name + ".instance")
        self.block_interval = block_interval
        self.snapshot_interval = snapshot_interval
        self.batch_size = batch_size
        self.stop_event = threading.Event()

    def _rpc(self, method: str, args: list[Any] | None):
        wallet = self.wallet_name if method in {"getstakinginfo", "getbalances", "listtransactions"} else None
        if method in {"getstakinginfo", "getbalances"} and args == [self.wallet_name]:
            args = None
        if args is None:
            return _call(method, self.config, wallet=wallet)
        return _call(method, self.config, wallet=wallet, args=args)

    def preflight(self) -> tuple[bool, str | None]:
        chain, chain_error = self._rpc("getblockchaininfo", None)
        # This is a node-level probe. Do not require a wallet context merely
        # to establish RPC availability; wallet-scoped reads remain unchanged.
        stake, stake_error = _call("getstakinginfo", self.config)
        if chain_error or stake_error or not isinstance(chain, dict) or not isinstance(stake, dict):
            return False, "RPC preflight failed"
        return True, None

    def check(self) -> int:
        ok, error = self.preflight()
        if ok:
            LOG.info("RPC preflight OK")
            return 0
        LOG.error("RPC preflight failed: %s", error)
        return 1

    def _start_run(self, name: str, started_at: str | None = None) -> int:
        pid, ticks, boot_id = current_identity()
        with CollectorLock(self.lock_path, blocking=True):
            with IntelligenceDB(self.db_path) as db:
                return db.start_collector_run(name, started_at, pid, ticks, boot_id)

    def recover_runs(self) -> int:
        with CollectorLock(self.lock_path, blocking=True):
            with IntelligenceDB(self.db_path) as db:
                return db.recover_interrupted_runs()

    def _finish_run(self, run_id: int, status: str, result: dict[str, Any] | None = None,
                    error: Exception | None = None) -> None:
        with CollectorLock(self.lock_path, blocking=True):
            with IntelligenceDB(self.db_path) as db:
                db.finish_collector_run(
                    run_id, status,
                    tip_height=result.get("height") if result else None,
                    records_seen=result.get("processed") if result else None,
                    records_written=result.get("processed") if result else None,
                    error_code=type(error).__name__ if error else None,
                    error_message=sanitize_error(error) if error else None,
                )

    def run_snapshot(self) -> dict[str, Any]:
        data = prepare_snapshot(self._rpc, self.wallet_name)
        with CollectorLock(self.lock_path, blocking=True):
            with IntelligenceDB(self.db_path) as db:
                save_snapshot_plan(db, data)
        LOG.info("snapshot completed: rpc_status=%s", data.get("rpc_status"))
        return data

    def run_blocks(self) -> dict[str, Any]:
        plan = prepare_block_plan(self.db_path, self._rpc, batch_size=self.batch_size,
                                  wallet_name=self.wallet_name)
        with CollectorLock(self.lock_path, blocking=True):
            with IntelligenceDB(self.db_path) as db:
                validated_tip_hash = None
                if plan.blocks:
                    validated_tip_hash, error = self._rpc("getblockhash", [plan.blocks[-1].get("height")])
                    if error or not isinstance(validated_tip_hash, str):
                        raise StalePlan("tip hash revalidation failed")
                result = apply_block_plan(db, plan, wallet_name=self.wallet_name,
                                          validated_tip_hash=validated_tip_hash)
        LOG.info("block scan completed: status=%s processed=%s height=%s",
                 result.get("status"), result.get("processed", 0), result.get("height"))
        return result

    def once(self) -> int:
        with InstanceLock(self.instance_lock_path):
            self.recover_runs()
            run_id = self._start_run("collector_once")
            result = None
            try:
                ok, error = self.preflight()
                if not ok:
                    raise RuntimeError("RPC_PREFLIGHT_FAILED")
                self.run_snapshot()
                result = {"status": "SNAPSHOT_OK"}
                result = self.run_blocks()
            except Exception as exc:
                self._finish_run(run_id, "PARTIAL" if result else "FAILED", result, exc)
                LOG.error("collector once failed: %s", sanitize_error(exc))
                return 1
            self._finish_run(run_id, "SUCCESS", result)
            return 0

    def _worker(self, name: str, interval: float, operation) -> None:
        next_run = time.monotonic()
        retry_delay = 1.0
        while not self.stop_event.is_set():
            now = time.monotonic()
            if now < next_run:
                self.stop_event.wait(next_run - now)
                continue
            try:
                started_at = utc_now()
                run_id = self._start_run(name.replace(" ", "_"), started_at)
                result = None
                try:
                    ok, error = self.preflight()
                    if not ok:
                        raise RuntimeError("RPC_PREFLIGHT_FAILED")
                    result = operation()
                except Exception as exc:
                    self._finish_run(run_id, "FAILED", result, exc)
                    raise
                else:
                    self._finish_run(run_id, "SUCCESS", result if isinstance(result, dict) else None)
                    retry_delay = 1.0
                    next_run += interval
            except (RuntimeError, StalePlan) as exc:
                LOG.error("%s skipped: %s", name, exc)
                next_run = time.monotonic() + min(retry_delay, interval)
                retry_delay = min(retry_delay * 2, 30.0, interval)
            except Exception:
                LOG.error("%s failed", name)
                next_run = time.monotonic() + min(retry_delay, interval)
                retry_delay = min(retry_delay * 2, 30.0, interval)

    def run(self) -> None:
        instance_lock = InstanceLock(self.instance_lock_path)
        instance_lock.__enter__()
        try:
            self.recover_runs()
            LOG.info("collector runner started: block_interval=%ss snapshot_interval=%ss lock=%s",
                     self.block_interval, self.snapshot_interval, self.lock_path)
            threads = [
                threading.Thread(target=self._worker, args=("block scan", self.block_interval, self.run_blocks),
                                 name="ghostnode-block-scanner"),
                threading.Thread(target=self._worker, args=("snapshot", self.snapshot_interval, self.run_snapshot),
                                 name="ghostnode-snapshot"),
            ]
            for thread in threads:
                thread.start()
            try:
                while any(thread.is_alive() for thread in threads):
                    self.stop_event.wait(1.0)
                    if self.stop_event.is_set():
                        break
            finally:
                self.stop_event.set()
                for thread in threads:
                    thread.join(timeout=max(self.config.timeout + 2, 10))
                LOG.info("collector runner stopped")
        finally:
            instance_lock.__exit__(None, None, None)


def install_signal_handlers(runner: CollectorRunner) -> None:
    def stop(signum, _frame):
        LOG.info("shutdown requested: signal=%s", signum)
        runner.stop_event.set()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
