"""Serial protocol for talking to the Badger 2040."""

import struct

from .config import BUTTON_BYTES, MAX_BUTTON_READ_BYTES


def image_to_payload(img):
    packed = img.tobytes()

    header = struct.pack(
        ">2sHH",
        b"BD",
        img.width,
        img.height,
    )

    return header + packed


def send_frame(ser, img):
    payload = image_to_payload(img)

    ser.write(payload)
    ser.flush()


def read_pending_buttons(ser):
    presses = []

    pending = ser.in_waiting

    if pending <= 0:
        return presses

    chunk = ser.read(
        min(pending, MAX_BUTTON_READ_BYTES)
    )

    for index in range(len(chunk)):
        byte = chunk[index:index + 1]

        if byte in BUTTON_BYTES:
            presses.append(byte)

    return presses
