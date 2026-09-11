"""Static configuration for the Docker monitor."""

import os

WIDTH, HEIGHT = 296, 128

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(PROJECT_DIR, "assets")

LOGO_GLOB_PATTERN = os.path.join(ASSETS_DIR, "logo*.jpg")
BREACH_IMAGE_PATH = os.path.join(ASSETS_DIR, "breach.jpg")
BREACH_ICON_PATH = os.path.join(ASSETS_DIR, "mgsAlert.jpg")

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
