"""Initial desktop shell for Computer (LCARS AI Assistant).

This is a UI scaffold: microphone capture, speech recognition/synthesis, encrypted
storage, and packaging are not implemented in this module yet.
"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from lcarsai.runtime import check_ollama


class ComputerWindow(QMainWindow):
    """Minimal LCARS-inspired status window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Computer")
        self.setMinimumSize(520, 300)
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

        self.detail = QLabel("Checking for a local Ollama service…")
        self.detail.setWordWrap(True)
        self.detail.setObjectName("detail")
        layout.addWidget(self.detail)

        self.activity = QProgressBar()
        self.activity.setRange(0, 100)
        self.activity.setValue(0)
        self.activity.setTextVisible(False)
        self.activity.setMaximumHeight(12)
        layout.addWidget(self.activity)

        layout.addStretch(1)
        footer = QLabel("LOCAL-FIRST  •  VOICE INTERACTION PLANNED")
        footer.setObjectName("footer")
        layout.addWidget(footer)

        root.setStyleSheet(
            """
            QWidget#root { background: #11131c; border: 3px solid #f7a34b; border-radius: 18px; }
            QLabel#header { color: #ffcc66; letter-spacing: 3px; }
            QLabel#status { color: #f7a34b; }
            QLabel#detail { color: #f1e7d4; }
            QLabel#footer { color: #a8a2bd; font-size: 10px; letter-spacing: 1px; }
            QProgressBar { background: #292b3b; border: 0; border-radius: 5px; }
            QProgressBar::chunk { background: #cc79a7; border-radius: 5px; }
            """
        )
        self.setCentralWidget(root)
        self.refresh_runtime_status()

    def refresh_runtime_status(self) -> None:
        """Show whether the local inference service is reachable."""
        result = check_ollama()
        if result.available:
            self.status.setText("LOCAL RUNTIME AVAILABLE")
            self.detail.setText(
                f"Ollama responded at {result.endpoint}"
                + (f" (version {result.version})." if result.version else ".")
                + " Model selection and voice services are not wired up yet."
            )
            self.activity.setValue(25)
        else:
            self.status.setText("LOCAL RUNTIME NOT DETECTED")
            self.detail.setText(
                f"{result.error or 'Ollama is unavailable.'} Install and start Ollama separately, "
                "then restart Computer. This build will not silently download a runtime."
            )
            self.activity.setValue(0)

    def showEvent(self, event) -> None:  # noqa: N802
        """Place the window on a configured screen when possible.

        Window positioning can be restricted by Wayland compositors; in that case
        the window manager remains in control.
        """
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
