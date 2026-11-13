from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from ghostnode.collectors.network import collect_network
from ghostnode.collectors.rpc import collect_rpc
from ghostnode.collectors.service import collect_service
from ghostnode.collectors.system import collect_system
from ghostnode.collectors.wallet import collect_wallet
from ghostnode.collectors.staking import collect_staking
from ghostnode.config import Config
from ghostnode.models.results import Result, Status
from ghostnode.intelligence.views import blocks as intelligence_blocks
from ghostnode.intelligence.views import collector as intelligence_collector
from ghostnode.intelligence.views import overview as intelligence_overview
from ghostnode.intelligence.views import performance as intelligence_performance
from ghostnode.intelligence.views import rewards as intelligence_rewards

BASE_DIR = Path(__file__).resolve().parent


def _intelligence_path() -> Path:
    return Path(__import__("os").environ.get("GHOSTNODE_INTELLIGENCE_DB", "data/staking_intelligence.sqlite3")).expanduser()


def _overall(*results: Result) -> Status:
    for status in (Status.ERROR, Status.UNKNOWN, Status.WARN):
        if any(result.status == status for result in results):
            return status
    return Status.OK


def collect_dashboard(config: Config) -> dict:
    """Collect a dashboard snapshot without depending on HTTP or Click."""
    wallet_result = collect_wallet(config)
    results = {
        "status": collect_rpc(config),
        "network": collect_network(config),
        "service": collect_service(config),
        "system": collect_system(),
        "wallet": wallet_result,
        "staking": collect_staking(config, bool(wallet_result.data.get("loaded"))),
    }
    if wallet_result.data.get("loaded") is True:
        wallet_result.data["monitoring_mode"] = (
            "STAKING_MONITORING_READY" if results["staking"].status == Status.OK else "WALLET_READY"
        )
    elif wallet_result.data.get("loaded") is False:
        wallet_result.data["monitoring_mode"] = "NODE_ONLY_READY"
    else:
        wallet_result.data["monitoring_mode"] = "UNKNOWN"
    alerts = []
    for name, result in results.items():
        if result.status in {Status.ERROR, Status.UNKNOWN, Status.WARN}:
            alerts.append({"source": name, "status": result.status.value, "message": result.message or "Diagnostic warning"})
    if wallet_result.data.get("loaded") is False:
        alerts.append({"source": "wallet", "status": "WARN", "message": "Wallet is NOT LOADED"})
    return {
        "status": _overall(*results.values()).value,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "data": {name: result.as_dict() for name, result in results.items()},
        "alerts": alerts,
    }


def create_app(config: Config | None = None, clock: Callable[[], datetime] | None = None):
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse
    from fastapi.templating import Jinja2Templates

    active_config = config or Config()
    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    app = FastAPI(title="GhostNode Tools", docs_url=None, redoc_url=None)

    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        snapshot = collect_dashboard(active_config)
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={"snapshot": snapshot},
        )

    @app.get("/api/status")
    async def api_status():
        return collect_dashboard(active_config)

    @app.get("/api/intelligence/overview")
    async def api_intelligence_overview():
        return intelligence_overview(_intelligence_path())

    @app.get("/api/intelligence/performance")
    async def api_intelligence_performance(period: str = "24h", limit: int = 1000, range: str | None = None):
        # `range` is accepted as a compatibility alias for manual/API clients.
        return intelligence_performance(_intelligence_path(), range or period, limit,
                                        now=clock() if clock else None)

    @app.get("/api/intelligence/rewards")
    async def api_intelligence_rewards(status: str | None = None, limit: int = 100, offset: int = 0, since: str | None = None, until: str | None = None):
        return intelligence_rewards(_intelligence_path(), status, limit, offset, since, until)

    @app.get("/api/intelligence/blocks")
    async def api_intelligence_blocks(active: bool | None = None, pos: bool | None = None, wallet_produced: bool | None = None, limit: int = 100, offset: int = 0):
        return intelligence_blocks(_intelligence_path(), active, pos, wallet_produced, limit, offset)

    @app.get("/api/intelligence/collector")
    async def api_intelligence_collector():
        return intelligence_collector(_intelligence_path())

    return app
