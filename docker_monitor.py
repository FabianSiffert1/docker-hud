#!/usr/bin/env python3
"""
docker_monitor.py

Docker monitor for a Badger 2040 296x128 e-ink display.

The UI uses a small declarative layout system inspired by Jetpack Compose:
    Column
    Row
    Text
    Bitmap
    Divider
    Spacer

Requires:
    pip install docker pillow pyserial

Usage:
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


# ============================================================================
# Configuration
# ============================================================================

WIDTH, HEIGHT = 296, 128

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

LOGO_GLOB_PATTERN = os.path.join(SCRIPT_DIR, "logo*.jpg")
BREACH_IMAGE_PATH = os.path.join(SCRIPT_DIR, "breach.jpg")
BREACH_ICON_PATH = os.path.join(SCRIPT_DIR, "mgsAlert.jpg")

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

CONTAINER_LIST_VISIBLE_ROWS = 6
RESTART_CONFIRM_WINDOW_SECONDS = 10
DEFAULT_SNOOZE_MINUTES = 30

BUTTON_BYTES = {b"A", b"B", b"C", b"U", b"D"}


# ============================================================================
# Fonts
# ============================================================================

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


# ============================================================================
# Small declarative layout system
# ============================================================================

class Component:
    """
    Base class for everything that can be rendered.

    render() returns the height actually consumed by the component.
    """

    def measure(self, draw, width, height):
        return width, 0

    def render(self, draw, x, y, width, height):
        return 0


class Text(Component):
    def __init__(
        self,
        text,
        font,
        *,
        align="left",
        fill=0,
    ):
        self.text = text
        self.font = font
        self.align = align
        self.fill = fill

    def measure(self, draw, width, height):
        bbox = draw.textbbox(
            (0, 0),
            self.text,
            font=self.font,
        )

        return width, bbox[3] - bbox[1]

    def render(self, draw, x, y, width, height):
        bbox = draw.textbbox(
            (0, 0),
            self.text,
            font=self.font,
        )

        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        if self.align == "center":
            text_x = x + (width - text_width) // 2

        elif self.align == "right":
            text_x = x + width - text_width

        else:
            text_x = x

        draw.text(
            (text_x, y),
            self.text,
            font=self.font,
            fill=self.fill,
        )

        return text_height


class Divider(Component):
    def __init__(self, thickness=2, margin=0):
        self.thickness = thickness
        self.margin = margin

    def measure(self, draw, width, height):
        return width, self.thickness + self.margin * 2

    def render(self, draw, x, y, width, height):
        line_y = y + self.margin

        draw.line(
            (x, line_y, x + width, line_y),
            fill=0,
            width=self.thickness,
        )

        return self.thickness + self.margin * 2


class Spacer(Component):
    def __init__(self, weight=1):
        self.weight = weight

    def measure(self, draw, width, height):
        return width, 0


class Bitmap(Component):
    def __init__(
        self,
        image,
        *,
        align="center",
    ):
        self.image = image
        self.align = align

    def measure(self, draw, width, height):
        return self.image.width, self.image.height

    def render(self, draw, x, y, width, height):
        if self.align == "center":
            image_x = x + (width - self.image.width) // 2

        elif self.align == "right":
            image_x = x + width - self.image.width

        else:
            image_x = x

        canvas = getattr(
            draw,
            "_layout_canvas",
            None,
        )

        if canvas is None:
            raise RuntimeError(
                "Bitmap requires a layout canvas"
            )

        canvas.paste(
            self.image,
            (image_x, y),
        )

        return self.image.height


class Row(Component):
    def __init__(
        self,
        children,
        *,
        gap=0,
        padding=0,
        vertical_align="top",
    ):
        self.children = children
        self.gap = gap
        self.padding = padding
        self.vertical_align = vertical_align

    def measure(self, draw, width, height):
        content_width = max(
            0,
            width - self.padding * 2,
        )

        fixed_width = 0
        max_height = 0
        spacer_count = 0

        for child in self.children:
            if isinstance(child, Spacer):
                spacer_count += child.weight
                continue

            child_width, child_height = child.measure(
                draw,
                content_width,
                height,
            )

            fixed_width += child_width
            max_height = max(
                max_height,
                child_height,
            )

        fixed_width += self.gap * max(
            0,
            len(self.children) - 1,
        )

        return (
            min(
                width,
                fixed_width + self.padding * 2,
            ),
            max_height + self.padding * 2,
        )

    def render(self, draw, x, y, width, height):
        content_x = x + self.padding
        content_y = y + self.padding
        content_width = width - self.padding * 2
        content_height = height - self.padding * 2

        fixed_width = 0
        spacer_weight = 0
        child_sizes = []

        for child in self.children:
            if isinstance(child, Spacer):
                spacer_weight += child.weight
                child_sizes.append(
                    (child, 0, 0)
                )
                continue

            child_width, child_height = child.measure(
                draw,
                content_width,
                content_height,
            )

            fixed_width += child_width

            child_sizes.append(
                (
                    child,
                    child_width,
                    child_height,
                )
            )

        gaps = self.gap * max(
            0,
            len(self.children) - 1,
        )

        remaining_width = max(
            0,
            content_width
            - fixed_width
            - gaps,
        )

        spacer_width = (
            remaining_width / spacer_weight
            if spacer_weight
            else 0
        )

        cursor_x = content_x
        max_height = 0

        for child, child_width, child_height in child_sizes:

            if isinstance(child, Spacer):
                cursor_x += int(
                    spacer_width * child.weight
                )
                continue

            if self.vertical_align == "center":
                child_y = (
                    content_y
                    + (
                        content_height
                        - child_height
                    ) // 2
                )

            elif self.vertical_align == "bottom":
                child_y = (
                    content_y
                    + content_height
                    - child_height
                )

            else:
                child_y = content_y

            child.render(
                draw,
                cursor_x,
                child_y,
                child_width,
                child_height,
            )

            cursor_x += (
                child_width
                + self.gap
            )

            max_height = max(
                max_height,
                child_height,
            )

        return max_height + self.padding * 2


class Column(Component):
    def __init__(
        self,
        children,
        *,
        gap=0,
        padding=0,
        horizontal_align="left",
    ):
        self.children = children
        self.gap = gap
        self.padding = padding
        self.horizontal_align = horizontal_align

    def render(self, draw, x, y, width, height):
        content_x = x + self.padding
        content_y = y + self.padding

        content_width = max(
            0,
            width - self.padding * 2,
        )

        content_height = max(
            0,
            height - self.padding * 2,
        )

        fixed_height = 0
        spacer_weight = 0
        child_sizes = []

        for child in self.children:
            if isinstance(child, Spacer):
                spacer_weight += child.weight
                child_sizes.append((child, 0))
                continue

            _, child_height = child.measure(
                draw,
                content_width,
                content_height,
            )

            fixed_height += child_height
            child_sizes.append((child, child_height))

        gaps = self.gap * max(
            0,
            len(self.children) - 1,
        )

        remaining_height = max(
            0,
            content_height
            - fixed_height
            - gaps,
        )

        spacer_height = (
            remaining_height / spacer_weight
            if spacer_weight
            else 0
        )

        cursor_y = content_y

        for child, child_height in child_sizes:
            if isinstance(child, Spacer):
                cursor_y += int(
                    spacer_height * child.weight
                )
                continue

            child.render(
                draw,
                content_x,
                cursor_y,
                content_width,
                child_height,
            )

            cursor_y += child_height + self.gap

        return min(
            height,
            cursor_y - y + self.padding,
        )

def render_layout(layout):
    img = Image.new(
        "1",
        (WIDTH, HEIGHT),
        1,
    )

    draw = ImageDraw.Draw(img)

    draw._layout_canvas = img

    layout.render(
        draw,
        0,
        0,
        WIDTH,
        HEIGHT,
    )

    return img


# ============================================================================
# Images
# ============================================================================

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


# ============================================================================
# Docker status
# ============================================================================

def get_container_statuses(client, watched):
    results = []

    containers = {
        c.name: c
        for c in client.containers.list(all=True)
    }

    names = (
        watched
        if watched
        else list(containers.keys())
    )

    for name in names:
        container = containers.get(name)

        if container is None:
            results.append(
                (name, "missing", False)
            )
            continue

        container.reload()

        status = container.status
        health = None

        health_info = (
            container.attrs
            .get("State", {})
            .get("Health")
        )

        if health_info:
            health = (
                health_info.get("Status")
                == "healthy"
            )

        results.append(
            (
                name,
                status,
                health,
            )
        )

    return results


def is_problem(status, healthy):
    if status != "running":
        return True

    if healthy is False:
        return True

    return False


# ============================================================================
# Stats
# ============================================================================

def read_nuc_stats():
    stats = {}

    try:
        with open("/proc/uptime") as f:
            uptime_seconds = float(
                f.read().split()[0]
            )

        days, rem = divmod(
            int(uptime_seconds),
            86400,
        )

        hours, rem = divmod(
            rem,
            3600,
        )

        minutes = rem // 60

        stats["uptime"] = (
            f"{days}d {hours}h {minutes}m"
        )

    except Exception:
        stats["uptime"] = "N/A"

    try:
        import shutil

        total, used, free = (
            shutil.disk_usage("/")
        )

        stats["disk"] = (
            f"{used / total * 100:.0f}% used "
            f"({free // (2**30)}GB free)"
        )

    except Exception:
        stats["disk"] = "N/A"

    try:
        load1, load5, load15 = (
            os.getloadavg()
        )

        stats["load"] = (
            f"{load1:.2f} / "
            f"{load5:.2f} / "
            f"{load15:.2f}"
        )

    except Exception:
        stats["load"] = "N/A"

    try:
        with open("/proc/meminfo") as f:
            meminfo = {}

            for line in f:
                parts = line.split(":")

                if len(parts) == 2:
                    meminfo[
                        parts[0].strip()
                    ] = int(
                        parts[1]
                        .strip()
                        .split()[0]
                    )

        total_kb = meminfo.get(
            "MemTotal",
            0,
        )

        avail_kb = meminfo.get(
            "MemAvailable",
            0,
        )

        used_pct = (
            (
                1
                - avail_kb / total_kb
            )
            * 100
            if total_kb
            else 0
        )

        stats["memory"] = (
            f"{used_pct:.0f}% used"
        )

    except Exception:
        stats["memory"] = "N/A"

    try:
        with open(
            "/sys/class/thermal/"
            "thermal_zone0/temp"
        ) as f:
            temp_c = (
                int(f.read().strip())
                / 1000
            )

        stats["temp"] = (
            f"{temp_c:.0f}C"
        )

    except Exception:
        stats["temp"] = "N/A"

    return stats


# ============================================================================
# UI components
# ============================================================================

def timestamp_component():
    return Text(
        datetime.now().strftime("%H:%M:%S"),
        get_font(10),
        align="center",
    )


def stats_screen():
    stats = read_nuc_stats()

    return Column(
        [
            Text(
                "NUC Stats",
                get_font(14),
                align="center",
            ),
            Spacer(),
            Divider(),

            Text(
                f"Uptime: {stats['uptime']}",
                get_font(12),
            ),

            Text(
                f"Load (1/5/15m): {stats['load']}",
                get_font(12),
            ),

            Text(
                f"Memory: {stats['memory']}",
                get_font(12),
            ),

            Text(
                f"Disk: {stats['disk']}",
                get_font(12),
            ),

            Text(
                f"Temp: {stats['temp']}",
                get_font(12),
            ),

            Spacer(),

            timestamp_component(),
        ],
        gap=2,
        padding=6,
    )


def container_list_screen(
    statuses,
    selected_idx=0,
    scroll_offset=0,
    restart_armed_name=None,
):
    children = [
        Text(
            "Container Status",
            get_font(14),
            align="center",
        ),

        Divider(),
    ]

    end_idx = min(
        len(statuses),
        scroll_offset + CONTAINER_LIST_VISIBLE_ROWS,
    )

    visible = statuses[
        scroll_offset:end_idx
    ]

    for visible_idx, (
        name,
        status,
        healthy,
    ) in enumerate(visible):

        actual_idx = (
            scroll_offset
            + visible_idx
        )

        problem = is_problem(
            status,
            healthy,
        )

        marker = (
            "!!"
            if problem
            else "OK"
        )

        cursor = (
            ">"
            if actual_idx == selected_idx
            else " "
        )

        label = name[:20]

        if restart_armed_name == name:
            label += " (confirm?)"

        children.append(
            Text(
                f"{cursor}{marker}  {label}",
                get_font(11),
            )
        )

    children.extend([
        Spacer(),
        timestamp_component(),
    ])

    if len(statuses) > CONTAINER_LIST_VISIBLE_ROWS:
        children.insert(
            1,
            Text(
                f"{selected_idx + 1}/{len(statuses)}",
                get_font(10),
                align="right",
            ),
        )

    return Column(
        children,
        gap=1,
        padding=4,
    )


def alert_screen(
    problems,
    snoozed_until=None,
):
    children = []

    if os.path.exists(
        BREACH_IMAGE_PATH
    ):
        banner = logo_to_eink(
            BREACH_IMAGE_PATH,
            target_size=(
                WIDTH - 10,
                40,
            ),
        )

        children.append(
            Bitmap(
                banner,
                align="center",
            )
        )

    else:
        children.append(
            Text(
                "!! WARNING !!",
                get_font(20),
                align="center",
            )
        )

    for name, status, healthy in problems[:4]:
        reason = (
            "down"
            if status != "running"
            else "unhealthy"
        )

        children.append(
            Text(
                f"{name[:18]}: {reason}",
                get_font(12),
                align="center",
            )
        )

    if snoozed_until:
        remaining_min = max(
            0,
            int(
                (
                    snoozed_until
                    - time.time()
                )
                / 60
            ) + 1,
        )

        children.append(
            Text(
                f"snoozed ({remaining_min}m left)",
                get_font(10),
                align="center",
            )
        )

    children.extend([
        Spacer(),
        timestamp_component(),
    ])

    return Column(
        children,
        gap=1,
        padding=6,
        horizontal_align="center",
    )


def all_clear_screen(
    logo_path_override=None,
):
    logo_path = (
        logo_path_override
        or get_daily_logo_path()
    )

    if logo_path:
        logo = logo_to_eink(
            logo_path,
            target_size=(
                WIDTH - 10,
                HEIGHT - 16,
            ),
        )

        return Column(
            [
                Spacer(),

                Bitmap(
                    logo,
                    align="center",
                ),

                Spacer(),
            ],
            padding=5,
        )

    return Column(
        [
            Spacer(),

            Text(
                "X_X",
                get_font(30),
                align="center",
            ),

            Text(
                "no logo*.jpg found",
                get_font(10),
                align="center",
            ),

            Spacer(),
        ],
        padding=5,
        horizontal_align="center",
    )


# ============================================================================
# Serial protocol
# ============================================================================

def image_to_payload(img):
    packed = img.tobytes()

    header = struct.pack(
        ">2sHH",
        b"BD",
        img.width,
        img.height,
    )

    return header + packed


def send_frame(ser, img):
    payload = image_to_payload(img)

    ser.write(payload)
    ser.flush()


def read_pending_buttons(ser):
    presses = []

    while ser.in_waiting > 0:
        byte = ser.read(1)

        if byte in BUTTON_BYTES:
            presses.append(byte)

    return presses


# ============================================================================
# Rendering
# ============================================================================

def render_current_view(
    current_view,
    statuses,
    problems,
    selected_container_idx,
    container_scroll_offset,
    restart_armed_name,
    manual_logo_index,
    snooze_until,
):
    if current_view == "containers":
        layout = container_list_screen(
            statuses,
            selected_idx=selected_container_idx,
            scroll_offset=container_scroll_offset,
            restart_armed_name=restart_armed_name,
        )

    elif current_view == "stats":
        layout = stats_screen()

    else:
        now = time.time()

        if problems and now >= snooze_until:
            layout = alert_screen(
                problems,
                snoozed_until=None,
            )

        elif problems and now < snooze_until:
            layout = alert_screen(
                problems,
                snoozed_until=snooze_until,
            )

        else:
            logo_override = None

            if manual_logo_index is not None:
                logos = list_logos()

                if logos:
                    logo_override = logos[
                        manual_logo_index
                        % len(logos)
                    ]

            layout = all_clear_screen(
                logo_path_override=logo_override,
            )

    return render_layout(layout)


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--port",
        default="/dev/ttyACM0",
        help="Serial port for the Badger",
    )

    parser.add_argument(
        "--baud",
        type=int,
        default=115200,
    )

    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between Docker checks",
    )

    parser.add_argument(
        "--button-poll-interval",
        type=float,
        default=0.2,
        help="Seconds between button checks",
    )

    parser.add_argument(
        "--snooze-minutes",
        type=int,
        default=DEFAULT_SNOOZE_MINUTES,
        help="Alert snooze duration",
    )

    args = parser.parse_args()

    client = docker.from_env()

    try:
        ser = serial.Serial(
            args.port,
            args.baud,
            timeout=0.1,
        )

    except serial.SerialException as e:
        print(
            f"Could not open serial port "
            f"{args.port}: {e}",
            file=sys.stderr,
        )

        sys.exit(1)

    time.sleep(2)

    print(
        f"Monitoring containers every "
        f"{args.interval}s. "
        f"Port: {args.port}. "
        f"Ctrl+C to stop."
    )

    # ------------------------------------------------------------------
    # Persistent state
    # ------------------------------------------------------------------

    view_index = 0

    last_check_time = 0.0

    force_refresh = False
    needs_redraw = True

    manual_logo_index = None

    selected_container_idx = 0
    container_scroll_offset = 0

    snooze_until = 0.0
    last_displayed_snooze_minute = None

    restart_armed_name = None
    restart_armed_deadline = 0.0

    statuses = []
    problems = []

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    while True:
        try:
            now = time.time()

            current_view = VIEWS[
                view_index
            ]

            # ----------------------------------------------------------
            # Buttons
            # ----------------------------------------------------------

            for press in read_pending_buttons(ser):

                # ------------------------------------------------------
                # A = force Docker check + redraw
                # ------------------------------------------------------

                if press == b"A":
                    force_refresh = True

                    print(
                        f"[{datetime.now().isoformat(timespec='seconds')}] "
                        "Button A: force refresh"
                    )

                # ------------------------------------------------------
                # B = next view
                # ------------------------------------------------------

                elif press == b"B":
                    view_index = (
                        view_index + 1
                    ) % len(VIEWS)

                    current_view = VIEWS[
                        view_index
                    ]

                    selected_container_idx = 0
                    container_scroll_offset = 0

                    needs_redraw = True

                    print(
                        f"[{datetime.now().isoformat(timespec='seconds')}] "
                        f"Button B: view -> {current_view}"
                    )

                # ------------------------------------------------------
                # C = context action
                # ------------------------------------------------------

                elif press == b"C":

                    if current_view == "auto":

                        if problems:
                            snooze_until = (
                                now
                                + args.snooze_minutes * 60
                            )

                            last_displayed_snooze_minute = None

                            needs_redraw = True

                            print(
                                f"[{datetime.now().isoformat(timespec='seconds')}] "
                                f"Button C: snoozed for "
                                f"{args.snooze_minutes}m"
                            )

                    elif (
                        current_view == "containers"
                        and statuses
                    ):
                        target_name = statuses[
                            selected_container_idx
                        ][0]

                        # Confirm restart
                        if (
                            restart_armed_name
                            == target_name
                            and now
                            < restart_armed_deadline
                        ):
                            print(
                                f"[{datetime.now().isoformat(timespec='seconds')}] "
                                f"Button C: restarting "
                                f"{target_name}"
                            )

                            try:
                                client.containers.get(
                                    target_name
                                ).restart()

                            except Exception as e:
                                print(
                                    f"  restart failed: {e}",
                                    file=sys.stderr,
                                )

                            restart_armed_name = None

                            force_refresh = True

                        # Arm restart
                        else:
                            restart_armed_name = (
                                target_name
                            )

                            restart_armed_deadline = (
                                now
                                + RESTART_CONFIRM_WINDOW_SECONDS
                            )

                            needs_redraw = True

                            print(
                                f"[{datetime.now().isoformat(timespec='seconds')}] "
                                f"Button C: armed restart "
                                f"on {target_name}"
                            )

                # ------------------------------------------------------
                # U = up
                # ------------------------------------------------------

                elif press == b"U":

                    if (
                        current_view == "containers"
                        and statuses
                    ):
                        old_idx = (
                            selected_container_idx
                        )

                        selected_container_idx = max(
                            0,
                            selected_container_idx - 1,
                        )

                        if (
                            selected_container_idx
                            != old_idx
                        ):
                            # Keep selected item visible.
                            if (
                                selected_container_idx
                                < container_scroll_offset
                            ):
                                container_scroll_offset = (
                                    selected_container_idx
                                )

                            needs_redraw = True

                    elif (
                        current_view == "auto"
                        and not problems
                    ):
                        logos = list_logos()

                        if logos:
                            idx = (
                                manual_logo_index
                                if manual_logo_index is not None
                                else 0
                            )

                            manual_logo_index = (
                                idx - 1
                            ) % len(logos)

                            needs_redraw = True

                # ------------------------------------------------------
                # D = down
                # ------------------------------------------------------

                elif press == b"D":

                    if (
                        current_view == "containers"
                        and statuses
                    ):
                        old_idx = (
                            selected_container_idx
                        )

                        selected_container_idx = min(
                            len(statuses) - 1,
                            selected_container_idx + 1,
                        )

                        if (
                            selected_container_idx
                            != old_idx
                        ):
                            # Keep selected item visible.
                            max_scroll = max(
                                0,
                                len(statuses)
                                - CONTAINER_LIST_VISIBLE_ROWS,
                            )

                            if (
                                selected_container_idx
                                >= (
                                    container_scroll_offset
                                    + CONTAINER_LIST_VISIBLE_ROWS
                                )
                            ):
                                container_scroll_offset = min(
                                    max_scroll,
                                    selected_container_idx
                                    - CONTAINER_LIST_VISIBLE_ROWS
                                    + 1,
                                )

                            needs_redraw = True

                    elif (
                        current_view == "auto"
                        and not problems
                    ):
                        logos = list_logos()

                        if logos:
                            idx = (
                                manual_logo_index
                                if manual_logo_index is not None
                                else 0
                            )

                            manual_logo_index = (
                                idx + 1
                            ) % len(logos)

                            needs_redraw = True

            # ----------------------------------------------------------
            # Restart confirmation timeout
            # ----------------------------------------------------------

            if (
                restart_armed_name
                and now >= restart_armed_deadline
            ):
                print(
                    f"[{datetime.now().isoformat(timespec='seconds')}] "
                    f"Restart confirmation expired for "
                    f"{restart_armed_name}"
                )

                restart_armed_name = None
                needs_redraw = True

            # ----------------------------------------------------------
            # Snooze timeout / countdown
            # ----------------------------------------------------------

            if snooze_until:

                if now >= snooze_until:
                    snooze_until = 0.0
                    last_displayed_snooze_minute = None
                    needs_redraw = True

                elif (
                    current_view == "auto"
                    and problems
                ):
                    # Only redraw when the visible "Xm left"
                    # value actually changes.
                    remaining_minute = max(
                        0,
                        int(
                            (
                                snooze_until
                                - now
                            )
                            / 60
                        ) + 1,
                    )

                    if (
                        remaining_minute
                        != last_displayed_snooze_minute
                    ):
                        last_displayed_snooze_minute = (
                            remaining_minute
                        )
                        needs_redraw = True

            # ----------------------------------------------------------
            # Docker polling
            # ----------------------------------------------------------

            due_for_check = (
                now - last_check_time
                >= args.interval
            )

            if due_for_check or force_refresh:

                last_check_time = now

                new_statuses = (
                    get_container_statuses(
                        client,
                        WATCHED_CONTAINERS,
                    )
                )

                new_problems = [
                    (
                        name,
                        status,
                        healthy,
                    )
                    for name, status, healthy
                    in new_statuses
                    if is_problem(
                        status,
                        healthy,
                    )
                ]

                statuses_changed = (
                    new_statuses != statuses
                )

                problems_changed = (
                    new_problems != problems
                )

                statuses = new_statuses
                problems = new_problems

                # Only redraw if the information visible on the
                # display actually changed.
                if (
                    statuses_changed
                    or problems_changed
                    or force_refresh
                ):
                    needs_redraw = True

                force_refresh = False

            # ----------------------------------------------------------
            # Render
            # ----------------------------------------------------------

            if needs_redraw:

                img = render_current_view(
                    current_view=current_view,
                    statuses=statuses,
                    problems=problems,
                    selected_container_idx=(
                        selected_container_idx
                    ),
                    container_scroll_offset=(
                        container_scroll_offset
                    ),
                    restart_armed_name=(
                        restart_armed_name
                    ),
                    manual_logo_index=(
                        manual_logo_index
                    ),
                    snooze_until=snooze_until,
                )

                send_frame(
                    ser,
                    img,
                )

                print(
                    f"[{datetime.now().isoformat(timespec='seconds')}] "
                    f"Redrew: {current_view}"
                )

                needs_redraw = False

        except Exception as e:
            print(
                f"Error during check: {e}",
                file=sys.stderr,
            )

        time.sleep(
            args.button_poll_interval
        )


if __name__ == "__main__":
    main()