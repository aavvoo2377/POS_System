import hashlib
import hmac
import json
import os
import string
import subprocess
import uuid
from datetime import datetime, date, timedelta
import ctypes
from ctypes import windll

# ── HMAC signing key (split for basic obfuscation) ──────────
_KEY_A = b"P0S_L1c3ns3_K3y_A_2026"
_KEY_B = b"!@#$%^&*()_+S3cr3tP4rt"

def _hmac_key() -> bytes:
    return hashlib.sha256(_KEY_A + _KEY_B).digest()

def _sign(data: dict) -> str:
    return hmac.new(
        _hmac_key(),
        json.dumps(data, sort_keys=True, ensure_ascii=False).encode(),
        hashlib.sha256,
    ).hexdigest()

def _verify(data: dict, sig: str) -> bool:
    return hmac.compare_digest(_sign(data), sig)


# ── Machine fingerprint ─────────────────────────────────────
def get_machine_id() -> str:
    parts = []
    try:
        parts.append(os.environ.get("COMPUTERNAME", ""))
    except Exception:
        pass
    try:
        parts.append(hex(uuid.getnode()))
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            "cmd /c vol C:", shell=True, text=True, timeout=3
        )
        parts.append(out.strip())
    except Exception:
        pass
    try:
        buf = (ctypes.c_wchar * 256)()
        windll.kernel32.GetComputerNameW(buf, ctypes.pointer(ctypes.c_ulong(256)))
        parts.append(buf.value or "")
    except Exception:
        pass
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Paths ───────────────────────────────────────────────────
def _appdata_dir() -> str:
    d = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")), "POS_System"
    )
    os.makedirs(d, exist_ok=True)
    return d

def _activation_path() -> str:
    return os.path.join(_appdata_dir(), "activation.dat")

def _used_path() -> str:
    return os.path.join(_appdata_dir(), "used_licenses.dat")


# ── USB scanning ────────────────────────────────────────────
def list_removable_drives() -> list:
    try:
        import win32api, win32file
    except ImportError:
        return []
    drives = []
    raw = win32api.GetLogicalDriveStrings()
    for d in raw.rstrip("\x00").split("\x00"):
        if d and win32file.GetDriveType(d) == win32file.DRIVE_REMOVABLE:
            drives.append(d)
    return drives

def scan_license_file(filename="pos_license.lic") -> str | None:
    for drive in list_removable_drives():
        path = os.path.join(drive, filename)
        if os.path.isfile(path):
            return path
    return None

