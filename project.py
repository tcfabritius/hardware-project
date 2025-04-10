from piotimer import Piotimer
from machine import Pin, ADC
from fifo import Fifo
import time
import micropython

micropython.alloc_emergency_exception_buf(200)


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


samples = isr_fifo(100, 27)  # create the improved fifo: size = 50, adc pin = pin_nr
tmr = Piotimer(period=20, mode=Piotimer.PERIODIC, callback=samples.handler)
x = 0
average = 0
min = 65535
max = 0
first_occurrence = True
last = 0
last_peak = 0
peak = 0
number = 0
# to read:
while True:
    if not samples.empty():
        if x % 500 == 0:
            average = (min + max) / 2
            min = 65535
            max = 0
        else:
            number = samples.get()
            if number < min:
                min = number
            if number > max:
                max = number

        if number - last < 0 and first_occurrence and number > average and peak != 0 and number != 0:
            peak = x
            first_occurrence = False

        if number - last > 0:
            first_occurrence = True

        if last_peak != 0 or peak != 0:
            interval = last_peak - peak
            interval = interval / 250
            bpm = int(60 / interval)
            print(bpm)

        time.sleep_ms(20)
        last_peak = peak
        last = number
        x += 1
