"""Logo discovery and e-ink image conversion."""

import glob
import random
from datetime import datetime

from PIL import Image

from .config import (
    LOGO_GLOB_PATTERN,
    LOGO_INVERT_INK_THRESHOLD,
)


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


def ink_ratio(img_1bit):
    pixels = list(img_1bit.getdata())

    if not pixels:
        return 0.0

    black = sum(
        1
        for p in pixels
        if p == 0
    )

    return black / len(pixels)


def should_invert(img_1bit):
    return (
        ink_ratio(img_1bit)
        < LOGO_INVERT_INK_THRESHOLD
    )


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

    yesterday_pick = random.Random(
        today_seed - 1
    ).choice(candidates)

    pool = [
        c
        for c in candidates
        if c != yesterday_pick
    ] or candidates

    rng = random.Random(today_seed)

    return rng.choice(pool)


def list_logos():
    return sorted(
        glob.glob(LOGO_GLOB_PATTERN)
    )
