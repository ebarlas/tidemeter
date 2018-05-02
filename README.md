## Overview

Tide Meter is a Raspberry Pi Python project for illuminating WS281X LEDs to reflect the water level at a NOAA tide station.

It it build upon the [`rpi_ws281x`](https://github.com/jgarff/rpi_ws281x) library.

## Dependencies

Tide Meter has the following dependencies.

* [`noaatides`](https://github.com/ebarlas/noaatides) - package with modules for querying water level at tide stations
* [`neopixel`](https://github.com/jgarff/rpi_ws281x) - module for controlling WS281X LEDs
* [`RPi.GPIO`](https://pypi.org/project/RPi.GPIO) - module for interacting with Raspberry Pi GPIO pins

## Requirements

The following physical component are required:

* Raspberry Pi
* 16 WS281X LEDs in a sequence
* 2 GPIO inputs to toggle display and power

Optional components:

* Speakers (requires `espeak` text-to-speech package)
* 3rd GPIO input to toggle sound


## Details

When `tide_meter.py` is launched, it loads configurations from `config.json`.
If it is launched with a command line argument, the value is taken to be the preferred configuration file name. 
The program immediately begins downloading tide predictions from the NOAA
[CO-OPS API](https://tidesandcurrents.noaa.gov/api/) via the `predictions` module of the `noaatides` package.
Once tide predictions are available, LEDs will begin to illuminate to reflect the current
water level.

## Installation

Follow installation instructions for the dependencies above. All three external dependencies
must be installed with the `pip` package manager prior to running `tide_meter.py`.

Clone or copy this project directory to the `pi` user home directory on a Raspberry Pi.

Run `sudo python tidemeter.py` or `tidemeter.sh` to launch the program.

Logs are written to `tidemeter.log` and rotated at 100 KB. Three backups are retained in 
addition to the active log file. 

## Service

Install the app as a service using the steps in the raspberrypi.org systemd [reference document](https://www.raspberrypi.org/documentation/linux/usage/systemd.md).
The `tidemeter.sh` and `tidemeter.service` files are included as a convenience.

```bash
# copy service configuration
sudo cp tidemeter.service /etc/systemd/system/
...
# start tide meter service 
sudo systemctl start tidemeter.service
...
# enable tide meter service
sudo systemctl enable tidemeter.service
```

## Configuration

The following parameters are defined in `config.json`:

* `tide_station` - NOAA tide station ID
* `tide_time_offset` - low/high tide addition time offsets
* `tide_level_offset` - low/high tide multiplicative water level offsets
* `tide_request_window` - tide prediction relative time range in days back and forward to query
* `tide_renew_threshold` - threshold at which new tide predictions are queried
* `log_file_name` - log file name
* `sound_enabled` - sound enabled boolean
* `gpio_pin_display` - GPIO input pin for display toggle
* `gpio_pin_sound` - GPIO input pin for sound toggle
* `gpio_pin_power` - GPIO input pin for power off
* `led_pin` - GPIO output pin for LED strip
* `led_brightness` - brightness level, 0-255