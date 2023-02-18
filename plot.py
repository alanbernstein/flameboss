import time
import os
import requests
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter
import pandas as pd

from ipdb import set_trace as db, iex


# cook_id, target_temp_F = 3045172, 203  # friendsgiving brisket
cook_id, target_temp_F = 3100633, 225  # pork shoulder test

@iex
def main():
    cook = Cook(cook_id, target_temp_F)
    cook.plot()
    plt.show()


class Cook(object):
    update_period_sec = 60*5
    url_format_string = 'https://myflameboss.com/en/cooks/%s/raw'
    cache_path = '.'
    def __init__(self, cook_id, target_temp_F):
        self.cook_id = cook_id
        self.target_temp_F = target_temp_F

        self.fname = '%s/%s.csv' % (self.cache_path, self.cook_id)
        self.raw_url = self.url_format_string % cook_id

        self.mode = 'live'
        self.get_from_cache_or_url()
        self.transform_sensor_data()

    def get_from_cache_or_url(self):

        should_refresh = True
        if os.path.exists(self.fname):
            now = time.time()
            last_updated_timestamp = os.stat(self.fname).st_mtime
            last_updated_duration = now - last_updated_timestamp
            should_refresh = last_updated_duration > self.update_period_sec

        if should_refresh:
            resp = requests.get(self.raw_url)
            print('retrieved from %s' % self.raw_url)
            self.raw_csv = resp.content.decode('utf-8')
            with open(self.fname, 'w') as f:
                f.write(self.raw_csv)
            print('wrote to %s' % self.fname)
        else:
            print('cache age %ds < %ds, reading' % (last_updated_duration, self.update_period_sec))

        self.raw_data = pd.read_csv(self.fname)

    def transform_sensor_data(self):
        def translate(x):
            # convert raw temperature data to celsius
            x = x.mask(x<-32000, 0)  # clean spurious values
            x = x.mask(x>2300, 0)
            x = x/10             # transform to celsius
            x = x * 1.8 + 32     # convert to fahrenheit
            return x

        self.data = self.raw_data.copy(deep=True)
        for id in ['set_temp', 'pit_temp', 'meat_temp1']:
            self.data[id] = translate(self.data[id])


    def projection_linear_manual(self, t, m, start_fraction):
        t1 = t[int(len(t)*0.7)]
        t2 = t[len(t)-1]

        m = self.data['meat_temp1']
        m1 = m[int(len(t)*0.7)]
        m2 = m[len(t)-1]
        m3 = self.target_temp_F
        # (m2-m1)/(t2-t1) = (m3-m1)/(t3-t1)
        # (t2-t1)/(m2-m1) = (t3-t1)/(m3-m1)
        # (t2-t1)/(m2-m1)*(m3-m1) = (t3-t1)
        # t3 = t1 + (t2-t1)/(m2-m1)*(m3-m1)
        t3 = t1 + (t2-t1)/(m2-m1)*(m3-m1)

        print('t[0] = %s' % t[0])
        print('t[end] = %s' % t[len(t)-1])
        print('linear extrapolation:')
        print('1: %5.2f°F at %s' % (m1, t1))
        print('2: %5.2f°F at %s' % (m2, t2))
        print('3: %5.2f°F at %s' % (m3, t3))

        h = plt.plot([t1, t3], [m1, m3], 'c--', label='linear projection')
        plt.plot([t1, t2, t3], [m1, m2, m3], 'co')

        return t3, h


    def plot(self):
        t = pd.to_datetime(self.data['time'] - 60*60*6, unit='s')
        duty_cycle = self.data['duty_cycle'] / 100.0

        fig, ax1 = plt.subplots()
        h1 = ax1.plot(t, self.data['set_temp'], 'b-', label='set temp')
        h2 = ax1.plot(t, self.data['pit_temp'], 'r-', label='pit temp')
        h3 = ax1.plot(t, self.data['meat_temp1'], 'y-', label='meat temp')
        # h4 = ax1.plot(t, self.data['meat_temp2'], 'y-', label='meat temp2')
        t3, h5 = self.projection_linear_manual(t, self.data['meat_temp1'], 0.7)
        h6 = ax1.plot([t[0], t3], [self.target_temp_F]*2, 'k--', label='meat target')
        ax1.set_ylabel('°F')

        for label in ax1.get_xticklabels(which='major'):
            label.set(rotation=30, horizontalalignment='right')

        ax2 = ax1.twinx()
        h7 = ax2.plot(t, duty_cycle, color=[0, 0.5, 0, 0.5], linewidth=1, label='duty cycle')
        ax2.set_ylabel('fan duty cycle')
        ax2.grid('off')

        h = h1+h2+h3+h5+h6+h7
        l = [hh.get_label() for hh in h]
        ax1.legend(h, l, loc=0)
        ax2.xaxis.set_major_formatter(DateFormatter('%m/%d %H:%M'))

main()
