from __future__ import annotations

import html
import json
import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from avivi_master.db import get_session
from avivi_master.deps import AdminContext, require_admin
from avivi_master.services import fleet

router = APIRouter(tags=["admin"])


def _require_super(ctx: AdminContext) -> None:
    if ctx.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super-admin only")


def _effective_business_id(ctx: AdminContext, requested: str | None) -> str | None:
    if ctx.role == "business_admin":
        return ctx.business_id
    return requested


def _sha256_hex(s: str) -> str:
    import hashlib

    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@router.get("/v1/admin/clients/json", dependencies=[Depends(require_admin)])
async def clients_json(
    ctx: AdminContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    business_id: str | None = None,
) -> list[dict]:
    bid = _effective_business_id(ctx, business_id)
    clients = await fleet.list_clients(session, business_id=bid)
    out: list[dict] = []
    for c in clients:
        pending = await fleet.count_pending_commands(session, c.id)
        out.append(
            {
                "id": c.id,
                "business_id": c.business_id,
                "hostname": c.hostname,
                "app_version": c.app_version,
                "last_heartbeat": c.last_heartbeat.isoformat() + "Z" if c.last_heartbeat else None,
                "license_status": c.license_status,
                "locked": c.locked,
                "pending_commands": pending,
                "has_owner_telegram": bool(c.owner_telegram_chat_id),
                "agent_domain": (c.agent_domain or "").strip(),
            }
        )
    return out


