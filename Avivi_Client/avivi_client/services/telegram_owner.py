from __future__ import annotations

import logging
import threading
import uuid
from typing import Callable

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

log = logging.getLogger(__name__)


class OwnerBotController:
    def __init__(
        self,
        token: str,
        allowed_chat_id: str | None,
        on_menu: Callable[[Update, ContextTypes.DEFAULT_TYPE], None] | None = None,
    ) -> None:
        self.token = token
        self.allowed_chat_id = allowed_chat_id
        self.on_menu = on_menu
        self._thread: threading.Thread | None = None
        self._pending: dict[str, dict] = {}
        self.on_approve: Callable[[str], None] | None = None
        self.on_reject: Callable[[str], None] | None = None
        self.on_mission_command: Callable[[str], None] | None = None
        self._mission_menu: list[tuple[str, str]] = []

    def _allowed(self, update: Update) -> bool:
        if not self.allowed_chat_id or not update.effective_chat:
            return True
        return str(update.effective_chat.id) == str(self.allowed_chat_id)

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or not self._allowed(update):
            return
        if self.on_menu:
            self.on_menu(update, context)
            return
        if update.message:
            await update.message.reply_text("Avivi owner bot online. Use /menu.")

    def set_mission_menu_commands(self, items: list[tuple[str, str]]) -> None:
        """(command_id, label) from MissionV1.owner_commands — max ~12 rows of 1 button."""
        self._mission_menu = items[:24]

    async def cmd_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.effective_chat or not self._allowed(update):
            return
        rows: list[list[InlineKeyboardButton]] = [
            [
                InlineKeyboardButton("ROI snapshot", callback_data="roi"),
                InlineKeyboardButton("Pending", callback_data="pending"),
            ]
        ]
        for cid, label in self._mission_menu:
            rows.append(
                [InlineKeyboardButton(label[:60], callback_data=f"mcmd:{cid}")],
            )
        kb = InlineKeyboardMarkup(rows)
        if update.message:
            await update.message.reply_text("Owner menu (missions + shortcuts)", reply_markup=kb)

    async def on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        if not q:
            return
        await q.answer()
        data = q.data or ""
        if data.startswith("approve:"):
            aid = data.split(":", 1)[1]
            if self.on_approve:
                self.on_approve(aid)
            await q.edit_message_text(text="Approved.")
        elif data.startswith("reject:"):
            aid = data.split(":", 1)[1]
            if self.on_reject:
                self.on_reject(aid)
            await q.edit_message_text(text="Rejected.")
        elif data == "roi" and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text="ROI: see nightly Master summary when configured."
            )
        elif data == "pending" and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Pending actions: {len(self._pending)}",
            )
        elif data.startswith("mcmd:"):
            cmd_id = data.split(":", 1)[1]
            if self.on_mission_command:
                self.on_mission_command(cmd_id)
            if q.message:
                await q.edit_message_text(text=f"Command `{cmd_id}` received on client.")

    def request_approval(self, title: str, detail: str) -> str:
        if not self.token or not self.allowed_chat_id:
            return ""
        aid = str(uuid.uuid4())[:8]
        self._pending[aid] = {"title": title, "detail": detail}
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        payload = {
            "chat_id": int(self.allowed_chat_id),
            "text": f"{title}\n{detail}",
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "Approve", "callback_data": f"approve:{aid}"},
                        {"text": "Reject", "callback_data": f"reject:{aid}"},
                    ]
                ]
            },
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                client.post(url, json=payload)
        except Exception as e:
            log.warning("send approval failed: %s", e)
        return aid

    def start_background(self) -> None:
        if not self.token:
            return

        def run() -> None:
            app = Application.builder().token(self.token).build()
            app.add_handler(CommandHandler("start", self.cmd_start))
            app.add_handler(CommandHandler("menu", self.cmd_menu))
            app.add_handler(CallbackQueryHandler(self.on_callback))
            log.info("Owner bot polling")
            app.run_polling(drop_pending_updates=True)

        self._thread = threading.Thread(target=run, name="avivi-owner-tg", daemon=True)
        self._thread.start()
