"""Environment or independently configured Windows current-user encrypted access."""
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path


def _unlock(path):
    if os.name != "nt" or path.is_symlink() or path.stat().st_size > 16384:
        raise ValueError("Protected Hub credential store unavailable")
    record = json.loads(path.read_text(encoding="utf-8"))
    if set(record) != {"schema_version", "store_type", "application", "created_at", "ciphertext_sha256", "ciphertext_base64"} or record["schema_version"] != 1 or record["store_type"] != "WINDOWS_DPAPI_CURRENT_USER" or record["application"] not in {"openmontage/distribution-hub-access/v1", "media-pipeline-core/distribution-hub-access/v1"}:
        raise ValueError("Invalid protected Hub credential schema")
    # Historical entropy label is cryptographic provenance, not a runtime dependency.
    encrypted = base64.b64decode(record["ciphertext_base64"], validate=True)
    if hashlib.sha256(encrypted).hexdigest() != record["ciphertext_sha256"]:
        raise ValueError("Protected Hub credential checksum mismatch")
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    def blob(data):
        buffer = ctypes.create_string_buffer(data)
        return Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))), buffer
    source, source_buffer = blob(encrypted)
    entropy, entropy_buffer = blob(record["application"].encode("utf-8"))
    clear = Blob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    if not crypt32.CryptUnprotectData(ctypes.byref(source), None, ctypes.byref(entropy), None, None, 1, ctypes.byref(clear)):
        raise ValueError("Current user could not unlock Hub credential")
    try:
        value = json.loads(ctypes.string_at(clear.data, clear.size).decode("utf-8"))
    finally:
        ctypes.memset(clear.data, 0, clear.size)
        kernel32.LocalFree(clear.data)
    if not isinstance(value, dict) or set(value) != {"client_id", "client_secret"} or any(not isinstance(v, str) or not v or "\n" in v or "\r" in v for v in value.values()):
        raise ValueError("Invalid Hub credential fields")
    return value


def configured_client():
    from lib.distribution_hub import HubClient, HubError
    values = [os.environ.get(k, "") for k in ("DISTRIBUTION_HUB_ORIGIN", "DISTRIBUTION_HUB_CLIENT_ID", "DISTRIBUTION_HUB_CLIENT_SECRET")]
    if any(values):
        return HubClient(*values)
    path = Path(os.environ.get("DISTRIBUTION_HUB_CONFIG", str(Path.home() / ".codex/private/openmontage/hub-client.json")))
    try:
        if path.is_symlink() or path.stat().st_size > 4096:
            raise ValueError()
        config = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(config, dict) or set(config) != {"origin", "credentialStore"} or not isinstance(config["credentialStore"], str) or not Path(config["credentialStore"]).is_absolute():
            raise ValueError()
        # Validate the origin before accessing the protected store.
        HubClient(config["origin"], "configured", "configured")
        credentials = _unlock(Path(config["credentialStore"]))
        return HubClient(config["origin"], credentials["client_id"], credentials["client_secret"])
    except (OSError, ValueError, TypeError, KeyError):
        raise HubError("Independent Hub access configuration unavailable") from None
