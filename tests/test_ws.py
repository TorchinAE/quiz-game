import pytest

pytestmark = pytest.mark.asyncio


async def test_ws_connect(client):
    async with client.stream("GET", "/ws/game"):
        # WebSocket upgrade should work
        pass


async def test_page_routes(client):
    """Test that all page routes return 200."""
    for path in ["/", "/lobby", "/game", "/admin", "/results"]:
        res = await client.get(path)
        assert res.status_code == 200, f"Route {path} failed"


async def test_static_css(client):
    res = await client.get("/static/style.css")
    assert res.status_code == 200
