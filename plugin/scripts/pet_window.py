"""The rest room as a desktop pet: the room itself, cut out and on the desktop.

There is no window around the room. The art is an isometric cutaway box with
nothing behind it, and the window is clipped to exactly that shape, so what
sits on the desktop is a little room rather than a picture of one in a frame.
Clipping does the job twice over: Windows draws nothing outside the shape and
sends clicks out there straight through to whatever is underneath, so the pet
never covers the window it is sitting on.

The pet belongs to the MCP session, not to any one visit: it opens the moment
the agent connects, shows an empty house while it waits, follows her in and out
of the room, and closes when she disconnects.

Needs pywebview (WebView2 on Windows); `open_room.py` falls back to the
tkinter frame player when it is missing.

    python pet_window.py [--ticket ABCD-EFGH] [--parent-pid 1234]
"""

from __future__ import annotations

import argparse
import atexit
import ctypes
import ctypes.wintypes as wintypes
import io
import os
import tempfile
import threading
import time
import urllib.request

import webview

BASE = 'http://127.0.0.1:8000'
ROOM_ART = f'{BASE}/static/anim/room/bg.png'
# How wide the room sits on the desktop. Its height follows the art, so the
# page never letterboxes and the clip can follow the walls exactly. Generous
# for a pet, because the pet is a whole room with people talking in it -- and
# being clipped to the walls, it covers nothing it does not actually draw.
WIDTH = 640
MARGIN = 24
POLL_SEC = 2.0
# A server that has gone for good should not strand a window on the desktop;
# one that is merely restarting should.
GIVE_UP_SEC = 30.0
# Only firmly painted pixels are kept, which pulls the clip a hair inside the
# art: better to lose the outermost half-transparent pixel than to leave a rim
# of bare window showing around the walls.
OPAQUE = 200
# Room rows per window size, so the shape can be re-cut as speech comes and
# goes without re-reading the whole room's alpha each time.
_ROWS: dict[tuple[int, int, int], list[tuple[int, int, int]]] = {}
# Pixels of slack added around each bubble's measured box. A bubble draws its
# rounded corners and its drop shadow outside that box, and a clip landing
# exactly on the measurement leaves it with a sliced top edge.
BLEED = 12
# Window pixels kept clear above the room for speech. Bubbles are drawn at a
# readable screen size rather than scaled with the room, so this has to be
# enough of both: a couple of lines of text, plus the gap that keeps them clear
# of the roof. Mirrors SPEECH in stage.js -- change one, change the other.
SPEECH = 380


