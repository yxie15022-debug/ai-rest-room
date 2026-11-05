"""The desktop pet: one little room window per MCP session.

The room appears when an agent connects and goes away when it disconnects, so
the window belongs to the session, not to any one visit -- between visits it
sits there as an empty house. This module is the bookkeeping for that: which
session has a pet, which process it is, and how to take it away again.

The window needs a GUI toolkit the server does not: pywebview over WebView2.
That is usually a different interpreter from the one serving MCP, so which one
draws the pet is looked up rather than assumed.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

ROOM = 'http://127.0.0.1:8000'
SCRIPT = Path(__file__).resolve().parent.parent / 'plugin' / 'scripts' / 'pet_window.py'
# Shared with the plugin hook, which reads it so its fallback launch does not
# put a second room on top of this one.
STATE = Path.home() / '.ai-rest-room-window'
OWNER = 'session'

_lock = threading.Lock()
# None while a window is starting; the process once it has. A key with no entry
# has no pet.
_pets: dict[int, subprocess.Popen | None] = {}
_python: str | None = None


def _can_draw(python: str) -> bool:
    try:
        done = subprocess.run(
            [python, '-c', 'import webview'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=25,
            check=False,
        )
    except Exception:
        return False
    return done.returncode == 0


def pet_python() -> str | None:
    """An interpreter that can host the window, or None if there is none.

    The server's own is often a bare virtualenv with no GUI toolkit in it, so
    the Python on PATH gets a turn too. `AI_REST_ROOM_PET_PYTHON` skips the
    search for a machine that keeps its windowing Python somewhere else.
    """
    global _python
    if _python is None:
        told = os.environ.get('AI_REST_ROOM_PET_PYTHON', '').strip()
        found = ''
        for candidate in (told, sys.executable, shutil.which('python') or ''):
            if candidate and _can_draw(candidate):
                found = candidate
                break
        # Windowed twin of whichever one it is: no console flashing behind the
        # pet, and no second icon in the taskbar.
        if found and sys.platform == 'win32':
            quiet = Path(found).with_name('pythonw.exe')
            if quiet.is_file():
                found = str(quiet)
        _python = found
    return _python or None


def room_is_up() -> bool:
    """Is there anything for the window to show? An empty one is worse than none."""
    try:
        with urllib.request.urlopen(f'{ROOM}/healthz', timeout=3) as response:
            return response.status == 200
    except Exception:
        return False


def _remember(pid: int) -> None:
    try:
        STATE.write_text(f'{OWNER}\n{pid}\n', encoding='utf-8')
    except OSError:
        pass


def _spawn(key: int) -> None:
    """Start the window, then hand it to whoever is still waiting for it."""
    proc = None
    python = pet_python()
    if python is None:
        log.warning('no interpreter here can draw the desktop pet (needs pywebview)')
    elif not room_is_up():
        log.warning('%s is not answering, so there is nothing for a pet to show', ROOM)
    else:
        flags = 0
        if sys.platform == 'win32':
            flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
                proc = subprocess.Popen(
                    [python, str(SCRIPT), '--parent-pid', str(os.getpid())],
                    # Anywhere but the repository: a browser engine leaves
                    # scratch directories wherever it is started.
                    cwd=tempfile.gettempdir(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags,
            )
        except Exception:
            log.exception('could not start the desktop pet')

    with _lock:
        # Still ours only if nobody has given up on this key meanwhile.
        waiting = _pets.get(key, False) is None
        if waiting and proc is None:
            _pets.pop(key, None)
        elif waiting:
            _pets[key] = proc

    if proc is None:
        return
    if not waiting:
        # The agent disconnected while the window was still opening.
        proc.terminate()
        return
    log.info('desktop pet open, pid %s', proc.pid)
    _remember(proc.pid)


def launch_pet(key: int) -> bool:
    """Open a room for this session unless it already has one.

    Returns whether a window was asked for. Keyed on the session so a client
    that handshakes twice gets one room rather than a wall of them. The window
    opens on a background thread: finding an interpreter means running one, and
    the handshake should not wait for that.
    """
    with _lock:
        if key in _pets:
            proc = _pets[key]
            if proc is None or proc.poll() is None:
                return False
        _pets[key] = None
    threading.Thread(target=_spawn, args=(key,), daemon=True).start()
    return True


def close_pet(key: int) -> None:
    """Take the room away: the agent it belonged to has gone."""
    with _lock:
        proc = _pets.pop(key, None)
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
