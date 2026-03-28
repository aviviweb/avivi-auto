from __future__ import annotations

import base64
import json
import os
from pathlib import Path

from PyQt6.QtCore import QByteArray, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from avivi_client.bootstrap.deps import ensure_dependencies
from avivi_client.config import ClientSettings, SettingsStore, first_run_deps_marker_path
from avivi_client.services.command_poll import ack_command, poll_commands
from avivi_client.services.enroll import enroll_sync
from avivi_client.services.heartbeat_worker import HeartbeatWorker
from avivi_client.services.master_events import post_client_event
from avivi_client.services.poll_worker import PollWorker
from avivi_client.services.messaging import WebWhatsAppGateway
from avivi_client.services.mission_runner import MissionRunner
from avivi_client.services.mission_sync import ack_mission, apply_mission_blob, fetch_pending
from avivi_client.services.telegram_owner import OwnerBotController
from avivi_client.services.watchdog import ProcessWatchdog
from avivi_client.storage import ClientCredentials
from avivi_shared.models import RemoteCommandType


THEME_QSS = """
QMainWindow, QWidget { background-color: #0f172a; color: #e2e8f0; }
QGroupBox { border: 1px solid #334155; margin-top: 8px; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; left: 8px; color: #34d399; }
QPushButton { background-color: #1e293b; border: 1px solid #475569; padding: 6px 12px; border-radius: 4px; }
QPushButton:hover { background-color: #334155; }
QLineEdit { background-color: #1e293b; border: 1px solid #475569; padding: 4px; color: #f8fafc; }
QListWidget { background-color: #1e293b; border: 1px solid #334155; }
QTabWidget::pane { border: 1px solid #334155; }
QTabBar::tab { background: #1e293b; color: #94a3b8; padding: 8px 16px; }
QTabBar::tab:selected { background: #0f172a; color: #34d399; border-bottom: 2px solid #34d399; }
QLabel#status_ok { color: #34d399; font-weight: 600; }
QLabel#status_warn { color: #fbbf24; font-weight: 600; }
QLabel#status_bad { color: #f87171; font-weight: 600; }
"""


