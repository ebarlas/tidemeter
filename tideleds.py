class LedConfiguration():
    def __init__(self, num_low_leds, num_high_leds, num_level_leds, min_led_level):
        self.num_low_leds = num_low_leds
        self.num_high_leds = num_high_leds
        self.num_level_leds = num_level_leds
        self.min_led_level = min_led_level


class TideLeds():
    def __init__(self, low_leds, high_leds, led_strip, display_time):
        self.low_leds = low_leds
        self.high_leds = high_leds
        self.led_strip = led_strip
        self.display_time = display_time

    def __str__(self):
        return 'low_leds={}, high_leds={}, led_strip={}, display_time={}'.format(
            self.low_leds, self.high_leds, self.led_strip, self.display_time)


def _high_low_leds(led_config, tide_rising, color_mapper, color_off):
    low_leds = [color_off if tide_rising else color_mapper(0)] * led_config.num_low_leds
    high_leds = [color_mapper(led_config.num_level_leds - 1) if tide_rising else color_off] * led_config.num_high_leds
    return low_leds, high_leds


def count_up_display(led_config, tide_level, tide_rising, color_mapper, color_off):
    low_leds, high_leds = _high_low_leds(led_config, tide_rising, color_mapper, color_off)

    led_strip = [color_off] * led_config.num_level_leds
    yield TideLeds(low_leds, high_leds, led_strip, 1)

    level_floor = int(tide_level)
    for n in range(led_config.num_level_leds):
        led_level = n + led_config.min_led_level
        if level_floor >= led_level:
            led_strip[n] = color_mapper(n)
            yield TideLeds(low_leds, high_leds, led_strip, 1)
        else:
            diff = int((tide_level - level_floor) * 10)
            for i in range(diff):
                for c in [color_mapper(n), color_off]:
                    led_strip[n] = c
                    yield TideLeds(low_leds, high_leds, led_strip, 0.1)
            return


def count_up_solid_display(led_config, tide_level, tide_rising, color_on, color_off):
    return count_up_display(led_config, tide_level, tide_rising, lambda n: color_on, color_off)


def off_display(led_config, color_off):
    low_leds = [color_off] * led_config.num_low_leds
    high_leds = [color_off] * led_config.num_high_leds
    led_strip = [color_off] * led_config.num_level_leds
    off_leds = TideLeds(low_leds, high_leds, led_strip, 1)
    while True:
        yield off_leds


def static_display(led_config, tide_level, tide_rising, color_mapper, color_off, display_time):
    low_leds, high_leds = _high_low_leds(led_config, tide_rising, color_mapper, color_off)

    led_strip = [color_off] * led_config.num_level_leds
    level_floor = int(tide_level)
    for n in range(led_config.num_level_leds):
        led_level = n + led_config.min_led_level
        if level_floor >= led_level:
            led_strip[n] = color_mapper(n)

    yield TideLeds(low_leds, high_leds, led_strip, display_time)


def static_solid_display(led_config, tide_level, tide_rising, color_on, color_off):
    return static_display(led_config, tide_level, tide_rising, lambda n: color_on, color_off, 10)


def static_wheel_display(led_config, tide_level, tide_rising, color_mapper, color_off):
    for i in range(256):
        mapper = lambda n: color_mapper(n, i)
        for tide_leds in static_display(led_config, tide_level, tide_rising, mapper, color_off, 0.1):
            yield tide_leds


def main():
    for tm in static_wheel_display(LedConfiguration(2, 2, 12, -2), 5.35, True, lambda n, i: n + i, 0):
        print(tm)


if __name__ == '__main__':
    main()
