"""User-approved, user-space Ollama setup for Computer."""
from __future__ import annotations

import json
import os
import platform
import shutil
import ssl
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile

import truststore
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
LINUX_BUNDLE = "https://ollama.com/download/ollama-linux-amd64.tar.zst"
WINDOWS_BUNDLE = "https://ollama.com/download/ollama-windows-amd64.zip"


@dataclass(frozen=True)
class RuntimeStatus:
    available: bool
    endpoint: str
    version: str | None = None
    error: str | None = None


def app_data_dir() -> Path:
    override = os.environ.get("LCARSAI_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "ComputerAI"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "computerai"


def runtime_dir() -> Path:
    return app_data_dir() / "runtime" / "ollama"


def models_dir() -> Path:
    override = os.environ.get("LCARSAI_MODELS_DIR")
    return Path(override).expanduser() if override else app_data_dir() / "models"


def ollama_endpoint() -> str:
    return os.environ.get("LCARSAI_OLLAMA_URL", DEFAULT_OLLAMA_URL).rstrip("/")


def check_ollama(timeout: float = 1.5) -> RuntimeStatus:
    endpoint = ollama_endpoint()
    if not endpoint.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]")):
        return RuntimeStatus(False, endpoint, error="Non-local Ollama endpoints are blocked by default.")
    try:
        req = urllib.request.Request(f"{endpoint}/api/version")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return RuntimeStatus(True, endpoint, payload.get("version") if isinstance(payload, dict) else None)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return RuntimeStatus(False, endpoint, error=f"Ollama is not responding ({type(exc).__name__}).")


