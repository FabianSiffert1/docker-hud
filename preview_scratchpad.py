# can be used to preview graphics
# run in your ide to show a preview window

# %%
import importlib
import docker_monitor
importlib.reload(docker_monitor)
import matplotlib.pyplot as plt

logos = docker_monitor.list_logos()
print(logos)  # see what's available and their index

img = docker_monitor.render_all_clear_screen(logo_path_override=logos[10])  # change index to try others
plt.imshow(img, cmap="gray")
plt.axis("off")
plt.show()

# %%
# Preview the alert/breach screen with fake problem data
fake_problems = [
    ("immich_server", "exited", False),
    ("homeassistant", "running", False),
]

img = docker_monitor.render_alert_screen(fake_problems)
plt.imshow(img, cmap="gray")
plt.axis("off")
plt.show()