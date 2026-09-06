#!/usr/bin/env python3
"""
docker_monitor.py

Runs on the NUC. Polls Docker container status/health, renders a
monochrome bitmap sized for the Badger 2040's 296x128 e-ink display,
and pushes it over USB serial to the Badger, which just displays
whatever image it receives.

Behavior:
    - No problems  -> logo.jpg shown ONCE when state becomes OK,
                      then the display is left alone (no refreshes)
                      until something actually changes.
    - Any problem  -> alert screen shown, but the DISPLAY is only
                      refreshed every --alert-interval seconds (default
                      600s / 10 min) to avoid hammering the e-ink panel
                      while still checking Docker status every --interval
                      seconds under the hood.

Requires:
    pip install docker pillow pyserial

Place a file called logo.jpg in the same folder as this script —
it will be dithered/thresholded to 1-bit and shown as the "all clear"
screen instead of the old smiley.

Usage:
    can be both ttyACM0 or ACM1, find right one
    python3 docker_monitor.py --port /dev/ttyACM1 --interval 60
"""

import argparse
import os
import struct
import sys
import time
from datetime import datetime

import docker
import serial
from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 296, 128

# Path to the logo shown on the "all clear" screen. Relative to this
# script's own folder, so it works regardless of the working directory
# the script is launched from (e.g. via systemd's WorkingDirectory).
LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.jpg")

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


def render_all_clear_screen():
    """
    All-clear screen. Shows logo.jpg centered, full-size. Falls back
    to a plain text message if the logo file is missing, so the
    script doesn't crash if you forget to copy it over.
    """
    img = Image.new("1", (WIDTH, HEIGHT), 1)
    draw = ImageDraw.Draw(img)

    if os.path.exists(LOGO_PATH):
        # Leave a little room at the bottom for the timestamp.
        logo = logo_to_eink(LOGO_PATH, target_size=(WIDTH - 10, HEIGHT - 16))
        x = (WIDTH - logo.width) // 2
        y = ((HEIGHT - 16) - logo.height) // 2
        img.paste(logo, (x, y))
    else:
        draw_centered_text(draw , HEIGHT // 2 - 26, f"X_X", get_font(30))
        draw_centered_text(draw, HEIGHT // 2 - 8, f"logo.jpg missing", get_font(10))

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
    img = Image.new("1", (WIDTH, HEIGHT), 1)
    draw = ImageDraw.Draw(img)
    big_font = get_font(20)
    small_font = get_font(12)

    draw.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), outline=0, width=3)
    draw.text((10, 8), "!! WARNING !!", font=big_font, fill=0)

    y = 40
    for name, status, healthy in problems[:4]:
        reason = "down" if status != "running" else "unhealthy"
        draw.text((10, y), f"{name[:18]}: {reason}", font=small_font, fill=0)
        y += 16

    timestamp = datetime.now().strftime("%H:%M:%S")
    draw.text((10, HEIGHT - 14), timestamp, font=get_font(10), fill=0)
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

    while True:
        try:
            statuses = get_container_statuses(client, WATCHED_CONTAINERS)
            problems = [(n, s, h) for n, s, h in statuses if is_problem(s, h)]

            now = time.time()

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

                # Only push when TRANSITIONING into OK state, not on every check.
                if last_pushed_state != "ok":
                    img = render_all_clear_screen()
                    send_frame(ser, img)
                    last_pushed_state = "ok"
                else:
                    print("  (already showing all-clear, skipping refresh)")

                last_alert_push = 0.0

        except Exception as e:
            print(f"Error during check: {e}", file=sys.stderr)

        time.sleep(args.interval)


if __name__ == "__main__":
    main()
