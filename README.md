rpi-neocam.py
-------------

Control a Raspberry Pi camera module and Adafruit Neopixel LEDs 
using a single button attached to an RPi GPIO pin.

Requirements
------------

- python-rpi.gpio
- python-picamera

- rpi_ws281x (https://github.com/jgarff/rpi_ws281x)

Tested on Python 2.7

Explanation
-----------

Uses a simple state machine and multi-threaded approach to RPi
camera control. Currently, supports both short and long press
detection of a button attached to RPi GPIO pin 23.

The program can currently capture still images sequences and 
video footage depending on the button presses used.

State machine is as follows:

- IDLE mode: Short press begins still image capture, Long press
begins video capture.
- STILL mode: Short press increments shot count, Long press aborts
currently running sequence.
- VIDEO mode: Short press extends video capture, Long press aborts
currently running sequence.

Various animations are displayed using the Neopixels according to the
currently selected capture mode. A camera flash is simulated using 
Neopixel sticks set to white color with increased brightness.

This script currently assumes the NeoPixels are configured as follows:

Stick(8) -> Ring(16) -> Stick(8)

It also assumes that the Neopixel string is connected to a PWM capable
GPIO pin on the Raspberry Pi (currently, hardcoded to pin 18)

Invocation
----------

Running the script is simple, with sensible defaults provided for 
most command line options:

```
usage: rpi-neocam.py [-h] [-o DIR] [-n N] [-d N] [-l N] [-hf] [-vf] [-v] [-V]

Raspberry Pi Camera and Adafruit NeoPixel controller script.

optional arguments:
  -h, --help            show this help message and exit
  -o DIR, --output DIR  output directory. Default: ..
  -n N, --nshots N      number of shots in still mode. Default: 5.
  -d N, --delay N       delay between shots in still mode. Default: 5.
  -l N, --length N      length of capture in video mode. Default: 30.
  -hf, --hflip          horizontally flip camera. Default: False.
  -vf, --vflip          vertically flip camera. Default: False.
  -v, --verbose         verbose output
  -V, --version         show program's version number and exit
```

Example:

```
sudo python rpi-neocam.py -o /home/pi -n 5 -d 1 -l 15
```

Debug level logging is enabled by supplying the --verbose or -V
command line parameter as follows:

```
sudo python rpi-neocam.py -o /home/pi -n 5 -d 1 -l 15 --verbose
```

Horizontal and vertical flipping of the camera can be enabled by
supplying the --hflip (or -hf) and --vflip (or -vf) as follows:

```
sudo python rpi-neocam.py -o /home/pi -n 5 -d 1 -l 15 --hflip --vflip
```

License & Copyright
-------------------

Copyright (C) 2016 - Zerosignal (zerosignal1982@gmail.com)

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

Raspberry Pi is a trademark of the Raspberry Pi Foundation. 
