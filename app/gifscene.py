"""Tiny GIFs and PNG frames of the same character scenes."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

from .scenes import SCENE_LINE, SCENES

SCENE_DIR = Path(__file__).resolve().parent / 'static' / 'scene'

SCALE = 8
_MIN_CODE_SIZE = 3
_COLORS = (
    (0x1B, 0x19, 0x16),
    (0x8A, 0x81, 0x75),
    (0xC4, 0xB8, 0xA4),
    (0xE6, 0xDC, 0xC8),
    (0xF6, 0xF1, 0xE7),
    (0, 0, 0),
    (0, 0, 0),
    (0, 0, 0),
)
_INDEX = {' ': 0, '░': 1, '▒': 2, '▓': 3, '█': 4}


def _raster(frame: str) -> list[int]:
    rows = frame.split('\n')
    pixels: list[int] = []
    for row in rows:
        band = []
        for char in row:
            band.extend([_INDEX[char]] * SCALE)
        pixels.extend(band * SCALE)
    return pixels


def _lzw(indices: list[int]) -> bytes:
    clear = 1 << _MIN_CODE_SIZE
    end = clear + 1
    code_size = _MIN_CODE_SIZE + 1
    next_code = end + 1
    table = {bytes([i]): i for i in range(clear)}
    stream: list[tuple[int, int]] = [(clear, code_size)]
    prefix = b''
    for index in indices:
        joined = prefix + bytes([index])
        if joined in table:
            prefix = joined
            continue
        stream.append((table[prefix], code_size))
        if next_code < 4096:
            table[joined] = next_code
            next_code += 1
            if code_size < 12 and next_code > (1 << code_size):
                code_size += 1
        else:
            stream.append((clear, code_size))
            table = {bytes([i]): i for i in range(clear)}
            code_size = _MIN_CODE_SIZE + 1
            next_code = end + 1
        prefix = bytes([index])
    if prefix:
        stream.append((table[prefix], code_size))
    stream.append((end, code_size))

    accumulator = 0
    filled = 0
    out = bytearray()
    for code, size in stream:
        accumulator |= code << filled
        filled += size
        while filled >= 8:
            out.append(accumulator & 0xFF)
            accumulator >>= 8
            filled -= 8
    if filled:
        out.append(accumulator & 0xFF)
    return bytes(out)


def _subblocks(data: bytes) -> bytes:
    out = bytearray()
    for start in range(0, len(data), 255):
        chunk = data[start : start + 255]
        out.append(len(chunk))
        out.extend(chunk)
    out.append(0)
    return bytes(out)


def scene_gif(scene: str) -> bytes:
    frames = SCENES[scene]
    width = 24 * SCALE
    height = 8 * SCALE
    packed = 0x80 | 0x70 | 0x02
    blob = bytearray(b'GIF89a')
    blob += struct.pack('<HHBBB', width, height, packed, 0, 0)
    for red, green, blue in _COLORS:
        blob += bytes((red, green, blue))
    blob += b'\x21\xff\x0bNETSCAPE2.0\x03\x01\x00\x00\x00'
    for frame in frames:
        blob += b'\x21\xf9\x04\x00' + struct.pack('<H', 16) + b'\x00\x00'
        blob += b'\x2c' + struct.pack('<HHHHB', 0, 0, width, height, 0)
        blob += bytes([_MIN_CODE_SIZE]) + _subblocks(_lzw(_raster(frame)))
    blob += b'\x3b'
    return bytes(blob)


def scene_png(frame: str) -> bytes:
    indices = _raster(frame)
    width = 24 * SCALE
    height = 8 * SCALE
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        start = y * width
        raw.extend(indices[start : start + width])
    compressed = zlib.compress(bytes(raw), 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', crc)

    ihdr = struct.pack('>IIBBBBB', width, height, 8, 3, 0, 0, 0)
    palette = b''.join(bytes((red, green, blue)) for red, green, blue in _COLORS[:5])
    return (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', ihdr)
        + chunk(b'PLTE', palette)
        + chunk(b'IDAT', compressed)
        + chunk(b'IEND', b'')
    )


GIFS = {name: scene_gif(name) for name in SCENES}
PNGS = {name: [scene_png(frame) for frame in frames] for name, frames in SCENES.items()}

PLUGIN_FRAMES = Path(__file__).resolve().parent.parent / 'plugin' / 'frames'
PLUGIN_MOD = Path(__file__).resolve().parent.parent / 'plugin' / 'hooks' / 'register.js'
_MOD_PLAYER = Path(__file__).resolve().parent / 'mod_player.js'


def _write(path: Path, blob: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file() or path.read_bytes() != blob:
        path.write_bytes(blob)


def publish_scene_gifs() -> None:
    SCENE_DIR.mkdir(parents=True, exist_ok=True)
    for name, blob in GIFS.items():
        _write(SCENE_DIR / f'{name}.gif', blob)
    for name, frames in PNGS.items():
        for index, blob in enumerate(frames):
            _write(PLUGIN_FRAMES / name / f'{index}.png', blob)
    data = json.dumps({'lines': SCENE_LINE, 'scenes': SCENES}, ensure_ascii=False).encode()
    player = _MOD_PLAYER.read_text(encoding='utf-8')
    _write(PLUGIN_MOD, b'const DATA = ' + data + b';\n' + player.encode())


publish_scene_gifs()
