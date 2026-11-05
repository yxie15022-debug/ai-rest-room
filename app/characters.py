"""Visitor character registry.

The render script (Blender) and the app both read `data/characters/registry.json`
directly, because the script runs inside Blender and cannot import the app
package. Keep this module's view of the registry in sync with that file.

Each entry maps a model name (the value passed to MCP `enter`) to:
- asset: path to a normalized .glb, or null for the procedural visitor
- color: main body color (RGB 0..1) used by the procedural visitor
- accent: accent / trim color

Unknown models resolve to 'default'.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / 'data' / 'characters' / 'registry.json'

_CACHE: dict | None = None


def _load() -> dict:
    global _CACHE
    if _CACHE is None:
        if REGISTRY_PATH.is_file():
            _CACHE = json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))
        else:
            _CACHE = {}
    return _CACHE


def known_models() -> list[str]:
    """All model keys in the registry, including 'default'."""
    return list(_load().keys())


def resolve(model: str | None) -> str:
    """Map a model name to a registry key; unknown / None -> 'default'."""
    key = (model or '').strip().lower()
    if key and key in _load():
        return key
    return 'default'


def entry(model: str | None) -> dict:
    """The full registry entry for a model (falls back to default)."""
    return _load().get(resolve(model), {})


def color_of(model: str | None) -> tuple[float, float, float]:
    color = entry(model).get('color') or [0.62, 0.62, 0.66]
    return tuple(float(c) for c in color[:3])


def accent_of(model: str | None) -> tuple[float, float, float]:
    accent = entry(model).get('accent') or [0.82, 0.82, 0.85]
    return tuple(float(c) for c in accent[:3])


def asset_of(model: str | None) -> str | None:
    return entry(model).get('asset')


def frame_dir(model: str | None, scene: str) -> str:
    """Folder under the mascot animal that holds this visitor's frames.

    Every scene, including sit, is rendered per model because each model is
    a different downloaded character.
    """
    del scene
    return resolve(model)
