"""Mutable state for the main loop."""

from datetime import datetime

from .config import VIEWS


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


class AppContext:
    def __init__(self, client):
        self.client = client
