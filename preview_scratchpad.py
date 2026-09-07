# %%
# Preview the container list view, including a selection cursor
# and an armed-restart state
from matplotlib import pyplot as plt
import docker_monitor

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

img = docker_monitor.render_container_list_screen(
    fake_statuses,
    selected_idx=3,                       # try different rows
    scroll_offset=0,
    restart_armed_name="homeassistant",   # set to None to see it without the "(confirm?)" tag
)
plt.imshow(img, cmap="gray")
plt.axis("off")
plt.show()

# %%
# Preview the stats screen — reads real values from wherever
# you run this, since it uses stdlib system calls, not fake data
img = docker_monitor.render_stats_screen()
plt.imshow(img, cmap="gray")
plt.axis("off")
plt.show()

# %%
# Preview the alert screen while snoozed
import time
fake_problems = [("immich_server", "exited", False)]
img = docker_monitor.render_alert_screen(fake_problems, snoozed_until=time.time() + 17 * 60)
plt.imshow(img, cmap="gray")
plt.axis("off")
plt.show()