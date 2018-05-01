import neopixel
import RPi.GPIO
import subprocess
import time
import os
import sys
import json
import datetime
import tideleds
import threading
import logging
import logging.handlers
from noaatides import predictions
from noaatides import task

# LED strip configuration:
LED_COUNT = 16  # Number of LED pixels.
LED_PIN = 21  # GPIO pin connected to the pixels (18 uses PWM!).
LED_FREQ_HZ = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA = 10  # DMA channel to use for generating signal (try 10)
LED_BRIGHTNESS = 255  # Set to 0 for darkest and 255 for brightest
LED_INVERT = False  # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL = 0  # set to '1' for GPIOs 13, 19, 41, 45 or 53
LED_STRIP = neopixel.ws.WS2811_STRIP_GRB  # Strip type and colour ordering

FNULL = open(os.devnull, 'w')

LED_CONFIG = tideleds.LedConfiguration(2, 2, 12, -2)

WHEEL_INTERVAL = 256 / LED_CONFIG.num_level_leds

COLOR_OFF = neopixel.Color(0, 0, 0)

COLOR_RED = neopixel.Color(255, 0, 0)
COLOR_GREEN = neopixel.Color(0, 255, 0)
COLOR_BLUE = neopixel.Color(0, 0, 255)
COLOR_MAGENTA = neopixel.Color(255, 0, 255)
COLOR_CYAN = neopixel.Color(0, 255, 255)

COLORS = [COLOR_RED, COLOR_GREEN, COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN]

RPi.GPIO.setmode(RPi.GPIO.BCM)

logger = logging.getLogger(__name__)


def init_logger(file_name):
    formatter = logging.Formatter('[%(asctime)s] <%(threadName)s> %(levelname)s - %(message)s')

    handler = logging.handlers.RotatingFileHandler(file_name, maxBytes=100000, backupCount=3)
    handler.setFormatter(formatter)

    log = logging.getLogger('')
    log.setLevel(logging.INFO)
    log.addHandler(handler)


def gpio_make_callback(pin, callback):
    def handler(channel):
        time.sleep(0.1)
        if RPi.GPIO.input(pin) == RPi.GPIO.HIGH:
            callback()

    return handler


def gpio_add_listener(pin, callback):
    RPi.GPIO.setup(pin, RPi.GPIO.IN, pull_up_down=RPi.GPIO.PUD_DOWN)
    RPi.GPIO.add_event_detect(pin, RPi.GPIO.RISING, callback=callback, bouncetime=500)


def wheel(pos):
    """Generate rainbow colors across 0-255 positions."""
    if pos < 85:
        return neopixel.Color(pos * 3, 255 - pos * 3, 0)
    elif pos < 170:
        pos -= 85
        return neopixel.Color(255 - pos * 3, 0, pos * 3)
    else:
        pos -= 170
        return neopixel.Color(0, pos * 3, 255 - pos * 3)


def wheel_color_mapper(n, i):
    return wheel(((n * WHEEL_INTERVAL) + i) & 255)


def to_color(color):
    return neopixel.Color(color[0], color[1], color[2])


def speak(message):
    # -g : Word gap. Pause between words, units of 10mS at the default speed
    # -a : Amplitude, 0 to 200, default is 100
    # -p : Pitch adjustment, 0 to 99, default is 50
    # -s : Speed in words per minute, default is 160
    # -k : Indicate capital letters with: 1=sound, 2=the word "capitals", higher values = a pitch increase (try -k20).
    return subprocess.Popen(
        ['espeak', message, '-g04ms', '-a150', '-p58', '-s175', '-k20'],
        stdout=FNULL,
        stderr=subprocess.STDOUT)


def announce_tide_events(tide_task, gpio_pin_sound):
    sound = {'on': True}

    def toggle_sound():
        sound['on'] = not sound['on']
        speak('The sound is now turned %s.' % ('on' if sound['on'] else 'off'))

    gpio_add_listener(gpio_pin_sound, gpio_make_callback(gpio_pin_sound, toggle_sound))

    prev = None

    while True:
        tide_now = tide_task.await_tide_now()

        if sound['on']:
            if prev and prev.tide_rising() != tide_now.tide_rising():
                h = 'high' if prev.tide_rising() else 'low'
                speak('It is now %s tide. The water level is %.2f feet.' % (h, tide_now.prev_tide.level))
            elif prev and int(tide_now.level) != int(prev.level):
                lvl = int(round(tide_now.level))
                f = 'foot' if lvl == 1 else 'feet'
                speak('The water level is %s %s.' % (lvl, f))

        prev = tide_now

        time.sleep(10)


def start_announcement_thread(tide_task, gpio_pin_sound):
    t = threading.Thread(target=announce_tide_events, args=(tide_task, gpio_pin_sound))
    t.setDaemon(True)
    t.start()


def log_tides(tide_task):
    while True:
        logger.info(tide_task.await_tide_now())
        time.sleep(60)


def start_tide_logger(tide_task):
    t = threading.Thread(target=log_tides, args=(tide_task,))
    t.setDaemon(True)
    t.start()


