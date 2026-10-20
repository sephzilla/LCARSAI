"""LCARS desktop shell and first-run local runtime setup."""
from __future__ import annotations

import os
import sys
import time

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from lcarsai.runtime import check_ollama, models_dir, pull_model, start_managed_runtime

_managed_process = None


class SetupWorker(QThread):
    progress = Signal(str)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, operation: str, model: str = "") -> None:
        super().__init__()
        self.operation = operation
        self.model = model

    def run(self) -> None:
        global _managed_process
        try:
            if self.operation == "runtime":
                self.progress.emit("Preparing Computer's private runtime directory…")
                _managed_process = start_managed_runtime()
                for attempt in range(45):
                    status = check_ollama(timeout=1.0)
                    if status.available:
                        self.succeeded.emit(f"Local runtime ready (Ollama {status.version or 'version unknown'}).")
                        return
                    if _managed_process.poll() is not None:
                        raise RuntimeError("Ollama exited during startup. Check your system's GPU drivers and runtime libraries.")
                    self.progress.emit(f"Starting local runtime… ({attempt + 1}/45)")
                    time.sleep(1)
                raise RuntimeError("Ollama did not become ready within 45 seconds.")
            elif self.operation == "model":
                pull_model(self.model, lambda text: self.progress.emit(text))
                self.succeeded.emit(f"Model {self.model} is ready for local use.")
            else:
                raise RuntimeError("Unknown setup operation.")
        except Exception as exc:
            self.failed.emit(str(exc))


class SetupDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Computer — Local AI Setup")
        self.setMinimumWidth(500)
        layout = QVBoxLayout(self)
        heading = QLabel("LOCAL AI CONFIGURATION")
        heading.setObjectName("setupHeading")
        heading.setFont(QFont("Sans Serif", 16, QFont.Weight.Bold))
        layout.addWidget(heading)

        self.info = QLabel(
            "Computer runs its language model locally. Setup downloads the official Ollama "
            "runtime into your user data directory and then downloads a model you choose. "
            "No administrator privileges or system package changes are required."
        )
        self.info.setWordWrap(True)
        layout.addWidget(self.info)

        self.location = QLabel(f"Model files: {models_dir()}\nRuntime files: managed by Computer")
        self.location.setWordWrap(True)
        layout.addWidget(self.location)

        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Local model"))
        self.model = QComboBox()
        self.model.addItem("Qwen3 8B — recommended", "qwen3:8b")
        self.model.addItem("Qwen3 4B — smaller download", "qwen3:4b")
        self.model.addItem("Qwen3 14B — larger / more memory", "qwen3:14b")
        model_row.addWidget(self.model, 1)
        layout.addLayout(model_row)

        self.status = QLabel("Ready to set up.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)

        buttons = QHBoxLayout()
        self.runtime_button = QPushButton("Install / Start Runtime")
        self.runtime_button.clicked.connect(lambda: self.run_operation("runtime"))
        buttons.addWidget(self.runtime_button)
        self.model_button = QPushButton("Download Model")
        self.model_button.clicked.connect(lambda: self.run_operation("model"))
        self.model_button.setEnabled(check_ollama().available)
        buttons.addWidget(self.model_button)
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        self.worker = None
        self.setStyleSheet("""
            QDialog { background: #11131c; color: #f1e7d4; }
            QLabel { color: #f1e7d4; }
            QLabel#setupHeading { color: #ffcc66; letter-spacing: 2px; }
            QPushButton { background: #f7a34b; color: #171522; padding: 9px; border: 0; border-radius: 5px; }
            QPushButton:disabled { background: #494653; color: #aaa; }
            QComboBox { padding: 7px; }
            QProgressBar { min-height: 10px; background: #292b3b; border: 0; }
            QProgressBar::chunk { background: #cc79a7; }
        """)

    def run_operation(self, operation: str) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        if operation == "model" and not check_ollama().available:
            QMessageBox.warning(self, "Runtime required", "Install and start the local runtime first.")
            return
        self.runtime_button.setEnabled(False)
        self.model_button.setEnabled(False)
        self.progress.show()
        self.status.setText("Starting…")
        model = self.model.currentData()
        self.worker = SetupWorker(operation, model)
        self.worker.progress.connect(self.status.setText)
        self.worker.succeeded.connect(self.operation_succeeded)
        self.worker.failed.connect(self.operation_failed)
        self.worker.finished.connect(self.operation_finished)
        self.worker.start()

    def operation_succeeded(self, message: str) -> None:
        self.status.setText(message)
        self.model_button.setEnabled(check_ollama().available)

    def operation_failed(self, message: str) -> None:
        self.status.setText(f"Setup failed: {message}")
        QMessageBox.warning(self, "Computer setup", message)

    def operation_finished(self) -> None:
        self.progress.hide()
        self.runtime_button.setEnabled(True)
        self.model_button.setEnabled(check_ollama().available)


class ComputerWindow(QMainWindow):
    """Minimal LCARS-inspired desktop shell."""
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Computer")
        self.setMinimumSize(560, 360)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)

        root = QWidget()
        root.setObjectName("root")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        header = QLabel("COMPUTER")
        header.setObjectName("header")
        header.setFont(QFont("Sans Serif", 24, QFont.Weight.Bold))
        layout.addWidget(header)

        self.status = QLabel("SYSTEM INITIALIZING")
        self.status.setObjectName("status")
        self.status.setFont(QFont("Sans Serif", 13, QFont.Weight.DemiBold))
        layout.addWidget(self.status)

        self.detail = QLabel("Checking local AI runtime…")
        self.detail.setWordWrap(True)
        self.detail.setObjectName("detail")
        layout.addWidget(self.detail)

        self.activity = QProgressBar()
        self.activity.setRange(0, 100)
        self.activity.setValue(0)
        self.activity.setTextVisible(False)
        self.activity.setMaximumHeight(12)
        layout.addWidget(self.activity)

        self.setup_button = QPushButton("LOCAL AI SETUP")
        self.setup_button.clicked.connect(self.open_setup)
        layout.addWidget(self.setup_button)
        layout.addStretch(1)
        footer = QLabel("LOCAL-FIRST  •  VOICE INTERACTION IN DEVELOPMENT")
        footer.setObjectName("footer")
        layout.addWidget(footer)

        root.setStyleSheet("""
            QWidget#root { background: #11131c; border: 3px solid #f7a34b; border-radius: 18px; }
            QLabel#header { color: #ffcc66; letter-spacing: 3px; }
            QLabel#status { color: #f7a34b; }
            QLabel#detail { color: #f1e7d4; }
            QLabel#footer { color: #a8a2bd; font-size: 10px; letter-spacing: 1px; }
            QProgressBar { background: #292b3b; border: 0; border-radius: 5px; }
            QProgressBar::chunk { background: #cc79a7; border-radius: 5px; }
            QPushButton { background: #f7a34b; color: #171522; padding: 10px; border: 0; border-radius: 5px; }
        """)
        self.setCentralWidget(root)
        self.refresh_runtime_status()

    def open_setup(self) -> None:
        dialog = SetupDialog(self)
        dialog.exec()
        self.refresh_runtime_status()

    def refresh_runtime_status(self) -> None:
        result = check_ollama()
        if result.available:
            self.status.setText("LOCAL RUNTIME AVAILABLE")
            self.detail.setText(
                f"Ollama responded at {result.endpoint}"
                + (f" (version {result.version})." if result.version else ".")
                + " Use Local AI Setup to download a model."
            )
            self.activity.setValue(25)
        else:
            self.status.setText("LOCAL RUNTIME NOT DETECTED")
            self.detail.setText(
                f"{result.error or 'Ollama is unavailable.'} Select Local AI Setup to install "
                "Computer-managed runtime files and start the service."
            )
            self.activity.setValue(0)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        target_name = os.environ.get("LCARSAI_SCREEN", "").strip().lower()
        if not target_name:
            return
        app = QApplication.instance()
        if app is None:
            return
        target = next((s for s in app.screens() if target_name in s.name().lower()), None)
        if target is not None:
            self.move(target.availableGeometry().center() - self.rect().center())


def main() -> int:
    app = QApplication(sys.argv)
    window = ComputerWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
