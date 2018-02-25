import requests
import pytz
import time
import datetime
import math
import threading
import csv

FORMAT_DATETIME = '%Y-%m-%dT%H:%M'
FORMAT_ISO8601 = '%Y-%m-%dT%H:%M:%SZ'

URL_NOAA = 'https://tidesandcurrents.noaa.gov/ioos-dif-sos/SOS'

TZ_UTC = pytz.timezone('UTC')
TZ_PAC = pytz.timezone('America/Los_Angeles')

HEADER_TIME = 'time_ISO8601'
HEADER_LEVEL = 'sea_surface_height_amplitude_due_to_equilibrium_ocean_tide [feet]'
HEADER_TYPE = 'type'


class TideOffset:
    def __init__(self, time, level):
        self.time = time
        self.level = level

    def __str__(self):
        return 'time={}, level={}'.format(self.time, self.level)

    def apply(self, prediction):
        i = 0 if prediction.high else 1
        return TidePrediction(
            prediction.time + datetime.timedelta(minutes=self.time[i]),
            prediction.level * self.level[i],
            prediction.high)

    def apply_all(self, predictions):
        return [self.apply(p) for p in predictions]


class TidePrediction:
    def __init__(self, time, level, high):
        self.time = time
        self.level = level
        self.high = high

    def __str__(self):
        return 'time={}, level={}, type={}'.format(
            format_datetime_local(self.time),
            self.level,
            'H' if self.high else 'L')


def parse_tide_prediction(str_time, str_level, str_high):
    return TidePrediction(parse_datetime_iso8601(str_time), float(str_level), str_high == 'H')


def parse_datetime_iso8601(utc_date_string):
    return datetime.datetime.strptime(utc_date_string, FORMAT_ISO8601).replace(tzinfo=TZ_UTC)


def format_datetime_iso8601(utc_datetime):
    return utc_datetime.strftime(FORMAT_ISO8601)


def format_datetime_local(utc_datetime):
    return utc_datetime.astimezone(TZ_PAC).strftime(FORMAT_DATETIME)


def request_tide_predictions(station_id, utc_from, utc_to):
    """
    Center for Operational Oceanographic Products and Services (CO-OPS)
    https://opendap.co-ops.nos.noaa.gov/ioos-dif-sos/
    """
    params = {
        'service': 'SOS',
        'request': 'GetObservation',
        'version': '1.0.0',
        'observedProperty': 'sea_surface_height_amplitude_due_to_equilibrium_ocean_tide',
        'offering': 'urn:ioos:station:NOAA.NOS.CO-OPS:{}'.format(station_id),
        'responseFormat': 'text/tab-separated-values',
        'eventTime': '{}/{}'.format(format_datetime_iso8601(utc_from), format_datetime_iso8601(utc_to)),
        'result': 'VerticalDatum==urn:ioos:def:datum:noaa::MLLW',
        'dataType': 'HighLowTidePredictions',
        'unit': 'Feet'
    }

    return requests.get(url=URL_NOAA, params=params).text


def parse_tide_predictions(text):
    lines = text.splitlines(False)
    header = lines[0].split('\t')

    pos_time = header.index(HEADER_TIME)
    pos_level = header.index(HEADER_LEVEL)
    pos_type = header.index(HEADER_TYPE)

    lines = (line.split('\t') for line in lines[1:])
    return [parse_tide_prediction(line[pos_time], line[pos_level], line[pos_type]) for line in lines]


def find_tide_pair(predictions, time):
    prev = None
    for p in predictions:
        if prev and prev.time <= time <= p.time:
            return prev, p
        prev = p


def _tide_sin(time):
    return (1 + math.sin((-0.5 + time) * math.pi)) / 2


def tide_level(tide_prev, tide_next, time_test):
    time_range = tide_next.time - tide_prev.time
    time_offset = time_test - tide_prev.time
    time_percent = time_offset.total_seconds() / time_range.total_seconds()
    level_range = tide_next.level - tide_prev.level
    return tide_prev.level + level_range * _tide_sin(time_percent)


def store_tide_prediction(predictions, file_name):
    with open(file_name, 'wb') as csvfile:
        writer = csv.writer(csvfile, delimiter=' ', quotechar='|', quoting=csv.QUOTE_MINIMAL)
        for p in predictions:
            writer.writerow([format_datetime_iso8601(p.time), p.level, 'H' if p.high else 'L'])


