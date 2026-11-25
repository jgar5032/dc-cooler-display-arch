# dc-cooler-display-arch

An independent community utility for compatible DeepCool digital displays on Arch Linux. Model names identify compatible hardware.

Display CPU temperature in Celsius, CPU usage, or alternate between them. The system service starts at boot before login and automatically reconnects to the USB display. The default is to detect an attached supported model, refresh every second, and alternate every eight seconds.

The daemon uses Python's standard library, Linux CPU sensors, and hidraw. The package includes a GTK settings window.

## Install and start at boot

Download the Arch package (`.pkg.tar.zst`) and run these commands from the download directory:

```sh
sudo pacman -U ./dc-cooler-display-arch-0.2.1-3-any.pkg.tar.zst
sudo systemctl enable --now deepcool-digital.service
```

Pacman installs the GUI dependencies with the package. Open **DC Cooler Display** from the app menu or run `dc-cooler-display-arch --gui`. Choose the display mode, timing, and device, then click **Save**. Your desktop's Polkit agent prompts for administrator authentication. The running service picks up changes within about a second.

When upgrading from `cooler-display-monitor` or `deepcool-digital`, accept pacman's prompt to remove the old package. Your boot setup and display preferences carry over.

To build from this checkout, run `makepkg -si` with `base-devel` installed, then enable the service as shown above. For command-line configuration, edit `/var/lib/deepcool-digital/settings.json` with `sudoedit`.

## Compatible DeepCool models

| Profile | USB VID:PID |
| --- | --- |
| AK400 DIGITAL | `3633:0001` |
| AK500 DIGITAL | `3633:0003` |
| AK500S DIGITAL | `3633:0004` |
| AK620 DIGITAL | `3633:0002` |
| AG400 DIGITAL | `3633:0008` |
| CH510 MESH DIGITAL | `34d3:1100` |

CH510 displays temperature and usage together. The other profiles support all three modes. On systems with multiple matching displays, select a specific model to override automatic detection.

## Command line

```sh
# Detect attached displays and preview a report straight from the checkout.
./deepcool-digital --list-devices
./deepcool-digital -d ak500s --dry-run --once

# Check the installed service.
systemctl status deepcool-digital.service
journalctl -u deepcool-digital.service -b
```

For a foreground session on the hardware, stop the service first and run the command as its service account.

```sh
sudo systemctl stop deepcool-digital.service
sudo -u deepcool-digital dc-cooler-display-arch -d ak500s --mode both --interval 1 --flip-interval 8 --debug
# Press Ctrl+C to exit the foreground session.
sudo systemctl start deepcool-digital.service
```

Use `--test` to send random readings, `--once` to send one update, or `--dry-run` to inspect the generated report without touching USB. Use `--help` for all options. If the journal reports a permission error after installing, reload the rules and reapply them to existing HID devices:

```sh
sudo udevadm control --reload
sudo udevadm trigger --subsystem-match=hidraw
```

## Custom USB IDs

For another cooler that uses the standard AK-style report, choose **Custom** and enter your VID and PID in hexadecimal, including the `0x` prefix. Choose an existing profile with **USB ID overrides** to reuse that profile's report format. The CLI equivalent is `--device custom --vendor 0x3633 --product 0x0004` with your own IDs.

For IDs outside the table, add a rule in `/etc/udev/rules.d/71-deepcool-digital-custom.rules` using the device's IDs, then reload and trigger udev as shown above.

```udev
SUBSYSTEM=="hidraw", ATTRS{idVendor}=="3633", ATTRS{idProduct}=="0004", GROUP="deepcool-digital", MODE="0660"
```

## Credits

Ported from [jgar5032's Windows script](https://github.com/jgar5032/deepcool-digital-info-windows), based on [Algorithm0's original Linux project](https://github.com/Algorithm0/deepcool-digital-info). Released under the MIT license.

The AK-series packet code derives from work by raghulkrishna and HY. Kelvin Lee. [Upstream AK-series project](https://github.com/raghulkrishna/deepcool-ak620-digital-linux)

sugayaa contributed the AG400 display fix. [Upstream contribution](https://github.com/Algorithm0/deepcool-digital-info/pull/6)
