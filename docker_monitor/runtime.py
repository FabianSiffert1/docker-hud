"""Mutable state for the main loop."""

from datetime import datetime

from .config import VIEWS, CONTAINER_LIST_VISIBLE_ROWS


class MonitorState:
    def __init__(self):
        self.view_index = 0

        self.last_check_time = 0.0

        self.force_refresh = False
        self.needs_redraw = True

        self.manual_logo_index = None

        self.current_day = datetime.now().date()

        self.selected_container_idx = 0
        self.container_scroll_offset = 0

        self.breach_count = 0
        self.show_breach_count = False

        self.restart_armed_name = None
        self.restart_armed_deadline = 0.0

        self.statuses = []
        self.problems = []

    @property
    def current_view(self):
        return VIEWS[self.view_index]

    @property
    def selected_container(self):
        if not self.statuses:
            return None

        if self.selected_container_idx >= len(self.statuses):
            return None

        return self.statuses[
            self.selected_container_idx
        ]

    def clamp_selection(self):
        if not self.statuses:
            self.selected_container_idx = 0
            self.container_scroll_offset = 0
            return

        last_idx = len(self.statuses) - 1

        if self.selected_container_idx > last_idx:
            self.selected_container_idx = last_idx

        max_scroll = max(
            0,
            len(self.statuses)
            - CONTAINER_LIST_VISIBLE_ROWS,
        )

        if self.container_scroll_offset > max_scroll:
            self.container_scroll_offset = max_scroll


class AppContext:
    def __init__(self, client):
        self.client = client
