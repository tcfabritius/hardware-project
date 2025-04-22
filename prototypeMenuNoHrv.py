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
menuItems = [
    "Measure HRV",
    "HRV Analysis",
    "Kubios Cloud",
    "History"
]
menuIndex = 0
events = Fifo(30)
i2c = I2C(1, scl=Pin(15), sda=Pin(14), freq=400000)
oled = SSD1306_I2C(128, 64, i2c)
mainMenuActive = True

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
# Static if-structure
    if index == 0:
        global mainMenuActive
        mainMenuActive = False
        oled.fill(0)
        oled.text("Measure HR----------", 1, 1, 1)
        oled.text("Rot 1: Exit.", 1, 20, 1)
        oled.show()
        time.sleep(1)
        
    elif index == 1:
        global mainMenuActive
        mainMenuActive = False
        oled.fill(0)
        oled.text("HRV Analysis----------", 1, 1, 1)
        oled.text("Rot 1: Exit.", 1, 20, 1)
        oled.show()
        time.sleep(1)
    
    elif index == 2:
        global mainMenuActive
        mainMenuActive = False
        oled.fill(0)
        oled.text("Kubios Cloud----------", 1, 1, 1)
        oled.text("Rot 1: Exit.", 1, 20, 1)
        oled.show()
        time.sleep(1)
    
    elif index == 3:
        global mainMenuActive
        mainMenuActive = False
        oled.fill(0)
        oled.text("History----------", 1, 1, 1)
        oled.text("Rot 1: Exit.", 1, 20, 1)
        oled.show()
        time.sleep(1)

# Heart bitmap 8x8 in hex
heart_bitmap = [
    0x42,  # 01000010
    0xEE,  # 11101110
    0xFF,  # 11111111
    0xFF,  # 11111111
    0x7E,  # 01111110
    0x3C,  # 00111100
    0x18,  # 00011000
    0x00   # 00000000
]

def draw_bitmap(oled, bitmap, x, y):
    for i, row in enumerate(bitmap):
        for j in range(8):
            if row & (1 << j):
                oled.pixel(x + j, y + i, 1)
            else:
                oled.pixel(x + j, y + i, 0)

def updateMenu():
    oled.fill(0)
    oled.text("MAIN----------", 1, 1, 1)
    menuLength = len(menuItems)

    for j in range(menuLength):
        if j == menuIndex:
            draw_bitmap(oled, heart_bitmap, 1, (j+1)*13)
        else:
            oled.text(" ", 1, (j+1)*13, 1)

        main = f"{j+1}. {menuItems[j]}"
        oled.text(main, 10, (j+1)*13, 1)

    oled.show()

rotFifo = Fifo(30, typecode='i')
rot = Encoder(10, 11, rotFifo)
button = InterruptButton(12, events)
updateMenu()
   
while True:
    if mainMenuActive:
        #Navigation
        if rotFifo.has_data():
            while rotFifo.has_data():
                menuIndex = (menuIndex + rotFifo.get()) % len(menuItems)
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
                mainMenuActive = True
                updateMenu()