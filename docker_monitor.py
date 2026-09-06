#!/usr/bin/env python3
"""
docker_monitor.py

Runs on the NUC. Polls Docker container status/health, renders a
monochrome bitmap sized for the Badger 2040's 296x128 e-ink display,
and pushes it over USB serial to the Badger, which just displays
whatever image it receives.

Behavior:
    - No problems  -> a random logo*.jpg (from this script's folder)
                      is shown, chosen once per day and refreshed
                      only on state change or day rollover.
    - Any problem  -> "breach.jpg" banner shown, but the DISPLAY is only
                      refreshed every --alert-interval seconds (default
                      600s / 10 min) to avoid hammering the e-ink panel
                      while still checking Docker status every --interval
                      seconds under the hood.

Requires:
    pip install docker pillow pyserial

Place one or more files named logo.jpg, logo1.jpg, logo2.jpg, etc.
in the same folder as this script — one is picked at random each
day and shown (dithered/thresholded to 1-bit) as the "all clear" screen.

Place a file named breach.jpg in the same folder — it's shown as the
banner at the top of the alert screen instead of plain "!! WARNING !!"
text. Falls back to the old text banner if breach.jpg is missing.

Usage:
    can be both ttyACM0 or ACM1, find right one
    python3 docker_monitor.py --port /dev/ttyACM1 --interval 60
"""

import argparse
import glob
import os
import random
import struct
import sys
import time
from datetime import datetime

import docker
import serial
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 296, 128

# Folder this script lives in — used to resolve logo/font paths regardless
# of the working directory the script is launched from.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Matches logo.jpg, logo1.jpg, logo2.jpg, logo23.jpg, etc.
LOGO_GLOB_PATTERN = os.path.join(SCRIPT_DIR, "logo*.jpg")

# Banner shown at the top of the alert screen, replacing the old
# rectangle border + "!! WARNING !!" text.
BREACH_IMAGE_PATH = os.path.join(SCRIPT_DIR, "breach.jpg")

WATCHED_CONTAINERS = [
   "immich_redis",
   "watchtower",
   "mosquitto",
   "homeassistant",
   "zigbee2mqtt",
   "immich_server",
   "immich_postgres",
   "immich_machine_learning",
]


def get_font(size=14):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def logo_to_eink(path, target_size):
    """
    Loads an image file, converts it to grayscale, resizes to fit
    within target_size (keeping aspect ratio), and thresholds it to
    pure 1-bit black/white for the e-ink display.
    """
    img = Image.open(path).convert("L")
    img.thumbnail(target_size, Image.LANCZOS)
    img_1bit = img.point(lambda p: 255 if p > 128 else 0).convert("1")
    return img_1bit


def get_daily_logo_path():
    """
    Picks one logo*.jpg from the script's folder, deterministically
    based on today's date — so the choice stays the same all day, but
    a new pick happens on a new day. No state file needed to remember
    yesterday's choice, since the date itself is the seed.
    Returns None if no logo*.jpg files are found.
    """
    candidates = sorted(glob.glob(LOGO_GLOB_PATTERN))
    if not candidates:
        return None

    today_seed = datetime.now().date().toordinal()
    rng = random.Random(today_seed)
    return rng.choice(candidates)


def list_logos():
    """
    Returns all logo*.jpg files found next to this script, sorted.
    Handy for previewing: list_logos()[2] gives you the 3rd one, etc.
    """
    return sorted(glob.glob(LOGO_GLOB_PATTERN))


def get_container_statuses(client, watched):
    results = []
    containers = {c.name: c for c in client.containers.list(all=True)}
    names = watched if watched else list(containers.keys())

    for name in names:
        c = containers.get(name)
        if c is None:
            results.append((name, "missing", False))
            continue

        c.reload()
        status = c.status
        health = None
        health_info = c.attrs.get("State", {}).get("Health")
        if health_info:
            health = health_info.get("Status") == "healthy"

        results.append((name, status, health))

    return results


def is_problem(status, healthy):
    if status != "running":
        return True
    if healthy is False:
        return True
    return False


