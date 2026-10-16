"""
Tiny storage layer used by reports and alerts.

With SUPABASE_URL + SUPABASE_SERVICE_KEY set, rows live in your Supabase database
(shared by every visitor, survives restarts). Without them, rows go to JSON files in
~/.firewatch, which is fine on your own computer but is wiped whenever a free Render
instance restarts.
"""

import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import config

_lock = threading.Lock()
LOCAL_LIMIT = 3000        # rows kept per local table


class StoreError(Exception):
    pass


def data_dir():
    return Path(os.environ.get("FIREWATCH_DATA") or (Path.home() / ".firewatch"))


def backend():
    return "supabase" if (config.SUPABASE_URL and config.SUPABASE_KEY) else "local"


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Supabase (REST)
# ---------------------------------------------------------------------------

def _request(method, path, body=None, prefer=None, timeout=15):
    url = config.SUPABASE_URL.rstrip("/") + "/rest/v1/" + path
    headers = {
        "apikey": config.SUPABASE_KEY,
        "Authorization": "Bearer " + config.SUPABASE_KEY,
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:160]
        raise StoreError(f"database error {err.code}: {detail}") from None
    except (urllib.error.URLError, OSError) as err:
        raise StoreError(f"database unreachable: {err}") from None
    return json.loads(raw) if raw else None


# ---------------------------------------------------------------------------
# Local JSON fallback
# ---------------------------------------------------------------------------

def _path(table):
    return data_dir() / f"{table}.json"


def _read(table):
    try:
        rows = json.loads(_path(table).read_text(encoding="utf-8"))
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def _write(table, rows):
    try:
        path = _path(table)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows[-LOCAL_LIMIT:]), encoding="utf-8")
        tmp.replace(path)
    except OSError as err:
        raise StoreError(f"could not save {table}: {err}") from None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def insert(table, row):
    row = dict(row)
    row.setdefault("created_at", now_iso())
    if backend() == "supabase":
        _request("POST", table, row, prefer="return=minimal")
        return row
    with _lock:
        rows = _read(table)
        rows.append(row)
        _write(table, rows)
    return row


def upsert(table, row, key):
    """Insert, or replace the row that has the same `key` value."""
    row = dict(row)
    row.setdefault("created_at", now_iso())
    if backend() == "supabase":
        _request("POST", f"{table}?on_conflict={urllib.parse.quote(key)}", row,
                 prefer="resolution=merge-duplicates,return=minimal")
        return row
    with _lock:
        rows = [r for r in _read(table) if r.get(key) != row.get(key)]
        rows.append(row)
        _write(table, rows)
    return row


def delete(table, key, value):
    if backend() == "supabase":
        _request("DELETE", f"{table}?{urllib.parse.quote(key)}=eq.{urllib.parse.quote(str(value))}")
        return
    with _lock:
        rows = [r for r in _read(table) if r.get(key) != value]
        _write(table, rows)


def select(table, since=None, limit=1000):
    """Newest first. `since` is an ISO timestamp such as 2026-10-17T00:00:00Z."""
    if backend() == "supabase":
        query = f"{table}?select=*&order=created_at.desc&limit={int(limit)}"
        if since:
            query += "&created_at=gte." + urllib.parse.quote(since)
        return _request("GET", query) or []
    with _lock:
        rows = _read(table)
    if since:
        rows = [r for r in rows if str(r.get("created_at", "")) >= since]
    rows.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
    return rows[:limit]
