from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from avivi_master.db import get_session
from avivi_master.deps import require_admin
from avivi_master.services import fleet

router = APIRouter(tags=["admin"])


@router.get("/v1/admin/clients/json", dependencies=[Depends(require_admin)])
async def clients_json(session: AsyncSession = Depends(get_session)) -> list[dict]:
    clients = await fleet.list_clients(session)
    out: list[dict] = []
    for c in clients:
        pending = await fleet.count_pending_commands(session, c.id)
        out.append(
            {
                "id": c.id,
                "hostname": c.hostname,
                "app_version": c.app_version,
                "last_heartbeat": c.last_heartbeat.isoformat() + "Z" if c.last_heartbeat else None,
                "license_status": c.license_status,
                "locked": c.locked,
                "pending_commands": pending,
                "has_owner_telegram": bool(c.owner_telegram_chat_id),
            }
        )
    return out


async def _fleet_table_html(session: AsyncSession) -> str:
    clients = await fleet.list_clients(session)
    parts: list[str] = []
    for c in clients:
        pending = await fleet.count_pending_commands(session, c.id)
        hb = c.last_heartbeat.isoformat() if c.last_heartbeat else "—"
        cid_disp = c.id[:14] + "…" if len(c.id) > 14 else c.id
        parts.append(
            f"<tr><td><code>{cid_disp}</code></td><td>{c.hostname}</td><td>{c.app_version}</td>"
            f"<td>{hb}</td><td>{c.license_status}</td><td>{'yes' if c.locked else 'no'}</td>"
            f"<td>{pending}</td><td>{'yes' if c.owner_telegram_chat_id else 'no'}</td></tr>"
        )
    return "".join(parts)


@router.get("/admin", response_class=HTMLResponse)
@router.get("/admin/ui", response_class=HTMLResponse)
async def admin_dashboard(session: AsyncSession = Depends(get_session)) -> str:
    """Fleet view; protect in production via reverse proxy or session auth."""
    rows = await _fleet_table_html(session)
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Avivi Master — Fleet</title>
<style>
body {{ font-family: system-ui, sans-serif; background:#0f172a; color:#e2e8f0; padding:1.5rem; }}
table {{ border-collapse: collapse; width:100%; max-width:1200px; }}
th, td {{ border:1px solid #334155; padding:8px; text-align:left; }}
th {{ background:#1e293b; color:#94a3b8; }}
h1 {{ color:#34d399; }}
a {{ color:#34d399; }}
</style></head><body>
<h1>Fleet dashboard</h1>
<p>JSON: <code>GET /v1/admin/clients/json</code> with <code>X-API-Key</code>.</p>
<table><tr><th>ID</th><th>Host</th><th>Version</th><th>Last heartbeat</th><th>License</th><th>Locked</th><th>Pending cmds</th><th>Owner TG</th></tr>
{rows}
</table></body></html>"""


class LockBody(BaseModel):
    locked: bool


@router.post("/v1/admin/clients/{client_id}/lock", dependencies=[Depends(require_admin)])
async def lock_client(client_id: str, body: LockBody, session: AsyncSession = Depends(get_session)) -> dict:
    c = await fleet.get_client(session, client_id)
    if not c:
        raise HTTPException(status_code=404, detail="Unknown client")
    await fleet.set_client_locked(session, client_id, body.locked)
    await fleet.append_audit(session, "admin", "lock", f"{client_id}={body.locked}")
    return {"ok": True}
