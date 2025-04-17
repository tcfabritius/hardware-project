from piotimer import Piotimer
import filefifo
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
hr = []
mean_hr = 0
ppi = []
mean_ppi = 0
rmssd = 0
sdnn = 0
while y < 500:
    if not samples.empty():
        # print(y)
        number = samples.get()
        if number < min:
            min = number
        if number > max:
            max = number
        y += 1

    if y == 499:
        # print(y)
        average = (min + max) / 2
        # print(f"Min {min}")
        # print(f"Max {max}")
        # print(f"Average {average}")
        min = 65535
        max = 0

while x < 7500:
    if not samples.empty():
        if x % 500 == 0:
            number = samples.get()
            if number < min:
                min = number
            if number > max:
                max = number
            # print(f"min {min}")
            # print(f"max {max}")
            average = (min + max) / 2 + (max - min) * 0.15
            # print(f"average {average}")
            min = 65535
            max = 0
        else:
            number = samples.get()
            if number < min:
                min = number
            if number > max:
                max = number

        if number - last < 0 and first_occurrence and number > average and number != 0:
            # print(f"Number {number}")
            # print(f"Last {last}")
            # print(f"Average {average}")
            peak = x
            first_occurrence = False

        if number < average:
            first_occurrence = True

        if last_peak != 0 or peak != 0:
            if peak - last_peak > 60:
                # print(f"Peak {peak}")
                # print(f"Last peak {last_peak}")
                interval = (peak - last_peak)

                if interval != 0:
                    interval = interval / 250
                    ppi.append(interval * 1000)
                    bpm = int(60 / interval)
                    if 30 <= bpm <= 240:
                        hr.append(bpm)
                        print(f"BPM {bpm}")

        last_peak = peak
        last = number
        x += 1

total = 0
for pi in ppi:
    total = total + pi

mean_ppi = total / len(ppi)
print(f"Mean PPI: {mean_ppi}")

total = 0
for h in hr:
    total = total + h
mean_hr = total / len(hr)
print(f"Mean HR: {mean_hr}")
for pi in ppi:
    sdnn = sdnn + (pi - mean_ppi) ** 2
sdnn = (1 / (len(ppi) - 1)) * sdnn
sdnn = sdnn ** 0.5
print(f"SDNN: {sdnn}")
for r in range(len(ppi) - 1):
    rmssd = rmssd + (ppi[r + 1] - ppi[r]) ** 2
rmssd = (1 / (len(ppi) - 1)) * rmssd
rmssd = rmssd ** 0.5
print(f"RMSSD: {rmssd}")

