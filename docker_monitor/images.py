"""Logo discovery and e-ink image conversion."""

import glob
import random
from datetime import datetime

from PIL import Image

from .config import LOGO_GLOB_PATTERN


def logo_to_eink(path, target_size):
    img = Image.open(path).convert("L")

    img.thumbnail(
        target_size,
        Image.LANCZOS,
    )

    img_1bit = img.point(
        lambda p: 255 if p > 128 else 0
    ).convert("1")

    return img_1bit


def get_daily_logo_path():
    candidates = sorted(
        glob.glob(LOGO_GLOB_PATTERN)
    )

    if not candidates:
        return None

    today_seed = (
        datetime.now()
        .date()
        .toordinal()
    )

    rng = random.Random(today_seed)

    return rng.choice(candidates)


def list_logos():
    return sorted(
        glob.glob(LOGO_GLOB_PATTERN)
    )