def load_tide_predictions(file_name):
    predictions = []
    with open(file_name, 'rb') as csvfile:
        reader = csv.reader(csvfile, delimiter=' ', quotechar='|')
        for row in reader:
            predictions.append(parse_tide_prediction(*row))
    return predictions


class TideNow:
    def __init__(self, prev_tide, next_tide, level, time):
        self.prev_tide = prev_tide
        self.next_tide = next_tide
        self.level = level
        self.time = time

    def tide_rising(self):
        return self.next_tide.high

    def __str__(self):
        return 'prev_tide=[{}], next_tide=[{}], level={}, time={}'.format(
            str(self.prev_tide),
            str(self.next_tide),
            self.level,
            format_datetime_local(self.time))


class TideTask:
    def __init__(self, tide_station, tide_offset, time_range, renew_threshold, file_name):
        self.tide_station = tide_station
        self.tide_offset = tide_offset
        self.time_range = time_range
        self.renew_threshold = renew_threshold
        self.file_name = file_name
        self.predictions = []
        self._try_load()

    def _try_load(self):
        try:
            self.predictions = load_tide_predictions(self.file_name)
            print('loaded %d predictions from %s' % (len(self.predictions), self.file_name))
        except Exception:
            pass

    def _try_store(self):
        try:
            store_tide_prediction(self.predictions, self.file_name)
            print('stored %d predictions to %s' % (len(self.predictions), self.file_name))
        except Exception:
            pass

    def should_renew_tides(self):
        return not self.predictions or self.predictions[-1].time < datetime.datetime.now(TZ_UTC) + self.renew_threshold

    def renew(self):
        now = datetime.datetime.now(TZ_UTC)
        text = request_tide_predictions(self.tide_station, now - self.time_range[0], now + self.time_range[1])
        self.predictions = self.tide_offset.apply_all(parse_tide_predictions(text))
        print 'renewed tides, count=%s, first=%s, last=%s' % (
            len(self.predictions),
            format_datetime_local(self.predictions[0].time),
            format_datetime_local(self.predictions[-1].time))
        self._try_store()

    def await_tide_now(self):
        while True:
            now = datetime.datetime.now(TZ_UTC)
            pair = find_tide_pair(self.predictions, now)
            if pair:
                level = tide_level(pair[0], pair[1], now)
                return TideNow(pair[0], pair[1], level, now)
            time.sleep(1)

    def _run_once(self):
        try:
            if self.should_renew_tides():
                self.renew()
        except Exception as ex:
            print 'error occurred querying tide predictions: ', ex

    def _run_loop(self):
        while True:
            self._run_once()
            time.sleep(60)

    def start(self):
        t = threading.Thread(target=self._run_loop)
        t.setDaemon(True)
        t.start()


def main():
    now = datetime.datetime.now(TZ_UTC)
    delta = datetime.timedelta(days=1)
    text = request_tide_predictions('9414290', now - delta, now + delta)
    print(text)

    print('-----')
    predictions = parse_tide_predictions(text)
    for p in predictions:
        print(p)

    print('-----')
    offset = TideOffset((131, 179), (1.15, 0.82))
    offset_predictions = offset.apply_all(predictions)
    for p in offset_predictions:
        print(p)

    print('-----')
    file_name = 'tides.csv'
    store_tide_prediction(offset_predictions, file_name)
    print('stored predictions to %s' % file_name)

    print('-----')
    loaded_predictions = load_tide_predictions(file_name)
    print('loaded %d predictions from %s' % (len(loaded_predictions), file_name))
    print('last loaded prediction: %s' % str(loaded_predictions[-1]))

    pair = find_tide_pair(offset_predictions, now)
    print('-----')
    print(pair[0])
    print(pair[1])
    print(tide_level(pair[0], pair[1], now))

    print('-----')
    tt = TideTask(
        '9414290',
        TideOffset((131, 179), (1.15, 0.82)),
        (datetime.timedelta(days=1), datetime.timedelta(days=7)),
        datetime.timedelta(days=1),
        'tasktides.csv')
    tt.start()
    tide_now = tt.await_tide_now()
    print(tide_now)


if __name__ == '__main__':
    main()
