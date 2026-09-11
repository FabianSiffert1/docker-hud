# %%
import matplotlib.pyplot as plt
from docker_monitor.layout import render_layout
from docker_monitor.screens import (
    all_clear_screen,
    alert_screen,
    container_list_screen,
    stats_screen,
)


def preview(layout, *, scale=4):
    """Render a layout and display it at a useful preview size."""
    img = render_layout(layout)

    width, height = img.size

    plt.figure(figsize=(width / 100 * scale, height / 100 * scale))
    plt.imshow(img, cmap="gray", interpolation="nearest")
    plt.axis("off")
    plt.show()


# %%
# Preview the container list view
fake_statuses = [
    ("immich_redis", "running", True),
    ("watchtower", "running", None),
    ("mosquitto", "running", True),
    ("homeassistant", "running", False),
    ("zigbee2mqtt", "running", True),
    ("immich_server", "exited", False),
    ("immich_postgres", "running", True),
    ("immich_machine_learning", "running", True),
]


# %%
# Preview the "everything is fine" screen
preview(
    all_clear_screen()
)

# %%
preview(
    container_list_screen(
        fake_statuses,
        selected_idx=3,
        restart_armed_name="homeassistant",
    )
)


# %%
# Preview the stats screen
preview(
    stats_screen()
)


# %%
# Preview the alert screen while snoozed
import time

fake_problems = [
    ("immich_server", "exited", False),
]

preview(
    alert_screen(
        fake_problems,
        snoozed_until=time.time() + 17 * 60,
    )
)