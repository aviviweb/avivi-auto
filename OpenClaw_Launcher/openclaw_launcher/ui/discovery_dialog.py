from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from openclaw_launcher.services.db_connection_test import (
    test_bridge_select_one,
    test_database_connection,
)
from openclaw_launcher.services.database_scanner import DatabaseScanner
from openclaw_launcher.services.db_discovery_scanner import DetectedService
from openclaw_launcher.services.db_profiles_store import DbProfile, DbProfilesStore
from openclaw_launcher.services.openclaw_config import (
    register_context_files_in_openclaw_config,
    register_skill_bundle_in_openclaw_config,
)
from openclaw_launcher.services.schema_introspection import (
    introspect_schema,
    write_schema_context_file,
)
from openclaw_launcher.services.skill_generator import generate_all_db_bridge_skill_artifacts


class DiscoveryDialog(QDialog):
    """Scan local DB ports, collect credentials, test connection, save profile, generate skill."""

    def __init__(
        self,
        store: DbProfilesStore,
        bridge_host: str,
        bridge_port: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Auto-Discovery and DB Integration")
        self.resize(520, 480)
        self._store = store
        self._bridge_host = bridge_host
        self._bridge_port = bridge_port
        self._selected: DetectedService | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Detected services (127.0.0.1) — open ports only are usable:"))

        self.list_detected = QListWidget()
        layout.addWidget(self.list_detected)

        row = QHBoxLayout()
        self.btn_scan = QPushButton("Scan ports")
        row.addWidget(self.btn_scan)
        layout.addLayout(row)

        form = QFormLayout()
        self.edit_user = QLineEdit()
        self.edit_pass = QLineEdit()
        self.edit_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_database = QLineEdit()
        self.edit_skill_id = QLineEdit("db_skill_auto")
        self.edit_profile_id = QLineEdit("discovered_db")
        form.addRow("Username", self.edit_user)
        form.addRow("Password", self.edit_pass)
        form.addRow("Database name", self.edit_database)
        form.addRow("Profile ID (launcher)", self.edit_profile_id)
        form.addRow("Skill ID (filename)", self.edit_skill_id)
        self.chk_read_only = QCheckBox("Read-only profile (bridge enforces)")
        self.chk_read_only.setChecked(True)
        form.addRow("", self.chk_read_only)
        layout.addLayout(form)

        self.lbl_status = QLabel("Select an open port above, then Test or Add.")
        self.lbl_status.setWordWrap(True)
        layout.addWidget(self.lbl_status)

        btn_row = QHBoxLayout()
        self.btn_test = QPushButton("Test connection (direct)")
        self.btn_test_bridge = QPushButton("Test via bridge")
        self.btn_apply = QPushButton("Save + skill + openclaw.json")
        self.btn_map_schema = QPushButton("Map schema → context + openclaw.json")
        btn_row.addWidget(self.btn_test)
        btn_row.addWidget(self.btn_test_bridge)
        layout.addLayout(btn_row)
        layout.addWidget(self.btn_map_schema)
        layout.addWidget(self.btn_apply)

        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

        self.btn_scan.clicked.connect(self._run_scan)
        self.list_detected.currentItemChanged.connect(self._on_select)
        self.btn_test.clicked.connect(self._on_test)
        self.btn_test_bridge.clicked.connect(self._on_test_bridge)
        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_map_schema.clicked.connect(self._on_map_schema)

        self._run_scan()

    def _run_scan(self) -> None:
        self.list_detected.clear()
        for d in DatabaseScanner.scan("127.0.0.1"):
            status = "OPEN" if d.open else "closed"
            text = f"[{status}] {d.label} — port {d.port} ({d.engine})"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, d)
            if not d.open:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.list_detected.addItem(item)
        self.lbl_status.setText("Pick an OPEN row, enter credentials, then Test.")

    def _on_select(self, current: QListWidgetItem | None, _prev: QListWidgetItem | None) -> None:
        if not current:
            self._selected = None
            return
        d = current.data(Qt.ItemDataRole.UserRole)
        self._selected = d if isinstance(d, DetectedService) else None

    def _build_profile(self) -> DbProfile | None:
        if not self._selected or not self._selected.open:
            QMessageBox.warning(self, "Discovery", "Select an open database port first.")
            return None
        db = self.edit_database.text().strip()
        if not db and self._selected.engine != "mongodb":
            QMessageBox.warning(self, "Discovery", "Database name is required for SQL engines.")
            return None
        pid = self.edit_profile_id.text().strip() or "discovered_db"
        return DbProfile(
            id=pid,
            engine=self._selected.engine,
            host=self._selected.host,
            port=self._selected.port,
            user=self.edit_user.text(),
            password=self.edit_pass.text(),
            database=db or "admin",
            ssl=False,
            read_only=self.chk_read_only.isChecked(),
        )

    def _on_test(self) -> None:
        prof = self._build_profile()
        if not prof:
            return
        ok, msg = test_database_connection(prof)
        self.lbl_status.setText(msg)
        if ok:
            QMessageBox.information(self, "Test", msg)
        else:
            QMessageBox.warning(self, "Test failed", msg)

    def _on_test_bridge(self) -> None:
        prof = self._build_profile()
        if not prof:
            return
        if prof.engine == "mongodb":
            QMessageBox.information(
                self,
                "Bridge",
                "MongoDB uses POST /query with collection in body; use direct test or save first.",
            )
            return
        ok_d, msg_d = test_database_connection(prof)
        if not ok_d:
            QMessageBox.warning(self, "Bridge", f"Fix direct connection first:\n{msg_d}")
            return
        tmp_id = "__openclaw_bridge_test_tmp"
        prof_tmp = DbProfile(
            id=tmp_id,
            engine=prof.engine,
            host=prof.host,
            port=prof.port,
            user=prof.user,
            password=prof.password,
            database=prof.database,
            ssl=prof.ssl,
            read_only=prof.read_only,
        )
        try:
            self._store.save_profile(prof_tmp)
            ok, msg = test_bridge_select_one(
                self._bridge_host, self._bridge_port, tmp_id
            )
            self.lbl_status.setText(msg)
            if ok:
                QMessageBox.information(self, "Bridge", msg)
            else:
                QMessageBox.warning(self, "Bridge failed", msg)
        finally:
            self._store.delete_profile(tmp_id)

    def _on_map_schema(self) -> None:
        prof = self._build_profile()
        if not prof:
            return
        ok, msg, body = introspect_schema(prof)
        if not ok or not body:
            QMessageBox.warning(self, "Schema map", msg or "No schema body")
            return
        try:
            path = write_schema_context_file(self._store.workspace_root, prof.id, body)
            register_context_files_in_openclaw_config([path])
        except Exception as e:
            QMessageBox.critical(self, "Schema map", str(e))
            return
        QMessageBox.information(
            self,
            "Schema map",
            f"{msg}\n\nWritten:\n{path}\nRegistered in ~/.openclaw/openclaw.json context_files.",
        )

    def _on_apply(self) -> None:
        prof = self._build_profile()
        if not prof:
            return
        ok, msg = test_database_connection(prof)
        if not ok:
            QMessageBox.warning(self, "Cannot add", f"Connection test failed:\n{msg}")
            return
        skill_id = self.edit_skill_id.text().strip() or "db_skill_auto"
        try:
            self._store.save_profile(prof)
            paths = generate_all_db_bridge_skill_artifacts(
                skill_id,
                prof.id,
                self._bridge_host,
                self._bridge_port,
                prof.engine,
            )
            register_skill_bundle_in_openclaw_config(paths, skill_id)
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return
        QMessageBox.information(
            self,
            "Done",
            "Profile saved.\nSkills: JSON + Python + JS\nopenclaw.json updated (paths + skill_paths).",
        )
        self.accept()
