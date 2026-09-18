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


class View:
    AUTO = "auto"
    CONTAINERS = "containers"
    STATS = "stats"


class Button:
    A = b"A"
    B = b"B"
    C = b"C"
    UP = b"U"
    DOWN = b"D"


VIEWS = [View.AUTO, View.CONTAINERS, View.STATS]

CONTAINER_LIST_VISIBLE_ROWS = 6
RESTART_CONFIRM_WINDOW_SECONDS = 10

BUTTON_BYTES = {
    Button.A,
    Button.B,
    Button.C,
    Button.UP,
    Button.DOWN,
}
