"""Extract the rounded tile's alpha using its imagegen separation matte.

The user explicitly requested programmatic clipping on 2026-11-06. RGB artwork
comes from the original image; the magenta matte only supplies the silhouette.
Requires Pillow on the build machine, not in the distributed application.
"""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter


def prepare(original, matte, output):
    with Image.open(original) as image:
        artwork = image.convert("RGBA")
    with Image.open(matte) as image:
        separation = image.convert("RGB")
    if artwork.size != separation.size:
        raise ValueError("Artwork and matte must have exactly the same dimensions")
    red, green, blue = separation.split()
    # Magenta has high R/B and zero G; the white/blue foreground has no magenta.
    magenta = ImageChops.subtract(ImageChops.darker(red, blue), green)
    alpha = ImageChops.invert(magenta).point(
        lambda value: max(0, min(255, round((value - 16) * 255 / 224)))
    )
    # Retain the single central tile and its antialiased boundary, not islands.
    component = alpha.point(lambda value: 255 if value >= 128 else 0)
    center = (artwork.width // 2, artwork.height // 2)
    if component.getpixel(center) != 255:
        raise ValueError("Matte does not contain an opaque central tile")
    ImageDraw.floodfill(component, center, 128)
    component = component.point(lambda value: 255 if value == 128 else 0)
    alpha = ImageChops.multiply(alpha, component.filter(ImageFilter.MaxFilter(3)))
    for point in ((0, 0), (artwork.width - 1, 0),
                  (0, artwork.height - 1), (artwork.width - 1, artwork.height - 1)):
        if alpha.getpixel(point) != 0:
            raise ValueError("The outer canvas must be fully transparent")
    coverage = sum(value > 0 for value in alpha.getdata()) / (artwork.width * artwork.height)
    if not 0.5 < coverage < 0.96:
        raise ValueError("Unexpected tile coverage: %s" % coverage)
    artwork.putalpha(alpha)
    artwork.save(output, format="PNG", optimize=True)
    return dict(size=artwork.size, alpha_bounds=alpha.getbbox(),
                nontransparent_fraction=round(coverage, 4), corners_transparent=True)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", type=Path, default=root / "assets/brand/app-logo-opaque.png")
    parser.add_argument("--matte", type=Path, default=root / "assets/brand/app-logo-matte.png")
    parser.add_argument("--output", type=Path, default=root / "assets/brand/app-logo.png")
    args = parser.parse_args()
    print(json.dumps(prepare(args.original, args.matte, args.output)))
