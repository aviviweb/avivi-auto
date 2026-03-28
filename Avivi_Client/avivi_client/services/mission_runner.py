from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any, Callable

from avivi_client.config import ClientSettings
from avivi_client.services import ai_router
from avivi_shared.crypto import decrypt_json, fernet_from_key
from avivi_shared.models import MissionV1

_TABLE_REF = re.compile(r"\b(?:from|join)\s+[`\"]?([\w.]+)[`\"]?", re.IGNORECASE)


def tables_referenced(sql: str) -> set[str]:
    names: set[str] = set()
    for m in _TABLE_REF.finditer(sql):
        part = m.group(1).split(".")[-1]
        names.add(part.lower())
    return names


def assert_mission_sql_allowed(mission: MissionV1, sql: str) -> tuple[bool, str]:
    s = sql.strip()
    low = s.lower().rstrip(";")
    if mission.db_scope.read_only:
        if not low.startswith("select"):
            return False, "Mission DB scope is read-only; only SELECT is allowed"
        if ";" in s:
            return False, "Multiple statements are not allowed"
    allowed = mission.db_scope.allowed_tables
    if allowed:
        refs = tables_referenced(sql)
        allow_l = {a.lower() for a in allowed}
        bad = [t for t in refs if t not in allow_l]
        if bad:
            return False, f"Table(s) outside mission scope: {bad}. Allowed: {sorted(allow_l)}"
    return True, ""


def _matches_sensitive_pattern(mission: MissionV1, text: str) -> bool:
    low = text.lower()
    for p in mission.sensitive_actions.patterns:
        if p and p.lower() in low:
            return True
    return False


class MissionRunner:
    """Loads missions from disk; coordinates HITL before outbound WhatsApp."""

    def __init__(
        self,
        missions_dir: Path,
        fernet_key_b64: str,
        hitl_request: Callable[[str, str], str] | None = None,
        on_send_whatsapp: Callable[[str, str], None] | None = None,
    ) -> None:
        self.missions_dir = missions_dir
        self.fernet_key_b64 = fernet_key_b64
        self.hitl_request = hitl_request
        self.on_send_whatsapp = on_send_whatsapp
        self._pending: dict[str, tuple[str, str]] = {}

    def load_missions(self) -> list[MissionV1]:
        out: list[MissionV1] = []
        if not self.missions_dir.exists():
            return out
        f = fernet_from_key(base64.b64decode(self.fernet_key_b64.encode("ascii")))
        for p in self.missions_dir.glob("*.enc"):
            try:
                raw = p.read_bytes()
                data = decrypt_json(raw, f)
                out.append(MissionV1.model_validate(data))
            except Exception:
                continue
        return out

    def primary_mission(self) -> MissionV1 | None:
        ms = self.load_missions()
        return ms[0] if ms else None

    def compose_system_prompt(
        self,
        mission: MissionV1,
        db_semantic_path: Path | None = None,
    ) -> str:
        parts = [mission.persona.system_prompt]
        parts.append(f"\n[Mission: {mission.mission_id} v{mission.version} — {mission.persona.name}]")
        if mission.db_scope.allowed_tables:
            parts.append(
                "\nAllowed tables: " + ", ".join(mission.db_scope.allowed_tables)
                + f" (read_only={mission.db_scope.read_only})"
            )
        if db_semantic_path and db_semantic_path.exists():
            try:
                parts.append("\n[Local DB semantic summary]\n" + db_semantic_path.read_text(encoding="utf-8")[:12000])
            except OSError:
                pass
        return "\n".join(parts)

    def chat_with_mission(
        self,
        mission: MissionV1,
        settings: ClientSettings,
        client_id: str,
        model: str,
        messages: list[dict[str, Any]],
        db_semantic_path: Path | None = None,
    ) -> dict[str, Any]:
        """Route LLM via mission.model_profile (local / relay / external)."""
        sys = self.compose_system_prompt(mission, db_semantic_path)
        full_msgs = [{"role": "system", "content": sys}, *messages]
        return ai_router.chat_completion(
            settings,
            client_id,
            self.fernet_key_b64,
            model,
            full_msgs,
            ai_mode_override=mission.model_profile.value,
        )

    def send_whatsapp_with_hitl(self, mission: MissionV1, to_phone: str, body: str) -> None:
        need_hitl = mission.sensitive_actions.require_hitl
        if _matches_sensitive_pattern(mission, body):
            need_hitl = True
        if need_hitl and self.hitl_request:
            aid = self.hitl_request("WhatsApp send", f"To {to_phone}: {body[:200]}")
            if aid:
                self._pending[aid] = (to_phone, body)
            return
        if self.on_send_whatsapp:
            self.on_send_whatsapp(to_phone, body)

    def on_owner_approved(self, action_id: str) -> None:
        item = self._pending.pop(action_id, None)
        if item and self.on_send_whatsapp:
            to_phone, body = item
            self.on_send_whatsapp(to_phone, body)

    def on_owner_rejected(self, action_id: str) -> None:
        self._pending.pop(action_id, None)