def _data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("HOME") or "."
    return Path(base) / "Avivi"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Avivi Automation Manager")
        self.resize(960, 640)
        self.setStyleSheet(THEME_QSS)

        self.settings_store = SettingsStore()
        self.settings: ClientSettings = self.settings_store.load()
        self.credentials_store = ClientCredentials()
        self.creds: dict | None = self.credentials_store.load_decrypted()

        self._heartbeat: HeartbeatWorker | None = None
        self._gateway = WebWhatsAppGateway()
        self._owner = OwnerBotController(
            self.settings.owner_telegram_bot_token,
            self.settings.owner_telegram_chat_id or None,
        )
        self._mission_runner: MissionRunner | None = None
        self._watchdog: ProcessWatchdog | None = None
        self._system_locked = False

        self._build_ui()
        self._wire_owner_bot()
        self._restore_mission_runner()
        if self.creds:
            self._start_heartbeat()

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_remote)
        self._poll_timer.start(45_000)

        QTimer.singleShot(500, self._initial_bootstrap)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        title = QLabel("Avivi Client")
        title.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        title.setStyleSheet("color: #34d399;")
        root.addWidget(title)

        tabs = QTabWidget()
        root.addWidget(tabs)

        tabs.addTab(self._tab_dashboard(), "Dashboard")
        tabs.addTab(self._tab_whatsapp(), "WhatsApp")
        tabs.addTab(self._tab_activity(), "Activity")
        tabs.addTab(self._tab_settings(), "Settings")

    def _card(self, title: str) -> tuple[QGroupBox, QVBoxLayout]:
        box = QGroupBox(title)
        lay = QVBoxLayout(box)
        return box, lay

    def _tab_dashboard(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        row = QHBoxLayout()
        self.card_health = QLabel("System: checking…")
        self.card_health.setObjectName("status_warn")
        self.card_db = QLabel("DB: not scanned")
        self.card_db.setObjectName("status_warn")
        self.card_wa = QLabel("WhatsApp: idle")
        self.card_wa.setObjectName("status_warn")
        for c in (self.card_health, self.card_db, self.card_wa):
            c.setMinimumHeight(64)
            row.addWidget(c)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        self.btn_deps = QPushButton("Check / install Node & Git")
        self.btn_deps.clicked.connect(self._on_deps)
        self.btn_enroll = QPushButton("Enroll with Master")
        self.btn_enroll.clicked.connect(self._on_enroll)
        self.btn_scan_db = QPushButton("Scan DB ports")
        self.btn_scan_db.clicked.connect(self._on_scan_db)
        row2.addWidget(self.btn_deps)
        row2.addWidget(self.btn_enroll)
        row2.addWidget(self.btn_scan_db)
        lay.addLayout(row2)

        return w

    def _tab_whatsapp(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.lbl_wa_identity = QLabel("Connected as: —")
        self.lbl_wa_identity.setStyleSheet("color: #34d399; font-size: 14px;")
        lay.addWidget(self.lbl_wa_identity)
        self.lbl_qr = QLabel("QR will appear here after gateway start")
        self.lbl_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_qr.setMinimumHeight(280)
        lay.addWidget(self.lbl_qr)
        row = QHBoxLayout()
        self.btn_wa_start = QPushButton("Start gateway")
        self.btn_wa_start.clicked.connect(self._on_wa_start)
        self.btn_wa_stop = QPushButton("Stop gateway")
        self.btn_wa_stop.clicked.connect(self._on_wa_stop)
        row.addWidget(self.btn_wa_start)
        row.addWidget(self.btn_wa_stop)
        lay.addLayout(row)
        self._qr_timer = QTimer(self)
        self._qr_timer.timeout.connect(self._refresh_qr)
        return w

    def _tab_activity(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.activity_list = QListWidget()
        lay.addWidget(self.activity_list)
        return w

    def _tab_settings(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self.edit_master = QLineEdit(self.settings.master_base_url)
        self.edit_build_ch = QLineEdit(self.settings.build_channel)
        self.chk_deps_startup = QCheckBox("Auto-install Node/Git on every startup (Windows)")
        self.chk_deps_startup.setChecked(self.settings.deps_auto_install_on_startup)
        self.chk_deps_first = QCheckBox("One-time auto-install on first launch (Windows)")
        self.chk_deps_first.setChecked(self.settings.deps_auto_install_first_run)
        self.chk_deps_sha = QCheckBox("Verify installer SHA256 (requires pinned hashes in deps.py)")
        self.chk_deps_sha.setChecked(self.settings.deps_verify_download_sha256)
        self.edit_ai = QLineEdit(self.settings.ai_mode)
        self.edit_ext_base = QLineEdit(self.settings.external_api_base)
        self.edit_ext_key = QLineEdit(self.settings.external_api_key)
        self.edit_ext_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_tg_token = QLineEdit(self.settings.owner_telegram_bot_token)
        self.edit_tg_chat = QLineEdit(self.settings.owner_telegram_chat_id)
        self.edit_cache = QLineEdit(str(self.settings.gateway_cache_dir))
        self.edit_my_host = QLineEdit(self.settings.mysql_host)
        self.edit_my_user = QLineEdit(self.settings.mysql_user)
        self.edit_my_pass = QLineEdit(self.settings.mysql_password)
        self.edit_my_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_my_db = QLineEdit(self.settings.mysql_database)
        self.edit_pg_host = QLineEdit(self.settings.pg_host)
        self.edit_pg_user = QLineEdit(self.settings.pg_user)
        self.edit_pg_pass = QLineEdit(self.settings.pg_password)
        self.edit_pg_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_pg_db = QLineEdit(self.settings.pg_database)
        form.addRow("Master URL", self.edit_master)
        form.addRow("Build channel (heartbeat)", self.edit_build_ch)
        form.addRow("", self.chk_deps_startup)
        form.addRow("", self.chk_deps_first)
        form.addRow("", self.chk_deps_sha)
        form.addRow("AI mode (local_ollama|remote_relay|external_api)", self.edit_ai)
        form.addRow("External API base", self.edit_ext_base)
        form.addRow("External API key", self.edit_ext_key)
        form.addRow("Owner Telegram bot token", self.edit_tg_token)
        form.addRow("Owner Telegram chat id", self.edit_tg_chat)
        form.addRow("Gateway cache dir (optional)", self.edit_cache)
        form.addRow("MySQL host", self.edit_my_host)
        form.addRow("MySQL user", self.edit_my_user)
        form.addRow("MySQL password", self.edit_my_pass)
        form.addRow("MySQL database", self.edit_my_db)
        form.addRow("Postgres host", self.edit_pg_host)
        form.addRow("Postgres user", self.edit_pg_user)
        form.addRow("Postgres password", self.edit_pg_pass)
        form.addRow("Postgres database", self.edit_pg_db)
        btn = QPushButton("Save settings")
        btn.clicked.connect(self._on_save_settings)
        form.addRow(btn)
        return w

    def log_activity(self, line: str) -> None:
        self.activity_list.addItem(line)
        self.activity_list.scrollToBottom()

    def _initial_bootstrap(self) -> None:
        self.log_activity("Avivi is starting…")
        marker = first_run_deps_marker_path()
        want_auto = self.settings.deps_auto_install_on_startup or (
            self.settings.deps_auto_install_first_run and not marker.exists()
        )
        if want_auto:
            st = ensure_dependencies(
                auto_install=True,
                verify_sha256=self.settings.deps_verify_download_sha256,
            )
            if self.settings.deps_auto_install_first_run and not marker.exists():
                try:
                    marker.parent.mkdir(parents=True, exist_ok=True)
                    marker.write_text("1", encoding="utf-8")
                except OSError:
                    pass
        else:
            st = ensure_dependencies(auto_install=False)
        self._update_health_card(st)

    def _update_health_card(self, st) -> None:
        parts = []
        if st.node_ok:
            parts.append(f"Node {st.node_version or ''} OK")
        else:
            parts.append("Node missing")
        parts.append("Git OK" if st.git_ok else "Git missing")
        self.card_health.setText("System: " + " | ".join(parts))
        self.card_health.setObjectName("status_ok" if st.node_ok and st.git_ok else "status_warn")
        self.card_health.style().unpolish(self.card_health)
        self.card_health.style().polish(self.card_health)
        for m in st.messages:
            self.log_activity(m)

    def _on_deps(self) -> None:
        self.log_activity("Checking dependencies (may require Administrator for silent install)…")
        st = ensure_dependencies(
            auto_install=True,
            verify_sha256=self.settings.deps_verify_download_sha256,
        )
        self._update_health_card(st)

    def _on_enroll(self) -> None:
        url = self.edit_master.text().strip() or self.settings.master_base_url
        self.settings.master_base_url = url
        s = self.settings.model_copy(update={"master_base_url": url})

        class EnrollThread(QThread):
            done = pyqtSignal(object)
            err = pyqtSignal(str)

            def __init__(self, base_url: str, st: ClientSettings) -> None:
                super().__init__()
                self._base_url = base_url
                self._st = st

            def run(self) -> None:
                try:
                    r = enroll_sync(self._base_url, self._st)
                    self.done.emit(r)
                except Exception as e:
                    self.err.emit(str(e))

        self._enroll_thread = EnrollThread(url, s)

        def ok(resp) -> None:
            self.credentials_store.save(resp.client_id, resp.fernet_key_b64, resp.hmac_secret_b64)
            self.creds = self.credentials_store.load_decrypted()
            self.log_activity(f"Enrolled as client {resp.client_id}")
            self._start_heartbeat()
            self._restore_mission_runner()

        self._enroll_thread.done.connect(ok)
        self._enroll_thread.err.connect(lambda e: self.log_activity(f"Enroll failed: {e}"))
        self._enroll_thread.start()

    def _start_heartbeat(self) -> None:
        if not self.creds:
            return
        if self._heartbeat:
            self._heartbeat.stop()
            self._heartbeat.wait(3000)
        self._heartbeat = HeartbeatWorker(
            self.settings.master_base_url,
            self.creds["client_id"],
            self.creds["fernet_key_b64"],
            self.settings,
            interval_sec=25,
        )
        self._heartbeat.status_signal.connect(self._on_heartbeat)
        self._heartbeat.error_signal.connect(lambda e: self.log_activity(f"Heartbeat error: {e}"))
        self._heartbeat.start()

    def _on_heartbeat(self, data: dict) -> None:
        if data.get("locked"):
            self._system_locked = True
            self.log_activity("Master locked this client.")
        caps = {
            "db_summary": getattr(self, "_last_db_summary", None),
            "wa": self._gateway.pairing_status(),
        }
        if self._heartbeat:
            self._heartbeat.set_capabilities({k: v for k, v in caps.items() if v})

    def _restore_mission_runner(self) -> None:
        if not self.creds:
            return
        md = _data_dir() / "missions" / "active"

        def hitl(title: str, detail: str) -> str:
            return self._owner.request_approval(title, detail)

        self._mission_runner = MissionRunner(
            md,
            self.creds["fernet_key_b64"],
            hitl_request=hitl,
            on_send_whatsapp=lambda to, msg: self._gateway.send_text(to, msg),
        )
        self._owner.on_approve = lambda aid: (
            self._mission_runner.on_owner_approved(aid) if self._mission_runner else None
        )
        self._owner.on_reject = lambda aid: (
            self._mission_runner.on_owner_rejected(aid) if self._mission_runner else None
        )
        self._owner.on_mission_command = self._on_owner_mission_command
        self._sync_owner_menu_from_missions()

    def _sync_owner_menu_from_missions(self) -> None:
        if not self._mission_runner:
            self._owner.set_mission_menu_commands([])
            return
        items: list[tuple[str, str]] = []
        for m in self._mission_runner.load_missions():
            for oc in m.owner_commands:
                items.append((oc.command_id, oc.label))
        self._owner.set_mission_menu_commands(items)

    def _on_owner_mission_command(self, cmd_id: str) -> None:
        self.log_activity(f"Owner Telegram menu: {cmd_id}")

    def _wire_owner_bot(self) -> None:
        if self.settings.owner_telegram_bot_token:
            self._owner.start_background()
            self.log_activity("Owner Telegram bot thread started.")

    def _on_save_settings(self) -> None:
        self.settings.master_base_url = self.edit_master.text().strip()
        self.settings.build_channel = self.edit_build_ch.text().strip() or "stable"
        self.settings.deps_auto_install_on_startup = self.chk_deps_startup.isChecked()
        self.settings.deps_auto_install_first_run = self.chk_deps_first.isChecked()
        self.settings.deps_verify_download_sha256 = self.chk_deps_sha.isChecked()
        self.settings.ai_mode = self.edit_ai.text().strip() or "local_ollama"
        self.settings.external_api_base = self.edit_ext_base.text().strip()
        self.settings.external_api_key = self.edit_ext_key.text().strip()
        self.settings.owner_telegram_bot_token = self.edit_tg_token.text().strip()
        self.settings.owner_telegram_chat_id = self.edit_tg_chat.text().strip()
        self.settings.gateway_cache_dir = self.edit_cache.text().strip()
        self.settings.mysql_host = self.edit_my_host.text().strip() or "127.0.0.1"
        self.settings.mysql_user = self.edit_my_user.text().strip()
        self.settings.mysql_password = self.edit_my_pass.text().strip()
        self.settings.mysql_database = self.edit_my_db.text().strip()
        self.settings.pg_host = self.edit_pg_host.text().strip() or "127.0.0.1"
        self.settings.pg_user = self.edit_pg_user.text().strip()
        self.settings.pg_password = self.edit_pg_pass.text().strip()
        self.settings.pg_database = self.edit_pg_db.text().strip()
        self.settings_store.save(self.settings)
        self.log_activity("Settings saved.")
        self._owner.token = self.settings.owner_telegram_bot_token
        self._owner.allowed_chat_id = self.settings.owner_telegram_chat_id or None

    def _on_scan_db(self) -> None:
        from avivi_client.services import db_scanner

        class T(QThread):
            done = pyqtSignal(object)

            def run(self_inner) -> None:
                ports = db_scanner.probe_local_ports()
                st = self.settings
                mysql = None
                if st.mysql_user and st.mysql_database:
                    mysql = {
                        "host": st.mysql_host,
                        "user": st.mysql_user,
                        "password": st.mysql_password,
                        "database": st.mysql_database,
                    }
                pg = None
                if st.pg_user and st.pg_database:
                    pg = {
                        "host": st.pg_host,
                        "user": st.pg_user,
                        "password": st.pg_password,
                        "database": st.pg_database,
                    }
                bundle = db_scanner.build_context_bundle(ports, mysql, pg)
                self_inner.done.emit(bundle)

        self._db_thread = T()
        self._db_thread.done.connect(self._on_db_done)
        self._db_thread.start()
        self.log_activity("Avivi is scanning for database ports…")

    def _on_db_done(self, bundle: dict) -> None:
        self._last_db_summary = json.dumps(bundle, indent=0)[:800]
        open_p = [str(p) for p, ok in bundle.get("open_ports", {}).items() if ok]
        self.card_db.setText("DB: open ports " + (", ".join(open_p) or "none"))
        self.card_db.setObjectName("status_ok" if open_p else "status_warn")
        self.card_db.style().unpolish(self.card_db)
        self.card_db.style().polish(self.card_db)
        self.log_activity("DB scan complete.")
        try:
            from avivi_client.services import db_scanner

            p = db_scanner.write_semantic_context(_data_dir(), bundle)
            self.log_activity(f"Saved DB semantic context for agents: {p.name}")
        except Exception as e:
            self.log_activity(f"Semantic context save failed: {e}")
        if self.creds:
            try:
                post_client_event(
                    self.settings.master_base_url,
                    self.creds["client_id"],
                    self.creds["fernet_key_b64"],
                    "db_semantic_scan",
                    "Local DB schema map refreshed",
                    minutes_saved=2.0,
                )
            except Exception:
                pass

    def _on_wa_start(self) -> None:
        cache = self.settings.resolved_cache_dir
        cache.mkdir(parents=True, exist_ok=True)
        self._gateway.stop()
        self._gateway.start()
        self.card_wa.setText(f"WhatsApp: {self._gateway.pairing_status()}")
        self._qr_timer.start(800)
        self.log_activity("WhatsApp gateway starting…")

        def get_proc():
            return self._gateway._proc

        def restart():
            self._gateway.stop()
            self._gateway.start()
            self.log_activity("Watchdog restarted WhatsApp gateway.")

        if self._watchdog:
            self._watchdog.stop()
        self._watchdog = ProcessWatchdog(get_proc, restart, cache)
        self._watchdog.on_recovery = lambda msg: self._on_watchdog_recovery(msg)
        self._watchdog.start()

    def _on_watchdog_recovery(self, msg: str) -> None:
        self.log_activity(msg)
        if self.creds:
            try:
                post_client_event(
                    self.settings.master_base_url,
                    self.creds["client_id"],
                    self.creds["fernet_key_b64"],
                    "gateway_recovered",
                    msg,
                    minutes_saved=0.0,
                )
            except Exception:
                pass

    def _on_wa_stop(self) -> None:
        self._qr_timer.stop()
        if self._watchdog:
            self._watchdog.stop()
            self._watchdog = None
        self._gateway.stop()
        self.card_wa.setText("WhatsApp: stopped")
        self.log_activity("WhatsApp gateway stopped.")

    def _refresh_qr(self) -> None:
        b64 = self._gateway.latest_qr_base64()
        self.lbl_wa_identity.setText("Connected as: " + self._gateway.identity_label())
        self.card_wa.setText(f"WhatsApp: {self._gateway.pairing_status()}")
        if not b64:
            return
        try:
            raw = base64.b64decode(b64)
            pix = QPixmap()
            pix.loadFromData(QByteArray(raw))
            if not pix.isNull():
                self.lbl_qr.setPixmap(pix.scaled(260, 260, Qt.AspectRatioMode.KeepAspectRatio))
        except Exception:
            pass

    def _poll_remote(self) -> None:
        if not self.creds or self._system_locked:
            return
        base = self.settings.master_base_url
        cid = self.creds["client_id"]
        fk = self.creds["fernet_key_b64"]
        hk = self.creds.get("hmac_secret_b64")
        try:
            pending = fetch_pending(base, cid, fk)
            dest = _data_dir() / "missions" / "active"
            for m in pending:
                apply_mission_blob(m["encrypted_blob_b64"], fk, hk, m.get("signature_hex"), dest)
                ack_mission(base, cid, m["id"], fk)
                self.log_activity(f"Applied mission {m.get('mission_id')} v{m.get('version')}")
            self._restore_mission_runner()
            self._sync_owner_menu_from_missions()
            cmds = poll_commands(base, cid, fk)
            for c in cmds:
                self._handle_command(c)
                ack_command(base, cid, c["id"], fk)
        except Exception as e:
            self.log_activity(f"Poll error: {e}")

    def _handle_command(self, c: dict) -> None:
        t = c.get("type")
        self.log_activity(f"Remote command: {t}")
        if t == RemoteCommandType.lock_system.value:
            self._system_locked = True
        elif t == RemoteCommandType.restart_gateway.value:
            self._on_wa_stop()
            self._on_wa_start()
        elif t == RemoteCommandType.push_mission.value:
            self.log_activity("Mission push scheduled — next poll will fetch payload.")

    def closeEvent(self, event) -> None:
        if self._poll_worker:
            self._poll_worker.stop()
            self._poll_worker.wait(5000)
            self._poll_worker = None
        if self._heartbeat:
            self._heartbeat.stop()
            self._heartbeat.wait(5000)
        event.accept()
