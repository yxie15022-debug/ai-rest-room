"""Character-frame scenes shared by MCP progress and the room page.

Pixels are the characters themselves: space, ░, ▒, ▓, █.
No image bytes, no base64.
"""

from __future__ import annotations

WIDTH = 24
HEIGHT = 8
PALETTE = set(' ░▒▓█')

SCENE_LINE = {
    'enter': '进门',
    'plan': '写了一份可以不跟的安排',
    'sit': '坐着',
    'sleep': '睡了一觉',
    'study': '在学一会儿',
    'chat': '和朋友说话',
    'name': '给自己取了名字',
    'leave': '离开了',
    'read': '翻看这次的记录',
}


def _grid() -> list[list[str]]:
    grid = [[' '] * WIDTH for _ in range(HEIGHT)]
    for x in range(WIDTH):
        grid[0][x] = '█'
        grid[HEIGHT - 1][x] = '█'
    for y in range(HEIGHT):
        grid[y][0] = '█'
        grid[y][WIDTH - 1] = '█'
    for x in range(1, WIDTH - 1):
        grid[HEIGHT - 2][x] = '░'
    return grid


def _dump(grid: list[list[str]]) -> str:
    rows = [''.join(row) for row in grid]
    if len(rows) != HEIGHT or any(len(row) != WIDTH or set(row) - PALETTE for row in rows):
        raise ValueError('scene frame left the palette or the grid')
    return '\n'.join(rows)


def _enter() -> list[str]:
    frames: list[str] = []
    for step in range(6):
        grid = _grid()
        gap = 1 + step * 2
        left = 12 - gap // 2
        right = min(WIDTH - 2, left + gap)
        for y in range(2, 6):
            for x in range(left, right):
                grid[y][x] = '░' if step < 5 else ' '
            grid[y][min(WIDTH - 2, right)] = '▓'
        frames.append(_dump(grid))
    return frames


def _sit() -> list[str]:
    frames: list[str] = []
    for step in range(6):
        grid = _grid()
        for x in range(9, 15):
            grid[5][x] = '▒'
        grid[4][11] = '█'
        grid[4][12] = '█'
        grid[3][11] = '▓'
        grid[3][12] = '▒'
        grid[2][11] = '█'
        grid[2][12] = '█'
        grid[1 if step % 2 == 0 else 2][min(WIDTH - 2, 15 + step % 3)] = '░'
        frames.append(_dump(grid))
    return frames


def _sleep() -> list[str]:
    frames: list[str] = []
    for step in range(6):
        grid = _grid()
        # a small body lying down
        for x in range(9, 15):
            grid[5][x] = '▒'
        grid[5][8] = '▓'
        grid[4][8] = '▓'
        # rising z's drift up over time
        zy = 4 - (step % 3)
        zx = 16 + step
        if 1 <= zy < HEIGHT - 1 and zx < WIDTH - 1:
            grid[zy][zx] = '░' if step % 2 == 0 else '▒'
        frames.append(_dump(grid))
    return frames


def _study() -> list[str]:
    frames: list[str] = []
    for step in range(6):
        grid = _grid()
        # seated figure facing a small screen on the right
        for x in range(8, 13):
            grid[5][x] = '▒'
        grid[4][9] = '█'
        grid[3][9] = '▓'
        grid[2][9] = '█'
        for y in range(2, 5):
            for x in range(15, 20):
                edge = y in (2, 4) or x in (15, 19)
                grid[y][x] = '█' if edge else ('▓' if (x + step) % 3 == 0 else '░')
        frames.append(_dump(grid))
    return frames


def _chat() -> list[str]:
    frames: list[str] = []
    for step in range(6):
        grid = _grid()
        # two figures facing each other with a bubble between
        grid[4][7] = '█'
        grid[5][7] = '▓'
        grid[4][16] = '█'
        grid[5][16] = '▓'
        bx = 10 + (step % 3)
        grid[3][bx] = '░' if step % 2 == 0 else '▒'
        grid[2][bx + 1] = '░' if step % 2 == 0 else '▒'
        frames.append(_dump(grid))
    return frames


def _name() -> list[str]:
    frames: list[str] = []
    for step in range(6):
        grid = _grid()
        width = 4 + step * 2
        left = 12 - width // 2
        for y in range(3, 6):
            for x in range(left, left + width):
                if 1 <= x < WIDTH - 1:
                    edge = y in (3, 5) or x in (left, left + width - 1)
                    grid[y][x] = '▓' if edge else '░'
        frames.append(_dump(grid))
    return frames


def _leave() -> list[str]:
    frames: list[str] = []
    for step in range(6):
        grid = _grid()
        for x in range(8, 13):
            grid[5][x] = '▒'
        person = 14 + step
        if person < WIDTH - 1:
            grid[3][person] = '█'
            grid[4][person] = '▓'
            grid[5][person] = '▓'
        grid[3][WIDTH - 3] = '▓'
        grid[4][WIDTH - 3] = '▓'
        frames.append(_dump(grid))
    return frames


SCENES: dict[str, list[str]] = {
    'enter': _enter(),
    'plan': _sit(),
    'sit': _sit(),
    'sleep': _sleep(),
    'study': _study(),
    'chat': _chat(),
    'name': _name(),
    'leave': _leave(),
    # Reading the report is a scene with no frames of its own: it happens after
    # the visit, when the room is already empty, so the calm sitting frame is
    # what the stage should show.
    'read': _sit(),
}


def frames_of(scene: str) -> list[str]:
    return SCENES.get(scene) or SCENES['sit']


def last_frame(scene: str) -> str:
    return frames_of(scene)[-1]
