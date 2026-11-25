"""GTK settings for the system display service."""

import os
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, Gtk

from .display import matching_device
from .settings import (
    CONFIG_PATH, DEVICES, MAX_INTERVAL, MIN_INTERVAL, MODES, Settings, encode_settings, load_settings,
    save_settings,
)


PROFILES = {"AUTO": "Automatic", **{name: name for name in DEVICES}, "CUSTOM": "Custom"}
SAVE_HELPER = Path("/usr/lib/deepcool-digital/deepcool-digital-save-settings")


def labeled_row(label, control):
    row = Gtk.Box(spacing=12)
    caption = Gtk.Label.new_with_mnemonic(label)
    caption.set_hexpand(True)
    caption.set_xalign(0)
    caption.set_mnemonic_widget(control)
    row.append(caption)
    row.append(control)
    return row


def interval_input(value):
    spin = Gtk.SpinButton.new_with_range(MIN_INTERVAL, MAX_INTERVAL, 0.1)
    spin.set_digits(2)
    spin.set_numeric(True)
    spin.set_value(value)
    return spin


class SettingsWindow(Gtk.ApplicationWindow):
    def __init__(self, app, path):
        super().__init__(application=app, title="DC Cooler Display", default_width=460)
        self.path = path
        error = None
        try:
            settings = load_settings(path)
        except (OSError, ValueError, RecursionError) as exc:
            settings = Settings()
            error = f"Could not load settings. {exc}"

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(20)
        content.set_margin_bottom(20)
        content.set_margin_start(20)
        content.set_margin_end(20)
        self.set_child(content)

        self.device = Gtk.DropDown.new_from_strings(list(PROFILES.values()))
        self.device.set_selected(list(PROFILES).index(settings.device))
        self.device.set_size_request(160, -1)
        content.append(labeled_row("_Device", self.device))

        self.detected = Gtk.Label(xalign=0, wrap=True)
        self.detected.add_css_class("dim-label")
        content.append(self.detected)

        self.mode = Gtk.DropDown.new_from_strings(list(MODES.values()))
        self.mode.set_selected(list(MODES).index(settings.mode))
        self.mode.set_size_request(160, -1)
        content.append(labeled_row("Display _mode", self.mode))

        self.interval = interval_input(settings.interval)
        content.append(labeled_row("_Update interval (seconds)", self.interval))
        self.flip = interval_input(settings.flip_interval)
        self.flip_row = labeled_row("_Alternation interval (seconds)", self.flip)
        content.append(self.flip_row)

        self.vendor = Gtk.Entry(placeholder_text="0x3633", width_chars=12)
        self.product = Gtk.Entry(placeholder_text="0x0004", width_chars=12)
        self.vendor.set_text(f"0x{settings.vendor:04x}" if settings.vendor is not None else "")
        self.product.set_text(f"0x{settings.product:04x}" if settings.product is not None else "")
        self.usb = Gtk.Expander(label="USB ID overrides", expanded=settings.vendor is not None or settings.product is not None)
        ids = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=8)
        ids.append(labeled_row("_Vendor ID", self.vendor))
        ids.append(labeled_row("_Product ID", self.product))
        self.usb.set_child(ids)
        content.append(self.usb)

        actions = Gtk.Box(spacing=12)
        self.status = Gtk.Label(xalign=0, wrap=True, hexpand=True)
        actions.append(self.status)
        self.save_button = Gtk.Button.new_with_mnemonic("_Save")
        self.save_button.set_valign(Gtk.Align.CENTER)
        self.save_button.add_css_class("suggested-action")
        self.save_button.connect("clicked", self.save)
        actions.append(self.save_button)
        content.append(actions)
        self.set_default_widget(self.save_button)

        self.device.connect("notify::selected", self.refresh)
        self.mode.connect("notify::selected", self.refresh)
        self.vendor.connect("changed", self.refresh)
        self.product.connect("changed", self.refresh)
        self.refresh()
        if path == CONFIG_PATH and not SAVE_HELPER.is_file():
            self.save_button.set_sensitive(False)
            self.show_status("Install the dc-cooler-display-arch package to save system settings.", error=True)
        elif path != CONFIG_PATH and not os.access(path.parent, os.W_OK):
            self.save_button.set_sensitive(False)
            self.show_status("Settings directory is unavailable.", error=True)
        elif error:
            self.show_status(error, error=True)

    def values(self):
        device = list(PROFILES)[self.device.get_selected()]
        return Settings(
            device=device,
            mode=list(MODES)[self.mode.get_selected()],
            interval=self.interval.get_value(),
            flip_interval=self.flip.get_value(),
            vendor=(self.vendor.get_text().strip() or None) if device != "AUTO" else None,
            product=(self.product.get_text().strip() or None) if device != "AUTO" else None,
        )

    def refresh(self, *_):
        profile = list(PROFILES)[self.device.get_selected()]
        self.usb.set_visible(profile != "AUTO")
        if profile == "CUSTOM":
            self.usb.set_expanded(True)
        try:
            detected = matching_device(self.values())
        except ValueError:
            detected = None
        simple = profile == "CH510" or (profile == "AUTO" and detected is not None and detected.profile == "CH510")
        message = f"Detected {detected.name} ({detected.vendor:04x}:{detected.product:04x})" if detected else "No matching USB display detected."
        if simple:
            message += "\nCH510 shows temperature and usage together."
        self.detected.set_text(message)
        self.mode.set_sensitive(not simple)
        self.flip_row.set_sensitive(not simple and list(MODES)[self.mode.get_selected()] == "both")

    def show_status(self, message, *, error=False):
        self.status.set_text(message)
        if error:
            self.status.add_css_class("error")
        else:
            self.status.remove_css_class("error")

    def save(self, _button):
        self.interval.update()
        self.flip.update()
        try:
            settings = self.values()
            if self.path == CONFIG_PATH:
                self.save_system_settings(settings)
                return
            save_settings(self.path, settings)
        except (GLib.Error, OSError, ValueError) as error:
            self.show_status(str(error), error=True)
        else:
            self.show_status("Settings saved.")

    def save_system_settings(self, settings):
        process = Gio.Subprocess.new(
            ["/usr/bin/pkexec", "--disable-internal-agent", "--user", "deepcool-digital", str(SAVE_HELPER)],
            Gio.SubprocessFlags.STDIN_PIPE | Gio.SubprocessFlags.STDOUT_SILENCE | Gio.SubprocessFlags.STDERR_PIPE,
        )
        self.show_status("Waiting for administrator authorization…")
        self.save_button.set_sensitive(False)
        process.communicate_utf8_async(encode_settings(settings), None, self.on_save_finished)

    def on_save_finished(self, process, result):
        self.save_button.set_sensitive(True)
        try:
            _, _, stderr = process.communicate_utf8_finish(result)
        except GLib.Error as error:
            self.show_status(str(error), error=True)
            return
        if process.get_successful():
            self.show_status("Settings saved.")
        elif process.get_if_exited() and process.get_exit_status() == 126:
            self.show_status("Save cancelled.")
        else:
            message = stderr.strip() if stderr else "Could not save system settings."
            self.show_status(message, error=True)


def run(path):
    app = Gtk.Application(application_id="io.github.jgar5032.DeepCoolDigital")

    def activate(application):
        window = application.get_active_window() or SettingsWindow(application, path)
        window.present()

    app.connect("activate", activate)
    return app.run([])
