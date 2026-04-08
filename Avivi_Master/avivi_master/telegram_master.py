from __future__ import annotations

import json
import logging
import threading

import httpx
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from avivi_master.config import settings
from avivi_shared.models import RemoteCommandType

log = logging.getLogger(__name__)


def _base_url() -> str:
    return f"http://127.0.0.1:{settings.port}"


def _allowed(chat_id: int) -> bool:
    allowed = settings.allowed_chat_ids
    return len(allowed) == 0 or chat_id in allowed


def _format_fleet_lines(data: object) -> str:
    if not isinstance(data, list):
        return str(data)[:3500]
    lines: list[str] = []
    for c in data[:40]:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id", "?"))[:10]
        host = str(c.get("hostname", ""))[:28]
        lic = str(c.get("license_status", ""))[:12]
        hb = c.get("last_heartbeat") or "never"
        if isinstance(hb, str) and len(hb) > 19:
            hb = hb[5:19]
        lock = "LOCK" if c.get("locked") else "ok"
        pend = c.get("pending_commands", 0)
        own = "TG" if c.get("has_owner_telegram") else "—"
        dom = str(c.get("agent_domain", "") or "")[:24] or "—"
        lines.append(f"{lock} {cid}… {host} | {dom} | {lic} | HB:{hb} | cmd:{pend} | {own}")
    return "\n".join(lines) if lines else "(no clients)"


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not _allowed(update.effective_chat.id):
        return
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            f"{_base_url()}/v1/admin/clients/json",
            headers={"X-API-Key": settings.admin_api_key},
        )
    if r.status_code != 200:
        text = f"Error {r.status_code}: {r.text[:500]}"
    else:
        try:
            text = "Fleet:\n" + _format_fleet_lines(r.json())
        except json.JSONDecodeError:
            text = r.text[:4000]
    if update.message:
        await update.message.reply_text(text[:4000])


async def _enqueue_command(client_id: str, command_type: str) -> tuple[int, str]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{_base_url()}/v1/commands/enqueue",
            headers={"X-API-Key": settings.admin_api_key},
            json={"client_id": client_id, "command_type": command_type, "payload": {}},
        )
        return r.status_code, r.text


async def cmd_restart_client(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not _allowed(update.effective_chat.id):
        return
    args = context.args or []
    if len(args) < 1:
        if update.message:
            await update.message.reply_text("Usage: /restart_client <client_id>")
        return
    code, body = await _enqueue_command(args[0], RemoteCommandType.restart_gateway.value)
    if update.message:
        await update.message.reply_text("ok" if code == 200 else body[:500])


async def cmd_lock_system(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not _allowed(update.effective_chat.id):
        return
    args = context.args or []
    if len(args) < 1:
        if update.message:
            await update.message.reply_text("Usage: /lock_system <client_id>")
        return
    code, body = await _enqueue_command(args[0], RemoteCommandType.lock_system.value)
    if update.message:
        await update.message.reply_text("ok" if code == 200 else body[:500])


async def cmd_lock_client(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not _allowed(update.effective_chat.id):
        return
    args = context.args or []
    if len(args) < 1:
        if update.message:
            await update.message.reply_text("Usage: /lock_client <client_id>")
        return
    cid = args[0]
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{_base_url()}/v1/admin/clients/{cid}/lock",
            headers={"X-API-Key": settings.admin_api_key},
            json={"locked": True},
        )
    if update.message:
        await update.message.reply_text("ok" if r.status_code == 200 else r.text)


async def cmd_unlock_client(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not _allowed(update.effective_chat.id):
        return
    args = context.args or []
    if len(args) < 1:
        if update.message:
            await update.message.reply_text("Usage: /unlock_client <client_id>")
        return
    cid = args[0]
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{_base_url()}/v1/admin/clients/{cid}/lock",
            headers={"X-API-Key": settings.admin_api_key},
            json={"locked": False},
        )
    if update.message:
        await update.message.reply_text("ok" if r.status_code == 200 else r.text)


async def cmd_deploy_mission(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not _allowed(update.effective_chat.id):
        return
    if update.message:
        await update.message.reply_text(
            "Deploy a mission:\n"
            "• POST /v1/missions/push with header X-API-Key (JSON: client_id, mission_id, "
            "version, encrypted_blob_b64, signature_hex optional)\n"
            "• Or enqueue client poll: /enqueue_push_mission <client_id>\n"
            "• Set agent domain: /set_agent_domain <client_id> <text>\n"
            "• Fleet UI: " + _base_url() + "/admin/ui"
        )


async def cmd_set_agent_domain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not _allowed(update.effective_chat.id):
        return
    args = context.args or []
    if len(args) < 2:
        if update.message:
            await update.message.reply_text("Usage: /set_agent_domain <client_id> <domain…>\nExample: /set_agent_domain abc-uuid שירות לקוחות")
        return
    cid = args[0]
    domain = " ".join(args[1:]).strip()[:256]
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.patch(
            f"{_base_url()}/v1/admin/clients/{cid}/agent_domain",
            headers={"X-API-Key": settings.admin_api_key},
            json={"agent_domain": domain},
        )
    if update.message:
        await update.message.reply_text("ok" if r.status_code == 200 else r.text[:500])


async def cmd_enqueue_push_mission(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not _allowed(update.effective_chat.id):
        return
    args = context.args or []
    if len(args) < 1:
        if update.message:
            await update.message.reply_text("Usage: /enqueue_push_mission <client_id>")
        return
    code, body = await _enqueue_command(args[0], RemoteCommandType.push_mission.value)
    if update.message:
        await update.message.reply_text("ok" if code == 200 else body[:500])


def start_master_bot_thread() -> None:
    token = settings.master_telegram_bot_token
    if not token:
        log.info("Master Telegram bot disabled (no AVIVI_MASTER_TELEGRAM_BOT_TOKEN)")
        return

    def run() -> None:
        app = Application.builder().token(token).build()
        app.add_handler(CommandHandler("status", cmd_status))
        app.add_handler(CommandHandler("lock_client", cmd_lock_client))
        app.add_handler(CommandHandler("unlock_client", cmd_unlock_client))
        app.add_handler(CommandHandler("deploy_mission", cmd_deploy_mission))
        app.add_handler(CommandHandler("restart_client", cmd_restart_client))
        app.add_handler(CommandHandler("lock_system", cmd_lock_system))
        app.add_handler(CommandHandler("enqueue_push_mission", cmd_enqueue_push_mission))
        app.add_handler(CommandHandler("set_agent_domain", cmd_set_agent_domain))
        log.info("Master admin bot polling")
        app.run_polling(drop_pending_updates=True)

    threading.Thread(target=run, name="avivi-master-telegram", daemon=True).start()
