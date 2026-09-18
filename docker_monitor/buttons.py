"""Button press handling."""

import sys
from datetime import datetime

from .config import (
    VIEWS,
    Button,
    View,
    CONTAINER_LIST_VISIBLE_ROWS,
    RESTART_CONFIRM_WINDOW_SECONDS,
)
from .images import list_logos


def handle_a(state, ctx, now):
    state.force_refresh = True

    print(
        f"[{datetime.now().isoformat(timespec='seconds')}] "
        "Button A: force refresh"
    )


def handle_b(state, ctx, now):
    state.view_index = (
        state.view_index + 1
    ) % len(VIEWS)

    state.selected_container_idx = 0
    state.container_scroll_offset = 0
    state.manual_logo_index = None

    state.needs_redraw = True

    print(
        f"[{datetime.now().isoformat(timespec='seconds')}] "
        f"Button B: view -> {state.current_view}"
    )


def handle_c(state, ctx, now):
    if state.current_view == View.AUTO:

        if not state.problems:
            state.show_breach_count = (
                not state.show_breach_count
            )

            state.needs_redraw = True

            print(
                f"[{datetime.now().isoformat(timespec='seconds')}] "
                f"Button C: breach count "
                f"{'shown' if state.show_breach_count else 'hidden'}"
            )

    elif (
        state.current_view == View.CONTAINERS
        and state.statuses
    ):
        target_name = state.statuses[
            state.selected_container_idx
        ][0]

        # Confirm restart
        if (
            state.restart_armed_name
            == target_name
            and now
            < state.restart_armed_deadline
        ):
            print(
                f"[{datetime.now().isoformat(timespec='seconds')}] "
                f"Button C: restarting "
                f"{target_name}"
            )

            try:
                ctx.client.containers.get(
                    target_name
                ).restart()

            except Exception as e:
                print(
                    f"  restart failed: {e}",
                    file=sys.stderr,
                )

            state.restart_armed_name = None

            state.force_refresh = True

        # Arm restart
        else:
            state.restart_armed_name = (
                target_name
            )

            state.restart_armed_deadline = (
                now
                + RESTART_CONFIRM_WINDOW_SECONDS
            )

            state.needs_redraw = True

            print(
                f"[{datetime.now().isoformat(timespec='seconds')}] "
                f"Button C: armed restart "
                f"on {target_name}"
            )


def handle_up(state, ctx, now):
    if (
        state.current_view == View.CONTAINERS
        and state.statuses
    ):
        old_idx = (
            state.selected_container_idx
        )

        state.selected_container_idx = max(
            0,
            state.selected_container_idx - 1,
        )

        if (
            state.selected_container_idx
            != old_idx
        ):
            # Keep selected item visible.
            if (
                state.selected_container_idx
                < state.container_scroll_offset
            ):
                state.container_scroll_offset = (
                    state.selected_container_idx
                )

            state.needs_redraw = True

    elif (
        state.current_view == View.AUTO
        and not state.problems
    ):
        logos = list_logos()

        if logos:
            idx = (
                state.manual_logo_index
                if state.manual_logo_index is not None
                else 0
            )

            state.manual_logo_index = (
                idx - 1
            ) % len(logos)

            state.needs_redraw = True


def handle_down(state, ctx, now):
    if (
        state.current_view == View.CONTAINERS
        and state.statuses
    ):
        old_idx = (
            state.selected_container_idx
        )

        state.selected_container_idx = min(
            len(state.statuses) - 1,
            state.selected_container_idx + 1,
        )

        if (
            state.selected_container_idx
            != old_idx
        ):
            # Keep selected item visible.
            max_scroll = max(
                0,
                len(state.statuses)
                - CONTAINER_LIST_VISIBLE_ROWS,
            )

            if (
                state.selected_container_idx
                >= (
                    state.container_scroll_offset
                    + CONTAINER_LIST_VISIBLE_ROWS
                )
            ):
                state.container_scroll_offset = min(
                    max_scroll,
                    state.selected_container_idx
                    - CONTAINER_LIST_VISIBLE_ROWS
                    + 1,
                )

            state.needs_redraw = True

    elif (
        state.current_view == View.AUTO
        and not state.problems
    ):
        logos = list_logos()

        if logos:
            idx = (
                state.manual_logo_index
                if state.manual_logo_index is not None
                else 0
            )

            state.manual_logo_index = (
                idx + 1
            ) % len(logos)

            state.needs_redraw = True


BUTTON_HANDLERS = {
    Button.A: handle_a,
    Button.B: handle_b,
    Button.C: handle_c,
    Button.UP: handle_up,
    Button.DOWN: handle_down,
}


def handle_press(press, state, ctx, now):
    handler = BUTTON_HANDLERS.get(press)

    if handler is not None:
        handler(state, ctx, now)
