from ssd1306 import SSD1306_I2C
from led import Led
from piotimer import Piotimer
import filefifo
from machine import Pin, ADC, I2C
from fifo import Fifo
import time
import micropython
micropython.alloc_emergency_exception_buf(200)

#Menu
items = [1,2,3,4,5,6,7]
menuIndex = 0
events = Fifo(30)
i2c = I2C(1, scl=Pin(15), sda=Pin(14), freq=400000)
oled = SSD1306_I2C(128, 64, i2c)

class InterruptButton:
    def __init__(self, button_pin, fifo):
        self.button = Pin(button_pin, mode=Pin.IN, pull=Pin.PULL_UP)
        self.lastPress = time.ticks_ms()
        self.fifo = fifo
        self.button.irq(handler=self.handler, trigger=Pin.IRQ_FALLING, hard=True)
    
    def handler(self, pin):
        now = time.ticks_ms()
        if time.ticks_diff(now, self.lastPress) > 250: #50ms cooldown
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

def updateMenu():
    oled.fill(0)
    oled.text("MAIN----------", 1, 1, 1)
    for i in range(3):
        if i == menuIndex:
            selected = "8>"
        else:
            selected = "  "
            
        main = f"{selected} Menu {i+1}"
        #(i+x) -> x is yOffset
        oled.text(main, 1, (i+1)*13, 1)
        oled.show()

# subclass Fifo to add handler that can be registered as timer callback
class isr_fifo(Fifo):
    def __init__(self, size, adc_pin_nr):
        super().__init__(size)
        self.av = ADC(adc_pin_nr)  # sensor AD channel
        self.dbg = Pin(0, Pin.OUT)  # debug GPIO pin for measuring timing with oscilloscope

    def handler(self, tid):
        # handler to read and store ADC value
        # this is to be registered as an ISR. Floats are not available in ISR
        self.put(self.av.read_u16())
        self.dbg.toggle()

#BPM mmeasurement values
samples = isr_fifo(500, 27)  # create the improved fifo: size = 50, adc pin = pin_nr
# samples = filefifo.Filefifo(50, name = 'capture01_250Hz.txt')
tmr = Piotimer(period=10, freq=250, mode=Piotimer.PERIODIC, callback=samples.handler)
x = 1
average = 0
min = 65535
max = 0
first_occurrence = True
last = 0
last_peak = 0
peak = 0
number = 0
skip = 0
y = 0

rotFifo = Fifo(30, typecode='i')
rot = Encoder(10, 11, rotFifo)
button = InterruptButton(12, events)
updateMenu()

#Start cycle
while y < 500:
    if not samples.empty():
        number = samples.get()
        if number < min:
            min = number
        if number > max:
            max = number
        y += 1

    if y == 499:
        average = (min + max) / 2
        min = 65535
        max = 0

#Main loop
while True:
    if not samples.empty():
        if x % 500 == 0:
            number = samples.get()
            if number < min:
                min = number
            if number > max:
                max = number
            average = (min + max) / 2 + (max - min) * 0.15
            min = 65535
            max = 0
        else:
            number = samples.get()
            if number < min:
                min = number
            if number > max:
                max = number

        if number - last < 0 and first_occurrence and number > average and number != 0:
            peak = x
            first_occurrence = False

        if number < average:
            first_occurrence = True

        if last_peak != 0 or peak != 0:
            if peak - last_peak > 60:
                interval = (peak - last_peak)

                if interval != 0:
                    interval = interval / 250
                    bpm = int(60 / interval)
                    if 30 <= bpm <= 240:
                            oled.fill(0)
                            feed = f"BPM: {bpm}"
                            oled.text(feed, 1, 10, 1)
                            oled.show()
                            
    #Menu stuff
    if rotFifo.has_data():
        while rotFifo.has_data():
            menuIndex = (menuIndex + rotFifo.get()) % 3
        updateMenu()

    if events.has_data():
        event = events.get()
        if event == 0:           
            updateMenu()



