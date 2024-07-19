import datetime
import time
import os
import requests
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib.dates import DateFormatter
import pandas as pd

from ipdb import set_trace as db, iex


# cook_id, target_temp_F = 3045172, 203  # friendsgiving brisket
# cook_id, target_temp_F = 3100633, 225  # pork shoulder test 2023/02/18
# cook_id, target_temp_F = 3104143, 225  # brisket point 2023/02/20
# cook_id, target_temp_F = 4047252, 203  # brisket 2024/06/15
cook_id, target_temp_F = 4115257, 203  # brisket 2024/07/19

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

        is_dst = time.daylight and time.localtime().tm_isdst > 0
        self.utc_offset = - (time.altzone if is_dst else time.timezone)

        self.fig, self.ax1 = plt.subplots()
        # self.ax2 = self.ax1.twinx()
        self.anim = animation.FuncAnimation(self.fig, self.plot, interval=(self.update_period_sec+1)*1000, cache_frame_data=False)


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
            self.last_update_time = datetime.datetime.now()
        else:
            self.last_update_time = datetime.datetime.fromtimestamp(os.stat(self.fname).st_mtime)
            print('cache age %ds < %ds, reading' % (last_updated_duration, self.update_period_sec))

        self.raw_data = pd.read_csv(self.fname)

    def transform_sensor_data(self):
        def transform_temp(x):
            # convert raw temperature data to fahrenheit
            x = x.mask(x<-32000, 0)  # clean spurious values
            x = x.mask(x>2300, 0)
            x = x/10             # transform to celsius
            x = x * 1.8 + 32     # convert to fahrenheit
            return x

        def transform_duty_cycle(x):
            x = x / 100.0
            return x

        self.data = self.raw_data.copy(deep=True)
        for id in ['set_temp', 'pit_temp', 'meat_temp1']:
            self.data[id] = transform_temp(self.data[id])

        self.data['duty_cycle'] = transform_duty_cycle(self.data['duty_cycle'])

    def projection_linear_manual(self, t, m, start_fraction):
        t1 = t[int(len(t)*start_fraction)]
        t2 = t[len(t)-1]

        m = self.data['meat_temp1']
        m1 = m[int(len(t)*start_fraction)]
        m2 = m[len(t)-1]
        m3 = self.target_temp_F
        # (m2-m1)/(t2-t1) = (m3-m1)/(t3-t1)
        # (t2-t1)/(m2-m1) = (t3-t1)/(m3-m1)
        # (t2-t1)/(m2-m1)*(m3-m1) = (t3-t1)
        # t3 = t1 + (t2-t1)/(m2-m1)*(m3-m1)
        t3 = t1 + (t2-t1)/(m2-m1)*(m3-m1)
        t3_ = pd.Timestamp(t3.year, t3.month, t3.day, t3.hour, t3.minute) # truncate seconds
        if 0:
            print('t[0] = %s' % t[0])
            print('t[end] = %s' % t[len(t)-1])
            print('linear extrapolation:')
            print('1: %5.2f°F at %s' % (m1, t1))
            print('2: %5.2f°F at %s' % (m2, t2))
            print('3: %5.2f°F at %s' % (m3, t3_))

        h = plt.plot([t1, t3], [m1, m3], 'c--', label='linear projection')
        plt.plot([t1, t2, t3], [m1, m2, m3], 'co')

        plt.text(t3, m3+5, '%5.2f°F at %s' % (m3, t3_), color='c', ha='right', va='bottom')

        return t3, h


    def plot(self, *args, **kwargs):
        self.ax1.clear()
        # self.ax2.clear()

        self.get_from_cache_or_url()
        self.transform_sensor_data()

        t = pd.to_datetime(self.data['time'] + self.utc_offset, unit='s')

        h1 = self.ax1.plot(t, self.data['set_temp'], 'b-', label='set temp')
        h2 = self.ax1.plot(t, self.data['pit_temp'], 'r-', label='pit temp')
        h3 = self.ax1.plot(t, self.data['meat_temp1'], 'y-', label='meat temp')
        # TODO: set start_fraction via realtime value, connect to slider - OR just show 5min, 10min, 20min projections
        # h4 = self.ax1.plot(t, self.data['meat_temp2'], 'y-', label='meat temp2')
        t3, h5 = self.projection_linear_manual(t, self.data['meat_temp1'], 0.9)
        h6 = self.ax1.plot([t[0], t3], [self.target_temp_F]*2, 'k--', label='meat target')
        self.ax1.set_ylabel('°F')

        for label in self.ax1.get_xticklabels(which='major'):
            label.set(rotation=30, horizontalalignment='right')

        plt.title(f"Updated at {self.last_update_time.strftime('%Y-%m-%d %H:%M:%S')}")

        #h7 = self.ax2.plot(t, self.data['duty_cycle'], color=[0, 0.5, 0, 0.5], linewidth=1, label='duty cycle')
        #self.ax2.set_ylabel('fan duty cycle')
        #self.ax2.grid('off')

        #h = h1+h2+h3+h5+h6+h7
        h = h1+h2+h3+h5+h6
        l = [hh.get_label() for hh in h]
        self.ax1.legend(h, l, loc=0)
        #self.ax2.xaxis.set_major_formatter(DateFormatter('%m/%d %H:%M'))

main()
