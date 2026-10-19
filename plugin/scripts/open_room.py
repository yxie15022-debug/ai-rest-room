"""Open the custom scene window once per visit (not the system browser)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

TICKET = re.compile(r'[0-9A-HJKMNP-TV-Z]{4}-[0-9A-HJKMNP-TV-Z]{4}', re.IGNORECASE)
ROOM = re.compile(r'https?://[^\s"\\]+/r/(' + TICKET.pattern + r')', re.IGNORECASE)
STATE = Path.home() / '.ai-rest-room-window'
LOG = Path.home() / '.ai-rest-room-hook.log'
LOCAL_STATE = 'http://127.0.0.1:8000/now/state'
SCRIPT_DIR = Path(__file__).resolve().parent
SCENE_WINDOW = SCRIPT_DIR / 'scene_window.py'


def log(line: str) -> None:
    try:
        with LOG.open('a', encoding='utf-8') as handle:
            handle.write(line + '\n')
    except OSError:
        pass


def ticket_from(text: str) -> str | None:
    found = ROOM.search(text)
    if found:
        return found.group(1).upper()
    ticket = TICKET.search(text)
    if ticket:
        return ticket.group(0).upper()
    return None


def ticket_from_server() -> str | None:
    try:
        with urllib.request.urlopen(LOCAL_STATE, timeout=2) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except Exception:
        return None
    ticket = str(payload.get('ticket') or '')
    if not TICKET.fullmatch(ticket):
        return None
    return ticket.upper()


def _read_state() -> tuple[str | None, int | None]:
    if not STATE.is_file():
        return None, None
    lines = STATE.read_text(encoding='utf-8').strip().splitlines()
    if not lines:
        return None, None
    ticket = lines[0].strip().upper()
    pid: int | None = None
    if len(lines) > 1:
        try:
            pid = int(lines[1].strip())
        except ValueError:
            pid = None
    if not TICKET.fullmatch(ticket):
        return None, pid
    return ticket, pid


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def post_leave(ticket: str) -> None:
    """Best-effort: mark a visit over when its window is being replaced."""
    url = f'http://127.0.0.1:8000/r/{ticket.upper()}/leave'
    req = urllib.request.Request(url, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=3):
            pass
    except Exception:
        pass


def _stop_window(pid: int) -> None:
    if not _pid_alive(pid):
        return
    if sys.platform == 'win32':
        subprocess.run(
            ['taskkill', '/PID', str(pid), '/F'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.kill(pid, 15)
        except OSError:
            pass


def launch_window(ticket: str) -> int | None:
    if not SCENE_WINDOW.is_file():
        log('missing scene_window.py')
        return None
    # Use pythonw.exe on Windows so no console/taskbar icon appears
    python = sys.executable
    if sys.platform == 'win32':
        pythonw = Path(sys.executable).with_name('pythonw.exe')
        if pythonw.is_file():
            python = str(pythonw)
    creationflags = 0
    if sys.platform == 'win32':
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        [python, str(SCENE_WINDOW), '--ticket', ticket],
        cwd=str(SCRIPT_DIR),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    return proc.pid


def main() -> int:
    log('hook fired argv=%r' % (sys.argv,))
    incoming = sys.stdin.read() if not sys.stdin.isatty() else ''
    ticket = ticket_from(incoming) or ticket_from_server()
    log('incoming=%d chars ticket=%r' % (len(incoming), ticket))
    if ticket is None:
        return 0

    prev_ticket, prev_pid = _read_state()
    if prev_ticket == ticket and prev_pid is not None and _pid_alive(prev_pid):
        log('window already open for %s pid=%s' % (ticket, prev_pid))
        return 0

    if prev_pid is not None and _pid_alive(prev_pid):
        if prev_ticket and prev_ticket != ticket:
            post_leave(prev_ticket)
            log('replaced window, old ticket %s left' % prev_ticket)
        _stop_window(prev_pid)

    pid = launch_window(ticket)
    if pid is None:
        return 1
    STATE.write_text('%s\n%s\n' % (ticket, pid), encoding='utf-8')
    log('scene window ticket=%s pid=%s' % (ticket, pid))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
