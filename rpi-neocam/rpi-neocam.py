#!/usr/bin/env python2.7

# rpi-neocam.py
# ------------- 
#
# Version 0.1, March 2016
#
# Control a Raspberry Pi camera module and Adafruit NeoPixel LEDs
# using a single button attached to RPi GPIO input pin
#
# Copyright (C) 2014 - Zerosignal (zerosignal1982@gmail.com)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import sys
import time
import logging
import argparse
import datetime
import threading
import subprocess

import RPi.GPIO as GPIO
import picamera as CAM

VERSION='0.1'

# check whether a given argument is a valid directory
def is_valid_directory(parser, arg):
    if not os.path.isdir(arg):
        parser.error('The directory {} does not exist!'.format(arg))
    else:
        return arg

# simple enum used to maintain varying controller states
class State():
    IDLE     = 1
    STARTUP  = 2
    SHUTDOWN = 3
    CAMSTILL = 4
    CAMVIDEO = 5

# base class for a stoppable thread object
class StoppableThread(threading.Thread):
    
    def __init__(self, group=None, target=None, name=None, verbose=None):
        super(StoppableThread, self).__init__(group=group, target=target, name=name, verbose=verbose)
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()

    def stopped(self):
        return self._stop.isSet()

# base camera thread providing common functionality between modes
class CameraThread(StoppableThread):

    def __init__(self, lock, group=None, target=None, name=None, verbose=None):
        super(CameraThread, self).__init__(group=group, target=target, name=name, verbose=verbose)
        self._init = threading.Event()
        self.lock = lock

    def is_init(self):
        return self._init.isSet()

    def init(self):
        self.lock.acquire()

        self.camera = CAM.PiCamera()
        self.camera.start_preview()

        self.logger = logging.getLogger('rpi-neocam')
        self.logger.debug('Camera initialising.')

        time.sleep(2)

        self.logger.debug('Camera initialisation complete.')

        self._init.set()

    def close(self):
        self.camera.close()
        self.lock.release()

    def get_timestamp(self):
        return datetime.datetime.today().strftime("%Y%m%d-%H%M%S")

# still camera controller thread
class StillThread(CameraThread):
    def __init__(self, lock, output=None, nshots=5, delay=5, group=None, target=None, name=None, verbose=None):

        super(StillThread,self).__init__(lock=lock, group=group, target=target, name=name, verbose=verbose)

        self.nshots = nshots
        self.delay  = delay
        self.output = output

    def capture(self):
        fn = self.output + os.path.sep + self.get_timestamp() + '.jpg'
        logger.debug('Generating still image: %s.' % fn)

        self.camera.capture(fn)

        logger.info('Generated still image: %s.' % fn)

    def increment(self):
        self.nshots += 1

    def run(self):
        logger.debug('Still camera thread running.')

        if(not self.is_init()):
            self.init()

        count = 0
        while((count != self.nshots) and not self.stopped()):
            self.capture()
            count += 1

            startTime = time.time()
            while(time.time() - startTime < self.delay):
                time.sleep(0.01)

        self.close()
        logger.debug('Still camera thread completed.')

# video camera controller thread
class VideoThread(CameraThread):
    def __init__(self, lock, output=None, length=30, group=None, target=None, name=None, verbose=None):

        super(VideoThread,self).__init__(lock=lock, group=group, target=target, name=name, verbose=verbose)

        self.length = length
        self.output = output

    def increment(self):
        self.length += 5

    def run(self):
        logger.debug('Video camera thread running.')

        if(not self.is_init()):
            self.init()

        fn = self.output + os.path.sep + self.get_timestamp() + '.h264'
        logger.debug('Generating video %s.' % fn)

        self.camera.resolution = (640, 480)
        self.camera.start_recording(fn)

        count = 0
        while((count != self.length) and not self.stopped()):
            self.camera.wait_recording(1)
            count += 1

        self.camera.stop_recording()

        logger.info('Generated video %s.' % fn)

        self.close()
        logger.debug('Video camera thread completed.')


