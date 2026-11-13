import httpx
import pytest

pytest.importorskip("fastapi")

from ghostnode.config import Config
from ghostnode.models.results import Result, Status
from ghostnode import web


@pytest.fixture
def anyio_backend():
    return "asyncio"


def snapshot_result(status=Status.OK, data=None):
    return Result(status, data or {"value": "safe"})


@pytest.mark.anyio
async def test_api_and_html_rendering(monkeypatch):
    monkeypatch.setattr(web, "collect_rpc", lambda config: snapshot_result(data={"network": {"version": "0.23.1.0"}}))
    monkeypatch.setattr(web, "collect_network", lambda config: snapshot_result(data={"connections": {"total": 11}, "peers": []}))
    monkeypatch.setattr(web, "collect_service", lambda config: snapshot_result(data={"active_state": "active"}))
    monkeypatch.setattr(web, "collect_system", lambda: snapshot_result(data={"hostname": "safe-host"}))
    monkeypatch.setattr(web, "collect_wallet", lambda config: snapshot_result(data={"wallet_name": "ghostmain", "balance": 12.5}))
    monkeypatch.setattr(web, "collect_staking", lambda config, loaded: snapshot_result(data={"staking": False, "network_weight": 10}))
    transport = httpx.ASGITransport(app=web.create_app(Config()))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        api = await client.get("/api/status")
        page = await client.get("/")
    assert api.status_code == 200
    assert api.json()["data"]["status"]["data"]["network"]["version"] == "0.23.1.0"
    assert api.json()["data"]["wallet"]["data"]["wallet_name"] == "ghostmain"
    assert "staking" in api.json()["data"]
    assert page.status_code == 200
    assert "safe-host" in page.text
    assert "setInterval(refreshData, 30000)" in page.text
    assert "API connected" in page.text
    assert "Wallet" in page.text
    assert "Peer Details" in page.text
    assert "Staking Intelligence" in page.text
    assert "Alerts" in page.text
    assert "Dashboard" in page.text


@pytest.mark.anyio
async def test_api_error_snapshot_and_no_peer_identifiers(monkeypatch):
    monkeypatch.setattr(web, "collect_rpc", lambda config: snapshot_result(Status.ERROR, {"error": "safe"}))
    monkeypatch.setattr(web, "collect_network", lambda config: snapshot_result(data={"peers": [{"subversion": "/GhostCore:0.23.1.0/"}]}))
    monkeypatch.setattr(web, "collect_service", lambda config: snapshot_result(Status.UNKNOWN))
    monkeypatch.setattr(web, "collect_system", lambda: snapshot_result())
    transport = httpx.ASGITransport(app=web.create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/status")
    assert response.json()["status"] == "ERROR"
    assert "203.0.113" not in response.text
    assert "peer-id" not in response.text


@pytest.mark.anyio
async def test_missing_values_render_as_na(monkeypatch):
    missing = snapshot_result(data={"cpu": {"usage_percent": None}, "disk": {"free": None}})
    monkeypatch.setattr(web, "collect_rpc", lambda config: missing)
    monkeypatch.setattr(web, "collect_network", lambda config: missing)
    monkeypatch.setattr(web, "collect_service", lambda config: missing)
    monkeypatch.setattr(web, "collect_system", lambda: missing)
    monkeypatch.setattr(web, "collect_wallet", lambda config: missing)
    monkeypatch.setattr(web, "collect_staking", lambda config, loaded: missing)
    transport = httpx.ASGITransport(app=web.create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert "N/A" in response.text
    assert "Updated" in response.text


def test_template_has_safe_nested_rendering_and_units():
    template = (web.BASE_DIR / "templates" / "dashboard.html").read_text()
    assert "[object Object]" not in template
    assert "toFixed" in template
    assert "N/A" in template
    assert "Disk used / total" in template
    assert "History" in template
    assert "not guaranteed" in template