def render(strip, tide_leds):
    n = 0
    for led_group in [tide_leds.low_leds, tide_leds.led_strip, tide_leds.high_leds]:
        for led_color in led_group:
            strip.setPixelColor(n, led_color)
            n = n + 1
    strip.show()


def power_off():
    p = subprocess.Popen(
        ['sudo', 'shutdown', '-h', 'now'],
        stdout=FNULL,
        stderr=subprocess.STDOUT)

    p.wait()


def main():
    file_name = sys.argv[1] if len(sys.argv) == 2 else 'config.json'

    with open(file_name, 'rb') as config_file:
        config = json.load(config_file)

    tide_station = config['tide_station']
    tide_time_offset_low = config['tide_time_offset']['low']
    tide_time_offset_high = config['tide_time_offset']['high']
    tide_level_offset_low = config['tide_level_offset']['low']
    tide_level_offset_high = config['tide_level_offset']['high']
    tide_request_window_back = config['tide_request_window']['back']
    tide_request_window_forward = config['tide_request_window']['forward']
    tide_renew_threshold = config['tide_renew_threshold']
    gpio_pin_display = config['gpio_pin_display']
    gpio_pin_sound = config['gpio_pin_sound']
    gpio_pin_power = config['gpio_pin_power']

    init_logger(config['log_file_name'])

    strip = neopixel.Adafruit_NeoPixel(
        LED_COUNT,
        config['led_pin'],
        LED_FREQ_HZ,
        LED_DMA,
        LED_INVERT,
        config['led_brightness'],
        LED_CHANNEL,
        LED_STRIP)

    strip.begin()

    time_offset = predictions.AdditiveOffset(
        datetime.timedelta(minutes=tide_time_offset_low),
        datetime.timedelta(minutes=tide_time_offset_high))
    level_offset = predictions.MultiplicativeOffset(
        tide_level_offset_low,
        tide_level_offset_high)
    tide_offset = predictions.TideOffset(time_offset, level_offset)
    query_range = (
        datetime.timedelta(days=tide_request_window_back),
        datetime.timedelta(days=tide_request_window_forward))
    renew_threshold = datetime.timedelta(days=tide_renew_threshold)

    tt = task.TideTask(tide_station, tide_offset, query_range, renew_threshold)
    tt.start()

    start_tide_logger(tt)

    if config['sound_enabled']:
        start_announcement_thread(tt, gpio_pin_sound)

    def color_wheel(n):
        return wheel_color_mapper(n, 0)

    def color_wheel_offset(n, i):
        return wheel_color_mapper(n, i)

    color = {'mode': 0}

    color_modes = [
        lambda tl, tr: tideleds.count_up_display(LED_CONFIG, tl, tr, color_wheel, COLOR_OFF),
        lambda tl, tr: tideleds.count_up_solid_display(LED_CONFIG, tl, tr, COLOR_RED, COLOR_OFF),
        lambda tl, tr: tideleds.count_up_solid_display(LED_CONFIG, tl, tr, COLOR_GREEN, COLOR_OFF),
        lambda tl, tr: tideleds.count_up_solid_display(LED_CONFIG, tl, tr, COLOR_BLUE, COLOR_OFF),
        lambda tl, tr: tideleds.count_up_solid_display(LED_CONFIG, tl, tr, COLOR_MAGENTA, COLOR_OFF),
        lambda tl, tr: tideleds.count_up_solid_display(LED_CONFIG, tl, tr, COLOR_CYAN, COLOR_OFF),
        lambda tl, tr: tideleds.static_wheel_display(LED_CONFIG, tl, tr, color_wheel_offset, COLOR_OFF),
        lambda tl, tr: tideleds.static_solid_display(LED_CONFIG, tl, tr, COLOR_RED, COLOR_OFF),
        lambda tl, tr: tideleds.static_solid_display(LED_CONFIG, tl, tr, COLOR_GREEN, COLOR_OFF),
        lambda tl, tr: tideleds.static_solid_display(LED_CONFIG, tl, tr, COLOR_BLUE, COLOR_OFF),
        lambda tl, tr: tideleds.static_solid_display(LED_CONFIG, tl, tr, COLOR_MAGENTA, COLOR_OFF),
        lambda tl, tr: tideleds.static_solid_display(LED_CONFIG, tl, tr, COLOR_CYAN, COLOR_OFF),
        lambda tl, tr: tideleds.off_display(LED_CONFIG, COLOR_OFF),
    ]

    event = threading.Event()

    def next_mode():
        color['mode'] = (color['mode'] + 1) % len(color_modes)
        event.set()

    gpio_add_listener(gpio_pin_display, gpio_make_callback(gpio_pin_display, next_mode))
    gpio_add_listener(gpio_pin_power, gpio_make_callback(gpio_pin_power, power_off))

    while True:
        tide_now = tt.await_tide_now()
        level = tide_now.level
        rising = tide_now.tide_rising()
        led_generator = color_modes[color['mode']](level, rising)
        for tide_leds in led_generator:
            render(strip, tide_leds)
            if event.wait(tide_leds.display_time):
                event.clear()
                break


if __name__ == '__main__':
    main()
