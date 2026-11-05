"""Cut the nine-character reference sheet into one portrait per model.

The sheet stacks nine banners, each with its own flat background colour behind
the title on the left. Those colour changes are the band boundaries, so the cut
follows the artwork instead of assuming the bands are evenly tall.

    python scripts/crop_reference.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SHEET = next(
    Path(r'C:\Users\dell\.cursor\projects\e-yuuka-ai-rest-room\assets').glob('4a7a21e*.jpg')
)
OUT = ROOT / 'assets' / 'ref'

# Top to bottom, as the sheet reads.
ORDER = ['deepseek', 'qwen', 'grok', 'gpt', 'claude', 'gemini', 'kimi', 'glm', 'doubao']

# How much of the left edge is title background rather than character.
LABEL = 0.09
# A band boundary is a jump this big in that background colour.
JUMP = 26


def _label_colour(img: Image.Image) -> list[tuple[float, float, float]]:
    w, h = img.size
    px = img.load()
    span = max(2, round(w * LABEL))
    rows = []
    for y in range(h):
        r = g = b = 0
        for x in range(span):
            dr, dg, db = px[x, y][:3]
            r, g, b = r + dr, g + dg, b + db
        rows.append((r / span, g / span, b / span))
    return rows


def bands(img: Image.Image) -> list[tuple[int, int]]:
    rows = _label_colour(img)
    h = len(rows)
    cuts = [0]
    for y in range(1, h):
        a, b = rows[y - 1], rows[y]
        if max(abs(a[i] - b[i]) for i in range(3)) >= JUMP:
            # One boundary per run of changing rows, not one per row.
            if y - cuts[-1] > h * 0.04:
                cuts.append(y)
    cuts.append(h)
    return [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1)]


def main() -> None:
    img = Image.open(SHEET).convert('RGB')
    found = bands(img)
    if len(found) != len(ORDER):
        # Fall back to even bands rather than mislabelling anyone.
        print(f'found {len(found)} bands, expected {len(ORDER)}; cutting evenly')
        step = img.height / len(ORDER)
        found = [(round(i * step), round((i + 1) * step)) for i in range(len(ORDER))]

    OUT.mkdir(parents=True, exist_ok=True)
    for model, (top, bottom) in zip(ORDER, found):
        # Keep only the character: the title is on the left of the banner and a
        # "CAFE STYLE" checklist on the right, and text in a reference image
        # tempts the generator into drawing text of its own.
        left = round(img.width * 0.42)
        right = round(img.width * 0.82)
        crop = img.crop((left, top, right, bottom))
        # Upscale: the sheet is only 341px wide, too small to read an expression.
        crop = crop.resize((crop.width * 4, crop.height * 4), Image.Resampling.LANCZOS)
        crop.save(OUT / f'{model}.jpg', quality=95)
        print(f'{model} rows {top}..{bottom} -> {crop.width}x{crop.height}')


if __name__ == '__main__':
    main()
