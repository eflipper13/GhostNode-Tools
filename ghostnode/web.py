from datetime import datetime, timezone
from json import JSONDecodeError
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
from ghostnode.network import (LAN_MODE, LOCALHOST, TOKEN_REQUIRED, NetworkSettings, load_network_settings,
                               read_dashboard_token, token_is_valid, validate_network_settings)

BASE_DIR = Path(__file__).resolve().parent


def _intelligence_path() -> Path:
    return Path(__import__("os").environ.get("GHOSTNODE_INTELLIGENCE_DB", "data/staking_intelligence.sqlite3")).expanduser()


def _overall(*results: Result) -> Status:
    for status in (Status.ERROR, Status.UNKNOWN, Status.WARN):
        if any(result.status == status for result in results):
            return status
    return Status.OK


def _dashboard_first_run(config: Config, wallet_result: Result,
                         staking_result: Result, rpc_result: Result) -> dict:
    readiness = wallet_result.data.get("readiness", "WALLET_STATUS_UNKNOWN")
    if config.rpc_host:
        mode = "REMOTE_NODE"
    elif readiness == "WALLET_READY":
        mode = "LOCAL_WALLET"
    else:
        mode = "NODE_ONLY"
    if rpc_result.status == Status.ERROR:
        status = "ERROR"
    elif wallet_result.status in {Status.UNKNOWN, Status.WARN} or staking_result.status in {Status.UNKNOWN, Status.WARN}:
        status = "WARN"
    else:
        status = "OK"
    return {
        "status": status,
        "mode": mode,
        "wallet_readiness": readiness,
        "staking_monitoring": (
            "STAKING_MONITORING_READY" if staking_result.status == Status.OK and wallet_result.data.get("loaded")
            else "NODE_ONLY_READY" if wallet_result.data.get("loaded") is False else "UNKNOWN"
        ),
        "backup_status": "GUIDANCE_AVAILABLE",
        "dashboard_bind": "127.0.0.1",
        "read_only": True,
    }


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
    first_run = _dashboard_first_run(config, wallet_result, results["staking"], results["status"])
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
        "data": {**{name: result.as_dict() for name, result in results.items()},
                 "first_run": first_run},
        "alerts": alerts,
    }


def create_app(config: Config | None = None, clock: Callable[[], datetime] | None = None,
               network_settings: NetworkSettings | None = None,
               dashboard_token: str | None = None):
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.templating import Jinja2Templates

    active_config = config or Config()
    settings = network_settings or load_network_settings(active_config.dashboard_network_config)
    if network_settings is None and active_config.dashboard_mode != "localhost":
        settings = NetworkSettings(active_config.dashboard_mode, active_config.dashboard_lan_address,
                                   active_config.dashboard_port)
    settings = validate_network_settings(settings)
    expected_token = dashboard_token if dashboard_token is not None else read_dashboard_token(active_config.dashboard_token_file)
    if settings.mode == LAN_MODE and settings.lan_auth_mode == TOKEN_REQUIRED and not expected_token:
        raise ValueError("LAN dashboard mode requires GHOSTNODE_DASHBOARD_TOKEN_FILE or GHOSTNODE_DASHBOARD_TOKEN")
    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    app = FastAPI(title="GhostNode Tools", docs_url=None, redoc_url=None)

    def listener_host(request: Request) -> str:
        server = request.scope.get("server")
        return server[0] if isinstance(server, (tuple, list)) and server else LOCALHOST

    def local_or_lan_origin_allowed(request: Request) -> bool:
        origin = request.headers.get("origin")
        if not origin or settings.mode != LAN_MODE:
            return True
        return origin in {f"http://{LOCALHOST}:{settings.port}",
                          f"http://{settings.lan_address}:{settings.port}"}

    @app.middleware("http")
    async def dashboard_access(request: Request, call_next):
        is_lan_request = settings.mode == LAN_MODE and listener_host(request) != LOCALHOST
        if is_lan_request and (settings.lan_auth_mode == TOKEN_REQUIRED or request.method in {"POST", "PUT", "PATCH", "DELETE"}):
            authorization = request.headers.get("authorization", "")
            provided = authorization[7:].strip() if authorization.lower().startswith("bearer ") else None
            if not token_is_valid(provided, expected_token):
                detail = ("LAN dashboard authentication required" if settings.lan_auth_mode == TOKEN_REQUIRED
                          else "administrative LAN authentication required")
                return JSONResponse({"detail": detail}, status_code=401,
                                    headers={"WWW-Authenticate": "Bearer"})
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and not local_or_lan_origin_allowed(request):
            return JSONResponse({"detail": "request origin is not allowed"}, status_code=403)
        return await call_next(request)

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

    @app.get("/api/network/settings")
    async def api_network_settings():
        return {"status": "OK", "data": {
            **settings.as_dict(),
            "security_status": (("AUTHENTICATED_LAN" if settings.lan_auth_mode == TOKEN_REQUIRED else "TRUSTED_LAN")
                                 if settings.mode == LAN_MODE else "LOCALHOST_ONLY"),
            "token_configured": bool(expected_token) if settings.mode == LAN_MODE else False,
            "restart_required_for_apply": True,
            "read_only": True,
        }}

    @app.post("/api/network/proposals")
    async def api_network_proposal(request: Request):
        """Validate a proposal without writing files or changing listeners."""
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
            proposed = NetworkSettings(payload.get("mode", settings.mode), payload.get("lan_address"),
                                       int(payload.get("port", settings.port)),
                                       payload.get("lan_auth_mode", settings.lan_auth_mode))
            checked = validate_network_settings(proposed)
        except (ValueError, TypeError, KeyError, JSONDecodeError) as exc:
            return JSONResponse({"status": "ERROR", "message": str(exc)}, status_code=400)
        return {"status": "PROPOSED", "data": {"settings": checked.as_dict(),
                                                  "applied": False,
                                                  "restart_required": True,
                                                  "message": "Review and apply through the explicit operator workflow."}}

    return app
