# Hardware notes

This document records the wiring associated with the current calculator setup. The application source has not been changed.

## Display and touch SPI wiring

| Module pin / signal | Raspberry Pi connection |
|---|---|
| TFT MOSI / SDI | Physical pin 19, GPIO 10 / MOSI |
| XPT2046 T_DIN | Shared with MOSI, physical pin 19 |
| TFT MISO / SDO | Physical pin 21, GPIO 9 / MISO |
| XPT2046 T_OUT / SDO | Shared with MISO, physical pin 21 |
| TFT SCK | Physical pin 23, GPIO 11 / SCLK |
| XPT2046 T_CLK | Shared with SCLK, physical pin 23 |
| TFT CS | Physical pin 24, GPIO 8 / CE0 |
| TFT D/C | Physical pin 18, GPIO 24 |
| TFT RESET | Physical pin 22, GPIO 25 |
| XPT2046 T_CS | Physical pin 26, GPIO 7 / CE1 |
| XPT2046 T_IRQ | Not connected; touch is polled by the application |

The display board's VCC/backlight arrangement depends on the exact module revision. Confirm the board's voltage requirements before connecting power. Enable SPI using Raspberry Pi OS configuration before starting the program.