@router.get("/v1/admin/businesses", dependencies=[Depends(require_admin)])
async def list_businesses(
    ctx: AdminContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    _require_super(ctx)
    rows = await fleet.list_businesses(session)
    return [
        {"id": b.id, "name": b.name, "active": b.active, "created_at": b.created_at.isoformat() + "Z"}
        for b in rows
    ]


@router.post("/v1/admin/businesses", dependencies=[Depends(require_admin)])
async def create_business(
    body: BusinessCreateBody,
    ctx: AdminContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _require_super(ctx)
    b = await fleet.create_business(session, body.name)
    await fleet.append_audit(session, "admin", "create_business", b.name)
    return {"id": b.id, "name": b.name, "active": b.active}


@router.get("/v1/admin/agents", dependencies=[Depends(require_admin)])
async def list_agents(
    ctx: AdminContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    business_id: str | None = None,
) -> list[dict]:
    bid = _effective_business_id(ctx, business_id)
    clients = await fleet.list_clients(session, business_id=bid)
    out: list[dict] = []
    for c in clients:
        pending = await fleet.count_pending_commands(session, c.id)
        out.append(
            {
                "id": c.id,
                "business_id": c.business_id,
                "hostname": c.hostname,
                "agent_domain": (c.agent_domain or "").strip(),
                "app_version": c.app_version,
                "last_heartbeat": c.last_heartbeat.isoformat() + "Z" if c.last_heartbeat else None,
                "license_status": c.license_status,
                "locked": c.locked,
                "pending_commands": pending,
                "has_owner_telegram": bool(c.owner_telegram_chat_id),
            }
        )
    return out


@router.patch("/v1/admin/agents/{client_id}", dependencies=[Depends(require_admin)])
async def patch_agent(
    client_id: str,
    body: AgentPatchBody,
    ctx: AdminContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    c = await fleet.get_client(session, client_id)
    if not c:
        raise HTTPException(status_code=404, detail="Unknown client")
    if ctx.role == "business_admin" and c.business_id != ctx.business_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    if body.business_id is not None:
        _require_super(ctx)
        await fleet.set_client_business(session, client_id, (body.business_id or None))

    if body.agent_domain is not None:
        await fleet.set_agent_domain(session, client_id, body.agent_domain)

    if body.locked is not None:
        await fleet.set_client_locked(session, client_id, bool(body.locked))

    await fleet.append_audit(session, "admin", "patch_agent", f"{client_id} {body.model_dump()}")
    c2 = await fleet.get_client(session, client_id)
    return {
        "ok": True,
        "id": client_id,
        "business_id": c2.business_id if c2 else None,
        "agent_domain": (c2.agent_domain or "").strip() if c2 else "",
        "locked": bool(c2.locked) if c2 else False,
    }


@router.get("/v1/admin/bots", dependencies=[Depends(require_admin)])
async def list_bots(
    ctx: AdminContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    business_id: str | None = None,
) -> list[dict]:
    bid = _effective_business_id(ctx, business_id)
    rows = await fleet.list_bots(session, business_id=bid)
    return [
        {
            "id": b.id,
            "business_id": b.business_id,
            "bot_type": b.bot_type,
            "display_name": b.display_name,
            "enabled": b.enabled,
            "token_ref": b.token_ref,
            "created_at": b.created_at.isoformat() + "Z",
        }
        for b in rows
    ]


@router.post("/v1/admin/bots", dependencies=[Depends(require_admin)])
async def create_bot(
    body: BotCreateBody,
    ctx: AdminContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    bid = _effective_business_id(ctx, body.business_id)
    if not bid:
        raise HTTPException(status_code=400, detail="business_id required")
    if ctx.role == "business_admin" and bid != ctx.business_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    b = await fleet.get_business(session, bid)
    if not b:
        raise HTTPException(status_code=404, detail="Unknown business")
    row = await fleet.create_bot(
        session,
        business_id=bid,
        bot_type=body.bot_type,
        display_name=body.display_name,
        token_ref=body.token_ref,
        enabled=body.enabled,
        config_json=json.dumps(body.config or {}, separators=(",", ":")),
    )
    await fleet.append_audit(session, "admin", "create_bot", f"{bid} {row.bot_type}")
    return {"id": row.id, "business_id": row.business_id, "bot_type": row.bot_type, "enabled": row.enabled}


@router.patch("/v1/admin/bots/{bot_id}", dependencies=[Depends(require_admin)])
async def patch_bot(
    bot_id: str,
    body: BotPatchBody,
    ctx: AdminContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    from sqlalchemy import update as sql_update

    rows = await fleet.list_bots(session)
    row = next((x for x in rows if x.id == bot_id), None)
    if not row:
        raise HTTPException(status_code=404, detail="Unknown bot")
    if ctx.role == "business_admin" and row.business_id != ctx.business_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    vals: dict = {}
    if body.enabled is not None:
        vals["enabled"] = bool(body.enabled)
    if body.display_name is not None:
        vals["display_name"] = (body.display_name or "").strip()[:256]
    if body.token_ref is not None:
        vals["token_ref"] = (body.token_ref or "").strip()[:256]
    if vals:
        from avivi_master.models_db import BotRow

        await session.execute(sql_update(BotRow).where(BotRow.id == bot_id).values(**vals))
        await session.commit()
    await fleet.append_audit(session, "admin", "patch_bot", f"{bot_id} {body.model_dump()}")
    return {"ok": True}


@router.get("/v1/admin/api_keys", dependencies=[Depends(require_admin)])
async def list_api_keys(
    ctx: AdminContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    business_id: str | None = None,
) -> list[dict]:
    _require_super(ctx)
    rows = await fleet.list_api_keys(session, business_id=business_id)
    return [
        {
            "id": r.id,
            "label": r.label,
            "role": r.role,
            "business_id": r.business_id,
            "enabled": r.enabled,
            "created_at": r.created_at.isoformat() + "Z",
            "last_used_at": r.last_used_at.isoformat() + "Z" if r.last_used_at else None,
            "key_hint": (r.key_hash_hex or "")[:8],
        }
        for r in rows
    ]


@router.post("/v1/admin/api_keys", dependencies=[Depends(require_admin)])
async def create_api_key(
    body: ApiKeyCreateBody,
    ctx: AdminContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    _require_super(ctx)
    if body.role not in ("super_admin", "business_admin"):
        raise HTTPException(status_code=400, detail="Invalid role")
    if body.role == "business_admin" and not body.business_id:
        raise HTTPException(status_code=400, detail="business_id required for business_admin")
    raw = secrets.token_urlsafe(24)
    from avivi_master.models_db import ApiKeyRow

    row = ApiKeyRow(
        key_hash_hex=_sha256_hex(raw),
        label=(body.label or "").strip()[:256],
        role=body.role,
        business_id=body.business_id,
        enabled=True,
        created_at=datetime.utcnow(),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    await fleet.append_audit(session, "admin", "create_api_key", f"{row.role} {row.business_id or ''} {row.label}")
    return {"id": row.id, "role": row.role, "business_id": row.business_id, "label": row.label, "api_key": raw}


@router.get("/v1/admin/audit", dependencies=[Depends(require_admin)])
async def list_audit(
    ctx: AdminContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    business_id: str | None = None,
    limit: int = 200,
) -> list[dict]:
    from avivi_master.models_db import AuditLogRow

    bid = _effective_business_id(ctx, business_id)
    lim = max(1, min(int(limit or 200), 500))
    q = select(AuditLogRow).order_by(AuditLogRow.created_at.desc()).limit(lim)
    if bid is not None:
        q = q.where(AuditLogRow.business_id == bid)
    r = await session.execute(q)
    rows = list(r.scalars().all())
    return [
        {
            "id": a.id,
            "business_id": a.business_id,
            "actor": a.actor,
            "action": a.action,
            "detail": a.detail,
            "created_at": a.created_at.isoformat() + "Z",
        }
        for a in rows
    ]


@router.get("/v1/admin/roi/summary", dependencies=[Depends(require_admin)])
async def roi_summary(
    ctx: AdminContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
    business_id: str | None = None,
    days: int = 1,
) -> dict:
    from datetime import datetime, timedelta

    from avivi_master.models_db import ClientRecord, ROIEventRow

    bid = _effective_business_id(ctx, business_id)
    d = max(1, min(int(days or 1), 31))
    start = datetime.utcnow() - timedelta(days=d)
    q = (
        select(ROIEventRow.client_id, func.sum(ROIEventRow.minutes_saved))
        .where(ROIEventRow.created_at >= start)
        .group_by(ROIEventRow.client_id)
    )
    if bid is not None:
        q = q.join(ClientRecord, ClientRecord.id == ROIEventRow.client_id).where(
            ClientRecord.business_id == bid
        )
    r = await session.execute(q)
    rows = [(str(x[0]), float(x[1] or 0)) for x in r.all()]
    total_minutes = sum(m for _, m in rows)
    return {
        "business_id": bid,
        "days": d,
        "total_minutes_saved": total_minutes,
        "by_client": [{"client_id": cid, "minutes_saved": mins} for cid, mins in rows],
    }

async def _fleet_table_html(session: AsyncSession) -> str:
    clients = await fleet.list_clients(session)
    parts: list[str] = []
    for c in clients:
        pending = await fleet.count_pending_commands(session, c.id)
        hb = c.last_heartbeat.isoformat() if c.last_heartbeat else "—"
        cid_disp = c.id[:14] + "…" if len(c.id) > 14 else c.id
        dom = html.escape((c.agent_domain or "").strip() or "—")
        host_e = html.escape(c.hostname or "")
        ver_e = html.escape(c.app_version or "")
        parts.append(
            f"<tr><td><code>{cid_disp}</code></td><td>{host_e}</td>"
            f"<td>{dom}</td><td>{ver_e}</td>"
            f"<td>{html.escape(hb)}</td><td>{html.escape(c.license_status or '')}</td><td>{'yes' if c.locked else 'no'}</td>"
            f"<td>{pending}</td><td>{'yes' if c.owner_telegram_chat_id else 'no'}</td></tr>"
        )
    return "".join(parts)


@router.get("/admin", response_class=HTMLResponse)
@router.get("/admin/ui", response_class=HTMLResponse)
async def admin_dashboard(session: AsyncSession = Depends(get_session)) -> str:
    """Ops dashboard UI; protect in production via reverse proxy or auth."""
    _ = session
    return """<!doctype html>
<html lang="he" dir="rtl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Avivi Master — Ops</title>
  <style>
    :root{--bg:#0c1222;--card:#151d32;--text:#e8edf5;--muted:#94a3b8;--accent:#34d399;--warn:#fbbf24;--bad:#f87171;}
    *{box-sizing:border-box}
    body{margin:0;font-family:"Segoe UI","Rubik","Heebo",system-ui,sans-serif;background:var(--bg);color:var(--text)}
    .wrap{max-width:1200px;margin:0 auto;padding:1.25rem 1rem 3rem}
    h1{margin:0 0 .25rem;font-size:1.45rem}
    .sub{color:var(--muted);font-size:.95rem}
    .card{background:rgba(21,29,50,.92);border:1px solid rgba(148,163,184,.12);border-radius:14px;padding:1rem;margin-top:1rem}
    .row{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap}
    input,select,button{font:inherit}
    input,select{background:#0f172a;border:1px solid rgba(148,163,184,.22);color:var(--text);padding:.5rem .6rem;border-radius:10px;min-width:240px}
    button{background:#1e293b;border:1px solid rgba(148,163,184,.22);color:var(--text);padding:.5rem .8rem;border-radius:10px;cursor:pointer}
    button.primary{border-color:rgba(52,211,153,.4);background:rgba(52,211,153,.12);color:var(--accent)}
    button.danger{border-color:rgba(248,113,113,.4);background:rgba(248,113,113,.12);color:var(--bad)}
    .tabs{display:flex;gap:.5rem;flex-wrap:wrap;margin:.9rem 0 .4rem}
    .tab{padding:.45rem .75rem;border-radius:999px;border:1px solid rgba(148,163,184,.22);color:var(--muted);background:transparent}
    .tab.active{color:var(--accent);border-color:rgba(52,211,153,.35);background:rgba(52,211,153,.10)}
    table{width:100%;border-collapse:collapse}
    th,td{border:1px solid rgba(148,163,184,.16);padding:.55rem .5rem;text-align:right;vertical-align:top}
    th{background:rgba(30,41,59,.75);color:var(--muted);font-weight:600}
    .pill{display:inline-block;padding:.15rem .55rem;border-radius:999px;font-size:.85rem;border:1px solid rgba(148,163,184,.2);color:var(--muted)}
    .pill.ok{border-color:rgba(52,211,153,.3);color:var(--accent);background:rgba(52,211,153,.08)}
    .pill.warn{border-color:rgba(251,191,36,.35);color:var(--warn);background:rgba(251,191,36,.08)}
    .pill.bad{border-color:rgba(248,113,113,.35);color:var(--bad);background:rgba(248,113,113,.08)}
    .muted{color:var(--muted)}
    .mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
    .hidden{display:none}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Avivi Master — דשבורד אופרציה</h1>
    <div class="sub">Multi-tenant · סוכנים · בוטים · משימות · ROI · לוגים</div>

    <div class="card">
      <div class="row">
        <label class="muted">מפתח אדמין (X-API-Key)</label>
        <input id="apiKey" placeholder="הדבק מפתח כאן" />
        <button class="primary" id="btnSaveKey">שמור</button>
        <button class="danger" id="btnClearKey">נקה</button>
        <span id="keyStatus" class="muted">לא הוגדר מפתח.</span>
      </div>
      <div class="row" style="margin-top:.8rem">
        <span class="pill" id="pillServer">Server: ?</span>
        <span class="pill" id="pillAgents">Agents: ?</span>
        <span class="pill" id="pillPending">Pending: ?</span>
        <label class="muted" style="margin-right:auto">סינון לפי עסק</label>
        <select id="businessSelect"><option value="">(הכל)</option></select>
        <button class="primary" id="btnRefresh">רענון</button>
      </div>
      <div class="tabs">
        <button class="tab active" data-tab="agents">סוכנים</button>
        <button class="tab" data-tab="businesses">עסקים</button>
        <button class="tab" data-tab="bots">בוטים</button>
        <button class="tab" data-tab="roi">ROI</button>
        <button class="tab" data-tab="logs">לוגים</button>
      </div>
    </div>

    <div id="tab_agents" class="card"></div>
    <div id="tab_businesses" class="card hidden"></div>
    <div id="tab_bots" class="card hidden"></div>
    <div id="tab_roi" class="card hidden"></div>
    <div id="tab_logs" class="card hidden"></div>
  </div>

<script>
  const $ = (id)=>document.getElementById(id);
  const keyStatus = $("keyStatus");
  const businessSelect = $("businessSelect");

  function getKey(){ return localStorage.getItem("avivi_admin_key") || ""; }
  function setKey(v){ localStorage.setItem("avivi_admin_key", v); }
  function clearKey(){ localStorage.removeItem("avivi_admin_key"); }
  function esc(s){ return String(s||"").replace(/[&<>\"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\\\"":"&quot;","'":"&#39;"}[c])); }

  async function api(path, opts={}){
    const key = getKey();
    const headers = Object.assign({"Content-Type":"application/json"}, opts.headers||{});
    if(key) headers["X-API-Key"] = key;
    const res = await fetch(path, Object.assign({}, opts, {headers}));
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch(e) { data = {raw:text}; }
    if(!res.ok){
      const msg = (data && (data.detail||data.raw)) ? (data.detail||data.raw) : (text||("HTTP "+res.status));
      throw new Error(msg);
    }
    return data;
  }

  function setTab(name){
    document.querySelectorAll(".tab").forEach(b=>b.classList.toggle("active", b.dataset.tab===name));
    ["agents","businesses","bots","roi","logs"].forEach(t=>$("tab_"+t).classList.toggle("hidden", t!==name));
  }

  function fmtHb(iso){
    if(!iso) return "—";
    const d = new Date(iso);
    if(isNaN(d.getTime())) return iso;
    return d.toLocaleString("he-IL");
  }
  function onlinePill(lastIso){
    if(!lastIso) return "<span class='pill bad'>לא פעיל</span>";
    const t = new Date(lastIso).getTime();
    const ago = (Date.now()-t)/1000;
    if(ago < 90) return "<span class='pill ok'>פעיל</span>";
    if(ago < 300) return "<span class='pill warn'>איטי</span>";
    return "<span class='pill bad'>לא פעיל</span>";
  }

  async function loadBusinesses(){
    businessSelect.innerHTML = "<option value=''> (הכל) </option>";
    try{
      const rows = await api("/v1/admin/businesses");
      for(const b of rows){
        const opt = document.createElement("option");
        opt.value = b.id;
        opt.textContent = b.name || b.id;
        businessSelect.appendChild(opt);
      }
      businessSelect.disabled = false;
    }catch(e){
      businessSelect.disabled = true;
    }
  }

  async function loadAgents(){
    const root = $("tab_agents");
    root.innerHTML = "<div class='muted'>טוען…</div>";
    const bid = businessSelect.value || "";
    const agents = await api("/v1/admin/agents" + (bid?("?business_id="+encodeURIComponent(bid)):""));
    let active=0, pending=0;
    for(const a of agents){
      if(a.last_heartbeat){
        const ago=(Date.now()-new Date(a.last_heartbeat).getTime())/1000;
        if(ago<90) active++;
      }
      pending += Number(a.pending_commands||0);
    }
    $("pillAgents").textContent = `Agents: ${agents.length} (פעילים: ${active})`;
    $("pillPending").textContent = `Pending: ${pending}`;

    const bizOptions = businessSelect.disabled ? "" : Array.from(businessSelect.options).filter(o=>o.value).map(o=>({id:o.value, name:o.textContent}));
    const rows = agents.map(a=>{
      const bizCell = businessSelect.disabled
        ? `<span class='muted mono'>${esc(a.business_id||"—")}</span>`
        : `<select data-biz='${esc(a.id)}'><option value=''>— לא משויך —</option>` + bizOptions.map(o=>`<option value='${esc(o.id)}' ${o.id===a.business_id?"selected":""}>${esc(o.name)}</option>`).join("") + `</select>`;
      const lockBtn = a.locked
        ? `<button class='danger' data-unlock='${esc(a.id)}'>שחרור</button>`
        : `<button data-lock='${esc(a.id)}'>נעילה</button>`;
      return `<tr>
        <td class='mono'>${esc(a.id.slice(0,12))}…</td>
        <td>${onlinePill(a.last_heartbeat)}<div class='muted'>${esc(a.hostname||"")}</div></td>
        <td><input data-domain='${esc(a.id)}' value='${esc(a.agent_domain||"")}' placeholder='למשל: שירות לקוחות' /></td>
        <td>${bizCell}</td>
        <td class='muted'>${esc(a.app_version||"")}</td>
        <td class='muted'>${fmtHb(a.last_heartbeat)}</td>
        <td>${a.pending_commands||0}</td>
        <td>${lockBtn}</td>
        <td><button class='primary' data-save='${esc(a.id)}'>שמור</button></td>
      </tr>`;
    }).join("");

    root.innerHTML = `
      <div class='row' style='justify-content:space-between'>
        <div><strong>סוכנים</strong> <span class='muted'>— ערוך תחום, שיוך לעסק, ונעילה</span></div>
        <button class='primary' id='btnAgentsRefresh'>רענון סוכנים</button>
      </div>
      <div style='overflow:auto;margin-top:.8rem'>
        <table>
          <thead><tr><th>ID</th><th>סטטוס</th><th>תחום</th><th>עסק</th><th>גרסה</th><th>Heartbeat</th><th>Pending</th><th>נעילה</th><th>עדכון</th></tr></thead>
          <tbody>${rows || "<tr><td colspan='9' class='muted'>אין סוכנים עדיין. הפעל לקוח ועשה Enroll.</td></tr>"}</tbody>
        </table>
      </div>
    `;

    $("btnAgentsRefresh").addEventListener("click", loadAgents);

    root.querySelectorAll("button[data-save]").forEach(btn=>btn.addEventListener("click", async ()=>{
      const id = btn.getAttribute("data-save");
      const dom = root.querySelector(`input[data-domain='${CSS.escape(id)}']`).value || "";
      const bizSel = root.querySelector(`select[data-biz='${CSS.escape(id)}']`);
      const payload = {agent_domain: dom};
      if(bizSel && !businessSelect.disabled){ payload.business_id = bizSel.value || ""; }
      try{ await api(`/v1/admin/agents/${encodeURIComponent(id)}`, {method:"PATCH", body: JSON.stringify(payload)}); await loadAgents(); }
      catch(e){ alert("שגיאה: " + e.message); }
    }));
    root.querySelectorAll("button[data-lock]").forEach(btn=>btn.addEventListener("click", async ()=>{
      const id = btn.getAttribute("data-lock");
      try{ await api(`/v1/admin/clients/${encodeURIComponent(id)}/lock`, {method:"POST", body: JSON.stringify({locked:true})}); await loadAgents(); }
      catch(e){ alert("שגיאה: " + e.message); }
    }));
    root.querySelectorAll("button[data-unlock]").forEach(btn=>btn.addEventListener("click", async ()=>{
      const id = btn.getAttribute("data-unlock");
      try{ await api(`/v1/admin/clients/${encodeURIComponent(id)}/lock`, {method:"POST", body: JSON.stringify({locked:false})}); await loadAgents(); }
      catch(e){ alert("שגיאה: " + e.message); }
    }));
  }

  async function loadBusinessesTab(){
    const root = $("tab_businesses");
    root.innerHTML = "<div class='muted'>טוען…</div>";
    try{
      const rows = await api("/v1/admin/businesses");
      const trs = rows.map(b=>`<tr><td class='mono'>${esc(b.id.slice(0,12))}…</td><td>${esc(b.name)}</td><td>${b.active?"פעיל":"לא פעיל"}</td><td class='muted'>${fmtHb(b.created_at)}</td></tr>`).join("");
      root.innerHTML = `
        <div class='row' style='justify-content:space-between'>
          <div><strong>עסקים</strong> <span class='muted'>— יצירת עסק חדש (Super Admin)</span></div>
          <div class='row'>
            <input id='newBizName' placeholder='שם העסק החדש' />
            <button class='primary' id='btnCreateBiz'>צור עסק</button>
            <button class='primary' id='btnCreateBizAndKey'>צור עסק + מפתח מנהל</button>
          </div>
        </div>
        <div class='muted' style='margin-top:.5rem'>
          טיפ: “צור עסק + מפתח מנהל” ייצור מפתח <span class='mono'>business_admin</span> לעסק החדש ויציג אותו פעם אחת — שמור אותו מיד.
        </div>
        <div style='overflow:auto;margin-top:.8rem'>
          <table><thead><tr><th>ID</th><th>שם</th><th>סטטוס</th><th>נוצר</th></tr></thead><tbody>${trs || "<tr><td colspan='4' class='muted'>אין עסקים.</td></tr>"}</tbody></table>
        </div>
      `;
      $("btnCreateBiz").addEventListener("click", async ()=>{
        const name = $("newBizName").value || "";
        if(!name.trim()) return alert("נא להזין שם עסק");
        try{ await api("/v1/admin/businesses", {method:"POST", body: JSON.stringify({name})}); await loadBusinesses(); await loadBusinessesTab(); }
        catch(e){ alert("שגיאה: " + e.message); }
      });

      $("btnCreateBizAndKey").addEventListener("click", async ()=>{
        const name = $("newBizName").value || "";
        if(!name.trim()) return alert("נא להזין שם עסק");
        try{
          const biz = await api("/v1/admin/businesses", {method:"POST", body: JSON.stringify({name})});
          const label = `business_admin: ${biz.name || biz.id}`;
          const keyOut = await api("/v1/admin/api_keys", {method:"POST", body: JSON.stringify({role:"business_admin", business_id: biz.id, label})});
          await loadBusinesses();
          await loadBusinessesTab();
          alert(
            "נוצר עסק חדש ונוצר מפתח מנהל (מוצג פעם אחת בלבד). שמור עכשיו:\\n\\n" +
            keyOut.api_key +
            \"\\n\\n\" +
            \"Business ID: \" + (biz.id||\"\") + \"\\n\" +
            \"Business name: \" + (biz.name||\"\")
          );
        }
        catch(e){ alert("שגיאה: " + e.message); }
      });
    }catch(e){
      root.innerHTML = "<strong>אין הרשאה לטאב עסקים.</strong><div class='muted'>נדרש Super Admin.</div>";
    }
  }

  async function loadBots(){
    const root = $("tab_bots");
    root.innerHTML = "<div class='muted'>טוען…</div>";
    const bid = businessSelect.value || "";
    const bots = await api("/v1/admin/bots" + (bid?("?business_id="+encodeURIComponent(bid)):""));
    const trs = bots.map(b=>{
      const toggle = b.enabled ? `<button class='danger' data-bot='${esc(b.id)}' data-enable='0'>כבה</button>` : `<button class='primary' data-bot='${esc(b.id)}' data-enable='1'>הפעל</button>`;
      return `<tr><td class='mono'>${esc(b.id.slice(0,12))}…</td><td>${esc(b.display_name||"")}</td><td class='muted'>${esc(b.bot_type||"")}</td><td class='muted mono'>${esc(b.business_id||"")}</td><td class='muted mono'>${esc(b.token_ref||"")}</td><td>${b.enabled?"כן":"לא"}</td><td>${toggle}</td></tr>`;
    }).join("");

    root.innerHTML = `
      <div class='row' style='justify-content:space-between'>
        <div><strong>בוטים</strong> <span class='muted'>— token_ref מצביע לשם משתנה ב-.env</span></div>
        <div class='row'>
          <input id='botType' placeholder='סוג (למשל master_telegram)' />
          <input id='botName' placeholder='שם תצוגה' />
          <input id='botTokenRef' placeholder='token_ref (ENV var name)' />
          <button class='primary' id='btnCreateBot'>צור</button>
        </div>
      </div>
      <div style='overflow:auto;margin-top:.8rem'>
        <table><thead><tr><th>ID</th><th>שם</th><th>סוג</th><th>עסק</th><th>token_ref</th><th>Enabled</th><th>פעולה</th></tr></thead><tbody>${trs || "<tr><td colspan='7' class='muted'>אין בוטים.</td></tr>"}</tbody></table>
      </div>
    `;
    $("btnCreateBot").addEventListener("click", async ()=>{
      const bot_type = $("botType").value || "";
      const display_name = $("botName").value || "";
      const token_ref = $("botTokenRef").value || "";
      const business_id = businessSelect.disabled ? null : (businessSelect.value || null);
      if(!bot_type.trim()) return alert("חובה bot_type");
      try{
        await api("/v1/admin/bots", {method:"POST", body: JSON.stringify({business_id, bot_type, display_name, token_ref, enabled:false, config:{}})});
        await loadBots();
      }catch(e){ alert("שגיאה: " + e.message); }
    });
    root.querySelectorAll("button[data-bot]").forEach(btn=>btn.addEventListener("click", async ()=>{
      const id = btn.getAttribute("data-bot");
      const en = btn.getAttribute("data-enable")==="1";
      try{ await api(`/v1/admin/bots/${encodeURIComponent(id)}`, {method:"PATCH", body: JSON.stringify({enabled: en})}); await loadBots(); }
      catch(e){ alert("שגיאה: " + e.message); }
    }));
  }

  async function loadROI(){
    const root = $("tab_roi");
    root.innerHTML = "<div class='muted'>טוען…</div>";
    const bid = businessSelect.value || "";
    const q = bid ? ("?business_id="+encodeURIComponent(bid)+"&") : "?";
    const d1 = await api("/v1/admin/roi/summary"+q+"days=1");
    const d7 = await api("/v1/admin/roi/summary"+q+"days=7");
    root.innerHTML = `
      <strong>ROI</strong>
      <div class='muted'>סיכום דקות שנחסכו לפי אירועים מהסוכנים.</div>
      <div class='row' style='margin-top:.8rem'>
        <span class='pill ok'>24 שעות: ${Math.round(d1.total_minutes_saved||0)} דקות</span>
        <span class='pill ok'>7 ימים: ${Math.round(d7.total_minutes_saved||0)} דקות</span>
      </div>
    `;
  }

  async function loadLogs(){
    const root = $("tab_logs");
    root.innerHTML = "<div class='muted'>טוען…</div>";
    const bid = businessSelect.value || "";
    const rows = await api("/v1/admin/audit" + (bid?("?business_id="+encodeURIComponent(bid)):""));
    const trs = rows.map(a=>`<tr><td class='mono'>${esc(a.created_at||"")}</td><td class='muted mono'>${esc(a.business_id||"")}</td><td>${esc(a.actor||"")}</td><td>${esc(a.action||"")}</td><td class='muted'>${esc(a.detail||"")}</td></tr>`).join("");
    root.innerHTML = `
      <div class='row' style='justify-content:space-between'>
        <div><strong>Audit log</strong> <span class='muted'>— פעולות אחרונות</span></div>
        <button class='primary' id='btnLogsRefresh'>רענון</button>
      </div>
      <div style='overflow:auto;margin-top:.8rem'>
        <table><thead><tr><th>זמן</th><th>עסק</th><th>Actor</th><th>Action</th><th>Detail</th></tr></thead><tbody>${trs || "<tr><td colspan='5' class='muted'>אין לוגים.</td></tr>"}</tbody></table>
      </div>
    `;
    $("btnLogsRefresh").addEventListener("click", loadLogs);
  }

  async function refreshAll(){
    if(!getKey()){
      keyStatus.textContent = "לא הוגדר מפתח.";
      return;
    }
    try{
      const health = await fetch("/health");
      $("pillServer").textContent = health.ok ? "Server: OK" : "Server: DOWN";
      $("pillServer").className = "pill " + (health.ok ? "ok" : "bad");
      keyStatus.textContent = "מפתח מוגדר. הדשבורד מתעדכן אוטומטית.";
      await loadBusinesses();
      const active = document.querySelector(".tab.active").dataset.tab;
      if(active==="agents") await loadAgents();
      if(active==="businesses") await loadBusinessesTab();
      if(active==="bots") await loadBots();
      if(active==="roi") await loadROI();
      if(active==="logs") await loadLogs();
    }catch(e){
      keyStatus.textContent = "שגיאה: " + e.message;
    }
  }

  document.querySelectorAll(".tab").forEach(b=>b.addEventListener("click", async ()=>{
    setTab(b.dataset.tab);
    await refreshAll();
  }));
  $("btnSaveKey").addEventListener("click", ()=>{ setKey($("apiKey").value.trim()); refreshAll(); });
  $("btnClearKey").addEventListener("click", ()=>{ clearKey(); $("apiKey").value=""; keyStatus.textContent="המפתח נמחק."; });
  $("btnRefresh").addEventListener("click", refreshAll);
  businessSelect.addEventListener("change", refreshAll);

  $("apiKey").value = getKey();
  refreshAll();
  setInterval(()=>{ if(getKey()) refreshAll(); }, 10000);
</script>
</body>
</html>"""


class LockBody(BaseModel):
    locked: bool


class AgentDomainBody(BaseModel):
    agent_domain: str = ""


class BusinessCreateBody(BaseModel):
    name: str


class BotCreateBody(BaseModel):
    business_id: str | None = None
    bot_type: str
    display_name: str = ""
    enabled: bool = False
    token_ref: str = ""
    config: dict = {}


class BotPatchBody(BaseModel):
    enabled: bool | None = None
    display_name: str | None = None
    token_ref: str | None = None


class AgentPatchBody(BaseModel):
    agent_domain: str | None = None
    locked: bool | None = None
    business_id: str | None = None  # super admin only


class ApiKeyCreateBody(BaseModel):
    role: str = "business_admin"  # super_admin|business_admin
    business_id: str | None = None
    label: str = ""


@router.patch("/v1/admin/clients/{client_id}/agent_domain", dependencies=[Depends(require_admin)])
async def patch_agent_domain(
    client_id: str,
    body: AgentDomainBody,
    ctx: AdminContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    c = await fleet.get_client(session, client_id)
    if not c:
        raise HTTPException(status_code=404, detail="Unknown client")
    if ctx.role == "business_admin" and c.business_id != ctx.business_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    ok = await fleet.set_agent_domain(session, client_id, body.agent_domain)
    if not ok:
        raise HTTPException(status_code=404, detail="Unknown client")
    await fleet.append_audit(session, "admin", "agent_domain", f"{client_id}={body.agent_domain!r}")
    return {"ok": True, "agent_domain": (body.agent_domain or "").strip()[:256]}


@router.post("/v1/admin/clients/{client_id}/lock", dependencies=[Depends(require_admin)])
async def lock_client(
    client_id: str,
    body: LockBody,
    ctx: AdminContext = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    c = await fleet.get_client(session, client_id)
    if not c:
        raise HTTPException(status_code=404, detail="Unknown client")
    if ctx.role == "business_admin" and c.business_id != ctx.business_id:
        raise HTTPException(status_code=403, detail="Forbidden")
    await fleet.set_client_locked(session, client_id, body.locked)
    await fleet.append_audit(session, "admin", "lock", f"{client_id}={body.locked}")
    return {"ok": True}