# main controller class responsible for thread and state management
class Controller():
    def __init__(self, args, btnPin=23):

        self.btnPin  = btnPin
        self.count   = 0

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(btnPin, GPIO.IN)

        self.state = State.IDLE
        self.logger = logging.getLogger('rpi-neocam')

        self.args = args

        self.lock = threading.Lock()

        self.threads = { 
            'st' : StillThread(name='StillThread', lock=self.lock, output=self.args.output, nshots=self.args.num, delay=self.args.delay), 
            'vt' : VideoThread(name='VideoThread', lock=self.lock, output=self.args.output, length=self.args.length),
            }

        threading.current_thread().name = 'CntrlThread'

    # callback function to handle reading button state from rpi-gpio
    def handle_button(self, pin):
        threading.current_thread().name = 'BttnThread'

        startTime = time.time()
        while (GPIO.input(pin) == False):
            time.sleep(0.01)

        self.count = self.count + 1

        logger.debug('Current state: %i' % self.state)

        pressTime = time.time() - startTime
        if(pressTime > 3):                                      # long press detected
            logger.debug('Long press detected.')

            # if we are idle, start a video capture
            if(self.state == State.IDLE):
                logger.info("Video capture started.")
                self.threads.get('vt').start()

            # if we are capturing still images, abort the thread
            if(self.state == State.CAMSTILL):
                if(self.threads.get('st').is_alive()):
                    self.threads.get('st').stop()

                logger.info("Still image capture aborted.")

            # if we are capturing video footage, abort the thread
            if(self.state == State.CAMVIDEO):
                if(self.threads.get('vt').is_alive()):
                    self.threads.get('vt').stop()

                logger.info("Video capture aborted.")
            
        else:                                                   # short press detected
            logger.debug('Short press detected.')

            # if we are idle, start a still image capture sequence
            if(self.state == State.IDLE):
                logger.info("Still image capture started.")
                self.threads.get('st').start()

            # if we are capturing still images, increment the counter
            if(self.state == State.CAMSTILL):
                if(self.threads.get('st').is_alive()):
                    self.threads.get('st').increment()

                logger.info("Still capture incremented.")

            # if we are capturing video footage, increment the time
            if(self.state == State.CAMVIDEO):
                if(self.threads.get('vt').is_alive()):
                    self.threads.get('vt').increment()

                logger.info("Video capture incremented.")


    def start(self):

        # set up the GPIO key press detection
        GPIO.add_event_detect(self.btnPin, GPIO.FALLING, callback=self.handle_button, bouncetime=200)

        # main controller loop, simple state machine
        try:
            while True:
                self.state = State.IDLE                 # assume we are idle until we discover otherwise

                # check whether one of our camera threads are running and,
                # if so, set the state accordingly.
                for thread in threading.enumerate():
                    if (thread.name == 'StillThread'):
                        self.state = State.CAMSTILL
                    if(thread.name == 'VideoThread'):
                        self.state = State.CAMVIDEO

                # check whether a thread has been run before and,
                # if so, recreate the object read for use again
                for thread in self.threads.itervalues():
                    if(thread.name == 'StillThread'):
                        if ((self.state == State.IDLE) and thread.is_init()):
                            self.threads['st'] = StillThread(name='StillThread', lock=self.lock, output=self.args.output, nshots=self.args.num, delay=self.args.delay)
                    if(thread.name == 'VideoThread'):
                        if ((self.state == State.IDLE) and thread.is_init()):
                            self.threads['vt'] = VideoThread(name='VideoThread', lock=self.lock, output=self.args.output, length=self.args.length)
                time.sleep(0.01)

        # clean up rpi-gpio
        except KeyboardInterrupt:
            pass
        finally:
            GPIO.cleanup()

# main entry point
if __name__ == '__main__':

    # argument parsing
    parser = argparse.ArgumentParser(description='Raspberry Pi Camera and Adafruit NeoPixel controller script.')
    parser.add_argument('-o', '--output', dest='output', default='~/Pictures', metavar='DIR', help='output directory. Default: %(default)s.', type=lambda x: is_valid_directory(parser, x))
    parser.add_argument('-n', '--num', dest='num', default=5, type=int, metavar='N', help='number of shots in still mode. Default: %(default)i.')
    parser.add_argument('-d', '--delay', dest='delay', default=5, type=int, metavar='N', help='delay between shots in still mode. Default: %(default)i.')
    parser.add_argument('-l', '--length', dest='length', default=30, type=int, metavar='N', help='length of capture in video mode. Default: %(default)i.')
    parser.add_argument('-v', '--verbose', dest='verbose', action='store_true', help='verbose output')
    parser.add_argument('-V', '--version', action='version', version='%(prog)s ' + VERSION)

    args = parser.parse_args()

    # logging setup
    logger = logging.getLogger('rpi-neocam')
    if(args.verbose):
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    ch = logging.StreamHandler(sys.stdout)
    fm = logging.Formatter('%(asctime)s - %(name)s - %(levelname)-5s - (%(threadName)-10s): %(message)s', "%Y-%m-%d %H:%M:%S")

    ch.setFormatter(fm)

    logger.addHandler(ch)

    # expand output path
    output = os.path.expanduser(args.output)
    logger.debug('Output path is: %s' % output)

    # make sure num shots is in range
    # min 1, max 60
    if(not args.num in range(1,61)):
        logger.error('Invalid number of shots specified.')
        sys.exit(1)

    # make sure delay is in range
    # min 1, max 60
    if(not args.delay in range(1,61)):
        logger.error('Invalid delay specified.')
        sys.exit(1)

    # make video length is in range
    # min 1, max 120
    if(not args.length in range(1,121)):
        logger.error('Invalid length specified.')
        sys.exit(1)

    logger.info('Controller starting.')

    # begin controller thread
    c = Controller(args=args, btnPin=23)
    c.start()

    logger.info('Controller exiting.')
