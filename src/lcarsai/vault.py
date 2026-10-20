"""Passphrase-encrypted local notes with an independent recovery key."""
from __future__ import annotations
import base64, json, os, secrets
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from lcarsai.runtime import app_data_dir

VAULT_FILE = app_data_dir() / "vault.enc"
KEYS_FILE = app_data_dir() / "vault.keys"

def _derive(secret: str, salt: bytes) -> bytes:
    key = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(secret.encode("utf-8"))
    return base64.urlsafe_b64encode(key)

class EncryptedVault:
    """Encrypted local notes; the recovery key is displayed once and is not stored."""
    def __init__(self):
        self._items: list[dict[str, str]] = []
        self._data_key: bytes | None = None

    @property
    def exists(self) -> bool:
        return VAULT_FILE.exists() and KEYS_FILE.exists()

    def create(self, passphrase: str) -> str:
        if len(passphrase) < 10:
            raise ValueError("Choose a passphrase at least 10 characters long.")
        if self.exists:
            raise RuntimeError("A vault already exists. Unlock it instead.")
        app_data_dir().mkdir(parents=True, exist_ok=True)
        recovery = secrets.token_urlsafe(32)
        data_key = Fernet.generate_key()
        pass_salt, recovery_salt = secrets.token_bytes(16), secrets.token_bytes(16)
        metadata = {
            "passphrase_salt": base64.b64encode(pass_salt).decode("ascii"),
            "recovery_salt": base64.b64encode(recovery_salt).decode("ascii"),
            "passphrase_wrap": Fernet(_derive(passphrase, pass_salt)).encrypt(data_key).decode("ascii"),
            "recovery_wrap": Fernet(_derive(recovery, recovery_salt)).encrypt(data_key).decode("ascii"),
        }
        KEYS_FILE.write_text(json.dumps(metadata), encoding="utf-8")
        VAULT_FILE.write_bytes(Fernet(data_key).encrypt(b"[]"))
        for path in (KEYS_FILE, VAULT_FILE):
            try: os.chmod(path, 0o600)
            except OSError: pass
        self._data_key, self._items = data_key, []
        return recovery

    def unlock(self, secret: str, recovery: bool = False) -> None:
        if not self.exists:
            raise RuntimeError("No encrypted vault exists yet.")
        metadata = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
        prefix = "recovery" if recovery else "passphrase"
        salt = base64.b64decode(metadata[f"{prefix}_salt"])
        wrapped = metadata[f"{prefix}_wrap"].encode("ascii")
        try:
            data_key = Fernet(_derive(secret, salt)).decrypt(wrapped)
            payload = Fernet(data_key).decrypt(VAULT_FILE.read_bytes())
            items = json.loads(payload.decode("utf-8"))
        except (InvalidToken, ValueError, UnicodeDecodeError, KeyError) as exc:
            raise RuntimeError("That passphrase or recovery key could not unlock the vault.") from exc
        self._data_key = data_key
        self._items = items if isinstance(items, list) else []

    def _save(self) -> None:
        if self._data_key is None: raise RuntimeError("Unlock the vault before saving.")
        VAULT_FILE.write_bytes(Fernet(self._data_key).encrypt(json.dumps(self._items).encode("utf-8")))

    def list_items(self) -> list[dict[str, str]]:
        return list(self._items)

    def add(self, title: str, note: str) -> None:
        if self._data_key is None: raise RuntimeError("Unlock the vault before saving.")
        if not title.strip() or not note.strip(): raise ValueError("Both a title and note are required.")
        self._items.append({"title": title.strip(), "note": note.strip()})
        self._save()

    def delete(self, index: int) -> None:
        if self._data_key is None: raise RuntimeError("Unlock the vault before saving.")
        del self._items[index]
        self._save()

    def lock(self) -> None:
        self._items = []
        self._data_key = None
