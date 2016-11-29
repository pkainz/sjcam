#! /usr/bin/env python

#  victsing4k.py - VicTsing 4k WiFi Camera support functions
# 
#  This code is based on the code of Adam Laurie 2015, All rights reserved.
#
# note camera firmware seems to be very buggy!
# if you send an invalid command parameter, you will likely crash the camera
# and it will stop talking to you. power on/off is the only recourse!

import os
import sys
import requests
from xml.etree import ElementTree
from bs4 import BeautifulSoup
import subprocess
import math
import platform


# todo:
# 3002 lists what appears to be a bunch of other commands - need to explore!
# find a way to read current wifi name and password
# what does camera mode 2 do?
# camera modes 3 and 4 not working
# what is data from cmd 3019?


class camera:
    DEBUG = False
    ip = '192.168.1.254'
    DEVNULL = None
    MODE_PHOTO = '0'
    MODE_MOVIE = '1'
    MODE_TPHOTO = '4'
    MODE_TMOVIE = '3'
    START = '1'
    STOP = '0'
    ERROR_STATUS = '-256'
    # config commands with configurable parameters
    CONFIG = {
        '1002': ['Photo_Image_Size', '20M_5120x3840', '16M_4608x3456', '12M_4032x3024', '10M_3648x2736', '8M_3264x2448',
                 '5M_2592x1944', '3M_2048x1536', 'VGA_640x480', '1.2M_1280x960', '2M_1920x1080'],
        '1006': ['Sharpness', 'High', 'Normal', 'Medium'],
        '1007': ['White_Balance', 'Auto', 'Daylight', 'Cloudy', 'Tungsten', 'Fluorescent'],
        #'1008': ['Color', 'Color', 'B/W', 'Sepia'],  # not existent in victsing
        '1009': ['ISO', 'Auto', '100', '200', '400'],
        #'1011': ['Anti_Shaking', 'Off', 'On'],  # not existent at 1011 in victsing
        '2002': ['Movie_Resolution', 'UHD_24fps', 'QHD_30fps', '3MHD_30fps', 'FHD_96fps', 'FHD_60fps', 'FHD_30fps',
                 'HD_120fps', 'HD_60fps', 'HD_30fps', 'WVGA_30fps', 'VGA_240fps', 'VGA_30fps', 'QVGA_30fps'],
        '2003': ['Cyclic_Record', 'Off', '3min', '5min', '10min'],
        '2004': ['HDR/WDR', 'Off', 'On'],
        '2005': ['Exposure', '+2.0', '+5/3', '+4/3', '+1.0', '+2/3', '+1/3', '+0.0', '-1/3', '-2/3', '-1.0', '-4/3',
                 '-5/3', '-2.0'],
        '2006': ['Motion_Detection', 'Off', 'On'],
        '2007': ['Audio', 'Off', 'On'],
        '2008': ['Date_Stamping', 'Off', 'On'],
        #'2011': ['??UNKNOWN??'],  # returns status 0
        #   http://192.168.1.254/?custom=1&cmd=2011 (without 'par=' results in camera crash)
        #'2012': ['??UNKNOWN??'],  #
        #   http://192.168.1.254/?custom=1&cmd=2012 (without 'par=' results in camera crash)
        #'2013': ['??UNKNOWN??'],  #
        #   http://192.168.1.254/?custom=1&cmd=2013&par=* (always results in camera crash)
        #'2014': ['??UNKNOWN??'],  #
        #   http://192.168.1.254/?custom=1&cmd=2014&par=* (always results in camera crash)
        #'2016': ['??UNKNOWN??'],  # returns status 0, value 0
        #'2015': ['??UNKNOWN??'],  #
        #   http://192.168.1.254/?custom=1&cmd=2015 (without 'par=' results in camera crash)
        #'2017': ['??UNKNOWN??'],  #
        #   http://192.168.1.254/?custom=1&cmd=2017 (without 'par=' results in camera crash)
        #'2019': ['Videolapse', 'Off', '100ms', '200ms', '500ms', '1s', '2s', '5s'], # not existent on victsing at this index
        '3007': ['Auto_Power_Off', 'Off', '1min', '3min', '5min', '10min'],
        '3008': ['Language', 'English', 'French', 'German', 'Spanish', 'Italian', 'Portuguese',
                 'Russian', 'Unknown_1', 'Unknown_2', 'Unknown_3', 'Polish', 'Unknown_4'],
        #'3009': ['??UNKNOWN??'],
        '3010': ['Format', 'Cancel', 'OK'],
        '3011': ['Default_Setting', 'Cancel', 'OK'],
        '3025': ['Frequency', '50Hz', '60Hz'],
        '3026': ['Rotate', 'Off', 'On'],
        #'3033': ['??UNKNOWN??'],
    }

    # Params that cannot be set via WiFi
    # Gyroscope
    # Diving Mode

    # commands with no or free-form string parameters
    COMMANDS = {
        'CONFIG': '3014',
        'DATE': '3005',
        'DISK_SPACE': '3017',
        'MODE_PHOTO_MOVIE': '3001',
        'MOVIE_REMAINING': '2009',
        'PHOTOS_REMAINING': '1003',
        'SNAP': '1001',
        'START_STOP': '2001',
        'STATUS_MODE': '3016',
        'TIME': '3006',
        'VERSION': '3012',
        'WIFI_NAME': '3003',
        'WIFI_PW': '3004',
    }

    def get_config_by_name(self, config):
        for conf in self.CONFIG:
            if self.CONFIG[conf][0].upper() == config.upper():
                return conf
        return None

    def get_remaining_photos(self):
        ret, info = self.send_command('PHOTOS_REMAINING')
        if not ret:
            return ret, info
        remaining = self.get_element(info, 'Value')
        if remaining:
            return True, int(remaining)
        return False, 0

    def get_version(self):
        ret, info = self.send_command('VERSION')
        if not ret:
            return ret, info
        ver = self.get_element(info, 'String')
        if ver:
            return True, str(ver)
        return False, 0

    def get_remaining_movie(self):
        ret, info = self.send_command('MOVIE_REMAINING')
        if not ret:
            return ret, info
        remaining = self.get_element(info, 'Value')
        if remaining:
            m, s = divmod(int(remaining), 60)
            h, m = divmod(m, 60)
            return True, h, m, s
        return False, 0, 0, 0

    def get_disk_space(self):
        ret, info = self.send_command('DISK_SPACE')
        if not ret:
            return ret, info
        space = self.get_element(info, 'Value')
        if space:
            return True, int(space)
        return False, 0

    # extract a single element from response to 'send_command'
    def get_element(self, response, element):
        tree = ElementTree.fromstring(response.text)
        try:
            return tree.find(element).text
        except:
            return None

    def get_file(self, path, f):
        ret, flen = self.print_directory(quiet=True, find=f)
        if not ret:
            return False, "Could not read directory"
        if not flen:
            return False, "Could not get file length"
        r = requests.get("http://" + self.ip + f, stream=True)
        fname = f.split('/')[-1:][0]
        outfile = open(path + fname, "wb")
        gotlen = 0
        for chunk in r.iter_content(chunk_size=2048 * 1024):
            if chunk:  # filter out keep-alive new chunks
                gotlen += len(chunk)
                print '    %s of %s    \r' % (self.human_readable(gotlen), flen)
                sys.stdout.flush()
                outfile.write(chunk)
        outfile.close()
        r.close()
        return True, fname

    # return file length and creation date/time from html table
    def get_file_details(self, cells, filename):
        for x in range(len(cells)):
            try:
                entry = cells[x].findChildren('a')[0].get('href')
            except:
                continue
            if entry == filename:
                return cells[x + 1].string.strip(), cells[x + 2].string.strip().split(' ')[0], \
                       cells[x + 2].string.strip().split(' ')[1]
        return None, None, None

    def get_mode(self):
        # TODO this mode always returns 0, not sure if this reflects the status of the camera!
        ret, info = self.send_command('STATUS_MODE')
        if ret:
            return True, self.get_element(info, 'Status')
        else:
            return False, info

    # not sure what's going on here, but we seem to be able to grab a low res image
    # when in PHOTO mode
    def get_preview(self):
        r = requests.get('http://' + self.ip + ':8192/', stream=True)
        if not r.raw.readline().strip() == "--arflebarfle":
            return False, 'Preview image not found!'
        size = 0
        # 4 lines of header including blank
        for x in range(3):
            header = r.raw.readline()
            if header.startswith('Content-length:'):
                size = int(header.split(' ')[1])
        if not size:
            return False, 'Could not determine image size!'
        data = r.raw.read(size)
        r.close()
        return True, data

    def http_test(self):
        try:
            resp = requests.get('http://' + self.ip, timeout=1)
        except:
            return 'HTTP socket CLOSED'
        if resp.status_code == 200:
            return 'HTTP socket OPEN'
        return 'HTTP socket open but returned: %d' % resp.status_code

    def human_readable(self, num):
        units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB']
        p = math.floor(math.log(num, 2) / 10)
        return "%.2f %s" % (num / math.pow(1024, p), units[int(p)])

    def ping(self):
        ret = subprocess.Popen(["ping", "-c1", "-W 1", self.ip], stdout=subprocess.PIPE).communicate()[0]
        if ret.find(' 0%') >= 0 or (platform.system() == 'Darwin' and ret.find(' 0.0%') >= 0):
            return 'Host is UP'
        return 'Host is DOWN'

    def print_config_help(self, parameter):
        if parameter:
            print '    %s:' % self.CONFIG[self.get_config_by_name(parameter)][0]
            print ', '.join([i for i in self.CONFIG[self.get_config_by_name(parameter)][1:]])
        else:
            for item in self.CONFIG:
                print '    %s:' % self.CONFIG[item][0],
                print ', '.join([i for i in self.CONFIG[item][1:]])

    def print_config(self):
        ret, info = self.send_command('CONFIG')
        if ret:
            tree = ElementTree.fromstring(info.text)
            # XML is not properly nested, so we need to kludge it
            print
            for branch in tree:
                if branch.tag == 'Status':
                    try:
                        print self.CONFIG[current][int(branch.text) + 1]
                    except:
                        print branch.text
                else:
                    current = branch.text
                    try:
                        print '    %s:' % self.CONFIG[branch.text][0],
                    except:
                        print '    %s:' % branch.text,
        else:
            return False, "Couldn't read config!"
        return True, None

    def print_directory(self, quiet=False, find=None):
        for thing in "PHOTO", "MOVIE":
            if not quiet:
                print
                print '    %s:' % thing
                print
            try:
                resp = requests.get("http://" + self.ip + "/NOVATEK/%s" % thing, timeout=5)
            except:
                return False, 'Timeout!'
            if resp.status_code != 200:
                return False, resp
            soup = BeautifulSoup(resp.text, 'lxml')
            try:
                table = soup.findChildren('table')[0]
            except:
                break
            rows = table.findChildren(['tr'])
            for row in rows:
                cells = row.findChildren('td')
                for cell in cells:
                    if cell.findChildren('a'):
                        entry = cell.findChildren('a')[0].get('href')
                        if entry.find('del') > 0:
                            continue
                        fsize, fdate, ftime = self.get_file_details(cells, entry)
                        if find == entry:
                            return True, fsize
                        if not quiet:
                            print '      %s    % 10.10s    %s    %s' % (entry, fsize, fdate, ftime)
        if not quiet:
            print
            print '    SD Card space remaining:',
            ret, sd = self.get_disk_space()
            if not ret:
                return ret, sd
            if sd == 0:
                print 'None!'
            else:
                print self.human_readable(sd)

    # send command by name or number
    def send_command(self, command, param=None, str_param=None):
        try:
            full_command = 'http://' + self.ip + '/?custom=1&cmd=' + self.COMMANDS[command]
        except:
            full_command = 'http://' + self.ip + '/?custom=1&cmd=' + command
        if param:
            full_command += '&par=' + param
        if str_param:
            full_command += '&str=' + str_param
        if self.DEBUG:
            print 'DEBUG: >>>', full_command
        try:
            resp = requests.get(full_command, timeout=5)
            if self.DEBUG:
                print 'DEBUG: <<<', resp
        except:
            return False, 'Timeout!'
        if resp.status_code == 200:
            return True, resp
        else:
            return False, resp

    def set_config(self, param, val):
        config = self.get_config_by_name(param)
        if not config:
            return False, 'No such parameter'
        found = False
        for num, item in enumerate(self.CONFIG[config]):
            if item.upper() == val.upper():
                found = True
                num -= 1
                break
        if not found:
            return False, 'Invalid value for parameter'
        return self.send_command(config, param=str(num))

    def set_date(self, date):
        return self.send_command('DATE', str_param=date)

    def set_mode(self, mode):
        if mode == 'PHOTO':
            ret, info = self.send_command('MODE_PHOTO_MOVIE', param=self.MODE_PHOTO)
            if not ret:
                return ret, info
            switch = self.MODE_PHOTO
        elif mode == 'TPHOTO':
            ret, info = self.send_command('MODE_PHOTO_MOVIE', param=self.MODE_TPHOTO)
            if not ret:
                return ret, info
            switch = self.MODE_TPHOTO
        elif mode == 'MOVIE':
            ret, info = self.send_command('MODE_PHOTO_MOVIE', param=self.MODE_MOVIE)
            if not ret:
                return ret, info
            switch = self.MODE_MOVIE
        elif mode == 'TMOVIE':
            ret, info = self.send_command('MODE_PHOTO_MOVIE', param=self.MODE_TMOVIE)
            if not ret:
                return ret, info
            switch = self.MODE_TMOVIE
        else:
            return False, 'Unrecognised MODE'
        return True, switch
        # wait for mode switch
        # while 42:
        #     # TODO this hangs in a loop, because the camera does not return the mode properly
        #     stat, mode = self.get_mode()
        #     if stat:
        #         if mode == switch:
        #             return True, None
        #     else:
        #         return False, mode

    def set_time(self, time):
        return self.send_command('TIME', str_param=time)

    def set_wifi_name(self, name):
        return self.send_command('WIFI_NAME', str_param=name)

    def set_wifi_pw(self, pw):
        return self.send_command('WIFI_PW', str_param=pw)

    # take a picture, optionally store it, and return the DCIM filename
    def snap(self, path):
        ret, info = self.send_command('SNAP')
        if not ret:
            return ret, info
        try:
            resp = requests.get("http://" + self.ip + "/NOVATEK/PHOTO", timeout=5)
        except:
            return False, 'Timeout!'
        if resp.status_code != 200:
            return False, resp
        soup = BeautifulSoup(resp.text, 'html.parser')
        f = soup.find_all('a')[len(soup.find_all('a')) - 2].get('href')
        fname = f.split('/')[-1:][0]
        if path:
            return self.get_file(path, f)
        return True, fname

    def start_stop_movie(self, action):
        return self.send_command('START_STOP', param=action)

    def stream(self):
        if not self.DEVNULL:
            self.DEVNULL = open(os.devnull, 'wb')
        subprocess.Popen(['vlc', 'rtsp://' + self.ip + ':554/stream0/svc0/track1'],
                         stdout=self.DEVNULL,
                         stderr=subprocess.STDOUT)
