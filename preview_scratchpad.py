# can be used to preview graphics
# run in your ide to show a preview window

# %%
import importlib
import docker_monitor
importlib.reload(docker_monitor)
import matplotlib.pyplot as plt

img = docker_monitor.render_all_clear_screen()
plt.imshow(img, cmap="gray")
plt.axis("off")
plt.show()