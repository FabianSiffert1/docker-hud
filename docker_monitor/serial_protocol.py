"""Serial protocol for talking to the Badger 2040."""

import struct

from .config import BUTTON_BYTES


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

    while ser.in_waiting > 0:
        byte = ser.read(1)

        if byte in BUTTON_BYTES:
            presses.append(byte)

    return presses
