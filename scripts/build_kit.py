"""Make the live demo kit: five of our photos with GPS written into them, so uploading one drops its own pin.

The places are in scripts/demo_places.py (KIT). The photos come from seed/photos and are left out of the seed cases.
Run once from the repo root after changing a place:  uv run python scripts/build_kit.py
then rebuild the seed (uv run python scripts/build_seed.py) so the kit's readings are cached.
"""

from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

from PIL import Image

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "scripts"))
from demo_places import KIT  # noqa: E402

OUT = APP / "seed" / "live_demo"


def dms(v: float):
    v = abs(v)
    d = int(v)
    m = int((v - d) * 60)
    s = round(((v - d) * 60 - m) * 60, 4)
    return (Fraction(d), Fraction(m), Fraction(s).limit_denominator(10000))


for file, source, lat, lon, street, outcome in KIT:
    im = Image.open(APP / "seed" / "photos" / f"{source}_before.jpg").convert("RGB")
    exif = Image.Exif()
    exif[0x8825] = {1: "N" if lat >= 0 else "S", 2: dms(lat), 3: "E" if lon >= 0 else "W", 4: dms(lon)}
    im.save(OUT / file, "JPEG", quality=85, exif=exif.tobytes())
    print(f"{file}: {street} ({lat:.6f}, {lon:.6f}), {outcome}")
