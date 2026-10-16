"""
Local account storage for sign up / log in.

Accounts are kept in a JSON file in the user's home folder (~/.firewatch/users.json),
so they survive restarts and stay out of the project / OneDrive folder. Passwords are
never stored: only a random salt and a PBKDF2-SHA256 hash.

This is fine for a single-machine demo. For a real multi-user deployment, replace
this module with a proper backend (hosted database + auth provider).
"""

import hashlib
import hmac
import json
import os
import re
import secrets
from pathlib import Path

DATA_FILE = Path(os.environ.get("FIREWATCH_USERS", Path.home() / ".firewatch" / "users.json"))
ITERATIONS = 200_000
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^(\+27|0)\d{9}$")


# Browser mode (Vercel / flet build web): there is no real disk, so accounts live in the
# visitor's browser storage. main.py calls use_browser_storage() at startup.
_mem = None
_on_save = None


def use_browser_storage(raw, on_save):
    """raw: JSON string previously saved (or None). on_save(json_text) persists it."""
    global _mem, _on_save
    try:
        _mem = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        _mem = {}
    _on_save = on_save


def _load():
    if _mem is not None:
        return _mem
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(users):
    if _mem is not None:
        if users is not _mem:
            _mem.clear()
            _mem.update(users)
        if _on_save:
            _on_save(json.dumps(_mem))
        return
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(users, indent=2), encoding="utf-8")


def _pbkdf2(password, salt, iters):
    try:
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iters)
    except AttributeError:
        # Some in-browser Python builds lack hashlib.pbkdf2_hmac: do it with hmac instead.
        base = hmac.new(password.encode(), digestmod=hashlib.sha256)

        def prf(data):
            h = base.copy()
            h.update(data)
            return h.digest()

        u = prf(salt + b"\x00\x00\x00\x01")
        acc = int.from_bytes(u, "big")
        for _ in range(iters - 1):
            u = prf(u)
            acc ^= int.from_bytes(u, "big")
        return acc.to_bytes(32, "big")


def _hash(password, salt, iters=ITERATIONS):
    return _pbkdf2(password, bytes.fromhex(salt), iters).hex()


def _default_iters():
    # Full strength where the fast C version exists, lighter in the slow fallback.
    return ITERATIONS if hasattr(hashlib, "pbkdf2_hmac") else 20_000


def _public(user):
    return {k: v for k, v in user.items() if k not in ("salt", "hash", "iters")}


def clean_phone(phone):
    return re.sub(r"[\s\-()]", "", phone or "")


def valid_phone(phone):
    return bool(PHONE_RE.match(clean_phone(phone)))


ALERT_MODES = ('off', 'email', 'sms', 'both')


def register(name, email, phone, home_zone_id, password, consent, alerts='off'):
    """Returns (user, error). Exactly one of the two is None."""
    name, email = (name or "").strip(), (email or "").strip().lower()
    if len(name) < 2:
        return None, "Please enter your full name."
    if not EMAIL_RE.match(email):
        return None, "Enter a valid email address."
    if not valid_phone(phone):
        return None, "Enter a valid South African mobile number, e.g. 082 123 4567."
    if not home_zone_id:
        return None, "Choose your nearest town."
    if len(password or "") < 8:
        return None, "Password must be at least 8 characters."
    if not consent:
        return None, "Please accept the emergency data-sharing notice to continue."

    users = _load()
    if email in users:
        return None, "An account with this email already exists. Try logging in."
    salt = secrets.token_hex(16)
    iters = _default_iters()
    users[email] = {
        "name": name, "email": email, "phone": clean_phone(phone),
        "home_zone_id": home_zone_id, "consent": True,
        "alerts": alerts if alerts in ALERT_MODES else "off",
        "salt": salt, "iters": iters, "hash": _hash(password, salt, iters),
    }
    _save(users)
    return _public(users[email]), None


def login(email, password):
    email = (email or "").strip().lower()
    user = _load().get(email)
    # Same message for "no such user" and "wrong password" so emails can't be probed.
    if not user or not hmac.compare_digest(
        _hash(password or "", user["salt"], user.get("iters", ITERATIONS)), user["hash"]):
        return None, "Incorrect email or password."
    return _public(user), None


def update_profile(email, name, phone, home_zone_id, alerts=None):
    name = (name or "").strip()
    if len(name) < 2:
        return None, "Please enter your full name."
    if not valid_phone(phone):
        return None, "Enter a valid South African mobile number."
    users = _load()
    user = users.get(email)
    if not user:
        return None, "Account not found."
    user.update(name=name, phone=clean_phone(phone), home_zone_id=home_zone_id)
    if alerts in ALERT_MODES:
        user['alerts'] = alerts
    _save(users)
    return _public(user), None
