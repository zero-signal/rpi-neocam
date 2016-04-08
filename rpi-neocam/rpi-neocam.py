#!/usr/bin/env python2.7

# rpi-neocam.py
# ------------- 
#
# Version 0.2, April 2016
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
import neopixel as NEO

VERSION='0.2'

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

# class for interacting with Adafruit NeoPixels arranged as
# stick(8) -> ring(16) -> stick(8)
class LEDControl():

    def __init__(self):
        self.LED_COUNT      = 32
        self.LED_PIN        = 18
        self.LED_FREQ_HZ    = 800000
        self.LED_DMA        = 5
        self.LED_BRIGHTNESS = 10
        self.LED_INVERT     = False
        self.WAIT_MS        = 50

        self.logger = logging.getLogger('rpi-neocam')

        self.logger.debug('LEDs initialising.')

        self.strip = NEO.Adafruit_NeoPixel(self.LED_COUNT, self.LED_PIN, self.LED_FREQ_HZ, self.LED_DMA, self.LED_INVERT, self.LED_BRIGHTNESS)
        self.strip.begin()

        self.logger.debug('LEDs initialised.')

    # Performs a wipe of the specifed color along the entire length of strip
    def wipe(self, color):
        for i in range(0,8):
            self.strip.setPixelColor(i, color)
            self.strip.show()
            time.sleep(self.WAIT_MS/1000.0)

        for i in range(0,8):
            self.strip.setPixelColor(8 + i, color)
            self.strip.setPixelColor(((self.strip.numPixels() - 8) - i - 1), color)
            self.strip.show()
            time.sleep(self.WAIT_MS/1000.0)

        for i in range(24, self.strip.numPixels()):
            self.strip.setPixelColor(i, color)
            self.strip.show()
            time.sleep(self.WAIT_MS/1000.0)

    # Performs a wipe of the specified color around the ring section of the strip
    def ringWipe(self, color):
        for i in range(0,8):
            self.strip.setPixelColor(8 + i, color)
            self.strip.setPixelColor(((self.strip.numPixels() - 8) - i - 1), color)
            self.strip.show()
            time.sleep(self.WAIT_MS/1000.0)

        time.sleep(0.5)
        self.clear()

    # Sets the sticks in the strip to the specified color
    def stickSolid(self, color):
        for i in range(0,8):
            self.strip.setPixelColor(i, color)

        for i in range(24, self.strip.numPixels()):
            self.strip.setPixelColor(i, color)

        self.strip.show()

    # Perfoms a 'bounce' animation along the sticks in the strip
    def stickBounce(self, color):
        for x in range(0,2):
            for i in range(0,8):
                for j in range(0,8):
                    self.strip.setPixelColor(j, NEO.Color(0,0,0))
                    self.strip.setPixelColor(24 + j, NEO.Color(0,0,0))

                self.strip.setPixelColor(i, color)
                self.strip.setPixelColor(24 + i, color)

                self.strip.show()

                time.sleep(self.WAIT_MS/1000.0)

            for i in range(0,8):
                for j in range(0,8):
                    self.strip.setPixelColor(8 - j -1, NEO.Color(0,0,0))
                    self.strip.setPixelColor(self.strip.numPixels() - j - 1, NEO.Color(0,0,0))

                self.strip.setPixelColor(8 - i -1, color)
                self.strip.setPixelColor(self.strip.numPixels() - i - 1, color)

                self.strip.show()

                time.sleep(self.WAIT_MS/1000.0)

            self.clear()

    # Countdown timer animation using the ring
    def showTimer(self, secs):
            self.clear()

            if(secs >= 7):
                color = NEO.Color(255,0,0)
            elif (secs < 7 and secs >= 4):
                color = NEO.Color(255,255,0)
            else:
                color = NEO.Color(0,255,0)

            if(secs < 16):
                for i in range(0,secs):
                    self.strip.setPixelColor(8 + i, color)
            else:
                for i in range(8, 24):
                    self.strip.setPixelColor(i, color)
            
            self.strip.show()

    # Turns all LEDs off
    def clear(self):
        c = NEO.Color(0,0,0)
        for i in range(self.strip.numPixels()):
            self.strip.setPixelColor(i,c)

        self.strip.show()

    # Turn on the flash, using stickSolid, white color, increased brightness
    def flashOn(self):
        self.strip.setBrightness(100)
        self.stickSolid(NEO.Color(255,255,255))

    # Turn off the flash
    def flashOff(self):
        self.stickSolid(NEO.Color(0,0,0))
        self.strip.setBrightness(self.LED_BRIGHTNESS)
   
    # Performs an animation indicating the start of a still image capture sequence
    def stillStart(self):
        self.ringWipe(NEO.Color(255,0,0))

    # Performs an animation indicating the end of a still image capture sequence
    def stillEnd(self):
        self.ringWipe(NEO.Color(0,255,0))

    # Performs an animation indicating the start of a video capture
    def videoStart(self):
        self.stickBounce(NEO.Color(255,0,0))

    # Performs an animation indicating the end of a video capture
    def videoEnd(self):
        self.stickBounce(NEO.Color(0,255,0))

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

    def __init__(self, args, lock, group=None, target=None, name=None, verbose=None):
        super(CameraThread, self).__init__(group=group, target=target, name=name, verbose=verbose)
        self._init = threading.Event()
        self.lock = lock

        if (args.hflip):
            self.hflip = True
        else:
            self.hflip = False

        if (args.vflip):
            self.vflip = True
        else:
            self.vflip = False

    def is_init(self):
        return self._init.isSet()

    def init(self):
        self.lock.acquire()

        self.camera = CAM.PiCamera()

        # set flip if enabled
        if(self.hflip):
            self.camera.hflip = True
        if(self.vflip):
            self.camera.vflip = True

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
    def __init__(self, lock, args, group=None, target=None, name=None, verbose=None):

        super(StillThread,self).__init__(args=args, lock=lock, group=group, target=target, name=name, verbose=verbose)

        self.nshots = args.nshots
        self.delay  = args.delay
        self.output = args.output

    def capture(self):
        fn = self.output + os.path.sep + self.get_timestamp() + '.jpg'
        logger.debug('Generating still image: %s.' % fn)

        self.leds.flashOn()
        time.sleep(0.1)

        self.camera.capture(fn)
        self.leds.flashOff()

        logger.info('Generated still image: %s.' % fn)

    def increment(self):
        self.nshots += 1

    def run(self):
        logger.debug('Still camera thread running.')

        self.leds = LEDControl()
        self.leds.stillStart()

        if(not self.is_init()):
            self.init()

        count = 0
        while((count != self.nshots) and not self.stopped()):

            startTime = currTime = time.time()
            while(currTime - startTime < self.delay):
                self.leds.showTimer(int(self.delay - (currTime - startTime)))

                time.sleep(0.01)
                currTime = time.time()

            self.capture()
            count += 1

        self.leds.stillEnd()
        self.close()

        logger.debug('Still camera thread completed.')

