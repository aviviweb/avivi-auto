from __future__ import annotations

import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

import httpx
from PyQt6.QtCore import QElapsedTimer, QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openclaw_launcher.config_model import LauncherSettings
from openclaw_launcher.services.db_bridge_server import DbBridgeServer
from openclaw_launcher.services.db_profiles_store import DbProfilesStore
from openclaw_launcher.services.gateway_supervisor import GatewayState, GatewaySupervisor
from openclaw_launcher.services.activity_feed import append_activity, read_activity_tail
from openclaw_launcher.services.launcher_secrets_store import LauncherSecretsStore
from openclaw_launcher.services.openclaw_backup import maybe_run_daily_openclaw_backup
from openclaw_launcher.services.openclaw_config import sync_telegram_channel_to_openclaw_config
from openclaw_launcher.services.orchestrator_bootstrap import ensure_task_manager_skill_registered
from openclaw_launcher.services.orchestration import (
    load_orchestration,
    run_orchestration_tick,
    save_orchestration,
)
from openclaw_launcher.services.recovery import RecoveryOrchestrator
from openclaw_launcher.services.telegram_health import check_telegram_bot
from openclaw_launcher.services.workspace_bootstrap import ensure_workspace
from openclaw_launcher.ui.db_profiles_dialog import DbProfileDialog
from openclaw_launcher.ui.discovery_dialog import DiscoveryDialog

THEME = """
QMainWindow, QWidget { background-color: #0f172a; color: #e2e8f0; }
QGroupBox { border: 1px solid #334155; margin-top: 8px; }
QLabel#tg_ok { color: #34d399; font-weight: bold; }
QLabel#tg_bad { color: #f87171; font-weight: bold; }
QPushButton { background-color: #1e293b; border: 1px solid #475569; padding: 6px; }
QLineEdit { background-color: #1e293b; border: 1px solid #475569; color: #f8fafc; padding: 4px; }
QPlainTextEdit { background-color: #1e293b; border: 1px solid #475569; color: #f8fafc; font-family: Consolas, monospace; font-size: 11px; }
"""


