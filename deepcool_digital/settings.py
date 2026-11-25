"""Shared settings for the display service and desktop app."""

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import stat
import tempfile


CONFIG_PATH = Path("/var/lib/deepcool-digital/settings.json")
MIN_INTERVAL = 0.1
MAX_INTERVAL = 3600.0
MAX_SETTINGS_BYTES = 4096
MODES = {"both": "Alternate", "temp": "Temperature", "usage": "CPU usage"}
DEVICES = {
    "AK400": (0x3633, 0x0001),
    "AK500": (0x3633, 0x0003),
    "AK500S": (0x3633, 0x0004),
    "AK620": (0x3633, 0x0002),
    "AG400": (0x3633, 0x0008),
    "CH510": (0x34D3, 0x1100),
}


def usb_id(value):
    if isinstance(value, str):
        value = int(value, 0)
    if type(value) is not int or not 1 <= value <= 0xFFFF:
        raise ValueError("USB IDs must be between 0x0001 and 0xffff.")
    return value


@dataclass(frozen=True)
class Settings:
    device: str = "AUTO"
    mode: str = "both"
    interval: float = 1.0
    flip_interval: float = 8.0
    vendor: int | None = None
    product: int | None = None

    def __post_init__(self):
        if not isinstance(self.device, str) or self.device not in ("AUTO", "CUSTOM", *DEVICES):
            raise ValueError("Choose a supported device, automatic detection, or a custom device.")
        if not isinstance(self.mode, str) or self.mode not in MODES:
            raise ValueError("Choose Alternate, Temperature, or CPU usage.")
        for name, value in (("Update interval", self.interval), ("Alternation interval", self.flip_interval)):
            if type(value) not in (int, float) or not MIN_INTERVAL <= value <= MAX_INTERVAL:
                raise ValueError(f"{name} must be between {MIN_INTERVAL:g} and {MAX_INTERVAL:g} seconds.")
        if self.device == "AUTO" and (self.vendor is not None or self.product is not None):
            raise ValueError("Choose a device profile or Custom to override USB IDs.")
        if self.device == "CUSTOM" and (self.vendor is None or self.product is None):
            raise ValueError("Enter both USB IDs for a custom device.")
        for field in ("vendor", "product"):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, usb_id(value))

    def target_ids(self):
        vendor, product = DEVICES.get(self.device, (None, None))
        return self.vendor or vendor, self.product or product


def load_settings(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except FileNotFoundError:
        return Settings()
    with os.fdopen(fd, "rb") as config:
        if not stat.S_ISREG(os.fstat(config.fileno()).st_mode):
            raise ValueError("Settings must be a regular file.")
        return decode_settings(config.read(MAX_SETTINGS_BYTES + 1))


def decode_settings(data):
    if len(data) > MAX_SETTINGS_BYTES:
        raise ValueError("Settings file is too large.")
    values = json.loads(data)
    if not isinstance(values, dict):
        raise ValueError("Settings must be a JSON object.")
    try:
        return Settings(**values)
    except TypeError as error:
        raise ValueError(str(error)) from error


def encode_settings(settings):
    return json.dumps(asdict(settings), indent=2) + "\n"


def save_settings(path, settings):
    # A rename lets the running service see a complete file on each refresh.
    fd, temp_path = tempfile.mkstemp(dir=path.parent, prefix=".settings-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as config:
            os.fchmod(config.fileno(), 0o644)
            config.write(encode_settings(settings))
            config.flush()
            os.fsync(config.fileno())
        os.replace(temp_path, path)
    finally:
        Path(temp_path).unlink(missing_ok=True)
