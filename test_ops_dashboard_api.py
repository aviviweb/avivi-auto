from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_multitenant_admin_api_smoke(tmp_path) -> None:
    # Ensure a dedicated DB for this test before importing the app.
    db_path = tmp_path / "avivi_master_test.db"
    os.environ["AVIVI_DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    # Use the built-in env super-admin key path.
    os.environ["AVIVI_ADMIN_API_KEY"] = "test-super-admin-key"

    from avivi_master.init_db import init_models
    from avivi_master.main import app
    from avivi_master.config import settings

    # Other tests may have imported settings before we set env vars.
    settings.admin_api_key = "test-super-admin-key"

    await init_models()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"X-API-Key": "test-super-admin-key"}

        # Create business
        r = await client.post("/v1/admin/businesses", headers=headers, json={"name": "Biz A"})
        assert r.status_code == 200
        biz = r.json()
        assert biz["name"] == "Biz A"
        biz_id = biz["id"]

        # List businesses
        r = await client.get("/v1/admin/businesses", headers=headers)
        assert r.status_code == 200
        assert any(b["id"] == biz_id for b in r.json())

        # Enroll an agent (unassigned business)
        r = await client.post("/v1/enroll", json={"hostname": "pc-1", "app_version": "0.1.0"})
        assert r.status_code == 200
        enrolled = r.json()
        agent_id = enrolled["client_id"]

        # Assign business + domain
        r = await client.patch(
            f"/v1/admin/agents/{agent_id}",
            headers=headers,
            json={"business_id": biz_id, "agent_domain": "שירות לקוחות"},
        )
        assert r.status_code == 200
        out = r.json()
        assert out["business_id"] == biz_id
        assert out["agent_domain"] == "שירות לקוחות"

        # Agents filtered by business
        r = await client.get(f"/v1/admin/agents?business_id={biz_id}", headers=headers)
        assert r.status_code == 200
        agents = r.json()
        assert any(a["id"] == agent_id and a["agent_domain"] == "שירות לקוחות" for a in agents)

