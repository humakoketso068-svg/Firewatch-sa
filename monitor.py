"""
Background worker (server only). It runs in its own thread for the life of the
process: every few minutes it downloads fresh NASA FIRMS data into the shared cache
and sends hometown alerts. Every visitor's session then just reads the cache, so ten
visitors cost one NASA request, not ten.
"""

import threading
import time
import traceback

import alerts
import config
import firms

_started = False
_start_lock = threading.Lock()


def _loop():
    while True:
        try:
            state = firms.refresh(force=True)
            if state["error"]:
                print("firms:", state["error"])
            alerts.check_and_notify(state["hotspots"])
        except Exception:
            traceback.print_exc()
        time.sleep(config.REFRESH_MIN * 60)


def start():
    """Safe to call from every session; only the first call starts the thread."""
    global _started
    if config.IN_BROWSER or not firms.available():
        return
    with _start_lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, name="firewatch-monitor", daemon=True).start()
