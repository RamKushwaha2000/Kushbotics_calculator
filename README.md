# Kushbotics Calculator

A Raspberry Pi touchscreen calculator built around an ILI9341 320×240 SPI TFT and an XPT2046 touch controller. The application includes standard and scientific calculator screens, trigonometry, a computer algebra system (CAS), 2D graphing, 3D surface plotting, settings (Wi-Fi, Bluetooth, power saving), and a Kushbotics splash screen.

> **Source preservation:** `kushbotics_calculator.py` and `kushbotics_logo.png` are included exactly as supplied. The application code has not been refactored or edited as part of preparing this repository.

**Tested on:** Raspberry Pi 3 Model B, Raspberry Pi OS (32-bit, Debian Trixie), set up and managed through Raspberry Pi Connect remote shell.

## Contents

1. [Hardware](#hardware)
2. [Quick start](#quick-start)
3. [Start automatically at power-on](#start-automatically-at-power-on)
4. [Optional: faster boot](#optional-faster-boot)
5. [Everyday commands](#everyday-commands)
6. [Troubleshooting](#troubleshooting)
7. [Repository contents](#repository-contents)

## Hardware

- Raspberry Pi 3 Model B
- ILI9341 320×240 SPI TFT display
- XPT2046 resistive touch controller
- `kushbotics_logo.png` (kept in the same directory as the Python script)

### SPI pin mapping

| Signal | Raspberry Pi physical pin | BCM GPIO |
|---|---:|---:|
| SPI MOSI | 19 | GPIO 10 |
| SPI MISO | 21 | GPIO 9 |
| SPI SCLK | 23 | GPIO 11 |
| Display CS (CE0) | 24 | GPIO 8 |
| Display DC | 18 | GPIO 24 |
| Display RESET | 22 | GPIO 25 |
| Touch CS (CE1) | 26 | GPIO 7 |

The display and touch controller share MOSI, MISO, and SCLK. See [HARDWARE.md](HARDWARE.md) for the full wiring table and notes on powering the display.

## Quick start

These steps start from a fresh SD card and use only a terminal, so they work over SSH or the Raspberry Pi Connect remote shell.

### 1. Flash the SD card

Use Raspberry Pi Imager and choose **Raspberry Pi OS (32-bit)**. In the OS customisation settings, set:

- your username and password
- your Wi-Fi name and password (the Pi 3 supports **2.4 GHz only**, so use your 2.4 GHz network)
- SSH and/or Raspberry Pi Connect

Wi-Fi saved this way is system-wide, so the Pi reconnects automatically at every power-on, before anyone logs in.

### 2. Open a shell on the Pi

Either use SSH, or open **connect.raspberrypi.com**, click your device, then **Connect → Remote shell**.

Check that Wi-Fi is connected and saved:

```bash
nmcli device status | cat
ls /etc/netplan
```

`wlan0` should show `connected`, and a `.yaml` file should be listed.

### 3. Install system packages

```bash
sudo apt update
sudo apt install -y git python3-venv python3-pil python3-numpy python3-sympy python3-spidev python3-cbor2
```

> **This step is slow on a Pi 3.** Installing SymPy can show no output for 5 to 15 minutes. Do not unplug the Pi. If the terminal seems frozen, open a second shell and run:
>
> ```bash
> sudo dpkg --configure -a
> sudo apt install -y git python3-venv python3-pil python3-numpy python3-sympy python3-spidev python3-cbor2
> ```

### 4. Enable SPI and reboot

```bash
sudo raspi-config nonint do_spi 0
sudo reboot
```

If you use Raspberry Pi Connect, also run this once before rebooting so Pi Connect starts at boot without anyone logging in:

```bash
sudo loginctl enable-linger $USER
```

Wait 1 to 2 minutes, then open a new shell.

### 5. Download the project and install the display library

```bash
cd ~
git clone https://github.com/RamKushwaha2000/Kushbotics_calculator.git
cd Kushbotics_calculator
python3 -m venv --system-site-packages venv
./venv/bin/pip install smbus2
./venv/bin/pip install --no-deps luma.core luma.lcd
```

The `--system-site-packages` option reuses the packages installed with `apt`. The `--no-deps` option stops pip from rebuilding `cbor2` from source, which fails on Raspberry Pi OS with a "Failed building wheel for cbor2" error.

> **Why not `pip install -r requirements.txt`?** On a Pi 3 this tries to compile `cbor2` (a dependency of `luma.core`) and fails. The commands above install the same libraries without compiling anything. `requirements.txt` is kept as a list of what the project needs, for other setups.

### 6. Check the install

```bash
./venv/bin/python -c "import PIL, numpy, sympy, spidev, cbor2, smbus2; from luma.core.interface.serial import spi; from luma.lcd.device import ili9341; print('all good')"
```

You should see `all good`. If it says `No module named 'RPi'`, run `sudo apt install -y python3-rpi-lgpio` and try again.

### 7. Run the calculator

```bash
ls /dev/spidev*
sudo ./venv/bin/python kushbotics_calculator.py
```

You should see `/dev/spidev0.0` and `/dev/spidev0.1`, then the Kushbotics logo on the TFT. Press **Ctrl+C** to stop.

The program talks to the SPI display directly, so it only runs on a Raspberry Pi connected to the hardware. It is not expected to run as a full UI on a regular desktop. It is run with `sudo` so the Wi-Fi and Bluetooth toggles in Settings work without extra permissions.

## Start automatically at power-on

After the manual run works, install the built-in systemd service. Run it with the virtual environment's Python, because the service stores whichever interpreter you use here:

```bash
cd ~/Kushbotics_calculator
sudo ./venv/bin/python kushbotics_calculator.py --install-autostart
sudo systemctl start kushbotics-calculator
systemctl status kushbotics-calculator --no-pager
```

The status should say `active (running)`. Make sure the manual run from step 7 is stopped first, because only one program can use the screen.

Reboot to test:

```bash
sudo reboot
```

The calculator should appear on its own, and the Pi should reconnect to your saved Wi-Fi. At this point the project is complete. Everything below is optional.

Remove autostart with:

```bash
cd ~/Kushbotics_calculator
sudo ./venv/bin/python kushbotics_calculator.py --uninstall-autostart
```

## Optional: faster boot

These steps shorten the time from power-on to the calculator screen. Do them only after autostart works, and **reboot and check after each step** so you know which change caused a problem.

**What stays on:** NetworkManager (saved Wi-Fi and the Settings screen), Bluetooth (the Settings toggle), SSH, and Raspberry Pi Connect.

**What you lose:** with the desktop turned off, Raspberry Pi Connect *screen sharing* no longer works. The remote shell still does.

### Measure first

```bash
systemd-analyze
systemd-analyze critical-chain kushbotics-calculator.service
```

The `@` time next to `kushbotics-calculator.service` is when the calculator starts. By default it is ordered after everything else, so it starts last.

### A. Start the calculator earlier

```bash
sudo sed -i 's/^After=.*/After=sysinit.target/' /etc/systemd/system/kushbotics-calculator.service
sudo systemctl daemon-reload
systemctl cat kushbotics-calculator.service | cat
```

The `After=` line should now say only `sysinit.target`. NetworkManager still starts in parallel, and the app waits up to 8 seconds for it by itself. If the display is not ready that early, the service retries every 3 seconds.

### B. Boot to console and disable unused services

```bash
sudo systemctl set-default multi-user.target

for s in NetworkManager-wait-online cups cups.socket cups.path cups-browsed \
         avahi-daemon avahi-daemon.socket triggerhappy ModemManager \
         apt-daily.timer apt-daily-upgrade.timer man-db.timer \
         e2scrub_all.timer fstrim.timer; do
  sudo systemctl disable "$s" 2>/dev/null
done
```

Turning off `avahi-daemon` means `raspberrypi.local` no longer resolves, which does not matter if you use Raspberry Pi Connect.

### C. Turn off cloud-init (saves about 12 seconds)

cloud-init does first-boot setup that is no longer needed. First confirm your Wi-Fi is stored permanently in netplan:

```bash
grep -l "wifis" /etc/netplan/*
```

**Only continue if this prints a filename.** If it prints nothing, skip this step. Then:

```bash
sudo touch /etc/cloud/cloud-init.disabled
sudo reboot
```

To undo it, delete the file: `sudo rm /etc/cloud/cloud-init.disabled`.

### D. Firmware and kernel tweaks

This removes the rainbow splash, the boot delay, the audio driver and most boot messages. Backups are made first.

```bash
sudo cp /boot/firmware/config.txt /boot/firmware/config.txt.bak
sudo cp /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.bak

sudo tee -a /boot/firmware/config.txt <<'EOF'

# --- Kushbotics fast boot ---
disable_splash=1
boot_delay=0
dtparam=audio=off
EOF

sudo sed -i 's/ splash//' /boot/firmware/cmdline.txt
sudo sed -i '1 s/$/ quiet loglevel=3 logo.nologo/' /boot/firmware/cmdline.txt
sudo reboot
```

If the Pi does not boot afterwards, put the SD card in a computer and copy `config.txt.bak` and `cmdline.txt.bak` back over `config.txt` and `cmdline.txt` in the boot partition.

> Do not add `dtoverlay=disable-bt` to `config.txt`. It would break the Bluetooth toggle in the Settings screen.

### What to expect

A Pi 3 needs about 9 seconds for the kernel and firmware alone, which cannot be removed. Boot time depends heavily on your SD card, so measure your own with `systemd-analyze`. A fast A1/A2-rated card helps.

### Undo the boot tuning

```bash
sudo systemctl set-default graphical.target
sudo cp /boot/firmware/config.txt.bak /boot/firmware/config.txt
sudo cp /boot/firmware/cmdline.txt.bak /boot/firmware/cmdline.txt
sudo rm -f /etc/cloud/cloud-init.disabled
```

## Everyday commands

```bash
# update the calculator to the latest version
cd ~/Kushbotics_calculator && git pull && sudo systemctl restart kushbotics-calculator

# stop / start / restart the calculator
sudo systemctl stop kushbotics-calculator
sudo systemctl start kushbotics-calculator
sudo systemctl restart kushbotics-calculator

# view recent logs
journalctl -u kushbotics-calculator -b --no-pager | tail -30

# built-in help
./venv/bin/python kushbotics_calculator.py --help
```

Stop the service before running the calculator manually, because only one program can use the screen at a time.

## Troubleshooting

| Problem | What to try |
|---|---|
| `Failed building wheel for cbor2` | Use the `--no-deps` install in [step 5](#5-download-the-project-and-install-the-display-library) and `python3-cbor2` from `apt`. |
| `apt install` seems frozen | It is probably still working (SymPy is large). Wait up to 15 minutes. If it stays stuck, run `sudo dpkg --configure -a` from a second shell, then repeat the install. |
| `No module named 'RPi'` | `sudo apt install -y python3-rpi-lgpio` |
| `/dev/spidev*` not found | Run `sudo raspi-config nonint do_spi 0` and reboot. |
| Blank screen | Recheck the wiring against the pin table above and make sure the TFT has the correct power. A weak power supply also causes problems; use a good 5 V 2.5 A supply. |
| Service status is `failed` | Run `journalctl -u kushbotics-calculator -b --no-pager \| tail -30` and read the error. Make sure you installed autostart using `./venv/bin/python`. |
| Pi never shows Online in Raspberry Pi Connect after reboot | Run `sudo loginctl enable-linger $USER` (see [step 4](#4-enable-spi-and-reboot)), confirm Wi-Fi is the 2.4 GHz network, and wait 1 to 2 minutes. |
| `Failed to start` right after enabling cloud-init changes | Remove `/etc/cloud/cloud-init.disabled` and reboot. |

## Repository contents

```text
Kushbotics_calculator/
├── .gitignore
├── HARDWARE.md
├── README.md
├── requirements.txt
├── kushbotics_calculator.py
└── kushbotics_logo.png
```

## License

No license has been added because a license choice has not been specified. Choose a license before inviting others to reuse or redistribute the project.
