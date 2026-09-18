"""UI screens built from the layout primitives."""

import os
import time
from datetime import datetime

from .config import (
    WIDTH,
    HEIGHT,
    BREACH_IMAGE_PATH,
    CONTAINER_LIST_VISIBLE_ROWS,
)
from .docker_status import is_problem
from .fonts import get_font
from .images import get_daily_logo_path, list_logos, logo_to_eink
from .layout import Bitmap, Column, Divider, Spacer, Text, render_layout
from .stats import read_nuc_stats


def timestamp_component():
    return Text(
        datetime.now().strftime("%H:%M:%S"),
        get_font(10),
        align="center",
    )


def breach_count_component(breach_count):
    label = (
        "no breaches yet"
        if breach_count == 0
        else f"{breach_count} breach"
        + ("" if breach_count == 1 else "es")
        + " since boot"
    )

    return Text(
        label,
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
    breach_count=0,
    show_breach_count=False,
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
                HEIGHT - 16 - (
                    14
                    if show_breach_count
                    else 0
                ),
            ),
        )

        children = [
            Spacer(),

            Bitmap(
                logo,
                align="center",
            ),

            Spacer(),
        ]

        if show_breach_count:
            children.append(
                breach_count_component(
                    breach_count
                )
            )

        return Column(
            children,
            padding=5,
        )

    children = [
        Spacer(),

        Text(
            "X_X",
            get_font(30),
            align="center",
        ),
        Spacer(),
        Text(
            "no logo*.jpg found",
            get_font(10),
            align="center",
        ),

        Spacer(),
    ]

    if show_breach_count:
        children.append(
            breach_count_component(
                breach_count
            )
        )

    return Column(
        children,
        padding=5,
        horizontal_align="center",
    )


def render_current_view(
    current_view,
    statuses,
    problems,
    selected_container_idx,
    container_scroll_offset,
    restart_armed_name,
    manual_logo_index,
    breach_count=0,
    show_breach_count=False,
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
        if problems:
            layout = alert_screen(
                problems,
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
                breach_count=breach_count,
                show_breach_count=show_breach_count,
            )

    return render_layout(layout)