def alive(pid: int) -> bool:
    """Is that process still running?"""
    if os.name != 'nt':
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    query_limited_information = 0x1000
    still_active = 259
    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(query_limited_information, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == still_active
    finally:
        kernel.CloseHandle(handle)


def served() -> bool:
    try:
        with urllib.request.urlopen(f'{BASE}/healthz', timeout=4) as response:
            return response.status == 200
    except Exception:
        return False


def watch(window: webview.Window, parent: int) -> None:
    """Shut the pet once whatever opened it is gone.

    The MCP server closes this window itself when the agent disconnects, so
    both of these are nets under that: one for a server killed outright, one
    for a room with nothing left to draw it.
    """
    quiet = 0.0
    while True:
        time.sleep(POLL_SEC)
        if parent and not alive(parent):
            window.destroy()
            return
        quiet = 0.0 if served() else quiet + POLL_SEC
        if quiet >= GIVE_UP_SEC:
            window.destroy()
            return


def room_art():
    """The room's own picture, for its shape. None if it cannot be had."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with urllib.request.urlopen(ROOM_ART, timeout=8) as response:
            return Image.open(io.BytesIO(response.read())).convert('RGBA')
    except Exception:
        return None


def _rows(art, width: int, height: int):
    """The run of room on each row of a `width` x `height` picture of it.

    One run per row is all an isometric box ever needs: floor and two walls
    make a single solid outline with no notch in it.

    Cached by size: the window asks for its shape on every change of speech,
    and re-reading a few hundred thousand alpha values each time would make the
    pet lag a bubble behind.
    """
    key = (id(art), width, height)
    cached = _ROWS.get(key)
    if cached is not None:
        return cached
    alpha = art.resize((width, height)).getchannel('A').load()
    rows = []
    for y in range(height):
        run = [x for x in range(width) if alpha[x, y] >= OPAQUE]
        if run:
            rows.append((run[0], run[-1] + 1, y))
    _ROWS[key] = rows
    return rows


def clip_to_room(hwnd: int, art) -> bool:
    """Cut the window to the room's own outline: the shape before any speech.

    Only the first frame and old pages need this. Once the page is laid out it
    reports its outline and `shape_loop` follows that instead.
    """
    client = wintypes.RECT()
    if not ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(client)):
        return False
    cw, ch = client.right, client.bottom
    if cw <= 0 or ch <= 0:
        return False

    # Same fit as the page: the room sits in a box that also holds the space
    # kept for speech above it, then the room itself is centred at its bottom.
    scale = min(cw / art.width, ch / (art.height + SPEECH))
    w = max(1, round(art.width * scale))
    h = max(1, round(art.height * scale))
    ox = (cw - w) // 2
    spare = ch - (art.height + SPEECH) * scale
    oy = max(0, round(spare / 2 + SPEECH * scale))

    gdi = ctypes.windll.gdi32
    shape = gdi.CreateRectRgn(0, 0, 0, 0)
    row = gdi.CreateRectRgn(0, 0, 0, 0)
    rgn_or = 2
    for left, right, y in _rows(art, w, h):
        gdi.SetRectRgn(row, ox + left, oy + y, ox + right, oy + y + 1)
        gdi.CombineRgn(shape, shape, row, rgn_or)
    gdi.DeleteObject(row)

    # The window owns the region from here; it must not be deleted.
    return bool(ctypes.windll.user32.SetWindowRgn(hwnd, shape, True))


def clip_to_shape(hwnd: int, art, room, boxes) -> bool:
    """Cut the window to the room's silhouette plus whatever speech is up.

    The room is cut from its own art, row by row, so the pet keeps the walls'
    shape instead of becoming a rectangle with a room drawn in it. Speech is
    added as plain boxes on top: a bubble is a rounded panel, and its corners
    are not worth tracing.
    """
    left = int(round(room['x']))
    top = int(round(room['y']))
    w = max(1, int(round(room['w'])))
    h = max(1, int(round(room['h'])))

    client = wintypes.RECT()
    if not ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(client)):
        return False

    gdi = ctypes.windll.gdi32
    shape = gdi.CreateRectRgn(0, 0, 0, 0)
    row = gdi.CreateRectRgn(0, 0, 0, 0)
    rgn_or = 2
    any_box = False

    if art is not None:
        for run_left, run_right, y in _rows(art, w, h):
            gdi.SetRectRgn(row, left + run_left, top + y, left + run_right, top + y + 1)
            gdi.CombineRgn(shape, shape, row, rgn_or)
            any_box = True

    for box in boxes:
        # Slack, in both directions: a bubble has rounded corners and a soft
        # drop shadow that are drawn outside the box it was measured by, and a
        # clip that lands exactly on the measurement shaves the shadow off and
        # leaves a bubble with a flat top.
        box_left = int(round(box['x'])) - BLEED
        box_top = int(round(box['y'])) - BLEED
        box_right = int(round(box['x'] + box['w'])) + BLEED
        box_bottom = int(round(box['y'] + box['h'])) + BLEED
        if box_right <= box_left or box_bottom <= box_top:
            continue
        any_box = True
        # Clamp to the window: a region reaching past it is legal but some
        # compositors clip it differently from one that does not.
        gdi.SetRectRgn(
            row,
            max(0, box_left),
            max(0, box_top),
            min(client.right, box_right),
            min(client.bottom, box_bottom),
        )
        gdi.CombineRgn(shape, shape, row, rgn_or)

    gdi.DeleteObject(row)
    if not any_box:
        gdi.DeleteObject(shape)
        return False

    # The window owns the region from here; it must not be deleted.
    return bool(ctypes.windll.user32.SetWindowRgn(hwnd, shape, True))


def handle(window: webview.Window) -> int:
    """The window's own HWND, by title: pywebview does not hand it over."""
    return ctypes.windll.user32.FindWindowW(None, window.title)


# A lock file is enough for this: one pet per desktop, and a stale lock from a
# crashed window must not lock the next one out forever.
_SINGLE = os.path.join(tempfile.gettempdir(), 'ai-rest-room-pet.single')
_MUTEX = threading.Lock()


def take_the_screen() -> bool:
    """Claim the one desktop pet slot, taking it over from a dead holder."""
    with _MUTEX:
        try:
            with open(_SINGLE, encoding='utf-8') as fh:
                owner = int((fh.read() or '0').strip() or 0)
        except (OSError, ValueError):
            owner = 0
        if owner and owner != os.getpid() and alive(owner):
            return False
        try:
            with open(_SINGLE, 'w', encoding='utf-8') as fh:
                fh.write(str(os.getpid()))
        except OSError:
            # No lock is better than no pet: a read-only temp dir is not a
            # reason to refuse to draw.
            pass
        atexit.register(release_the_screen)
        return True


def release_the_screen() -> None:
    try:
        with open(_SINGLE, encoding='utf-8') as fh:
            owner = int((fh.read() or '0').strip() or 0)
    except (OSError, ValueError):
        return
    if owner != os.getpid():
        return
    try:
        os.remove(_SINGLE)
    except OSError:
        pass


def park(window: webview.Window, hwnd: int) -> None:
    """Tuck the window into the bottom-right corner of the primary screen.

    Measured after it exists rather than from the size asked for: asked for one
    number of pixels, Windows hands back another, and a corner worked out from
    the original number lands in the wrong place.
    """
    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    for screen in webview.screens:
        window.move(
            max(0, screen.width - width - MARGIN),
            max(0, screen.height - height - MARGIN * 3),
        )
        return


def shape_loop(window: webview.Window, art) -> None:
    """Keep the window shaped like what the page is drawing.

    Speech rises off a head, and a cutaway room's roof slopes in from both
    sides, so most bubbles leave the walls. A window cut to the walls alone
    slices their tops off, which is why the shape is asked for again and again
    rather than worked out once. Only a real change is applied: re-cutting a
    window on every poll would flicker it on the desktop.

    The room art is still the fallback for the first frame, before the page has
    laid anything out, and for a page too old to report an outline at all.
    """
    # Poll fast and start from nothing. A frameless transparent window is a
    # plain rectangle until something clips it, and on a slow machine that was
    # a second of visible grey box -- the "why is there a frame?" this started
    # as. Clipping to the empty region first means it is never seen uncut.
    hwnd = 0
    for _ in range(240):
        hwnd = handle(window)
        if hwnd:
            empty = ctypes.windll.gdi32.CreateRectRgn(0, 0, 0, 0)
            ctypes.windll.user32.SetWindowRgn(hwnd, empty, True)
            break
        time.sleep(0.05)
    else:
        return

    # A pet is furniture, not an application: it gets no taskbar button and no
    # Alt+Tab entry. WS_EX_TOOLWINDOW is the flag for exactly that, and it has
    # to be set on the window itself after it exists.
    user32 = ctypes.windll.user32
    GWL_EXSTYLE = -20
    WS_EX_TOOLWINDOW = 0x00000080
    WS_EX_APPWINDOW = 0x00040000
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
    # The taskbar only re-reads the style when the window is hidden and shown
    # again; without this the button it already made stays.
    SW_HIDE, SW_SHOWNOACTIVATE = 0, 4
    user32.ShowWindow(hwnd, SW_HIDE)
    user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)

    if art is not None:
        clip_to_room(hwnd, art)
    park(window, hwnd)

    last = ''
    while True:
        time.sleep(POLL_SEC / 8)
        try:
            said = window.evaluate_js('window.__outline ? window.__outline() : null')
        except Exception:
            # The window is gone, or busy navigating; either way ask again.
            continue
        if not isinstance(said, dict):
            continue
        boxes = said.get('boxes') or []
        room = said.get('room')
        if not isinstance(room, dict):
            continue
        key = repr((room, boxes))
        if key == last:
            continue
        last = key
        try:
            clip_to_shape(hwnd, art, room, boxes)
        except Exception:
            return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ticket', default='')
    parser.add_argument('--parent-pid', type=int, default=0)
    parser.add_argument('--width', type=int, default=WIDTH)
    args = parser.parse_args()

    # One window, one room. A second one on top of the first is not harmless:
    # the newest starts as a plain rectangle for the moment before it is
    # clipped, and a rectangle over a cut-out room reads as a frame around it.
    if not take_the_screen():
        return 0

    ticket = args.ticket.strip().upper()
    # Without a ticket the page goes looking for the visit itself, because the
    # pet opens when the agent connects -- before she has one.
    follow = f'ticket={ticket}' if ticket else 'follow=now'

    # The art decides the window's shape, so fetch it before opening anything.
    # The window is taller than the room by SPEECH, which is the open air a
    # bubble sits in.
    art = room_art()
    width = args.width
    height = round(width * art.height / art.width) + SPEECH if art else width + SPEECH

    window = webview.create_window(
        '休息室',
        f'{BASE}/static/anim/stage.html?{follow}&pet=1',
        width=width,
        height=height,
        frameless=True,
        easy_drag=True,
        on_top=True,
        resizable=False,
        # The page paints only the room; everything else must be nothing at
        # all, not the form's own grey, or the clip would have a colour.
        transparent=True,
    )

    # The page's own close button needs a way back here. One exposed function,
    # not a `js_api` object: pywebview walks a js_api's public attributes to
    # build the bridge, and a window parked on one of them leads it down the
    # WinForms accessibility tree until the stack runs out.
    def close() -> None:
        window.destroy()

    window.expose(close)

    threading.Thread(target=shape_loop, args=(window, art), daemon=True).start()
    threading.Thread(target=watch, args=(window, args.parent_pid), daemon=True).start()
    # Say where WebView2 may keep its browser profile, or it writes an
    # `EBWebView` folder into whatever directory the pet happened to start in
    # -- which is the repository. Private mode still clears it on the way out.
    webview.start(storage_path=os.path.join(tempfile.gettempdir(), 'ai-rest-room-pet'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
