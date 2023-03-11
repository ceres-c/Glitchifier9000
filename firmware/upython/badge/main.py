# from enum import Enum, auto
# import signal
import os
import sys

try:
    os.mkdir('/data')
except OSError:
    print_debug('/data already exists')

import machine
import sys
import time
import select
import io

from micropython import const
from ssd1306 import SSD1306_I2C
from machine import Pin, I2C, Timer
from array import array

from ctf import ctf_main
from boot import BootAnimator
from glitchifier9000 import Glitchifier9000
from graphics import OLED_WIDTH, OLED_HEIGHT, OLED_I2C_ID, OLED_I2C_SCL, OLED_I2C_SDA
from debug import print_debug, toggle_debug
from nametag import read_namefile, write_namefile, NametagAnimator
from buttons import Buttons, BUTTON
from utils import enum, get_stdin_byte_or_button_press
from wackamole import WackIt
from tetris import Tetris


BadgeState = enum(
    REPL = const(0),

    NAMETAG_SHOW = const(1), 
    GLITCHIFIER9000 = const(2),
    CTF = const(3),
    WACKAMOLE = const(4),
    TETRIS = const(5),

    NAMETAG_SET = const(6), 
    CLEAR_DATA = const(7),
    TOGGLE_DEBUG = const(8),

    BOOT = const(90),
    MENU = const(91),

    IDLE = const(99),
)

# First two arguments are x,y base, to be provided in function call
TRIANGLE_POLY = (array('h', [3,0, 6,3, 3,6]), 1, 1)

def menu_line():
    return '\n'.join(f' {BadgeState.__dict__[x]}: {x}' for x in [
        'NAMETAG_SHOW', 
        'GLITCHIFIER9000', 
        'CTF',
        'WACKAMOLE',
        'TETRIS',
    ]) + '\n\n' + '\n'.join(f' {BadgeState.__dict__[x]}: {x}' for x in [
        'NAMETAG_SET', 
        'CLEAR_DATA', 
        'TOGGLE_DEBUG', 
    ]) + '\n\n' + '\n'.join(f' {BadgeState.__dict__[x]}: {x}' for x in [
        'REPL',
    ])

def init_i2c_oled():
    try:
        i2c = I2C(OLED_I2C_ID, sda=Pin(OLED_I2C_SDA), scl=Pin(OLED_I2C_SCL))
        oled = SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, i2c)
        return i2c, oled
    except:
        print_debug(f'I2C scan = {i2c.scan()}')
        print_debug(f'I2C Configuration = {i2c}')
        # print_debug(f'I2C Address = 0x{i2c.scan()[0]:x}')
        return None

def c_add(c, d):
    c -= 0x20
    c += d
    c %= 0x5f
    c += 0x20
    return c