def read_license_file(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        sig = data.pop("signature", "")
        if not sig or not _verify(data, sig):
            return None
        return data
    except Exception:
        return None

def delete_license_file(path: str) -> bool:
    try:
        os.remove(path)
        return True
    except Exception:
        return False


# ── Used-license tracking (prevents re-use of same file) ───
def _get_used_set() -> set:
    p = _used_path()
    if not os.path.isfile(p):
        return set()
    try:
        with open(p, "r") as f:
            return set(json.load(f))
    except Exception:
        return set()

def _save_used_set(s: set) -> None:
    with open(_used_path(), "w") as f:
        json.dump(list(s), f)

def mark_used(license_id: str) -> None:
    s = _get_used_set()
    s.add(license_id)
    _save_used_set(s)

def is_used(license_id: str) -> bool:
    return license_id in _get_used_set()


# ── Activation (bound to machine) ───────────────────────────
def save_activation(license_data: dict) -> None:
    act = {
        "license_id": license_data["license_id"],
        "expires_at": license_data["expires_at"],
        "issued_to": license_data.get("issued_to", ""),
        "machine_id": get_machine_id(),
        "activated_at": datetime.now().isoformat(),
    }
    act["signature"] = _sign(act)
    with open(_activation_path(), "w", encoding="utf-8") as f:
        json.dump(act, f, ensure_ascii=False, indent=2)

def load_activation() -> dict | None:
    p = _activation_path()
    if not os.path.isfile(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        sig = data.pop("signature", "")
        if not sig or not _verify(data, sig):
            return None
        if data.get("machine_id") != get_machine_id():
            return None
        return data
    except Exception:
        return None


# ── Status helpers ──────────────────────────────────────────
def days_remaining(activation: dict) -> int:
    try:
        exp = datetime.fromisoformat(activation["expires_at"])
        delta = exp - datetime.now()
        return max(0, delta.days)
    except Exception:
        return 0

def is_expired(activation: dict) -> bool:
    return days_remaining(activation) == 0

def validate_date_str(s: str) -> bool:
    try:
        datetime.fromisoformat(s)
        return True
    except Exception:
        return False


# ── High-level activation flow ──────────────────────────────
ActivationStatus = str  # "active" | "expired" | "not_activated" | "wrong_machine"

def check_status() -> tuple[ActivationStatus, dict | None]:
    act = load_activation()
    if act is None:
        return ("not_activated", None)
    if "expires_at" not in act or not validate_date_str(act["expires_at"]):
        return ("corrupted", act)
    if is_expired(act):
        return ("expired", act)
    return ("active", act)


# ── Attempt activation from a license file path ─────────────
def activate_from_file(lic_path: str) -> tuple[bool, str]:
    lic = read_license_file(lic_path)
    if lic is None:
        return (False, "ملف الترخيص غير صالح أو تالف")
    if not validate_date_str(lic.get("expires_at", "")):
        return (False, "تاريخ الانتهاء في الملف غير صحيح")
    if is_used(lic["license_id"]):
        return (False, "ملف الترخيص مستخدم مسبقاً")
    save_activation(lic)
    mark_used(lic["license_id"])
    delete_license_file(lic_path)
    return (True, f"تم التفعيل بنجاح حتى {lic['expires_at']}")


# ── Renewal (add days to existing activation) ────────────────
def renew_activation(new_lic: dict) -> tuple[bool, str]:
    """Add the full duration from new_lic to the current activation."""
    act = load_activation()
    if act is None:
        return (False, "لا يوجد تفعيل سابق. استخدم التفعيل الأول بدلاً من التجديد.")

    # Use stored duration_days if available, else calculate remaining days
    extra_days = new_lic.get("duration_days")
    if extra_days is None:
        new_exp = datetime.fromisoformat(new_lic["expires_at"])
        now = datetime.now()
        extra_days = max(0, (new_exp - now).days)
    if extra_days <= 0:
        return (False, "ملف الترخيص الجديد منتهي الصلاحية")

    current_exp = datetime.fromisoformat(act["expires_at"])
    base = max(current_exp, datetime.now())
    final_expiry = base + timedelta(days=extra_days)

    license_data = {
        "license_id": new_lic["license_id"],
        "expires_at": final_expiry.isoformat(),
        "issued_to": new_lic.get("issued_to", act.get("issued_to", "")),
    }
    save_activation(license_data)
    mark_used(new_lic["license_id"])
    return (True, f"تم التجديد بنجاح حتى {final_expiry.strftime('%Y-%m-%d')}")


def renew_from_usb() -> tuple[bool, str]:
    """Scan USB for a license file and renew the current activation."""
    path = scan_license_file("pos_license.lic")
    if path is None:
        return (False, "لا يوجد ملف ترخيص على الفلاشة USB")
    lic = read_license_file(path)
    if lic is None:
        return (False, "ملف الترخيص غير صالح أو تالف")
    if not validate_date_str(lic.get("expires_at", "")):
        return (False, "تاريخ الانتهاء في الملف غير صحيح")
    if is_used(lic["license_id"]):
        try:
            os.remove(path)
        except OSError:
            pass
        return (False, "ملف الترخيص مستخدم مسبقاً")

    ok, msg = renew_activation(lic)
    if ok:
        delete_license_file(path)
    return (ok, msg)