# video camera controller thread
class VideoThread(CameraThread):
    def __init__(self, lock, args, group=None, target=None, name=None, verbose=None):

        super(VideoThread,self).__init__(args=args, lock=lock, group=group, target=target, name=name, verbose=verbose)

        self.length = args.length
        self.output = args.output

    def increment(self):
        self.length += 5

    def run(self):
        logger.debug('Video camera thread running.')

        self.leds = LEDControl()
        self.leds.videoStart()

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

        self.leds.videoEnd()

        self.close()
        logger.debug('Video camera thread completed.')


# main controller class responsible for thread and state management
class Controller():
    def __init__(self, args, btnPin=23):

        self.btnPin  = btnPin
        self.count   = 0

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(btnPin, GPIO.IN)

        self.state = State.STARTUP
        self.logger = logging.getLogger('rpi-neocam')

        self.args = args

        self.lock = threading.Lock()

        self.threads = { 
            'st' : StillThread(name='StillThread', lock=self.lock, args=self.args),
            'vt' : VideoThread(name='VideoThread', lock=self.lock, args=self.args)
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

        if(self.state == State.STARTUP):
            self.leds = LEDControl()

            for color in [NEO.Color(0,255,0),NEO.Color(255,255,0),NEO.Color(255,0,0)]:
                self.leds.wipe(color)

            self.leds.clear()

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
                            self.threads['st'] = StillThread(name='StillThread', lock=self.lock, args=self.args)
                    if(thread.name == 'VideoThread'):
                        if ((self.state == State.IDLE) and thread.is_init()):
                            self.threads['vt'] = VideoThread(name='VideoThread', lock=self.lock, args=self.args)
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
    parser.add_argument('-o', '--output', dest='output', default='.', metavar='DIR', help='output directory. Default: %(default)s.', type=lambda x: is_valid_directory(parser, x))
    parser.add_argument('-n', '--nshots', dest='nshots', default=5, type=int, metavar='N', help='number of shots in still mode. Default: %(default)i.')
    parser.add_argument('-d', '--delay', dest='delay', default=5, type=int, metavar='N', help='delay between shots in still mode. Default: %(default)i.')
    parser.add_argument('-l', '--length', dest='length', default=30, type=int, metavar='N', help='length of capture in video mode. Default: %(default)i.')
    parser.add_argument('-hf', '--hflip', dest='hflip', action='store_true', required=False, default=False, help='horizontally flip camera. Default: False.')
    parser.add_argument('-vf', '--vflip', dest='vflip', action='store_true', required=False, default=False, help='vertically flip camera. Default: False.')
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
    if(not args.nshots in range(1,61)):
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
