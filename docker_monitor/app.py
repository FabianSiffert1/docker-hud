"""Main loop: polls Docker, reads buttons, drives the e-ink display."""

import argparse
import sys
import time
from datetime import datetime

import docker
import serial

from .config import (
    VIEWS,
    CONTAINER_LIST_VISIBLE_ROWS,
    DEFAULT_SNOOZE_MINUTES,
    RESTART_CONFIRM_WINDOW_SECONDS,
    WATCHED_CONTAINERS,
)
from .docker_status import get_container_statuses, is_problem
from .images import list_logos
from .screens import render_current_view
from .serial_protocol import read_pending_buttons, send_frame


def build_arg_parser():
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

    return parser


def main():
    parser = build_arg_parser()
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
