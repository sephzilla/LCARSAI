"""Computer: local, voice-first LCARS desktop assistant."""
from __future__ import annotations

import atexit
import os
import signal
import sys
import threading
import time

from PySide6.QtCore import QThread, Qt, QSettings, Signal, QTimer
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QHBoxLayout, QLabel, QMainWindow, QMenu,
    QMessageBox, QProgressBar, QPushButton, QSystemTrayIcon, QVBoxLayout, QWidget,
    QInputDialog, QListWidget, QLineEdit, QSlider, QCheckBox, QFormLayout,
)

from lcarsai.runtime import (
    app_data_dir, check_ollama, find_ollama, has_model, install_runtime, models_dir,
    pull_model, start_managed_runtime, stop_managed_runtime,
)
from lcarsai.assistant import LocalAssistant
from lcarsai.voice import record_until_stopped, transcribe_local, speak_local, wait_for_wake_word, list_local_voices, list_input_devices
from lcarsai.startup import set_startup_enabled
from lcarsai.web_lookup import search_web
from lcarsai.vault import EncryptedVault

_managed_process = None


def _shutdown_managed_runtime() -> None:
    global _managed_process
    process, _managed_process = _managed_process, None
    stop_managed_runtime(process)


def _handle_termination_signal(signum, _frame) -> None:
    _shutdown_managed_runtime()
    raise SystemExit(128 + signum)


atexit.register(_shutdown_managed_runtime)


class SetupWorker(QThread):
    progress = Signal(str)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, operation: str, model: str = ""):
        super().__init__()
        self.operation, self.model = operation, model

    def run(self):
        global _managed_process
        try:
            if self.operation == "runtime":
                if check_ollama(timeout=1).available:
                    self.succeeded.emit("Ollama is already running.")
                    return
                self.progress.emit("Installing the official local Ollama runtime…")
                binary = find_ollama() or install_runtime(lambda done, total: self.progress.emit(
                    f"Downloading Ollama runtime: {done // 1048576} MB"
                    + (f" / {total // 1048576} MB" if total else "")
                ))
                self.progress.emit("Starting local inference service…")
                _managed_process = start_managed_runtime()
                for attempt in range(60):
                    status = check_ollama(timeout=1)
                    if status.available:
                        self.succeeded.emit("Local runtime started.")
                        return
                    if _managed_process.poll() is not None:
                        raise RuntimeError(f"Ollama exited immediately after starting ({binary}).")
                    self.progress.emit(f"Waiting for Ollama… {attempt + 1}/60")
                    time.sleep(1)
                raise RuntimeError("Ollama did not become ready within 60 seconds.")
            elif self.operation == "model":
                if not check_ollama().available:
                    _managed_process = start_managed_runtime()
                    for _ in range(45):
                        if check_ollama(timeout=1).available:
                            break
                        time.sleep(1)
                    else:
                        raise RuntimeError("Ollama did not start.")
                pull_model(self.model, lambda message: self.progress.emit(message))
                if not has_model(self.model, timeout=10):
                    raise RuntimeError(f"Model {self.model} could not be verified after download.")
                self.succeeded.emit(f"Model {self.model} is installed.")
        except Exception as exc:
            self.failed.emit(str(exc))


