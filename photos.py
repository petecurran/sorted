"""Photo intake: hash the original bytes, read EXIF GPS, then save an oriented, resized JPEG with all metadata gone."""
from __future__ import annotations

import hashlib
import io
import math
from pathlib import Path

from PIL import Image, ImageOps

from common import UPLOADS, log

MAX_PX = 1600


MAX_BYTES = 40_000_000


class BadImage(ValueError):
    pass


def _sips_convert(data: bytes) -> Image.Image | None:
    """Convert an image Pillow can't read (e.g. iPhone HEIC) with macOS's built-in sips. EXIF GPS survives."""
    import shutil
    import subprocess
    import tempfile
    if not shutil.which("sips"):
        return None
    with tempfile.TemporaryDirectory() as d:
        src, dst = Path(d) / "in.heic", Path(d) / "out.jpg"
        src.write_bytes(data)
        try:
            subprocess.run(["sips", "-s", "format", "jpeg", str(src), "--out", str(dst)], check=True,
                           capture_output=True, timeout=20)
            img = Image.open(io.BytesIO(dst.read_bytes()))
            img.load()
            return img
        except Exception as e:
            log.info("sips could not convert upload: %s", e)
            return None


def _dms(v) -> float:
    d, m, s = (float(x) for x in v)
    return d + m / 60 + s / 3600


def exif_gps(img: Image.Image) -> tuple[float, float] | None:
    try:
        gps = img.getexif().get_ifd(0x8825)
        if not gps or 2 not in gps or 4 not in gps:
            return None
        lat, lon = _dms(gps[2]), _dms(gps[4])
        if str(gps.get(1, "N")).upper().startswith("S"):
            lat = -lat
        if str(gps.get(3, "E")).upper().startswith("W"):
            lon = -lon
        if not (math.isfinite(lat) and math.isfinite(lon)) or (abs(lat) < 1e-6 and abs(lon) < 1e-6):
            return None
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return None
        return round(lat, 6), round(lon, 6)
    except Exception as e:
        log.info("no usable EXIF GPS: %s", e)
        return None


def process(data: bytes, prefix: str = "") -> dict:
    """Returns {sha, gps, path, url}. Raises BadImage if Pillow can't read it."""
    if not data:
        raise BadImage("empty file")
    if len(data) > MAX_BYTES:
        raise BadImage(f"photo is larger than {MAX_BYTES // 1_000_000} MB")
    sha = hashlib.sha256(data).hexdigest()
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:
        img = _sips_convert(data)  # HEIC etc. on macOS, without extra Python dependencies
        if img is None:
            raise BadImage(str(e)) from e
    gps = exif_gps(img)
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((MAX_PX, MAX_PX), Image.LANCZOS)
    clean = Image.frombytes(img.mode, img.size, img.tobytes())  # brand-new image: no EXIF, XMP, ICC or GPS
    UPLOADS.mkdir(parents=True, exist_ok=True)
    name = f"{prefix}{sha[:24]}.jpg"
    path = UPLOADS / name
    if not path.exists():
        clean.save(path, "JPEG", quality=85, optimize=True)
    return {"sha": sha, "gps": gps, "path": str(path), "url": f"/media/{name}"}
