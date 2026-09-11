"""Local machine (NUC) stats."""

import os
import shutil


def read_nuc_stats():
    stats = {}

    try:
        with open("/proc/uptime") as f:
            uptime_seconds = float(
                f.read().split()[0]
            )

        days, rem = divmod(
            int(uptime_seconds),
            86400,
        )

        hours, rem = divmod(
            rem,
            3600,
        )

        minutes = rem // 60

        stats["uptime"] = (
            f"{days}d {hours}h {minutes}m"
        )

    except Exception:
        stats["uptime"] = "N/A"

    try:
        total, used, free = (
            shutil.disk_usage("/")
        )

        stats["disk"] = (
            f"{used / total * 100:.0f}% used "
            f"({free // (2**30)}GB free)"
        )

    except Exception:
        stats["disk"] = "N/A"

    try:
        load1, load5, load15 = (
            os.getloadavg()
        )

        stats["load"] = (
            f"{load1:.2f} / "
            f"{load5:.2f} / "
            f"{load15:.2f}"
        )

    except Exception:
        stats["load"] = "N/A"

    try:
        with open("/proc/meminfo") as f:
            meminfo = {}

            for line in f:
                parts = line.split(":")

                if len(parts) == 2:
                    meminfo[
                        parts[0].strip()
                    ] = int(
                        parts[1]
                        .strip()
                        .split()[0]
                    )

        total_kb = meminfo.get(
            "MemTotal",
            0,
        )

        avail_kb = meminfo.get(
            "MemAvailable",
            0,
        )

        used_pct = (
            (
                1
                - avail_kb / total_kb
            )
            * 100
            if total_kb
            else 0
        )

        stats["memory"] = (
            f"{used_pct:.0f}% used"
        )

    except Exception:
        stats["memory"] = "N/A"

    try:
        with open(
            "/sys/class/thermal/"
            "thermal_zone0/temp"
        ) as f:
            temp_c = (
                int(f.read().strip())
                / 1000
            )

        stats["temp"] = (
            f"{temp_c:.0f}C"
        )

    except Exception:
        stats["temp"] = "N/A"

    return stats