class SetupDialog(QDialog):
    ready = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Computer — Local AI Setup")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        heading = QLabel("LOCAL AI CONFIGURATION")
        heading.setFont(QFont("Sans Serif", 16, QFont.Weight.Bold))
        layout.addWidget(heading)
        self.info = QLabel(
            f"Model storage: {models_dir()}\nRuntime storage: {app_data_dir() / 'runtime' / 'ollama'}\n"
            "Inference and speech recognition run locally. First-time downloads require internet."
        )
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        row = QHBoxLayout()
        row.addWidget(QLabel("Model"))
        self.model = QComboBox()
        self.model.addItem("Qwen3 8B — recommended", "qwen3:8b")
        self.model.addItem("Qwen3 4B — smaller", "qwen3:4b")
        self.model.addItem("Qwen3 14B — larger", "qwen3:14b")
        row.addWidget(self.model, 1)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel("Panel monitor"))
        self.monitor = QComboBox()
        for screen in QApplication.screens():
            self.monitor.addItem(screen.name(), screen.name())
        settings = QSettings("ComputerAI", "Computer")
        selected = settings.value("monitor", "")
        index = self.monitor.findData(selected)
        if index >= 0:
            self.monitor.setCurrentIndex(index)
        row.addWidget(self.monitor, 1)
        layout.addLayout(row)
        self.status = QLabel("Ready.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        self.runtime_button = QPushButton("Install / Start Ollama")
        self.runtime_button.clicked.connect(lambda: self.run_operation("runtime"))
        buttons.addWidget(self.runtime_button)
        self.model_button = QPushButton("Download Model")
        self.model_button.clicked.connect(lambda: self.run_operation("model"))
        buttons.addWidget(self.model_button)
        save = QPushButton("Save Preferences")
        save.clicked.connect(self.save_preferences)
        buttons.addWidget(save)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.worker = None
        self.setStyleSheet("""
            QDialog { background:#11131c; color:#f1e7d4; }
            QLabel { color:#f1e7d4; }
            QPushButton { background:#f7a34b; color:#171522; padding:9px; border:0; border-radius:5px; }
            QPushButton:disabled { background:#494653; color:#aaa; }
            QComboBox { padding:7px; }
            QProgressBar { min-height:10px; background:#292b3b; }
            QProgressBar::chunk { background:#cc79a7; }
        """)

    def save_preferences(self):
        settings = QSettings("ComputerAI", "Computer")
        settings.setValue("monitor", self.monitor.currentData() or "")
        self.status.setText("Preferences saved.")

    def run_operation(self, operation):
        if self.worker is not None and self.worker.isRunning():
            return
        self.save_preferences()
        self.runtime_button.setEnabled(False)
        self.model_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.worker = SetupWorker(operation, self.model.currentData())
        self.worker.progress.connect(self.status.setText)
        self.worker.succeeded.connect(lambda message: self.operation_succeeded(operation, message))
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def operation_succeeded(self, operation, message):
        if operation == "model":
            QSettings("ComputerAI", "Computer").setValue("model", self.model.currentData())
        self.status.setText(message)

    def failed(self, message):
        self.status.setText("Setup failed: " + message)
        QMessageBox.warning(self, "Computer setup", message)

    def finished(self):
        self.progress.hide()
        self.runtime_button.setEnabled(True)
        self.model_button.setEnabled(check_ollama().available)
        self.ready.emit()


class VoiceWorker(QThread):
    transcript = Signal(str)
    failed = Signal(str)

    def __init__(self, auto_stop=False, input_device=-1):
        super().__init__()
        self.stop_event = threading.Event()
        self.auto_stop = auto_stop
        self.input_device = input_device

    def stop_recording(self):
        self.stop_event.set()

    def run(self):
        try:
            self.transcript.emit("Listening… speak naturally, then press STOP LISTENING.")
            audio = record_until_stopped(
                self.stop_event, auto_stop=self.auto_stop,
                preferred_device=None if self.input_device < 0 else self.input_device,
            )
            self.transcript.emit("Transcribing locally…")
            text = transcribe_local(audio)
            self.transcript.emit(text)
        except Exception as exc:
            self.failed.emit(str(exc))


class WakeWordWorker(QThread):
    activated = Signal()
    failed = Signal(str)

    def __init__(self, input_device=-1):
        super().__init__()
        self.stop_event = threading.Event()
        self.input_device = input_device

    def stop_listening(self):
        self.stop_event.set()

    def run(self):
        try:
            wait_for_wake_word(
                self.stop_event, "computer",
                None if self.input_device < 0 else self.input_device,
            )
            if not self.stop_event.is_set():
                self.activated.emit()
        except Exception as exc:
            if not self.stop_event.is_set():
                self.failed.emit(str(exc))


class ResponseWorker(QThread):
    response = Signal(str)
    failed = Signal(str)

    def __init__(self, assistant: LocalAssistant, prompt: str):
        super().__init__()
        self.assistant, self.prompt = assistant, prompt

    def run(self):
        try:
            prompt = self.prompt
            lower = prompt.lower().strip()
            trigger = next((phrase for phrase in (
                "search the web for ", "look up online ", "search online for ",
                "look that up on the web ",
            ) if lower.startswith(phrase)), None)
            if trigger:
                query = prompt[len(trigger):].strip()
                results = search_web(query, limit=5)
                if not results:
                    prompt = f"The user asked for a web search for {query!r}, but no results were returned. Explain that."
                else:
                    material = "\n".join(
                        f"- {r['title']} — {r['snippet']} ({r['url']})" for r in results
                    )
                    prompt = (
                        f"The user explicitly requested a web search for: {query}\n"
                        "Summarize these search results cautiously. Mention that results may need verification.\n"
                        + material
                    )
            self.response.emit(self.assistant.respond(prompt))
        except Exception as exc:
            self.failed.emit(str(exc))


class SpeechWorker(QThread):
    failed = Signal(str)

    def __init__(self, text: str, voice_id: str = "", rate: int = 178, volume: float = 1.0):
        super().__init__()
        self.text = text
        self.voice_id, self.rate, self.volume = voice_id, rate, volume

    def run(self):
        try:
            speak_local(self.text, self.voice_id, self.rate, self.volume)
        except Exception as exc:
            self.failed.emit(str(exc))


class VaultDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Computer — Encrypted Personal Vault")
        self.vault = EncryptedVault()
        layout = QVBoxLayout(self)
        self.status = QLabel("Notes are encrypted at rest. The vault is optional.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.items = QListWidget()
        layout.addWidget(self.items)
        buttons = QHBoxLayout()
        for label, fn in (
            ("Create / Unlock", self.unlock),
            ("Unlock with Recovery Key", self.unlock_recovery),
            ("Add Note", self.add_note),
            ("Delete Selected", self.delete_note),
            ("Lock", self.lock),
        ):
            button = QPushButton(label)
            button.clicked.connect(fn)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        layout.addWidget(close)
        self.setStyleSheet("QDialog{background:#11131c;color:#f1e7d4} QLabel{color:#f1e7d4} QPushButton{background:#f7a34b;padding:8px}")

    def unlock(self):
        if self.vault.exists:
            secret, ok = QInputDialog.getText(self, "Unlock vault", "Passphrase:", QLineEdit.EchoMode.Password)
            if not ok:
                return
            try:
                self.vault.unlock(secret)
            except Exception as exc:
                QMessageBox.warning(self, "Vault", str(exc))
                return
        else:
            secret, ok = QInputDialog.getText(self, "Create vault", "New passphrase (10+ characters):", QLineEdit.EchoMode.Password)
            if not ok:
                return
            try:
                recovery = self.vault.create(secret)
            except Exception as exc:
                QMessageBox.warning(self, "Vault", str(exc))
                return
            QMessageBox.information(
                self, "Save your recovery key",
                "Store this recovery key somewhere safe, outside this computer. It is shown only now:\n\n" + recovery
            )
        self.refresh()

    def unlock_recovery(self):
        secret, ok = QInputDialog.getText(self, "Recover vault", "Recovery key:", QLineEdit.EchoMode.Password)
        if not ok:
            return
        try:
            self.vault.unlock(secret, recovery=True)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Vault", str(exc))

    def refresh(self):
        self.items.clear()
        for item in self.vault.list_items():
            self.items.addItem(item["title"] + " — " + item["note"])
        self.status.setText("Vault unlocked." if self.vault._secret else "Vault locked.")

    def add_note(self):
        if not self.vault._secret:
            QMessageBox.information(self, "Vault", "Unlock the vault first.")
            return
        title, ok = QInputDialog.getText(self, "New note", "Title:")
        if not ok:
            return
        note, ok = QInputDialog.getMultiLineText(self, "New note", "Note:")
        if not ok:
            return
        try:
            self.vault.add(title, note)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Vault", str(exc))

    def delete_note(self):
        if not self.vault._secret:
            return
        index = self.items.currentRow()
        if index >= 0:
            self.vault.delete(index)
            self.refresh()

    def lock(self):
        self.vault.lock()
        self.refresh()


class SettingsDialog(QDialog):
    saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Computer — Preferences")
        self.setMinimumWidth(540)
        self.settings = QSettings("ComputerAI", "Computer")
        root = QVBoxLayout(self)
        title = QLabel("COMPUTER SYSTEM PREFERENCES")
        title.setFont(QFont("Sans Serif", 16, QFont.Weight.Bold))
        root.addWidget(title)
        form = QFormLayout()
        self.monitor = QComboBox()
        for screen in QApplication.screens():
            self.monitor.addItem(f"{screen.name()} — {screen.geometry().width()}×{screen.geometry().height()}", screen.name())
        saved_monitor = str(self.settings.value("monitor", "") or "")
        index = self.monitor.findData(saved_monitor)
        if index >= 0:
            self.monitor.setCurrentIndex(index)
        form.addRow("Panel monitor", self.monitor)

        self.microphone = QComboBox()
        self.microphone.addItem("System default / automatic fallback", -1)
        try:
            for device in list_input_devices():
                self.microphone.addItem(f'{device["name"]} ({device["hostapi"]})', device["index"])
        except Exception:
            pass
        saved_device = int(self.settings.value("inputDevice", -1))
        mic_index = self.microphone.findData(saved_device)
        if mic_index >= 0:
            self.microphone.setCurrentIndex(mic_index)
        form.addRow("Microphone input", self.microphone)

        self.scale = QSlider(Qt.Orientation.Horizontal)
        self.scale.setRange(70, 150)
        self.scale.setSingleStep(5)
        self.scale.setValue(int(self.settings.value("uiScale", 100)))
        self.scale_label = QLabel(f"{self.scale.value()}%")
        self.scale.valueChanged.connect(lambda value: self.scale_label.setText(f"{value}%"))
        scale_row = QHBoxLayout()
        scale_row.addWidget(self.scale, 1)
        scale_row.addWidget(self.scale_label)
        form.addRow("Interface scale / size", scale_row)

        self.voice = QComboBox()
        voices = list_local_voices()
        self.voice.addItem("System default", "")
        for item in voices:
            self.voice.addItem(item["name"], item["id"])
        saved_voice = str(self.settings.value("voiceId", "") or "")
        voice_index = self.voice.findData(saved_voice)
        if voice_index >= 0:
            self.voice.setCurrentIndex(voice_index)
        form.addRow("Speech voice", self.voice)

        self.rate = QSlider(Qt.Orientation.Horizontal)
        self.rate.setRange(120, 240)
        self.rate.setSingleStep(5)
        self.rate.setValue(int(self.settings.value("voiceRate", 178)))
        self.rate_label = QLabel(f"{self.rate.value()} wpm-ish")
        self.rate.valueChanged.connect(lambda value: self.rate_label.setText(f"{value}"))
        rate_row = QHBoxLayout()
        rate_row.addWidget(self.rate, 1)
        rate_row.addWidget(self.rate_label)
        form.addRow("Speech rate", rate_row)

        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(int(float(self.settings.value("voiceVolume", 1.0)) * 100))
        self.volume_label = QLabel(f"{self.volume.value()}%")
        self.volume.valueChanged.connect(lambda value: self.volume_label.setText(f"{value}%"))
        volume_row = QHBoxLayout()
        volume_row.addWidget(self.volume, 1)
        volume_row.addWidget(self.volume_label)
        form.addRow("Speech volume", volume_row)

        self.autostart = QCheckBox("Start Computer automatically when I log in")
        self.autostart.setChecked(str(self.settings.value("autoStart", "false")).lower() in ("true", "1", "yes"))
        form.addRow("Startup", self.autostart)
        root.addLayout(form)
        self.note = QLabel("Voice choices depend on speech voices installed in your operating system.")
        self.note.setWordWrap(True)
        root.addWidget(self.note)
        buttons = QHBoxLayout()
        save = QPushButton("SAVE PREFERENCES")
        save.clicked.connect(self.save_preferences)
        buttons.addWidget(save)
        test = QPushButton("TEST VOICE")
        test.clicked.connect(self.test_voice)
        buttons.addWidget(test)
        close = QPushButton("CLOSE")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)
        self.setStyleSheet("""
            QDialog { background:#11131c; color:#f1e7d4; }
            QLabel { color:#f1e7d4; }
            QPushButton { background:#f7a34b; color:#171522; padding:9px; border:0; border-radius:5px; }
            QComboBox { padding:7px; }
            QSlider::groove:horizontal { height:6px; background:#494653; }
            QSlider::handle:horizontal { background:#cc79a7; width:16px; margin:-6px 0; border-radius:8px; }
        """)

    def save_preferences(self):
        self.settings.setValue("monitor", self.monitor.currentData() or "")
        self.settings.setValue("inputDevice", int(self.microphone.currentData()))
        self.settings.setValue("uiScale", self.scale.value())
        self.settings.setValue("voiceId", self.voice.currentData() or "")
        self.settings.setValue("voiceRate", self.rate.value())
        self.settings.setValue("voiceVolume", self.volume.value() / 100.0)
        self.settings.setValue("autoStart", self.autostart.isChecked())
        try:
            set_startup_enabled(self.autostart.isChecked())
            self.note.setText("Preferences saved.")
        except Exception as exc:
            self.note.setText(f"Preferences saved, but login startup could not be changed: {exc}")
        self.saved.emit()

    def test_voice(self):
        try:
            speak_local(
                "Computer voice systems are operational.",
                str(self.voice.currentData() or ""),
                self.rate.value(),
                self.volume.value() / 100.0,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Voice test", str(exc))


class ComputerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Computer")
        self.setMinimumSize(600, 480)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.settings = QSettings("ComputerAI", "Computer")
        self.assistant = LocalAssistant(str(self.settings.value("model", "qwen3:8b")))
        self._last_monitor = str(self.settings.value("monitor", "") or "")
        self.voice_worker = None
        self.wake_worker = None
        self.response_worker = None
        self.speech_worker = None
        self._wake_error_shown = False
        self._drag_offset = None
        self._hide_after_response = False

        root = QWidget()
        root.setObjectName("root")
        shell = QHBoxLayout(root)
        shell.setContentsMargins(12, 12, 12, 12)
        shell.setSpacing(12)

        rail = QVBoxLayout()
        rail.setSpacing(7)
        rail_top = QLabel("LCARS")
        rail_top.setObjectName("railTop")
        rail_top.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rail_top.setFixedSize(112, 64)
        rail.addWidget(rail_top)
        for text, color, height in (
            ("SYSTEM", "#cc79a7", 46), ("VOICE", "#f7a34b", 68),
            ("LOCAL AI", "#ffcc66", 52), ("MEMORY", "#9b8ac4", 58),
            ("STATUS", "#cc79a7", 44),
        ):
            segment = QLabel(text)
            segment.setObjectName("railSegment")
            segment.setAlignment(Qt.AlignmentFlag.AlignCenter)
            segment.setFixedSize(112, height)
            segment.setStyleSheet(
                f"background:{color}; color:#171522; border-radius:17px; "
                "font-size:10px; font-weight:900; letter-spacing:1px;"
            )
            rail.addWidget(segment)
        rail.addStretch()
        rail_bottom = QLabel("NCC-1701-D")
        rail_bottom.setObjectName("railBottom")
        rail_bottom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rail.addWidget(rail_bottom)
        shell.addLayout(rail)

        content = QWidget()
        content.setObjectName("content")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(10)
        top = QHBoxLayout()
        header = QLabel("COMPUTER")
        header.setObjectName("header")
        header.setFont(QFont("Sans Serif", 26, QFont.Weight.Black))
        top.addWidget(header)
        subhead = QLabel("PERSONAL OPERATIONS SYSTEM")
        subhead.setObjectName("subhead")
        top.addWidget(subhead)
        top.addStretch()
        self.close_button = QPushButton("×")
        self.close_button.setFixedWidth(38)
        self.close_button.clicked.connect(self.hide)
        top.addWidget(self.close_button)
        layout.addLayout(top)
        divider = QWidget()
        divider.setFixedHeight(7)
        divider.setStyleSheet("background:#f7a34b; border-radius:3px;")
        layout.addWidget(divider)

        self.status = QLabel("SYSTEM INITIALIZING")
        self.status.setObjectName("status")
        self.status.setFont(QFont("Sans Serif", 13, QFont.Weight.DemiBold))
        layout.addWidget(self.status)
        self.detail = QLabel("Preparing local voice interface…")
        self.detail.setObjectName("detail")
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)
        self.wave = QLabel("◖  ◗  ◖  ◗  ◖  ◗  ◖")
        self.wave.setObjectName("wave")
        self.wave.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.wave.setFont(QFont("Sans Serif", 28, QFont.Weight.Bold))
        layout.addWidget(self.wave)
        self.conversation = QLabel("VOICE-ONLY INTERFACE\nPress LISTEN and speak. No cloud transcription.")
        self.conversation.setObjectName("conversation")
        self.conversation.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.conversation.setWordWrap(True)
        self.conversation.setMinimumHeight(110)
        layout.addWidget(self.conversation)
        self.activity = QProgressBar()
        self.activity.setRange(0, 100)
        self.activity.setValue(0)
        self.activity.setTextVisible(False)
        self.activity.setMaximumHeight(12)
        layout.addWidget(self.activity)

        controls = QHBoxLayout()
        self.listen_button = QPushButton("◉  LISTEN")
        self.listen_button.clicked.connect(self.toggle_listening)
        controls.addWidget(self.listen_button, 2)
        self.setup_button = QPushButton("LOCAL AI SETUP")
        self.setup_button.clicked.connect(self.open_setup)
        controls.addWidget(self.setup_button)
        self.vault_button = QPushButton("PERSONAL VAULT")
        self.vault_button.clicked.connect(self.open_vault)
        controls.addWidget(self.vault_button)
        self.preferences_button = QPushButton("PREFERENCES")
        self.preferences_button.clicked.connect(self.open_preferences)
        controls.addWidget(self.preferences_button)
        layout.addLayout(controls)
        footer = QLabel("LOCAL-FIRST  •  VOICE INPUT • LOCAL MODEL • SYSTEM SPEECH")
        footer.setObjectName("footer")
        layout.addWidget(footer)

        root.setStyleSheet("""
            QWidget#root { background:#080b18; border:0; }
            QWidget#content { background:#111626; border:0; }
            QLabel#railTop { background:#f7a34b; color:#111626; border-radius:28px 8px 8px 8px; font-size:17px; font-weight:900; letter-spacing:2px; }
            QLabel#railBottom { color:#9b8ac4; font-size:9px; font-weight:bold; }
            QLabel#header { color:#ffcc66; letter-spacing:4px; }
            QLabel#subhead { color:#9b8ac4; font-size:9px; letter-spacing:1px; padding-left:12px; }
            QLabel#status { color:#f7a34b; background:#20253a; border-left:8px solid #cc79a7; padding:9px 12px; font-size:13px; letter-spacing:1px; }
            QLabel#detail { color:#f1e7d4; padding:2px 8px; }
            QLabel#wave { color:#cc79a7; background:#20253a; padding:10px; border-radius:20px; }
            QLabel#conversation { color:#f1e7d4; background:#171d30; border:2px solid #6d6489; border-radius:18px; padding:15px; }
            QLabel#footer { color:#9b8ac4; font-size:9px; letter-spacing:1px; }
            QPushButton { background:#f7a34b; color:#171522; padding:10px; border:0; border-radius:15px 5px 15px 5px; font-weight:900; }
            QPushButton:disabled { background:#494653; color:#aaa; }
            QProgressBar { background:#292b3b; border:0; border-radius:5px; }
            QProgressBar::chunk { background:#cc79a7; border-radius:5px; }
        """)
        shell.addWidget(content, 1)
        self.setCentralWidget(root)
        self.apply_preferences(initial=True)
        self._create_tray()
        self.refresh_runtime_status()
        self.start_runtime_on_launch()
        QTimer.singleShot(1200, self.position_on_selected_screen)
        QTimer.singleShot(2500, self.start_wake_word_listener)

    def _create_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip("Computer — local voice assistant")
        menu = QMenu()
        show_action = QAction("Show Computer", self)
        show_action.triggered.connect(self.show_and_raise)
        menu.addAction(show_action)
        hide_action = QAction("Hide Computer", self)
        hide_action.triggered.connect(self.hide)
        menu.addAction(hide_action)
        menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.instance().quit)
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_and_raise() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def show_and_raise(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def position_on_selected_screen(self):
        name = str(self.settings.value("monitor", "") or "")
        screen = next((s for s in QApplication.screens() if s.name() == name), None)
        if screen is None:
            screen = QApplication.primaryScreen()
        if self.settings.value("positionSaved", False):
            self.move(int(self.settings.value("x", 100)), int(self.settings.value("y", 100)))
        elif screen:
            self.move(screen.availableGeometry().center() - self.rect().center())

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.isVisible():
            self.settings.setValue("x", self.x())
            self.settings.setValue("y", self.y())
            self.settings.setValue("positionSaved", True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_offset = None

    def refresh_runtime_status(self):
        result = check_ollama()
        if not result.available:
            self.status.setText("LOCAL RUNTIME NOT DETECTED")
            self.detail.setText("Open LOCAL AI SETUP to install or start Ollama.")
            self.listen_button.setEnabled(False)
            self.activity.setValue(0)
            return
        try:
            selected_model = str(self.settings.value("model", "qwen3:8b"))
            self.assistant.model = selected_model
            ready = has_model(selected_model, timeout=3)
        except RuntimeError as exc:
            self.status.setText("LOCAL MODEL CHECK FAILED")
            self.detail.setText(str(exc))
            self.listen_button.setEnabled(False)
            return
        if ready:
            self.status.setText("COMPUTER ONLINE")
            self.detail.setText(f"{selected_model} is installed. Press LISTEN to speak.")
            self.listen_button.setEnabled(True)
            self.activity.setValue(100)
            QTimer.singleShot(900, self.start_wake_word_listener)
        else:
            self.status.setText("MODEL REQUIRED")
            self.detail.setText("Open LOCAL AI SETUP and download qwen3:8b, or choose a smaller model.")
            self.listen_button.setEnabled(False)
            self.activity.setValue(0)

    def start_runtime_on_launch(self):
        if check_ollama().available or find_ollama() is None:
            return
        self.status.setText("STARTING LOCAL RUNTIME")
        self.detail.setText("Starting Computer's managed Ollama runtime…")
        self._startup_worker = SetupWorker("runtime")
        self._startup_worker.progress.connect(self.detail.setText)
        self._startup_worker.succeeded.connect(lambda _: self.refresh_runtime_status())
        self._startup_worker.failed.connect(lambda msg: self.runtime_failed(msg))
        self._startup_worker.start()

    def runtime_failed(self, message):
        self.status.setText("LOCAL RUNTIME FAILED")
        self.detail.setText(message + " Open LOCAL AI SETUP to retry.")

    def stop_wake_word_listener(self):
        worker = self.wake_worker
        self.wake_worker = None
        if worker is not None and worker.isRunning():
            worker.stop_listening()
            worker.wait(1200)

    def start_wake_word_listener(self):
        if self.voice_worker is not None and self.voice_worker.isRunning():
            return
        if self.wake_worker is not None and self.wake_worker.isRunning():
            return
        if not self.listen_button.isEnabled():
            return
        self.wake_worker = WakeWordWorker(int(self.settings.value("inputDevice", -1)))
        self.wake_worker.activated.connect(self.wake_word_detected)
        self.wake_worker.failed.connect(self.wake_word_failed)
        self.wake_worker.start()
        self.status.setText("WAKE WORD ARMED")
        self.detail.setText('Say “Computer” followed by your request. Wake detection runs locally.')

    def wake_word_detected(self):
        self.wake_worker = None
        self.show_and_raise()
        self.status.setText("COMPUTER HEARD YOU")
        self.conversation.setText("LISTENING FOR YOUR REQUEST…")
        self.begin_voice_capture(auto_stop=True)

    def wake_word_failed(self, message):
        self.wake_worker = None
        self.status.setText("WAKE WORD UNAVAILABLE")
        self.detail.setText(message + " Use LISTEN manually while this is being fixed.")
        self._wake_error_shown = True
        QTimer.singleShot(5000, self.start_wake_word_listener)

    def begin_voice_capture(self, auto_stop=False):
        self.stop_wake_word_listener()
        self.voice_worker = VoiceWorker(
            auto_stop=auto_stop, input_device=int(self.settings.value("inputDevice", -1))
        )
        self.voice_worker.transcript.connect(self.voice_progress)
        self.voice_worker.failed.connect(self.voice_failed)
        self.voice_worker.finished.connect(self.voice_finished)
        self.listen_button.setText("■  STOP LISTENING")
        self.status.setText("LISTENING")
        self.wave.setText("◖  ◖ ◗ ◖ ◗ ◖  ◗")
        self.activity.setRange(0, 0)
        self.voice_worker.start()

    def toggle_listening(self):
        if self.voice_worker is not None and self.voice_worker.isRunning():
            self.voice_worker.stop_recording()
            self.listen_button.setEnabled(False)
            self.detail.setText("Finishing recording…")
            return
        self.begin_voice_capture(auto_stop=False)

    def voice_progress(self, text):
        if text.startswith("Listening"):
            self.detail.setText("Microphone active. Press STOP LISTENING when you finish.")
            return
        if text == "Transcribing locally…":
            self.status.setText("PROCESSING SPEECH")
            self.detail.setText(text)
            return
        self.conversation.setText("YOU SAID\n" + text)
        self.detail.setText("Generating a local response…")
        self.status.setText("COMPUTING")
        self.activity.setRange(0, 0)
        self.response_worker = ResponseWorker(self.assistant, text)
        self.response_worker.response.connect(self.responded)
        self.response_worker.failed.connect(self.response_failed)
        self.response_worker.start()

    def voice_failed(self, message):
        self.status.setText("VOICE INPUT UNAVAILABLE")
        self.detail.setText(message)
        self.conversation.setText("Press LISTEN to try again.")
        self.activity.setRange(0, 100)

    def voice_finished(self):
        self.listen_button.setEnabled(True)
        self.listen_button.setText("◉  LISTEN")
        self.wave.setText("◖  ◗  ◖  ◗  ◖  ◗  ◖")
        self.activity.setRange(0, 100)
        QTimer.singleShot(1200, self.restart_wake_word_if_idle)

    def restart_wake_word_if_idle(self):
        response_busy = self.response_worker is not None and self.response_worker.isRunning()
        speech_busy = self.speech_worker is not None and self.speech_worker.isRunning()
        if not response_busy and not speech_busy:
            self.start_wake_word_listener()

    def responded(self, answer):
        self.conversation.setText("COMPUTER\n" + answer)
        self.status.setText("SPEAKING")
        self.detail.setText("Response generated locally.")
        self.activity.setValue(100)
        self.speech_worker = SpeechWorker(
            answer,
            str(self.settings.value("voiceId", "") or ""),
            int(self.settings.value("voiceRate", 178)),
            float(self.settings.value("voiceVolume", 1.0)),
        )
        self.speech_worker.failed.connect(lambda msg: self.detail.setText(msg))
        self.speech_worker.finished.connect(self.speech_finished)
        self.speech_worker.start()

    def response_failed(self, message):
        self.status.setText("RESPONSE FAILED")
        self.detail.setText(message)
        self.conversation.setText("I couldn't complete that request. Please try again.")
        self.activity.setRange(0, 100)
        QTimer.singleShot(1200, self.start_wake_word_listener)

    def speech_finished(self):
        self.status.setText("COMPUTER ONLINE")
        self.detail.setText("Ready for your next request.")
        self.listen_button.setEnabled(True)
        self.activity.setRange(0, 100)
        self.activity.setValue(100)
        QTimer.singleShot(7000, self.hide_after_response)
        QTimer.singleShot(8000, self.start_wake_word_listener)

    def hide_after_response(self):
        if self.isVisible() and not (self.voice_worker and self.voice_worker.isRunning()):
            self.hide()

    def apply_preferences(self, initial=False):
        scale = max(0.70, min(1.50, int(self.settings.value("uiScale", 100)) / 100.0))
        app = QApplication.instance()
        if app is not None:
            font = app.font()
            font.setPointSizeF(max(8.0, 10.0 * scale))
            app.setFont(font)
        target = self.size()
        if initial or target.width() < 600:
            self.resize(round(980 * scale), round(600 * scale))
        else:
            self.resize(round(980 * scale), round(600 * scale))
        monitor = str(self.settings.value("monitor", "") or "")
        if monitor != self._last_monitor:
            screen = next((s for s in QApplication.screens() if s.name() == monitor), None)
            if screen is not None:
                self.move(screen.availableGeometry().center() - self.rect().center())
            self._last_monitor = monitor

    def open_preferences(self):
        dialog = SettingsDialog(self)
        dialog.saved.connect(self.apply_preferences)
        dialog.exec()
        self.apply_preferences()

    def open_setup(self):
        dialog = SetupDialog(self)
        dialog.ready.connect(self.refresh_runtime_status)
        dialog.exec()
        self.refresh_runtime_status()

    def open_vault(self):
        dialog = VaultDialog(self)
        dialog.exec()


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.aboutToQuit.connect(_shutdown_managed_runtime)
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, _handle_termination_signal)
    window = ComputerWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
