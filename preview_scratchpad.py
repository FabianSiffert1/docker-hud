# %%
import matplotlib.pyplot as plt
import docker_monitor


def preview(layout, *, scale=4):
    """Render a layout and display it at a useful preview size."""
    img = docker_monitor.render_layout(layout)

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
    docker_monitor.all_clear_screen()
)

preview(
    docker_monitor.container_list_screen(
        fake_statuses,
        selected_idx=3,
        restart_armed_name="homeassistant",
    )
)


# %%
# Preview the stats screen
preview(
    docker_monitor.stats_screen()
)


# %%
# Preview the alert screen while snoozed
import time

fake_problems = [
    ("immich_server", "exited", False),
]

preview(
    docker_monitor.alert_screen(
        fake_problems,
        snoozed_until=time.time() + 17 * 60,
    )
)