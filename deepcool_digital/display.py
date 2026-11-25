"""Read Linux CPU sensors and drive the DeepCool HID display."""

from dataclasses import dataclass
from errno import EIO
import fcntl
import logging
import os
from pathlib import Path
from random import randint
import time

from .settings import DEVICES, Settings, load_settings


HID_ROOT = Path("/sys/class/hidraw")
HWMON_ROOT = Path("/sys/class/hwmon")
THERMAL_ROOT = Path("/sys/class/thermal")
RETRY_INTERVAL = 2.0
START_REPORT = bytes((0x10, 0xAA)) + bytes(62)
LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class HidDevice:
    path: Path
    vendor: int
    product: int
    name: str

    @property
    def profile(self):
        return next((name for name, ids in DEVICES.items() if ids == (self.vendor, self.product)), "CUSTOM")


def hid_devices(root=HID_ROOT):
    for entry in sorted(root.glob("hidraw*")):
        try:
            info = dict(
                line.split("=", 1)
                for line in (entry / "device/uevent").read_text().splitlines()
                if "=" in line
            )
            bus, vendor, product = (int(part, 16) for part in info["HID_ID"].split(":"))
        except (OSError, KeyError, ValueError):
            continue
        if bus == 0x03:
            yield HidDevice(Path("/dev") / entry.name, vendor, product, info.get("HID_NAME", "USB HID"))


def matching_device(settings):
    if settings.device == "AUTO":
        return next((device for device in hid_devices() if device.profile != "CUSTOM"), None)
    ids = settings.target_ids()
    return next((device for device in hid_devices() if (device.vendor, device.product) == ids), None)


