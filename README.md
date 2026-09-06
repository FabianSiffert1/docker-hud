# Badger 2040 Docker Health Monitor

E-ink display on a NUC-connected Badger 2040 showing a daily-rotating
logo when all Docker containers are healthy, and a warning screen when
something's down.

## Architecture

```
NUC (Docker host)                    Badger 2040 (CircuitPython)
------------------                   ---------------------------
docker_monitor.py                    code.py
  - polls Docker API      --USB-->     - reads framed image data
  - renders bitmap                     - draws it via displayio
  - sends over serial                  - knows nothing about Docker
```

## Requirements

- NUC (or any always-on Linux box) running Docker
- Pimoroni Badger 2040 (non-W), running CircuitPython
- USB-C to Micro-USB (or matching) cable between them

## NUC Setup

```bash
sudo apt install python3-pip
python3 -m venv ~/badger-monitor-env
source ~/badger-monitor-env/bin/activate
pip install docker pillow pyserial
```

Add your user to the `dialout` group (needed for serial access), then
log out/in:
```bash
sudo usermod -aG dialout $USER
```

Set the correct timezone, if timestamps look off:
```bash
sudo timedatectl set-timezone Europe/Berlin
```

Edit `WATCHED_CONTAINERS` in `docker_monitor.py` to match your actual
container names (`docker ps --format '{{.Names}}'`).

Find the Badger's **data** serial port (there are two — console +
data, see Badger setup below):
```bash
ls /dev/ttyACM*
```

Run it:
```bash
python3 docker_monitor.py --port /dev/ttyACM1 --interval 60
```

## Badger Setup (CircuitPython)

1. Add to `boot.py` on the Badger — opens a second serial port
   dedicated to data, separate from the REPL console:
   ```python
   import usb_cdc
   usb_cdc.enable(console=True, data=True)
   ```
   Unplug/replug for it to take effect.
2. Copy `code_circuitpython.py` onto the drive as `code.py`.
3. `board.DISPLAY` handles the e-ink panel natively — no extra driver
   library needed.

## Logos

Drop any number of `logo.jpg`, `logo1.jpg`, `logo2.jpg`, ... next to
`docker_monitor.py` on the NUC. One is picked at random each day
(stable all day, changes daily) and shown as the "all clear" screen.
No logos found -> falls back to an `X_X` text screen.

To preview/pick a specific logo before committing to it, use the
`preview.py` scratchpad (run in a local venv with just `pillow`
installed -- no Docker/serial needed):
```python
logos = docker_monitor.list_logos()
img = docker_monitor.render_all_clear_screen(logo_path_override=logos[0])
```

## Run on boot (systemd)

Edit `badger-monitor.service`, fixing `User=` and the venv/script
paths, then:
```bash
sudo cp badger-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now badger-monitor.service
```

Check status / logs:
```bash
systemctl status badger-monitor.service
journalctl -u badger-monitor.service -f
```

## Automatic apt updates (optional, NUC-wide)

```bash
sudo apt install unattended-upgrades
sudo dpkg-reconfigure --priority=low unattended-upgrades
```

## License

MIT -- see `LICENSE`. Logo files are excluded from this repo
(`.gitignore`); supply your own.