def find_ollama() -> Path | None:
    candidates = [shutil.which("ollama"), runtime_dir() / "ollama", runtime_dir() / "bin" / "ollama",
                  runtime_dir() / "ollama.exe", runtime_dir() / "bin" / "ollama.exe"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        candidate = local / "Programs/Ollama/ollama.exe"
        if candidate.is_file():
            return candidate
    return None


def _download(url: str, destination: Path, progress: Callable[[int, int], None] | None = None) -> None:
    """Download over HTTPS using the operating system's trusted certificate store."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "Computer-LCARS-AI/0.1"})
    try:
        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        with urllib.request.urlopen(request, timeout=60, context=context) as response, destination.open("wb") as out:
            total = int(response.headers.get("Content-Length", "0"))
            received = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                received += len(chunk)
                if progress:
                    progress(received, total)
    except urllib.error.URLError as exc:
        reason = exc.reason
        if isinstance(reason, (ssl.SSLCertVerificationError, ssl.SSLError)):
            raise RuntimeError(
                "Computer could not verify the HTTPS certificate for the official Ollama "
                "download. Update your operating system's CA certificates and try again. "
                "TLS certificate verification remains enabled."
            ) from exc
        raise RuntimeError(f"Secure runtime download failed: {exc}") from exc
    if destination.stat().st_size == 0:
        destination.unlink(missing_ok=True)
        raise RuntimeError("The runtime download was empty.")

def install_runtime(progress: Callable[[int, int], None] | None = None) -> Path:
    """Download official Ollama binaries into Computer's per-user data directory.

    No sudo, system package manager, or system service is invoked.
    """
    root = runtime_dir()
    root.mkdir(parents=True, exist_ok=True)
    system = platform.system()
    if system == "Windows":
        archive = root / "ollama-windows-amd64.zip"
        _download(WINDOWS_BUNDLE, archive, progress)
        staging = root / "extracting"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir()
        with zipfile.ZipFile(archive) as zf:
            for member in zf.infolist():
                target = (staging / member.filename).resolve()
                if not target.is_relative_to(staging.resolve()):
                    raise RuntimeError("Runtime archive contains an unsafe path.")
            zf.extractall(staging)
        binary = next(staging.rglob("ollama.exe"), None)
        if binary is None:
            raise RuntimeError("The official Windows archive did not contain ollama.exe.")
        for child in staging.iterdir():
            target = root / child.name
            if target.exists():
                shutil.rmtree(target) if target.is_dir() else target.unlink()
            shutil.move(str(child), str(target))
        shutil.rmtree(staging, ignore_errors=True)
        archive.unlink(missing_ok=True)
        result = next(root.rglob("ollama.exe"), None)
    elif system == "Linux":
        archive = root / "ollama-linux-amd64.tar.zst"
        _download(LINUX_BUNDLE, archive, progress)
        try:
            import zstandard
        except ImportError as exc:
            raise RuntimeError("Computer's setup component is missing zstandard; update the app.") from exc
        staging = root / "extracting"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir()
        with archive.open("rb") as source, zstandard.ZstdDecompressor().stream_reader(source) as reader:
            with tarfile.open(fileobj=reader, mode="r|") as tf:
                for member in tf:
                    target = (staging / member.name).resolve()
                    if not target.is_relative_to(staging.resolve()):
                        raise RuntimeError("Runtime archive contains an unsafe path.")
                    tf.extract(member, staging, filter="data")
        for child in staging.iterdir():
            target = root / child.name
            if target.exists():
                shutil.rmtree(target) if target.is_dir() else target.unlink()
            shutil.move(str(child), str(target))
        shutil.rmtree(staging, ignore_errors=True)
        archive.unlink(missing_ok=True)
        result = next((p for p in (root / "bin/ollama", root / "ollama") if p.is_file()), None)
        if result:
            result.chmod(result.stat().st_mode | 0o111)
    else:
        raise RuntimeError(f"Automatic runtime setup is not supported on {system} yet.")
    if result is None or not result.is_file():
        raise RuntimeError("Runtime download completed, but its executable was not found.")
    return result


def start_managed_runtime() -> subprocess.Popen:
    binary = find_ollama()
    if binary is None:
        binary = install_runtime()
    env = os.environ.copy()
    env["OLLAMA_HOST"] = "127.0.0.1:11434"
    env["OLLAMA_MODELS"] = str(models_dir())
    env.setdefault("OLLAMA_KEEP_ALIVE", "5m")
    if sys.platform == "linux":
        env.setdefault("OLLAMA_LIBRARY_PATH", str(runtime_dir() / "lib/ollama"))
    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
    return subprocess.Popen(
        [str(binary), "serve"],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=(sys.platform != "win32"),
        creationflags=creationflags,
    )


def stop_managed_runtime(process: subprocess.Popen | None, timeout: float = 3.0) -> None:
    """Stop only the Ollama process tree started and owned by this Computer session.

    A pre-existing Ollama service is never terminated by this function.
    """
    if process is None or process.poll() is not None:
        return

    try:
        process.terminate()
        process.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass
    except OSError:
        return

    try:
        if sys.platform == "win32":
            # Ollama can spawn runner processes; taskkill /T stops the owned process tree.
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=timeout,
            )
        else:
            # start_new_session=True makes the process PID its process-group ID.
            import signal
            import os

            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.TimeoutExpired):
        pass
    finally:
        try:
            process.wait(timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            pass


def pull_model(model: str, progress: Callable[[str], None] | None = None) -> None:
    """Pull a model from Ollama's model registry via the local API."""
    endpoint = ollama_endpoint()
    if not endpoint.startswith(("http://127.0.0.1", "http://localhost", "http://[::1]")):
        raise RuntimeError("Non-local Ollama endpoints are blocked by default.")
    payload = json.dumps({"name": model, "stream": True}).encode()
    req = urllib.request.Request(f"{endpoint}/api/pull", data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            for line in response:
                if not line.strip():
                    continue
                item = json.loads(line.decode("utf-8"))
                if progress:
                    status = item.get("status", "Working…")
                    total, done = item.get("total"), item.get("completed")
                    if isinstance(total, int) and total > 0 and isinstance(done, int):
                        status += f" ({done * 100 // total}%)"
                    progress(status)
                if item.get("error"):
                    raise RuntimeError(item["error"])
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Model download failed: {exc}") from exc
