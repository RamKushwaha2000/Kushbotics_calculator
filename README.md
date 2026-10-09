# Kushbotics Calculator

A Raspberry Pi touchscreen calculator built around an ILI9341 320×240 SPI TFT and an XPT2046 touch controller. The application includes standard and scientific calculator screens, trigonometry, a computer algebra system (CAS), 2D graphing, 3D surface plotting, settings, and a Kushbotics splash screen.

> **Source preservation:** `kushbotics_calculator.py` and `kushbotics_logo.png` are included exactly as supplied. The application code has not been refactored or edited as part of preparing this repository.

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

Enable SPI in Raspberry Pi OS before running the application. The display and touch controller share MOSI, MISO, and SCLK.

## Software requirements

- Raspberry Pi OS with Python 3
- Pillow
- luma.lcd (and luma.core)
- spidev
- NumPy (for graphing and 3D plotting)
- SymPy (for CAS features)

Install Python dependencies in the environment you intend to use:

```bash
python3 -m pip install -r requirements.txt
```

On Raspberry Pi OS, if your system Python is externally managed, use a virtual environment or the distribution's supported packages rather than forcing a system-wide pip installation.

## Run

Keep the script and logo together in the repository root:

```bash
python3 kushbotics_calculator.py
```

The application initializes the SPI display and touch controller directly, so run it on the Raspberry Pi connected to the hardware. It is not expected to run as a full UI on a regular desktop without the hardware.

## Optional: start automatically at boot

The script includes its own systemd autostart commands. After you have tested normal launch on the Raspberry Pi, you can install autostart with:

```bash
sudo python3 kushbotics_calculator.py --install-autostart
```

Remove it with:

```bash
sudo python3 kushbotics_calculator.py --uninstall-autostart
```

Review the script's built-in help before using optional commands:

```bash
python3 kushbotics_calculator.py --help
```

## Repository contents

```text
kushbotics-calculator/
├── .gitignore
├── HARDWARE.md
├── README.md
├── requirements.txt
├── kushbotics_calculator.py
└── kushbotics_logo.png
```

## GitHub setup

1. On GitHub, create a new repository named `kushbotics-calculator`.
2. For a clean first upload, do not initialize it with a README, license, or `.gitignore` (those files are already in this folder).
3. From this folder, run:

   ```bash
   git init
   git add README.md HARDWARE.md requirements.txt .gitignore kushbotics_calculator.py kushbotics_logo.png
   git commit -m "Initial release: Kushbotics Calculator v2.0"
   git branch -M main
   git remote add origin https://github.com/YOUR-USERNAME/kushbotics-calculator.git
   git push -u origin main
   ```

   Replace `YOUR-USERNAME` with your GitHub username. If you already created a remote repository, use its URL in the `git remote add origin` command.

## License

No license has been added because a license choice has not been specified. Choose a license before inviting others to reuse or redistribute the project.
