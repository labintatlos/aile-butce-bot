"""Derlenmiş arayüzün sunulması.

Kökten yapılan statik bağlama, yanlış sırada eklenirse `/api/...` isteklerini
gölgeler. Bu durumda arayüz açılır ama her istek 404 döner ve hata çok
kafa karıştırıcı olur; bu yüzden sıralama testle sabitlenir.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def built_frontend(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html><body>form</body></html>", encoding="utf-8")
    (dist / "app.js").write_text("console.log('ok')", encoding="utf-8")
    return dist


@pytest.fixture()
async def client_with_frontend(async_engine, built_frontend):
    from tests.conftest import _build_client, _test_settings

    settings = _test_settings(frontend_dist=str(built_frontend))
    async with _build_client(async_engine, settings) as client:
        yield client


async def test_frontend_is_served_from_the_root(client_with_frontend):
    response = await client_with_frontend.get("/")
    assert response.status_code == 200
    assert "form" in response.text


async def test_static_files_are_reachable(client_with_frontend):
    response = await client_with_frontend.get("/app.js")
    assert response.status_code == 200


async def test_api_is_not_shadowed_by_the_static_mount(client_with_frontend):
    """API hâlâ kendi yanıtını vermelidir, index.html değil."""
    response = await client_with_frontend.get("/api/bootstrap")
    assert response.status_code == 401
    assert "form" not in response.text


async def test_health_is_not_shadowed(client_with_frontend):
    response = await client_with_frontend.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_missing_build_leaves_the_api_working(client):
    """Arayüz derlenmemişse bot ve API çalışmaya devam eder."""
    assert (await client.get("/health")).status_code == 200
