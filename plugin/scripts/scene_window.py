"""Play pre-rendered mascot frames. No taskbar icon, no caption, just the animation."""

from __future__ import annotations

import argparse
import json
import sys
import tkinter as tk
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image, ImageTk

BASE = 'http://127.0.0.1:8000'
FRAME_MS = 42  # ~24fps
POLL_MS = 4000
FADE_STEPS = 12
MAX_H = 620
RADIUS = 22

MASCOT_ROOT = Path(__file__).resolve().parents[1] / 'frames' / 'mascot'
ANIMAL_MARKER = Path.home() / '.ai-rest-room-mascot'
CLIP = {
    'enter': 'enter',
    'sit': 'sit',
    'sleep': 'sleep',
    'wake': 'sleep',
    'study': 'study',
    'chat': 'chat',
    'listen': 'chat',
    'read': 'read',
    'look': 'look',
    'name': 'sit',
    'leave': 'enter',
}
PLAY_ONCE = {'enter', 'leave'}

BG = '#ffffff'


def mascot_root() -> Path:
    """The same choice file the room page reads. Rabbit is the fallback."""
    try:
        name = ANIMAL_MARKER.read_text(encoding='utf-8').strip()
    except OSError:
        name = ''
    if name and (MASCOT_ROOT / name).is_dir():
        return MASCOT_ROOT / name
    return MASCOT_ROOT / 'rabbit'


ROOT = mascot_root()


def fetch_state(ticket: str) -> dict:
    url = f'{BASE}/r/{ticket.upper()}/state'
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode('utf-8'))


def post_leave(ticket: str) -> None:
    """Tell the room this visit is over. Best-effort: never blocks closing."""
    url = f'{BASE}/r/{ticket.upper()}/leave'
    req = urllib.request.Request(url, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=3):
            pass
    except Exception:
        pass


def load_clip(name: str) -> list[Image.Image]:
    folder = ROOT / name
    if not folder.is_dir():
        return []
    return [Image.open(path).convert('RGB') for path in sorted(folder.glob('*.png'))]