class Main():
    def __init__(self, initial_state=BadgeState.BOOT) -> None:
        self.state = initial_state

        self.bootanimator = None
        self.nametaganimator = None
        self.name = ''

        self.in_char = None
        self.in_button = None

        self.menu_cursor_loc = 0 # In pixels
        self.name_cursor_loc = 0 # In characters

    def setup(self):
        self.name = read_namefile()
        ret = init_i2c_oled()
        if ret:
            self.i2c, self.oled = ret
        else:
            return ret

        self.buttons = Buttons(m.oled)
        self.buttons.button_action = self.buttons.button_record_recent
        return True

    def mainloop(self) -> None:
        self.bootanimator = BootAnimator(self.oled)
        self.nametaganimator = NametagAnimator(self.oled)

        while True:
            if self.state == BadgeState.BOOT:
                self.bootanimator.boot_animation_start(self.name,
                    boot_done_cb=lambda: self.nametaganimator.name_to_oled(self.name))

                self.state = BadgeState.IDLE
            
            elif self.state == BadgeState.MENU:
                # By default go back to MENU state
                selected = BadgeState.MENU
                
                # If we end here via stdin, give priority to that
                if self.in_char:
                    self.in_char = None
                    print_debug('Serial menu')
                    print(menu_line())
                    selected = input('> ')

                    print_debug(f'{selected=}')
                
                # Or we end up here via buttons, do button things
                elif self.in_button:
                    print_debug(f'{self.in_button=}')
                    self.in_button = None

                    print_debug('Screen menu')
                    self.oled.fill(0)
                    self.oled.poly(0, self.menu_cursor_loc, *TRIANGLE_POLY)

                    # Increments of 10 instead of 8 to have some spacing, but could fit 8 instead
                    # Same order as BadgeState enum
                    self.oled.text('NAMETAG_SHOW   ', 8, 0)
                    self.oled.text('GLITCHIFIER9000', 8, 8*1)
                    self.oled.text('CTF            ', 8, 8*2)
                    self.oled.text('WACKAMOLE      ', 8, 8*3)
                    self.oled.text('TETRIS         ', 8, 8*4)
                    self.oled.text('NAMETAG_SET    ', 8, 8*5)
                    self.oled.text('CLEAR_DATA     ', 8, 8*6)
                    self.oled.show()

                    # Wait for a button press
                    print_debug('Waiting for button')
                    while self.buttons.recent == None:
                        pass

                    print_debug(f'{self.buttons.recent=}')

                    # Recent is a tuple of GPIONUM, BUTTON enum index, BUTTON enum string
                    if self.buttons.recent[0] == BUTTON.DOWN:
                        self.menu_cursor_loc = (self.menu_cursor_loc + 8) % (8*7)
                    elif self.buttons.recent[0] == BUTTON.UP:
                        self.menu_cursor_loc = (self.menu_cursor_loc - 8) % (8*7)
                    elif self.buttons.recent[0] == BUTTON.MIDDLE:
                        selected = (self.menu_cursor_loc // 8) + 1 # Add one, 0 is REPL
                        print_debug(f'{self.menu_cursor_loc=} {selected=}')
                    
                    self.in_button = self.buttons.recent
                    self.buttons.recent = None

                else:
                    print_debug(f'Nothing in {self.in_char=} and {self.in_button=}, back to NAMETAG_SHOW')
                    selected = BadgeState.NAMETAG_SHOW

                try:
                    selected = int(selected)
                    if selected in BadgeState.__dict__.values():
                        self.state = selected
                    else:
                        raise ValueError
                except ValueError:
                    print(f'Invalid selection "{selected}"')

            elif self.state == BadgeState.NAMETAG_SHOW:
                self.name = read_namefile()
                print(f'Hello {self.name.strip()}!')

                self.nametaganimator.name_to_oled(self.name)

                self.state = BadgeState.IDLE
                
            elif self.state == BadgeState.NAMETAG_SET:
                # self.oled.fill(0)
                # self.oled.text('ENTER NAME OVER ', 0, 0)
                # self.oled.text('USB!            ', 0, 8)
                # self.oled.text('TODO MAKE BUTTON', 0, 24)
                # self.oled.text('INTERFACE FOR IT', 0, 32)
                # self.oled.show()


                # If we end here via stdin, give priority to that
                if self.in_char:
                    self.in_char = None

                    name = input('name?\n> ')
                    print_debug(f'{name=}')
                    if name:
                        write_namefile(name)
                    self.state = BadgeState.NAMETAG_SHOW

                # Or we end up here via buttons, do button things
                elif self.in_button:
                    print_debug(f'{self.in_button=}')
                    self.in_button = None

                    print_debug('Screen nameset')
                    self.oled.fill(0)

                    cursor_line = (self.name_cursor_loc + 1) * 8, 36, (self.name_cursor_loc + 2) * 8 - 1, 36

                    self.oled.line(*cursor_line, 1)
                    self.oled.text(m.name, 8, 28)
                    self.oled.show()

                    # Wait for a button press
                    print_debug('Waiting for button')
                    while self.buttons.recent == None:
                        pass

                    print_debug(f'{self.buttons.recent=}')

                    name = bytearray(self.name.encode())
                    print_debug(f'{self.name=}')
                    print_debug(f'{name=}')
                    if self.buttons.recent[0] == BUTTON.RIGHT:
                        self.name_cursor_loc = (self.name_cursor_loc + 1) % 14
                    elif self.buttons.recent[0] == BUTTON.LEFT:
                        self.name_cursor_loc = (self.name_cursor_loc - 1) % 14
                    elif self.buttons.recent[0] == BUTTON.UP:
                        name[self.name_cursor_loc] = c_add(name[self.name_cursor_loc], 1)
                    elif self.buttons.recent[0] == BUTTON.DOWN:
                        name[self.name_cursor_loc] = c_add(name[self.name_cursor_loc], -1)
                    elif self.buttons.recent[0] == BUTTON.MIDDLE:
                        self.name = name.decode()
                        print_debug(f'Permanently store {self.name=}')
                        print_debug(f'Back to NAMETAG_SHOW')
                        write_namefile(self.name)
                        self.state = BadgeState.NAMETAG_SHOW

                    self.name = name.decode()
                    print_debug(f'{name=}')
                    print_debug(f'{self.name=}')
                    
                    self.in_button = self.buttons.recent
                    self.buttons.recent = None
                else:
                    print_debug(f'Nothing in {self.in_char=} and {self.in_button=}, back to NAMETAG_SHOW')
                    self.state = BadgeState.NAMETAG_SHOW

            elif self.state == BadgeState.CLEAR_DATA:
                base = '/data'
                for f in os.listdir(base):
                    try:
                        print_debug('Remove ' + f'{base}/{f}')
                        os.remove(f'{base}/{f}')
                    except Exception as e:
                        print_debug(f'{base}/{f}')
                        print(f'{e=}')
                        pass
                
                break
            
            elif self.state == BadgeState.TOGGLE_DEBUG:
                toggle_debug()

                self.state = BadgeState.MENU
            
            elif self.state == BadgeState.IDLE:
                print_debug('ENTER IDLE')
                # machine.idle doesn't do much since we use CPU to animate screen with Timers

                # Wait for byte on stdin or button press
                self.in_char, self.in_button = get_stdin_byte_or_button_press(self.buttons, read_stdin=False)
                self.state = BadgeState.MENU

                # Kill any running animations
                if self.bootanimator.animating:
                    self.bootanimator.boot_animation_kill()
                if self.nametaganimator.animating:
                    self.nametaganimator.kill()
                
                
            elif self.state in [BadgeState.REPL, BadgeState.CTF, BadgeState.GLITCHIFIER9000, BadgeState.WACKAMOLE, BadgeState.TETRIS]:
                break

            else:
                self.state = BadgeState.MENU

        if self.bootanimator.animating:
            self.bootanimator.boot_animation_kill()
        if self.nametaganimator.animating:
            self.nametaganimator.kill()

        return self.state

if __name__ == '__main__':
    print('Riscufefe #5')
    print("Where's the FEFE, Lebowski!?")
    print()
    print('Press any button to reveal menu.')
    print()

    # m = Main(initial_state=BadgeState.NAMETAG_SET) # TODO: make sure it is BadgeState.BOOT (default)
    m = Main()
    if not m.setup():
        print('Could not set up screen, exit to REPL')
        sys.exit(-1)

    # Blink screen for alive check?
    m.oled.fill(1)
    m.oled.show()
    m.oled.fill(0)
    m.oled.show()

    exit_state = m.mainloop()

    if exit_state == BadgeState.CTF:
        def link_hider(timer):
            m.oled.fill(0)
            m.oled.show()

        def link_shower(timer):
            m.oled.fill(0)
            m.oled.text(' pastebin.com/  ', 0, 16)
            m.oled.text(' DbBdR2rs       ', 0, 24)
            m.oled.show()

            # Use another timer to hide so we don't hang for 200ms
            Timer().init(mode=Timer.ONE_SHOT, period=200, callback=link_hider)
            
        m.oled.fill(0)
        m.oled.show()
        tim = Timer()
        tim.init(freq=.3, callback=link_shower)
        ctf_main()

    if exit_state == BadgeState.GLITCHIFIER9000:
        g9k = Glitchifier9000(m.oled, m.buttons)
        g9k.glitchifier_loop()

    elif exit_state == BadgeState.WACKAMOLE:
        wack = WackIt(m.oled, m.buttons)
        wack.wackloop()

    elif exit_state == BadgeState.TETRIS:
        tetris = Tetris(m.oled, m.buttons)
        tetris.tetris_loop()

    elif exit_state == BadgeState.CLEAR_DATA:
        m.oled.fill(0)
        m.oled.text('REBOOT INCOMING', 0, 30)
        m.oled.show()
        machine.reset()

    elif exit_state == BadgeState.REPL:
        # drop to interpreter, happens automatically in mpy
        pass