def cooler_report(value, mode, profile):
    value = min(9999, max(0, value))
    data = bytearray(64)
    data[0] = 0x10
    data[1] = {"temp": 0x13, "usage": 0x4C}[mode]
    data[2] = min(255, (value + 9) // 10)
    digits = bytes(int(digit) for digit in str(value))
    stop = 7 if len(digits) == 4 else 6
    data[stop - len(digits):stop] = digits
    if profile == "AG400":
        data[3], data[4], data[5] = data[4], data[5], data[3]
    return bytes(data)


def ch510_report(usage, temp):
    # Send the same ASCII frame as the Windows port and its Linux predecessor.
    return f"_HLXDATA({usage},{temp},0,0,C)".encode("ascii")


def write_report(fd, report):
    if os.write(fd, report) != len(report):
        raise OSError(EIO, "Short HID write")


class CpuUsage:
    def __init__(self, path=Path("/proc/stat")):
        self.path = path
        self.previous = self.counters()

    def counters(self):
        with self.path.open() as proc_stat:
            # Guest time is already included in user and nice.
            return tuple(int(field) for field in proc_stat.readline().split()[1:9])

    def read(self):
        current = self.counters()
        deltas = [max(0, new - old) for old, new in zip(self.previous, current)]
        self.previous = current
        total = sum(deltas)
        idle = sum(deltas[3:5])
        return round(100 * (total - idle) / total) if total else 0


def read_millidegrees(path):
    return max(0, round(int(path.read_text().strip()) / 1000))


def cpu_temperature_inputs(hwmon=HWMON_ROOT, thermal=THERMAL_ROOT):
    candidates = []
    for chip in sorted(hwmon.glob("hwmon*")):
        try:
            driver = (chip / "name").read_text().strip()
        except OSError:
            continue
        if driver not in {"k10temp", "coretemp", "zenpower", "k8temp", "cpu_thermal", "cpu-thermal"}:
            continue
        for reading in sorted(chip.glob("temp*_input")):
            try:
                label = reading.with_name(reading.name.replace("_input", "_label")).read_text().strip()
            except OSError:
                label = ""
            priority = 0 if label == "Tdie" or label.startswith("Package id ") else 2
            if label == "Tctl":
                priority = 1
            candidates.append((priority, reading))
    for _, reading in sorted(candidates):
        yield reading
    for zone in sorted(thermal.glob("thermal_zone*")):
        try:
            label = (zone / "type").read_text().strip()
        except OSError:
            continue
        if label in {"x86_pkg_temp", "cpu-thermal", "cpu_thermal"}:
            yield zone / "temp"


class CpuTemperature:
    def __init__(self):
        self.path = None
        self.missing = False

    def read(self):
        if self.path is not None:
            try:
                return read_millidegrees(self.path)
            except (OSError, ValueError):
                self.path = None
        for candidate in cpu_temperature_inputs():
            try:
                value = read_millidegrees(candidate)
            except (OSError, ValueError):
                continue
            self.path = candidate
            self.missing = False
            LOG.info("CPU temperature sensor: %s", candidate)
            return value
        if not self.missing:
            LOG.warning("CPU temperature sensor unavailable. Displaying 0 °C until a sensor appears.")
            self.missing = True
        return 0


class Display:
    def __init__(self, settings, *, test=False, dry_run=False, usage=None, temperature=None):
        self.settings = settings
        self.test = test
        self.dry_run = dry_run
        self.usage = usage
        self.temperature = temperature
        self.fd = None
        self.profile = None
        self.active_mode = "temp"
        self.last_flip = 0.0

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        self.profile = None

    def connect(self):
        settings = self.settings
        device = matching_device(settings)
        self.profile = settings.device
        if settings.device == "AUTO":
            self.profile = device.profile if device else "AK500S"
        if not self.dry_run:
            if device is None:
                if settings.device == "AUTO":
                    target_name = "a supported DeepCool USB display"
                else:
                    vendor, product = settings.target_ids()
                    target_name = f"{settings.device} ({vendor:04x}:{product:04x})"
                raise FileNotFoundError(f"Waiting for {target_name}")
            fd = os.open(device.path, os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                os.close(fd)
                raise OSError(f"{device.path} is already in use by another instance") from error
            except OSError:
                os.close(fd)
                raise
            self.fd = fd
            LOG.info("Connected to %s at %s", device.name, device.path)
        if self.profile != "CH510":
            self.send("start", START_REPORT)
        self.active_mode = "temp"
        self.last_flip = time.monotonic()

    def send(self, mode, report, description=""):
        if self.dry_run:
            print(f"{self.profile} {mode}{description} | {report.hex(' ')}", flush=True)
        else:
            write_report(self.fd, report)
            LOG.debug("%s%s", mode, description)

    def update(self):
        if self.profile is None:
            self.connect()
        mode = self.settings.mode
        usage = randint(0, 100) if self.test else self.usage.read()
        if self.profile == "CH510":
            temp = self.read_temperature()
            self.send("both", ch510_report(usage, temp), f": {temp} °C, {usage}%")
            return
        if mode == "both":
            now = time.monotonic()
            if now - self.last_flip >= self.settings.flip_interval:
                self.active_mode = "usage" if self.active_mode == "temp" else "temp"
                self.last_flip = now
            mode = self.active_mode
        value = self.read_temperature() if mode == "temp" else usage
        unit = " °C" if mode == "temp" else "%"
        self.send(mode, cooler_report(value, mode, self.profile), f": {value}{unit}")

    def read_temperature(self):
        return randint(45, 95) if self.test else self.temperature.read()


class SettingsWatcher:
    def __init__(self, path, overrides):
        self.path = path
        self.overrides = overrides
        self.signature = ()

    def read(self):
        try:
            observation = self.path.lstat()
            signature = (observation.st_ino, observation.st_ctime_ns, observation.st_mtime_ns)
        except FileNotFoundError:
            signature = None
        except OSError as error:
            signature = (error.errno,)
            if signature != self.signature:
                LOG.warning("Could not access %s: %s", self.path, error)
            self.signature = signature
            return None
        if signature == self.signature:
            return None
        self.signature = signature
        try:
            return self.overrides(load_settings(self.path))
        except (OSError, ValueError, RecursionError) as error:
            LOG.warning("Could not load %s: %s", self.path, error)
            return None


def run_display(path, overrides, *, test=False, dry_run=False, once=False):
    watcher = SettingsWatcher(path, overrides)
    cpu = None if test else CpuUsage()
    temperature = None if test else CpuTemperature()
    display = None
    retry_error = None
    next_check = next_update = 0.0
    try:
        while True:
            now = time.monotonic()
            if now >= next_check:
                updated = watcher.read()
                if display is None or (updated is not None and updated != display.settings):
                    if display is not None:
                        display.close()
                    display = Display(
                        updated or overrides(Settings()), test=test, dry_run=dry_run, usage=cpu,
                        temperature=temperature,
                    )
                    next_update = now
                    retry_error = None
                next_check = now + 1.0
            if now >= next_update:
                try:
                    display.update()
                except OSError as error:
                    display.close()
                    if str(error) != retry_error:
                        LOG.warning("%s", error)
                        retry_error = str(error)
                    if once:
                        return 1
                    next_update = time.monotonic() + RETRY_INTERVAL
                else:
                    if once:
                        return 0
                    retry_error = None
                    next_update = time.monotonic() + display.settings.interval
            time.sleep(max(0, min(next_check, next_update) - time.monotonic()))
    finally:
        if display is not None:
            display.close()
