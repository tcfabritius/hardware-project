from ssd1306 import SSD1306_I2C
from led import Led
from piotimer import Piotimer
import filefifo
from machine import Pin, ADC, I2C
from fifo import Fifo
import time
import micropython
micropython.alloc_emergency_exception_buf(200)

#Menu and OLED
items = [1,2,3]
menuIndex = 0
events = Fifo(30)
i2c = I2C(1, scl=Pin(15), sda=Pin(14), freq=400000)
oled = SSD1306_I2C(128, 64, i2c)
menuActive = True

class InterruptButton:
    def __init__(self, button_pin, fifo):
        self.button = Pin(button_pin, mode=Pin.IN, pull=Pin.PULL_UP)
        self.lastPress = time.ticks_ms()
        self.fifo = fifo
        self.button.irq(handler=self.handler, trigger=Pin.IRQ_FALLING, hard=True)
    
    def handler(self, pin):
        now = time.ticks_ms()
        if time.ticks_diff(now, self.lastPress) > 250: #250ms cooldown
            self.lastPress = now
            self.fifo.put(0)

class Encoder:
    def __init__(self, rot_a, rot_b, fifo):
        self.a = Pin(rot_a, mode=Pin.IN)
        self.b = Pin(rot_b, mode=Pin.IN)
        self.fifo = fifo
        self.a.irq(handler=self.handler, trigger=Pin.IRQ_RISING, hard=True)

    def handler(self, pin):
        if self.b.value():
            #Left
            self.fifo.put(-1)
        else:
            #Right
            self.fifo.put(1)

def showSelection(index):
    global menuActive
    oled.fill(0)
    oled.text("Selected:", 1, 1, 1)
    oled.text(f"Menu {index+1}", 1, 20, 1)
    oled.show()
    time.sleep(0.1)
    menuActive = False
    oled.fill(0)
    oled.text(f"Menu {index+1}", 1, 1, 1)
    oled.text("Rot1 = Exit.", 1, 20, 1)
    oled.show()
    time.sleep(1)

def updateMenu():
    oled.fill(0)
    oled.text("MAIN----------", 1, 1, 1)
    x = len(items)
    for i in range(x):
        if i == menuIndex:
            selected = "8>"
        else:
            selected = "  "
            
        main = f"{selected} Menu {i+1}"
        #(i+x) -> x = yOffset
        oled.text(main, 1, (i+1)*13, 1)
        oled.show()

rotFifo = Fifo(30, typecode='i')
rot = Encoder(10, 11, rotFifo)
button = InterruptButton(12, events)
updateMenu()
   
while True:
    if menuActive:
        #Navigation
        if rotFifo.has_data():
            while rotFifo.has_data():
                menuIndex = (menuIndex + rotFifo.get()) % len(items)
            updateMenu()

        #On menu
        if events.has_data():
            event = events.get()
            if event == 0:
                showSelection(menuIndex)
    else:
        while rotFifo.has_data():
            rotFifo.get()
        #Wait for button press to re-enter
        if events.has_data():
            event = events.get()
            if event == 0:
                menuActive = True
                updateMenu()


