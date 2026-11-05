"""Generate a seamless herringbone wood-floor tile (256x256) for the Blender room."""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'herringbone.png'

WOOD_A = (196, 158, 110)
WOOD_B = (184, 145, 98)
WOOD_C = (206, 170, 122)
EDGE = (168, 132, 88)

T = 256
PLANK_L = 64   # plank length
PLANK_W = 16   # plank width


def herringbone() -> Image.Image:
    img = Image.new('RGB', (T, T), WOOD_A)
    d = ImageDraw.Draw(img)
    # herringbone: L-shaped pairs of planks at 90 degrees, tiled diagonally.
    # Draw on a bigger canvas and crop, so the pattern wraps seamlessly.
    big = Image.new('RGB', (T * 2, T * 2), WOOD_A)
    db = ImageDraw.Draw(big)
    step = PLANK_L // 2
    colors = (WOOD_A, WOOD_B, WOOD_C, WOOD_B)
    for row in range(-2, T * 2 // step + 4):
        for col in range(-2, T * 2 // step + 4):
            x = col * step + (row % 2) * step
            y = row * step
            c1 = colors[(row + col) % 4]
            c2 = colors[(row + col + 1) % 4]
            # horizontal plank
            db.rectangle([x, y, x + PLANK_L, y + PLANK_W], fill=c1, outline=EDGE)
            # vertical plank meeting its end
            db.rectangle([x + PLANK_L, y - PLANK_L + PLANK_W, x + PLANK_L + PLANK_W, y + PLANK_W],
                         fill=c2, outline=EDGE)
    # crop the centre tile and wrap edges via offset paste
    img = big.crop((T // 2, T // 2, T // 2 + T, T // 2 + T))
    return img


def main():
    im = herringbone()
    im.save(OUT)
    print('saved', OUT, im.size)


if __name__ == '__main__':
    main()