def render_all_clear_screen(logo_path_override=None):
    """
    All-clear screen. Shows one of the logo*.jpg files, chosen
    deterministically for today's date (see get_daily_logo_path),
    centered and scaled to fit. Falls back to the X_X text screen if
    no logo files are found, so the script doesn't crash if you
    forget to copy any over.

    Pass logo_path_override to force a specific logo file instead of
    the daily pick — handy for previewing individual logos in the
    scratchpad without waiting for the date-based rotation to land
    on the one you want to check.
    """
    img = Image.new("1", (WIDTH, HEIGHT), 1)
    draw = ImageDraw.Draw(img)

    logo_path = logo_path_override or get_daily_logo_path()

    if logo_path:
        # Leave a little room at the bottom for the timestamp.
        logo = logo_to_eink(logo_path, target_size=(WIDTH - 10, HEIGHT - 16))
        x = (WIDTH - logo.width) // 2
        y = ((HEIGHT - 16) - logo.height) // 2
        img.paste(logo, (x, y))
    else:
        draw_centered_text(draw, HEIGHT // 2 - 26, "X_X", get_font(30))
        draw_centered_text(draw, HEIGHT // 2 - 8, "no logo*.jpg found", get_font(10))

#   remove comments if you want a timestamp
#    timestamp = datetime.now().strftime("%H:%M:%S")
#    draw_centered_text(draw, HEIGHT - 12, f" {timestamp}", get_font(10))
    return img

def draw_centered_text(draw, y, text, font, fill=0):
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = (WIDTH - text_width) // 2
    draw.text((x, y), text, font=font, fill=fill)
    return x, y


def render_alert_screen(problems):
    """
    Alert screen. Shows breach.jpg as the top banner if it exists
    (a "BREACH DETECTED" style graphic), falling back to the old
    rectangle-border + "!! WARNING !!" text if the file is missing —
    so the script keeps working even if you forget to copy it over.
    """
    img = Image.new("1", (WIDTH, HEIGHT), 1)
    draw = ImageDraw.Draw(img)

    banner_height = 40  # reserved space at the top for the banner
    y = banner_height + 4

    if os.path.exists(BREACH_IMAGE_PATH):
        banner = logo_to_eink(BREACH_IMAGE_PATH, target_size=(WIDTH - 10, banner_height))
        x = (WIDTH - banner.width) // 2
        by = (banner_height - banner.height) // 2
        img.paste(banner, (x, by))
    else:
        draw.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), outline=0, width=3)
        draw_centered_text(draw, 10, "!! WARNING !!", font=get_font(20), fill=0)

    timestamp = datetime.now().strftime("%H:%M:%S")
    draw_centered_text(draw, HEIGHT // 3.6, f" {timestamp}", get_font(10))

    draw.line((0, HEIGHT // 2.7, WIDTH, HEIGHT // 2.7), fill=0, width=2)

    small_font = get_font(12)
    for name, status, healthy in problems[:4]:
        reason = "down" if status != "running" else "unhealthy"
        draw_centered_text(draw, y + 10, f"{name[:18]}: {reason}", font=small_font, fill=0)
        y += 16

    return img


def image_to_payload(img):
    """
    Packs a 1-bit PIL image into a simple framed payload:
    [MAGIC 2 bytes][width 2 bytes][height 2 bytes][data...]
    1 bpp packed MSB-first, row-major (standard PBM-style packing).
    """
    packed = img.tobytes()
    header = struct.pack(">2sHH", b"BD", img.width, img.height)
    return header + packed


def send_frame(ser, img):
    payload = image_to_payload(img)
    ser.write(payload)
    ser.flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyACM0", help="Serial port for the Badger")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--interval", type=int, default=60, help="Seconds between Docker checks")
    parser.add_argument(
        "--alert-interval",
        type=int,
        default=600,
        help="Seconds between display refreshes while a problem is active (default 600 = 10 min)",
    )
    args = parser.parse_args()

    client = docker.from_env()

    try:
        ser = serial.Serial(args.port, args.baud, timeout=2)
    except serial.SerialException as e:
        print(f"Could not open serial port {args.port}: {e}", file=sys.stderr)
        sys.exit(1)

    time.sleep(2)

    print(
        f"Monitoring containers every {args.interval}s. "
        f"Alert screen refreshes at most every {args.alert_interval}s. "
        f"Port: {args.port}. Ctrl+C to stop."
    )

    last_alert_push = 0.0
    # Tracks the last state actually pushed to the display: "ok", "alert", or None.
    last_pushed_state = None
    # Tracks the date we last showed the all-clear logo, so a new day
    # triggers a refresh (new daily logo) even if nothing else changed.
    last_ok_date = None

    while True:
        try:
            statuses = get_container_statuses(client, WATCHED_CONTAINERS)
            problems = [(n, s, h) for n, s, h in statuses if is_problem(s, h)]

            now = time.time()
            today = datetime.now().date()

            if problems:
                print(f"[{datetime.now().isoformat(timespec='seconds')}] ALERT: {problems}")

                if now - last_alert_push >= args.alert_interval:
                    img = render_alert_screen(problems)
                    send_frame(ser, img)
                    last_alert_push = now
                    last_pushed_state = "alert"
                else:
                    remaining = int(args.alert_interval - (now - last_alert_push))
                    print(f"  (skipping display refresh, next alert push in {remaining}s)")
            else:
                print(f"[{datetime.now().isoformat(timespec='seconds')}] OK ({len(statuses)} containers)")

                # Push when TRANSITIONING into OK state, OR when the day
                # has rolled over since we last showed the all-clear logo
                # (so the daily logo rotation actually takes effect).
                if last_pushed_state != "ok" or last_ok_date != today:
                    img = render_all_clear_screen()
                    send_frame(ser, img)
                    last_pushed_state = "ok"
                    last_ok_date = today
                else:
                    print("  (already showing all-clear, skipping refresh)")

                last_alert_push = 0.0

        except Exception as e:
            print(f"Error during check: {e}", file=sys.stderr)

        time.sleep(args.interval)


if __name__ == "__main__":
    main()