class SceneWindow:
    def __init__(self, ticket: str) -> None:
        self.ticket = ticket.upper()
        self.data = fetch_state(self.ticket)
        self.scene, self.line = self._latest()
        wanted = ('sit', 'read', 'look', 'enter', 'sleep', 'study', 'chat')
        self.clips = {name: frames for name in wanted if (frames := load_clip(name))}
        if not self.clips:
            raise FileNotFoundError(f'no mascot frames under {ROOT}')
        sample = next(iter(self.clips.values()))[0]
        scale = min(1.0, MAX_H / sample.height)
        self.size = (max(1, int(sample.width * scale)), max(1, int(sample.height * scale)))
        self.photos: dict[str, list[ImageTk.PhotoImage]] = {}
        self.frame_index = 0
        self.clip_name = ''
        self.hold = False
        self._leaving = False
        self._fade_step = 0
        self._drag_x = 0
        self._drag_y = 0

        self._host = tk.Tk()
        self._host.withdraw()
        self.root = tk.Toplevel(self._host)
        self.root.title(f'休息室 · {self.ticket}')
        self.root.configure(bg=BG)
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)

        for name, frames in self.clips.items():
            self.photos[name] = [ImageTk.PhotoImage(frame.resize(self.size, Image.Resampling.LANCZOS)) for frame in frames]
        if 'enter' in self.photos:
            self.photos['leave'] = list(reversed(self.photos['enter']))

        self.picture = tk.Label(self.root, bd=0, highlightthickness=0, bg=BG)
        self.picture.pack()
        self.picture.bind('<Button-1>', self._start_drag)
        self.picture.bind('<B1-Motion>', self._do_drag)
        self.picture.bind('<Double-Button-1>', lambda _e: self._close())

        self.root.protocol('WM_DELETE_WINDOW', self._close)
        self._show_clip(restart=True)
        width, height = self.size
        self.window_size = (width, height)
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 6)
        self.root.geometry(f'{width}x{height}+{x}+{y}')
        self.root.attributes('-alpha', 0.0)
        self.root.after(10, self._hide_taskbar)
        self._fade_in()
        self.root.after(FRAME_MS, self._tick)
        if self.data.get('still_inside'):
            self.root.after(POLL_MS, self._poll)

    def _latest(self) -> tuple[str, str]:
        stage = self.data.get('stage') or []
        if not stage:
            return 'sit', ''
        item = stage[-1]
        return str(item.get('scene') or 'sit'), str(item.get('line') or '')

    def _clip_for(self, scene: str) -> str:
        if scene == 'leave' and 'leave' in self.photos:
            return 'leave'
        mapped = CLIP.get(scene, 'sit')
        if mapped in self.photos:
            return mapped
        if 'sit' in self.photos:
            return 'sit'
        return next(iter(self.photos))

    def _show_clip(self, restart: bool) -> None:
        name = self._clip_for(self.scene)
        if restart or name != self.clip_name:
            self.clip_name = name
            self.frame_index = 0
            self.hold = False
        frames = self.photos[name]
        self.picture.configure(image=frames[self.frame_index])

    def _tick(self) -> None:
        if not self.root.winfo_exists():
            return
        scene, line = self._latest()
        changed = scene != self.scene
        self.scene, self.line = scene, line
        if changed:
            self._show_clip(restart=True)
        elif not self.hold:
            frames = self.photos[self.clip_name]
            if self.scene in PLAY_ONCE and self.frame_index >= len(frames) - 1:
                self.scene = 'sit'
                self.line = '坐着'
                self._show_clip(restart=True)
            else:
                self.frame_index = (self.frame_index + 1) % len(frames)
            self.picture.configure(image=frames[self.frame_index])
        self.root.after(FRAME_MS, self._tick)

    def _poll(self) -> None:
        if not self.root.winfo_exists():
            return
        try:
            self.data = fetch_state(self.ticket)
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            self.root.after(POLL_MS, self._poll)
            return
        if not self.data.get('still_inside'):
            self._finish_leave()
            return
        self.root.after(POLL_MS, self._poll)

    def _finish_leave(self) -> None:
        """Room marked this visit over elsewhere: play the exit, then close."""
        if self._leaving:
            return
        self._leaving = True
        self.scene = 'leave'
        self._show_clip(restart=True)
        self.root.after(1800, self._destroy)

    def _close(self) -> None:
        # User closed the window: the agent leaves too.
        if not self._leaving:
            self._leaving = True
            post_leave(self.ticket)
        self._destroy()

    def _destroy(self) -> None:
        try:
            self._host.destroy()
        except tk.TclError:
            pass

    def _start_drag(self, event: tk.Event) -> None:
        self._drag_x = event.x_root - self.root.winfo_x()
        self._drag_y = event.y_root - self.root.winfo_y()

    def _do_drag(self, event: tk.Event) -> None:
        width, height = self.window_size
        self.root.geometry(f'{width}x{height}+{event.x_root - self._drag_x}+{event.y_root - self._drag_y}')

    def _shape(self, hwnd: int) -> None:
        import ctypes

        gdi32 = ctypes.windll.gdi32
        user32 = ctypes.windll.user32
        width, height = self.window_size
        gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
        gdi32.CreateRoundRectRgn.restype = ctypes.c_void_p
        user32.SetWindowRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
        region = gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, RADIUS * 2, RADIUS * 2)
        if region:
            user32.SetWindowRgn(hwnd, region, True)

    def _hide_taskbar(self) -> None:
        if sys.platform != 'win32':
            return
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        try:
            owner = user32.GetParent(self._host.winfo_id()) or self._host.winfo_id()
            style = user32.GetWindowLongW(hwnd, -20)
            user32.SetWindowLongW(hwnd, -20, (style & ~0x00040000) | 0x00000080)
            user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
            user32.SetWindowLongPtrW.restype = ctypes.c_void_p
            user32.SetWindowLongPtrW(hwnd, -8, owner)
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x27)
        except Exception:
            pass
        try:
            alpha = self.root.attributes('-alpha')
        except tk.TclError:
            alpha = 1.0
        self.root.withdraw()
        self.root.deiconify()
        self.root.attributes('-topmost', True)
        try:
            self.root.attributes('-alpha', alpha)
        except tk.TclError:
            pass
        try:
            self._shape(hwnd)
        except Exception:
            pass

    def _fade_in(self) -> None:
        self._fade_step += 1
        alpha = min(1.0, self._fade_step / FADE_STEPS)
        try:
            self.root.attributes('-alpha', alpha)
        except tk.TclError:
            return
        if alpha < 1.0:
            self.root.after(30, self._fade_in)

    def run(self) -> None:
        self._host.mainloop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='休息室场景窗')
    parser.add_argument('--ticket', required=True)
    args = parser.parse_args(argv)
    try:
        SceneWindow(args.ticket).run()
    except urllib.error.HTTPError as exc:
        print(f'state HTTP {exc.code}', file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError) as exc:
        print(f'cannot reach {BASE}: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
