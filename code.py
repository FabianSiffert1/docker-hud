"""
code.py — CircuitPython version, for the Badger 2040 (non-W)

Runs ON the Badger. Two jobs, interleaved in one loop:
  1. Read framed monochrome bitmaps over USB serial (data port) and
     display them via displayio/board.DISPLAY.
  2. Watch all 5 buttons (A, B, C, UP, DOWN) — on press, send a single
     identifying byte back over the SAME data port, telling
     docker_monitor.py on the NUC what happened.

Frame format (must match docker_monitor.py's image_to_payload):
    [b'B'][b'D'][width: uint16 big-endian][height: uint16 big-endian][packed 1bpp data]

Button->NUC format: a single byte per press (debounced), one of:
    b"A" - button A  (force refresh)
    b"B" - button B  (switch view)
    b"C" - button C  (context action: snooze / select / confirm)
    b"U" - UP        (scroll up / previous logo)
    b"D" - DOWN      (scroll down / next logo)

NOTE: e-ink panels should not be refreshed more often than roughly
every 180 seconds per Adafruit's own guidance, to avoid damaging the
display over time. --interval on the NUC side should respect this.

NOTE: button pin naming (board.SW_A etc.) and press polarity are per
Pimoroni's Badger 2040 pinout as documented, but I haven't verified
against your actual physical unit — if a button doesn't register,
try flipping pull=digitalio.Pull.UP to Pull.DOWN (or vice versa) for
that pin and check whether "pressed" should test for True or False.
"""

import struct
import time

import board
import digitalio
import displayio
import usb_cdc

MAGIC = b"BD"
HEADER_LEN = 6

display = board.DISPLAY

# Uses the dedicated data serial port (see boot_py_addition.txt),
# NOT the console/REPL port — keeps binary data from ever colliding
# with Ctrl+C / Ctrl+D or REPL text output.
data_serial = usb_cdc.data

# Pull.DOWN + pressed==True is the common wiring for Pimoroni's boards
# (button connects the pin to 3.3V when pressed). Flip to Pull.UP /
# pressed==False per-button if a specific one doesn't respond.
BUTTON_PINS = {
    b"A": board.SW_A,
    b"B": board.SW_B,
    b"C": board.SW_C,
    b"U": board.SW_UP,
    b"D": board.SW_DOWN,
}

DEBOUNCE_SECONDS = 0.25

_buttons = {}
for _label, _pin in BUTTON_PINS.items():
    _dio = digitalio.DigitalInOut(_pin)
    _dio.direction = digitalio.Direction.INPUT
    _dio.pull = digitalio.Pull.DOWN
    _buttons[_label] = {"dio": _dio, "last_state": False, "last_time": 0.0}


def check_buttons_and_send():
    """
    Polls all 5 buttons. On a debounced press, sends the button's
    identifying byte over the data serial port.
    """
    now = time.monotonic()
    for label, state in _buttons.items():
        pressed = state["dio"].value
        if pressed and not state["last_state"] and (now - state["last_time"]) > DEBOUNCE_SECONDS:
            data_serial.write(label)
            state["last_time"] = now
        state["last_state"] = pressed


def read_exact(n):
    buf = bytearray()
    while len(buf) < n:
        chunk = data_serial.read(n - len(buf))
        if chunk:
            buf.extend(chunk)
        else:
            # No data waiting right now — check buttons while we wait,
            # instead of blocking silently until a frame arrives.
            check_buttons_and_send()
    return bytes(buf)


def read_frame():
    header = read_exact(HEADER_LEN)
    magic, width, height = struct.unpack(">2sHH", header)
    if magic != MAGIC:
        raise ValueError("bad magic, resyncing")

    row_bytes = (width + 7) // 8
    data_len = row_bytes * height
    data = read_exact(data_len)
    return width, height, data


def draw_frame(width, height, data):
    bitmap = displayio.Bitmap(width, height, 2)
    palette = displayio.Palette(2)
    palette[0] = 0xFFFFFF  # 0 = white
    palette[1] = 0x000000  # 1 = black

    row_bytes = (width + 7) // 8
    for y in range(height):
        row_start = y * row_bytes
        for x in range(width):
            byte = data[row_start + (x // 8)]
            bit = (byte >> (7 - (x % 8))) & 1
            bitmap[x, y] = 0 if bit else 1

    tile_grid = displayio.TileGrid(bitmap, pixel_shader=palette)
    group = displayio.Group()
    group.append(tile_grid)

    display.root_group = group
    display.refresh()


def main():
    while True:
        try:
            check_buttons_and_send()

            if data_serial.in_waiting >= HEADER_LEN:
                width, height, data = read_frame()
                draw_frame(width, height, data)
                time.sleep(1)  # respect e-ink refresh limits
            else:
                time.sleep(0.05)  # short poll interval for responsive buttons

        except ValueError:
            continue
        except Exception:
            time.sleep(1)
            continue


if __name__ == "__main__":
    main()