class _ThreadSignals(QObject):
    telegram_test_done = pyqtSignal(bool, str, object)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Business AI Orchestrator — OpenClaw Launcher")
        self.resize(960, 720)
        self.setStyleSheet(THEME)

        boot = ensure_workspace()
        _tmp = LauncherSettings.load(boot["config"] / "launcher.yaml")
        resolved = _tmp.resolved_workspace_root()
        self._paths = ensure_workspace(resolved) if resolved != boot["root"] else boot
        self._root = self._paths["root"]
        self._launcher_yaml = self._paths["config"] / "launcher.yaml"
        self._settings = LauncherSettings.load(self._launcher_yaml)
        self._secrets = LauncherSecretsStore(self._root)
        self._orch_yaml = self._paths["config"] / "orchestration.yaml"
        self._orch = load_orchestration(self._orch_yaml)

        try:
            ensure_task_manager_skill_registered(self._root)
        except Exception:
            pass

        self._recovery = RecoveryOrchestrator(
            recovery_log=self._paths["logs"] / "recovery.log",
            cache_dirs=self._settings.recovery.cache_dirs,
            process_name_substrings=self._settings.recovery.process_name_substrings,
            max_log_mb=self._settings.logging.recovery_log_max_mb,
        )
        self._supervisor = GatewaySupervisor(
            self._settings.gateway,
            on_crash=self._on_gateway_crash,
        )
        self._db_store = DbProfilesStore(self._root)
        self._bridge = DbBridgeServer(
            self._settings.db_bridge.host,
            self._settings.db_bridge.port,
            self._db_store,
            self._root,
        )
        ok, msg = self._bridge.start()
        self._telegram_failures = 0
        self._tg_last_ok: datetime | None = None
        self._tg_last_latency_ms: int | None = None
        self._uptimer = QElapsedTimer()
        self._uptimer.start()
        self._thread_signals = _ThreadSignals()
        self._thread_signals.telegram_test_done.connect(self._apply_telegram_test_result)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        t = QLabel("Business AI Orchestrator")
        t.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        t.setStyleSheet("color: #34d399;")
        layout.addWidget(t)
        layout.addWidget(QLabel(f"Workspace: {self._root}"))

        dash = QGroupBox("Enterprise dashboard")
        dvl = QVBoxLayout(dash)
        self.lbl_dash_agent = QLabel("Active agent: —")
        self.lbl_dash_db = QLabel("DB profiles / bridge: —")
        self.lbl_dash_msgs = QLabel("Message count: — (optional launcher_telemetry.json)")
        self.lbl_dash_uptime = QLabel("Launcher uptime: —")
        self.lbl_dash_gw_state = QLabel("Gateway state: —")
        for w in (
            self.lbl_dash_agent,
            self.lbl_dash_db,
            self.lbl_dash_msgs,
            self.lbl_dash_uptime,
            self.lbl_dash_gw_state,
        ):
            dvl.addWidget(w)
        layout.addWidget(dash)

        sm = QGroupBox("Smart Manager — top urgent tasks")
        sml = QVBoxLayout(sm)
        self.list_tasks = QListWidget()
        self.list_tasks.setMaximumHeight(110)
        sml.addWidget(self.list_tasks)
        layout.addWidget(sm)

        act = QGroupBox("Activity feed")
        al = QVBoxLayout(act)
        self.txt_activity = QPlainTextEdit()
        self.txt_activity.setReadOnly(True)
        self.txt_activity.setFixedHeight(100)
        al.addWidget(self.txt_activity)
        layout.addWidget(act)

        gw = QGroupBox("Gateway")
        gvl = QVBoxLayout(gw)
        self.lbl_gateway = QLabel("stopped")
        gvl.addWidget(self.lbl_gateway)
        r1 = QHBoxLayout()
        for txt, fn in [
            ("Start", self._start_gw),
            ("Stop", self._stop_gw),
            ("Recovery", self._manual_recovery),
        ]:
            b = QPushButton(txt)
            b.clicked.connect(fn)
            r1.addWidget(b)
        gvl.addLayout(r1)
        self.edit_cmd = QLineEdit(" ".join(self._settings.gateway.command))
        gvl.addWidget(QLabel("Command (space-separated):"))
        gvl.addWidget(self.edit_cmd)
        bs = QPushButton("Save launcher.yaml")
        bs.clicked.connect(self._save_launcher)
        gvl.addWidget(bs)
        layout.addWidget(gw)

        tg = QGroupBox("Telegram (zero-config onboarding)")
        tvl = QVBoxLayout(tg)
        _tok = (
            self._settings.telegram_bot_token.strip()
            or self._secrets.get_telegram_bot_token()
        )
        self.edit_tg = QLineEdit(_tok)
        self.edit_tg.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_tg.setPlaceholderText("Bot token — auto-syncs to openclaw.json channels")
        tvl.addWidget(self.edit_tg)
        tgr = QHBoxLayout()
        self.btn_tg_save = QPushButton("Save token encrypted")
        self.btn_tg_save.clicked.connect(self._save_telegram_encrypted)
        tgr.addWidget(self.btn_tg_save)
        self.btn_tg_sync = QPushButton("Sync now → openclaw.json")
        self.btn_tg_sync.clicked.connect(self._sync_telegram_openclaw_now)
        tgr.addWidget(self.btn_tg_sync)
        tvl.addLayout(tgr)
        self.lbl_tg = QLabel("—")
        self.lbl_tg.setObjectName("tg_bad")
        tvl.addWidget(self.lbl_tg)
        self.lbl_tg_meta = QLabel("")
        self.lbl_tg_meta.setStyleSheet("color: #94a3b8; font-size: 11px;")
        tvl.addWidget(self.lbl_tg_meta)
        layout.addWidget(tg)

        self._tg_auto = QTimer(self)
        self._tg_auto.setSingleShot(True)
        self._tg_auto.timeout.connect(self._debounced_telegram_pipeline)
        self.edit_tg.textChanged.connect(lambda: self._tg_auto.start(900))

        orch = QGroupBox("Orchestration")
        ovl = QVBoxLayout(orch)
        self.chk_master = QCheckBox("Master switch")
        self.chk_master.setChecked(self._orch.master_switch)
        self.chk_master.toggled.connect(self._toggle_master)
        ovl.addWidget(self.chk_master)
        layout.addWidget(orch)

        db = QGroupBox("Database")
        dvl = QVBoxLayout(db)
        self.list_p = QListWidget()
        self._refresh_profiles()
        dvl.addWidget(self.list_p)
        r2 = QHBoxLayout()
        b_prof = QPushButton("Add/Edit profile")
        b_prof.clicked.connect(self._dlg_profile)
        b_disc = QPushButton("Auto-discover DB…")
        b_disc.clicked.connect(self._dlg_discovery)
        b_ws = QPushButton("Open workspace")
        b_ws.clicked.connect(self._open_ws)
        r2.addWidget(b_prof)
        r2.addWidget(b_disc)
        r2.addWidget(b_ws)
        dvl.addLayout(r2)
        layout.addWidget(db)

        crit = QGroupBox("Critical log (recovery / launcher)")
        cvl = QVBoxLayout(crit)
        self.txt_critical = QPlainTextEdit()
        self.txt_critical.setReadOnly(True)
        self.txt_critical.setMaximumBlockCount(400)
        self.txt_critical.setFixedHeight(140)
        cvl.addWidget(self.txt_critical)
        layout.addWidget(crit)

        self.log_events = QListWidget()
        self.log_events.setMaximumHeight(56)
        layout.addWidget(QLabel("Recent events"))
        layout.addWidget(self.log_events)

        self._log(f"Bridge: {msg}")
        append_activity(self._root, "Launcher started; workspace ready")

        self._timer_gw = QTimer(self)
        self._timer_gw.timeout.connect(self._tick_gw)
        self._timer_gw.start(2000)
        self._timer_tg = QTimer(self)
        self._timer_tg.timeout.connect(self._tick_tg)
        self._timer_tg.start(15000)
        self._tick_tg()
        self._timer_o = QTimer(self)
        self._timer_o.timeout.connect(self._tick_o)
        self._timer_o.start(max(15, self._orch.poll_interval_sec) * 1000)
        self._timer_dash = QTimer(self)
        self._timer_dash.timeout.connect(self._refresh_dashboard)
        self._timer_dash.start(5000)
        self._timer_backup = QTimer(self)
        self._timer_backup.timeout.connect(self._tick_backup)
        self._timer_backup.start(60_000)
        self._refresh_dashboard()
        self._tick_backup()

    def _log(self, m: str) -> None:
        self.log_events.addItem(m)
        self.log_events.scrollToBottom()

    def _refresh_critical_logs(self) -> None:
        rec = self._paths["logs"] / "recovery.log"
        launch = self._paths["logs"] / "launcher.log"
        picked: list[str] = []
        for path in (rec, launch):
            if not path.exists():
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line in lines[-400:]:
                low = line.lower()
                if (
                    "\terror\t" in low
                    or "\tcrash\t" in low
                    or "\trecovery_start\t" in low
                    or "recovery_start" in low
                    or "gateway_crash" in low
                    or "gateway exited" in low
                    or "telegram_failures" in low
                ):
                    picked.append(line)
        text = "\n".join(picked[-120:])
        self.txt_critical.setPlainText(text)
        sb = self.txt_critical.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _refresh_dashboard(self) -> None:
        sec = self._uptimer.elapsed() // 1000
        h, r = divmod(sec, 3600)
        m, s = divmod(r, 60)
        self.lbl_dash_uptime.setText(f"Launcher uptime: {h:02d}:{m:02d}:{s:02d}")

        active_p = self._paths["agents"] / "active.json"
        agent_txt = "—"
        if active_p.exists():
            try:
                doc = json.loads(active_p.read_text(encoding="utf-8"))
                agent_txt = str(doc.get("active_profile", doc))
            except (json.JSONDecodeError, OSError):
                agent_txt = "(invalid active.json)"
        self.lbl_dash_agent.setText(f"Active agent: {agent_txt}")

        nprof = len(self._db_store.list_profiles())
        bridge_ok = False
        try:
            r = httpx.get(
                f"http://{self._settings.db_bridge.host}:{self._settings.db_bridge.port}/health",
                timeout=2.0,
            )
            bridge_ok = r.status_code == 200
        except Exception:
            bridge_ok = False
        self.lbl_dash_db.setText(
            f"DB profiles: {nprof} · Bridge /health: {'OK' if bridge_ok else 'down'}"
        )

        tel = self._root / "launcher_telemetry.json"
        msg_c = "—"
        if tel.exists():
            try:
                doc = json.loads(tel.read_text(encoding="utf-8"))
                if isinstance(doc, dict) and "message_count" in doc:
                    msg_c = str(doc["message_count"])
            except (json.JSONDecodeError, OSError):
                msg_c = "(invalid JSON)"
        self.lbl_dash_msgs.setText(f"Message count: {msg_c}")

        st = self._supervisor.state
        self.lbl_dash_gw_state.setText(f"Gateway state: {st.value}")

        self._refresh_critical_logs()
        self._refresh_task_board()
        self._refresh_activity_feed()

    def _tick_backup(self) -> None:
        note = maybe_run_daily_openclaw_backup(self._paths["backups"])
        if note:
            self._log(note)

    def _refresh_profiles(self) -> None:
        self.list_p.clear()
        for p in self._db_store.list_profiles():
            self.list_p.addItem(p.get("id", "?"))

    def _refresh_task_board(self) -> None:
        self.list_tasks.clear()
        p = self._paths["task_logs"] / "tasks.json"
        if not p.exists():
            self.list_tasks.addItem("(No tasks yet — agent uses business_task_manager skill)")
            return
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            tasks = doc.get("tasks") if isinstance(doc, dict) else None
            if not isinstance(tasks, list):
                tasks = []
        except (json.JSONDecodeError, OSError):
            self.list_tasks.addItem("(Invalid tasks.json)")
            return
        rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

        def sort_key(t: dict) -> tuple[int, str]:
            u = str(t.get("urgency", "LOW")).upper()
            return (rank.get(u, 9), str(t.get("title", "")))

        scored = [t for t in tasks if isinstance(t, dict)]
        scored.sort(key=sort_key)
        if not scored:
            self.list_tasks.addItem("(No tasks in tasks.json yet)")
            return
        for t in scored[:5]:
            u = str(t.get("urgency", "?")).upper()
            title = str(t.get("title", "(no title)"))[:64]
            self.list_tasks.addItem(f"[{u}] {title}")

    def _refresh_activity_feed(self) -> None:
        self.txt_activity.setPlainText(read_activity_tail(self._root, 50))
        sb = self.txt_activity.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _run_recovery_thread(self, reason: str, restart) -> None:
        def work() -> None:
            self._recovery.run_recovery(reason, restart, launcher_pid=os.getpid())

        threading.Thread(target=work, daemon=True, name="recovery").start()

    def _on_gateway_crash(self, reason: str) -> None:
        self._recovery.append_log(reason, "crash")
        append_activity(self._root, f"Gateway crash — recovery started ({reason[:80]})")

        def r() -> None:
            self._supervisor.start()

        self._run_recovery_thread(reason, r)

    def _start_gw(self) -> None:
        ok, msg = self._supervisor.start()
        self._log(msg)
        self.lbl_gateway.setText(msg)
        append_activity(self._root, "Gateway start requested")

    def _stop_gw(self) -> None:
        self._supervisor.stop()
        self.lbl_gateway.setText("stopped")
        append_activity(self._root, "Gateway stopped")

    def _manual_recovery(self) -> None:
        self._supervisor.stop()
        append_activity(self._root, "Manual recovery — clearing cache & restarting gateway")

        def r() -> None:
            self._supervisor.start()

        self._run_recovery_thread("manual", r)

    def _save_launcher(self) -> None:
        parts = self.edit_cmd.text().strip().split()
        self._settings.gateway.command = parts or ["openclaw", "gateway"]
        self._settings.save(self._launcher_yaml)
        self._supervisor.cfg = self._settings.gateway

    def _tick_gw(self) -> None:
        self._supervisor.tick()
        st = self._supervisor.state
        if self._supervisor.is_running() and self._supervisor.process:
            self.lbl_gateway.setText(f"{st.value} pid={self._supervisor.process.pid}")
        elif st == GatewayState.ERROR:
            self.lbl_gateway.setText("error (see recovery)")
        else:
            self.lbl_gateway.setText(st.value)

    def _tick_tg(self) -> None:
        tok = self.edit_tg.text().strip() or self._settings.telegram_bot_token
        ok, d, lat_ms = check_telegram_bot(tok)
        self.lbl_tg.setText(d)
        self.lbl_tg.setObjectName("tg_ok" if ok else "tg_bad")
        self.lbl_tg.style().unpolish(self.lbl_tg)
        self.lbl_tg.style().polish(self.lbl_tg)
        if ok:
            self._tg_last_ok = datetime.now()
            self._tg_last_latency_ms = lat_ms
            extra = f"Last OK: {self._tg_last_ok:%H:%M:%S}"
            if lat_ms is not None:
                extra += f" · {lat_ms} ms"
            self.lbl_tg_meta.setText(extra)
        else:
            self.lbl_tg_meta.setText("")
        if not ok:
            self._telegram_failures += 1
            if self._telegram_failures >= self._settings.recovery.telegram_failures_before_recovery:
                self._telegram_failures = 0
                self._supervisor.stop()
                append_activity(
                    self._root,
                    "Telegram check failed repeatedly — self-healing (cache flush + gateway restart)",
                )

                def r() -> None:
                    self._supervisor.start()

                self._run_recovery_thread("telegram_failures", r)
        else:
            self._telegram_failures = 0

    def _toggle_master(self, v: bool) -> None:
        self._orch.master_switch = v
        save_orchestration(self._orch_yaml, self._orch)

    def _tick_o(self) -> None:
        self._orch = load_orchestration(self._orch_yaml)
        self.chk_master.blockSignals(True)
        self.chk_master.setChecked(self._orch.master_switch)
        self.chk_master.blockSignals(False)
        m = run_orchestration_tick(
            self._root,
            self._orch,
            self._settings.db_bridge.host,
            self._settings.db_bridge.port,
        )
        if m:
            self._log(m)
            append_activity(self._root, m[:200])

    def _dlg_profile(self) -> None:
        cur = self.list_p.currentItem()
        pid = cur.text() if cur else None
        if DbProfileDialog(self._db_store, profile_id=pid, parent=self).exec():
            self._refresh_profiles()

    def _dlg_discovery(self) -> None:
        dlg = DiscoveryDialog(
            self._db_store,
            self._settings.db_bridge.host,
            self._settings.db_bridge.port,
            parent=self,
        )
        if dlg.exec():
            self._refresh_profiles()
            append_activity(self._root, "DB profile & skills updated from auto-discovery")

    def _save_telegram_encrypted(self) -> None:
        tok = self.edit_tg.text().strip()
        self._secrets.set_telegram_bot_token(tok)
        self._settings.telegram_bot_token = ""
        self._settings.save(self._launcher_yaml)
        append_activity(self._root, "Telegram token saved encrypted (config/launcher_secrets.enc)")

    def _sync_telegram_openclaw_now(self) -> None:
        tok = self.edit_tg.text().strip()
        if not tok:
            self._log("Telegram: empty token")
            return
        try:
            sync_telegram_channel_to_openclaw_config(tok)
        except Exception as e:
            self._log(f"openclaw.json sync failed: {e}")
            return
        append_activity(self._root, "Synced Telegram bot to openclaw.json channels")
        self._telegram_test_background()

    def _debounced_telegram_pipeline(self) -> None:
        tok = self.edit_tg.text().strip()
        if len(tok) < 40:
            return
        try:
            sync_telegram_channel_to_openclaw_config(tok)
            self._secrets.set_telegram_bot_token(tok)
            self._settings.telegram_bot_token = ""
            self._settings.save(self._launcher_yaml)
        except Exception:
            return
        append_activity(self._root, "Auto-synced Telegram token to openclaw.json")
        self._telegram_test_background()

    def _telegram_test_background(self) -> None:
        tok = self.edit_tg.text().strip()

        def work() -> None:
            ok, detail, lat = check_telegram_bot(tok)
            self._thread_signals.telegram_test_done.emit(ok, detail, lat)

        threading.Thread(target=work, daemon=True, name="tg-test").start()

    def _apply_telegram_test_result(
        self, ok: bool, detail: str, lat_ms: int | None
    ) -> None:
        if ok:
            extra = f"Background test OK: {detail}"
            if lat_ms is not None:
                extra += f" ({lat_ms} ms)"
            append_activity(self._root, extra)
        else:
            append_activity(self._root, f"Telegram test failed: {detail[:120]}")

    def _open_ws(self) -> None:
        p = str(self._root)
        if sys.platform == "win32":
            os.startfile(p)  # type: ignore[attr-defined]
        else:
            QFileDialog.getOpenFileName(self, dir=p)

    def closeEvent(self, e) -> None:
        self._bridge.stop()
        self._supervisor.stop()
        e.accept()
