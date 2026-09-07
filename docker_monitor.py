#!/usr/bin/env python3
"""
docker_monitor.py

Runs on the NUC. Polls Docker container status/health, renders a
monochrome bitmap sized for the Badger 2040's 296x128 e-ink display,
and pushes it over USB serial to the Badger. The Badger also sends
button-press bytes back over the same connection.

Views (cycled with button B):
    "auto"       - normal all-clear (logo) / breach alert behavior
    "containers" - manual scrollable list of every watched container
    "stats"      - basic NUC system stats (uptime, disk, load, mem)

Button mapping:
    A       - force an immediate Docker check + redraw
    B       - cycle view: auto -> containers -> stats -> auto ...
    C       - context action:
                "auto" + active alert  -> snooze the alert for
                                           --snooze-minutes (default 30)
                "containers"           -> arm restart on the selected
                                           container; press C again
                                           within 10s to confirm and
                                           actually restart it
                "stats"                -> no-op
    UP/DOWN - context action:
                "containers" -> move the selection cursor
                "auto"       -> manually cycle through logo*.jpg
                                 (only meaningful while healthy)
                "stats"      -> no-op

Requires:
    pip install docker pillow pyserial

Place one or more files named logo.jpg, logo1.jpg, logo2.jpg, etc.
in the same folder as this script — one is picked at random each
day and shown (dithered/thresholded to 1-bit) as the "all clear" screen,
unless manually overridden via UP/DOWN in the "auto" view.

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

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_GLOB_PATTERN = os.path.join(SCRIPT_DIR, "logo*.jpg")
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

VIEWS = ["auto", "containers", "stats"]
CONTAINER_LIST_VISIBLE_ROWS = 6  # how many rows fit on screen at once
RESTART_CONFIRM_WINDOW_SECONDS = 10
DEFAULT_SNOOZE_MINUTES = 30

BUTTON_BYTES = {b"A", b"B", b"C", b"U", b"D"}


# ---------------------------------------------------------------- fonts/logos

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
    img = Image.open(path).convert("L")
    img.thumbnail(target_size, Image.LANCZOS)
    img_1bit = img.point(lambda p: 255 if p > 128 else 0).convert("1")
    return img_1bit


def get_daily_logo_path():
    candidates = sorted(glob.glob(LOGO_GLOB_PATTERN))
    if not candidates:
        return None
    today_seed = datetime.now().date().toordinal()
    rng = random.Random(today_seed)
    return rng.choice(candidates)


def list_logos():
    return sorted(glob.glob(LOGO_GLOB_PATTERN))


# ------------------------------------------------------------- docker status

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


# -------------------------------------------------------------- text helpers

def draw_centered_text(draw, y, text, font, fill=0):
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = (WIDTH - text_width) // 2
    draw.text((x, y), text, font=font, fill=fill)
    return x, y


# ------------------------------------------------------------------ screens

def render_all_clear_screen(logo_path_override=None):
    img = Image.new("1", (WIDTH, HEIGHT), 1)
    draw = ImageDraw.Draw(img)

    logo_path = logo_path_override or get_daily_logo_path()

    if logo_path:
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


def render_alert_screen(problems, snoozed_until=None):
    img = Image.new("1", (WIDTH, HEIGHT), 1)
    draw = ImageDraw.Draw(img)

    banner_height = 40
    y = banner_height + 4

    if os.path.exists(BREACH_IMAGE_PATH):
        banner = logo_to_eink(BREACH_IMAGE_PATH, target_size=(WIDTH - 10, banner_height))
        x = (WIDTH - banner.width) // 2
        by = (banner_height - banner.height) // 2
        img.paste(banner, (x, by))
    else:
        draw.rectangle((0, 0, WIDTH - 1, HEIGHT - 1), outline=0, width=3)
        draw.text((10, 8), "!! WARNING !!", font=get_font(20), fill=0)

    small_font = get_font(12)
    for name, status, healthy in problems[:4]:
        reason = "down" if status != "running" else "unhealthy"
        draw.text((10, y), f"{name[:18]}: {reason}", font=small_font, fill=0)
        y += 16

    if snoozed_until:
        remaining_min = max(0, int((snoozed_until - time.time()) / 60) + 1)
        draw.text((10, HEIGHT - 26), f"snoozed ({remaining_min}m left)", font=get_font(10), fill=0)

    timestamp = datetime.now().strftime("%H:%M:%S")
    draw.text((10, HEIGHT - 14), timestamp, font=get_font(10), fill=0)
    return img


def render_container_list_screen(statuses, selected_idx=0, scroll_offset=0, restart_armed_name=None):
    img = Image.new("1", (WIDTH, HEIGHT), 1)
    draw = ImageDraw.Draw(img)
    title_font = get_font(14)
    row_font = get_font(11)

    draw_centered_text(draw, 2, "Container Status", title_font)
    draw.line((4, 20, WIDTH - 4, 20), fill=0, width=2)

    visible = statuses[scroll_offset:scroll_offset + CONTAINER_LIST_VISIBLE_ROWS]

    y = 26
    for offset, (name, status, healthy) in enumerate(visible):
        idx = scroll_offset + offset
        problem = is_problem(status, healthy)
        marker = "!!" if problem else "OK"
        cursor = ">" if idx == selected_idx else " "
        label = name[:20]
        if restart_armed_name == name:
            label += " (confirm?)"
        draw.text((4, y), f"{cursor}{marker}  {label}", font=row_font, fill=0)
        y += 14

    # Scroll position indicator, if there's more than fits on screen.
    if len(statuses) > CONTAINER_LIST_VISIBLE_ROWS:
        draw.text((WIDTH - 40, 2), f"{selected_idx + 1}/{len(statuses)}", font=get_font(10), fill=0)

    timestamp = datetime.now().strftime("%H:%M:%S")
    draw_centered_text(draw, HEIGHT - 12, timestamp, get_font(10))
    return img


def read_nuc_stats():
    """
    Reads basic system stats using only the standard library — no
    extra pip dependency needed. CPU temp is best-effort since its
    location varies by hardware; falls back to "N/A" if not found.
    """
    stats = {}

    try:
        with open("/proc/uptime") as f:
            uptime_seconds = float(f.read().split()[0])
        days, rem = divmod(int(uptime_seconds), 86400)
        hours, rem = divmod(rem, 3600)
        minutes = rem // 60
        stats["uptime"] = f"{days}d {hours}h {minutes}m"
    except Exception:
        stats["uptime"] = "N/A"

    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        stats["disk"] = f"{used / total * 100:.0f}% used ({free // (2**30)}GB free)"
    except Exception:
        stats["disk"] = "N/A"

    try:
        load1, load5, load15 = os.getloadavg()
        stats["load"] = f"{load1:.2f} / {load5:.2f} / {load15:.2f}"
    except Exception:
        stats["load"] = "N/A"

    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    meminfo[parts[0].strip()] = int(parts[1].strip().split()[0])
        total_kb = meminfo.get("MemTotal", 0)
        avail_kb = meminfo.get("MemAvailable", 0)
        used_pct = (1 - avail_kb / total_kb) * 100 if total_kb else 0
        stats["memory"] = f"{used_pct:.0f}% used"
    except Exception:
        stats["memory"] = "N/A"

    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            temp_c = int(f.read().strip()) / 1000
        stats["temp"] = f"{temp_c:.0f}C"
    except Exception:
        stats["temp"] = "N/A"

    return stats


def render_stats_screen():
    img = Image.new("1", (WIDTH, HEIGHT), 1)
    draw = ImageDraw.Draw(img)
    title_font = get_font(14)
    row_font = get_font(12)

    draw_centered_text(draw, 2, "NUC Stats", title_font)
    draw.line((4, 20, WIDTH - 4, 20), fill=0, width=2)

    stats = read_nuc_stats()
    rows = [
        f"Uptime: {stats['uptime']}",
        f"Load (1/5/15m): {stats['load']}",
        f"Memory: {stats['memory']}",
        f"Disk: {stats['disk']}",
        f"Temp: {stats['temp']}",
    ]

    y = 28
    for row in rows:
        draw.text((6, y), row, font=row_font, fill=0)
        y += 16

    timestamp = datetime.now().strftime("%H:%M:%S")
    draw_centered_text(draw, HEIGHT - 12, timestamp, get_font(10))
    return img


# ------------------------------------------------------------------- serial

def image_to_payload(img):
    packed = img.tobytes()
    header = struct.pack(">2sHH", b"BD", img.width, img.height)
    return header + packed


def send_frame(ser, img):
    payload = image_to_payload(img)
    ser.write(payload)
    ser.flush()


def read_pending_buttons(ser):
    """
    Non-blocking read of any queued button-press bytes. Returns a
    list of bytes in the order received (there may be several if
    presses queued up while we were doing other work).
    """
    presses = []
    while ser.in_waiting > 0:
        byte = ser.read(1)
        if byte in BUTTON_BYTES:
            presses.append(byte)
    return presses


# --------------------------------------------------------------------- main

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
    parser.add_argument(
        "--button-poll-interval",
        type=float,
        default=0.2,
        help="Seconds between checks for button presses (default 0.2 — keeps the badge responsive)",
    )
    parser.add_argument(
        "--snooze-minutes",
        type=int,
        default=DEFAULT_SNOOZE_MINUTES,
        help="How long the C button snoozes an active alert for (default 30)",
    )
    args = parser.parse_args()

    client = docker.from_env()

    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"Could not open serial port {args.port}: {e}", file=sys.stderr)
        sys.exit(1)

    time.sleep(2)

    print(
        f"Monitoring containers every {args.interval}s. "
        f"Alert refresh every {args.alert_interval}s. Port: {args.port}. Ctrl+C to stop."
    )

    # --- persistent state across loop iterations ---
    view_index = 0
    last_check_time = 0.0
    force_refresh = False
    needs_redraw = True  # draw something on first loop

    last_pushed_signature = None  # tracks (view, content-hash-ish) to avoid redundant pushes

    manual_logo_index = None  # None = automatic daily pick
    selected_container_idx = 0
    container_scroll_offset = 0

    snooze_until = 0.0
    restart_armed_name = None
    restart_armed_deadline = 0.0

    statuses = []
    problems = []

    while True:
        try:
            now = time.time()
            current_view = VIEWS[view_index]

            # ---- handle any queued button presses ----
            for press in read_pending_buttons(ser):
                if press == b"A":
                    force_refresh = True
                    print(f"[{datetime.now().isoformat(timespec='seconds')}] Button A: force refresh")

                elif press == b"B":
                    view_index = (view_index + 1) % len(VIEWS)
                    current_view = VIEWS[view_index]
                    # Reset per-view ephemeral state on switch.
                    selected_container_idx = 0
                    container_scroll_offset = 0
                    needs_redraw = True
                    print(f"[{datetime.now().isoformat(timespec='seconds')}] Button B: view -> {current_view}")

                elif press == b"C":
                    if current_view == "auto":
                        if problems:
                            snooze_until = now + args.snooze_minutes * 60
                            needs_redraw = True
                            print(f"[{datetime.now().isoformat(timespec='seconds')}] Button C: snoozed for {args.snooze_minutes}m")
                    elif current_view == "containers" and statuses:
                        target_name = statuses[selected_container_idx][0]
                        if restart_armed_name == target_name and now < restart_armed_deadline:
                            # Confirmed — actually restart it.
                            print(f"[{datetime.now().isoformat(timespec='seconds')}] Button C: restarting {target_name}")
                            try:
                                client.containers.get(target_name).restart()
                            except Exception as e:
                                print(f"  restart failed: {e}", file=sys.stderr)
                            restart_armed_name = None
                            force_refresh = True
                        else:
                            # Arm it — needs a second press within the window to confirm.
                            restart_armed_name = target_name
                            restart_armed_deadline = now + RESTART_CONFIRM_WINDOW_SECONDS
                            needs_redraw = True
                            print(f"[{datetime.now().isoformat(timespec='seconds')}] Button C: armed restart on {target_name} (confirm within {RESTART_CONFIRM_WINDOW_SECONDS}s)")
                    # "stats" view: no-op for C

                elif press == b"U":
                    if current_view == "containers" and statuses:
                        selected_container_idx = max(0, selected_container_idx - 1)
                        if selected_container_idx < container_scroll_offset:
                            container_scroll_offset = selected_container_idx
                        needs_redraw = True
                    elif current_view == "auto" and not problems:
                        logos = list_logos()
                        if logos:
                            idx = manual_logo_index if manual_logo_index is not None else 0
                            manual_logo_index = (idx - 1) % len(logos)
                            needs_redraw = True

                elif press == b"D":
                    if current_view == "containers" and statuses:
                        selected_container_idx = min(len(statuses) - 1, selected_container_idx + 1)
                        if selected_container_idx >= container_scroll_offset + CONTAINER_LIST_VISIBLE_ROWS:
                            container_scroll_offset = selected_container_idx - CONTAINER_LIST_VISIBLE_ROWS + 1
                        needs_redraw = True
                    elif current_view == "auto" and not problems:
                        logos = list_logos()
                        if logos:
                            idx = manual_logo_index if manual_logo_index is not None else 0
                            manual_logo_index = (idx + 1) % len(logos)
                            needs_redraw = True

            # Restart-arm window expiring on its own (no second press in time).
            if restart_armed_name and now >= restart_armed_deadline:
                print(f"[{datetime.now().isoformat(timespec='seconds')}] Restart confirm window expired for {restart_armed_name}")
                restart_armed_name = None
                needs_redraw = True

            # Snooze expiring on its own.
            if snooze_until and now >= snooze_until:
                snooze_until = 0.0
                needs_redraw = True

            # ---- decide whether to actually poll Docker this cycle ----
            due_for_check = (now - last_check_time) >= args.interval
            if due_for_check or force_refresh:
                last_check_time = now
                statuses = get_container_statuses(client, WATCHED_CONTAINERS)
                problems = [(n, s, h) for n, s, h in statuses if is_problem(s, h)]
                needs_redraw = True
                force_refresh = False

            # ---- render + push, only if something warrants it ----
            if needs_redraw:
                if current_view == "containers":
                    img = render_container_list_screen(
                        statuses,
                        selected_idx=selected_container_idx,
                        scroll_offset=container_scroll_offset,
                        restart_armed_name=restart_armed_name,
                    )
                    send_frame(ser, img)
                    print(f"[{datetime.now().isoformat(timespec='seconds')}] Redrew: containers view")

                elif current_view == "stats":
                    img = render_stats_screen()
                    send_frame(ser, img)
                    print(f"[{datetime.now().isoformat(timespec='seconds')}] Redrew: stats view")

                else:  # "auto"
                    if problems and now >= snooze_until:
                        img = render_alert_screen(problems, snoozed_until=None)
                        send_frame(ser, img)
                        print(f"[{datetime.now().isoformat(timespec='seconds')}] Redrew: ALERT {problems}")
                    elif problems and now < snooze_until:
                        img = render_alert_screen(problems, snoozed_until=snooze_until)
                        send_frame(ser, img)
                        print(f"[{datetime.now().isoformat(timespec='seconds')}] Redrew: ALERT (snoozed)")
                    else:
                        logo_override = None
                        if manual_logo_index is not None:
                            logos = list_logos()
                            if logos:
                                logo_override = logos[manual_logo_index % len(logos)]
                        img = render_all_clear_screen(logo_path_override=logo_override)
                        send_frame(ser, img)
                        print(f"[{datetime.now().isoformat(timespec='seconds')}] Redrew: all-clear")

                needs_redraw = False

        except Exception as e:
            print(f"Error during check: {e}", file=sys.stderr)

        time.sleep(args.button_poll_interval)


if __name__ == "__main__":
    main()
