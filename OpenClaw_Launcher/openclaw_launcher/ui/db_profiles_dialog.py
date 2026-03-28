from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from openclaw_launcher.services.db_profiles_store import DbProfile, DbProfilesStore


class DbProfileDialog(QDialog):
    def __init__(self, store: DbProfilesStore, profile_id: str | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Database profile")
        self._store = store
        self._existing_id = profile_id

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.edit_id = QLineEdit()
        self.combo_engine = QComboBox()
        self.combo_engine.addItems(["postgresql", "mysql", "mongodb", "mssql"])
        self.edit_host = QLineEdit("127.0.0.1")
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1, 65535)
        self.spin_port.setValue(5432)
        self.edit_user = QLineEdit()
        self.edit_pass = QLineEdit()
        self.edit_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_db = QLineEdit()
        self.chk_read_only = QCheckBox("Read-only profile (recommended)")
        self.chk_read_only.setChecked(True)

        form.addRow("Profile ID", self.edit_id)
        form.addRow("Engine", self.combo_engine)
        form.addRow("Host", self.edit_host)
        form.addRow("Port", self.spin_port)
        form.addRow("User", self.edit_user)
        form.addRow("Password", self.edit_pass)
        form.addRow("Database", self.edit_db)
        form.addRow("", self.chk_read_only)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if profile_id:
            self.edit_id.setText(profile_id)
            self.edit_id.setReadOnly(True)
            p = store.get_full_profile(profile_id)
            if p:
                idx = self.combo_engine.findText(p.engine)
                if idx >= 0:
                    self.combo_engine.setCurrentIndex(idx)
                self.edit_host.setText(p.host)
                self.spin_port.setValue(p.port)
                self.edit_user.setText(p.user)
                self.edit_pass.setText(p.password)
                self.edit_db.setText(p.database)
                self.chk_read_only.setChecked(p.read_only)

    def _save(self) -> None:
        pid = self.edit_id.text().strip()
        if not pid:
            QMessageBox.warning(self, "Validation", "Profile ID is required.")
            return
        if not self._existing_id and any(r.get("id") == pid for r in self._store.list_profiles()):
            QMessageBox.warning(self, "Validation", "Profile ID already exists.")
            return
        prof = DbProfile(
            id=pid,
            engine=self.combo_engine.currentText(),
            host=self.edit_host.text().strip(),
            port=self.spin_port.value(),
            user=self.edit_user.text(),
            password=self.edit_pass.text(),
            database=self.edit_db.text().strip(),
            read_only=self.chk_read_only.isChecked(),
        )
        self._store.save_profile(prof)
        self.accept()
