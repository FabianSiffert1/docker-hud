"""Time-driven state transitions."""

from datetime import datetime

from .config import WATCHED_CONTAINERS
from .docker_status import get_container_statuses, is_problem


def apply_day_rollover(state, today):
    if today != state.current_day:
        state.current_day = today

        if state.manual_logo_index is not None:
            print(
                f"[{datetime.now().isoformat(timespec='seconds')}] "
                "New day: releasing manual logo selection"
            )

        state.manual_logo_index = None

        state.needs_redraw = True


def apply_restart_timeout(state, now):
    if (
        state.restart_armed_name
        and now >= state.restart_armed_deadline
    ):
        print(
            f"[{datetime.now().isoformat(timespec='seconds')}] "
            f"Restart confirmation expired for "
            f"{state.restart_armed_name}"
        )

        state.restart_armed_name = None
        state.needs_redraw = True


def poll_docker(state, ctx, now, interval):
    due_for_check = (
        now - state.last_check_time
        >= interval
    )

    if not (due_for_check or state.force_refresh):
        return

    state.last_check_time = now

    new_statuses = (
        get_container_statuses(
            ctx.client,
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
        new_statuses != state.statuses
    )

    problems_changed = (
        new_problems != state.problems
    )

    if new_problems and not state.problems:
        state.breach_count += 1

        print(
            f"[{datetime.now().isoformat(timespec='seconds')}] "
            f"Breach #{state.breach_count}: "
            f"{len(new_problems)} container(s) down"
        )

    state.statuses = new_statuses
    state.problems = new_problems

    # Only redraw if the information visible on the
    # display actually changed.
    if (
        statuses_changed
        or problems_changed
        or state.force_refresh
    ):
        state.needs_redraw = True

    state.force_refresh = False
