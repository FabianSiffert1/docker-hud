"""Main loop: polls Docker, reads buttons, drives the e-ink display."""

import argparse
import sys
import time
import traceback
from datetime import datetime

import docker
import serial

from .buttons import handle_press
from .config import MAX_CONSECUTIVE_ERRORS
from .runtime import AppContext, MonitorState
from .screens import render_current_view
from .serial_protocol import read_pending_buttons, send_frame
from .transitions import (
    apply_day_rollover,
    apply_restart_timeout,
    poll_docker,
)


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

    return parser


def render_and_send(state, ser):
    img = render_current_view(
        current_view=state.current_view,
        statuses=state.statuses,
        problems=state.problems,
        selected_container_idx=(
            state.selected_container_idx
        ),
        container_scroll_offset=(
            state.container_scroll_offset
        ),
        restart_armed_name=(
            state.restart_armed_name
        ),
        manual_logo_index=(
            state.manual_logo_index
        ),
        breach_count=state.breach_count,
        show_breach_count=state.show_breach_count,
    )

    send_frame(
        ser,
        img,
    )

    print(
        f"[{datetime.now().isoformat(timespec='seconds')}] "
        f"Redrew: {state.current_view}"
    )

    state.needs_redraw = False


def tick(state, ctx, ser, interval):
    now = time.time()

    for press in read_pending_buttons(ser):
        handle_press(press, state, ctx, now)

    apply_day_rollover(
        state,
        datetime.now().date(),
    )

    apply_restart_timeout(state, now)

    poll_docker(state, ctx, now, interval)

    if state.needs_redraw:
        render_and_send(state, ser)


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

    state = MonitorState()
    ctx = AppContext(client)

    consecutive_errors = 0

    try:
        while True:
            try:
                tick(
                    state,
                    ctx,
                    ser,
                    args.interval,
                )

                consecutive_errors = 0

            except serial.SerialException as e:
                print(
                    f"Serial link lost on {args.port}: {e}",
                    file=sys.stderr,
                )

                sys.exit(1)

            except Exception:
                consecutive_errors += 1

                traceback.print_exc()

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    print(
                        f"Giving up after "
                        f"{consecutive_errors} consecutive errors",
                        file=sys.stderr,
                    )

                    sys.exit(1)

            time.sleep(
                args.button_poll_interval
            )

    except KeyboardInterrupt:
        print("Stopped.")

    finally:
        ser.close()


if __name__ == "__main__":
    main()
