from piotimer import Piotimer
import filefifo
from machine import Pin, ADC, I2C
from ssd1306 import SSD1306_I2C
from fifo import Fifo
import time
import micropython

micropython.alloc_emergency_exception_buf(200)

# === OLED Setup ===
i2c = I2C(1, scl=Pin(15), sda=Pin(14))
oled = SSD1306_I2C(128, 64, i2c)

# === Pulse Sensor Setup ===
pulse = ADC(27)
led = Pin(25, Pin.OUT)

samplegraph = []
samplesum = 0
sampleavg = 0
averageG = 0
yG = 0
minGV = 0
maxGV = 0
x = 1
average = 0
minV = 65535
maxV = 0
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
lastX = 0
GRAPH_HEIGHT = 64
GRAPH_WIDTH = 128
y_values = [GRAPH_HEIGHT // 2] * GRAPH_WIDTH

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
   
samples = isr_fifo(750, 27)
tmr = Piotimer(period=10, freq=250, mode=Piotimer.PERIODIC, callback=samples.handler)

def scale(value, min_val=25000, max_val=65000, height=64):
    """
    Scales the raw ADC value to fit within the OLED display height.
    """
    # Clamp the value to the specified range
    value = max(min_val, min(max_val, value))
    # Scale the value to the display height
    scaled = int((value - min_val) * (height - 1) / (max_val - min_val))
    return height - 1 - scaled  # Invert to match OLED top-to-bottom orientation

def scaler(value, minVal, maxVal):
    if maxVal == minVal:
        return 32
    scaled = int((value - minVal) * 63 / (maxVal - minVal))
    return min(max(scaled, 0), 63)

def show_BPM(bpm):
    
    # Display the "BPM" label at the top-left corner
    oled.text("BPM:", bpm, 0, 0)

    # Update the display
    #oled.show()

def signal_graph(val, x):
    
    samplegraph.append(val)

    if len(samplegraph) == 5:
        samplesum = sum(samplegraph)
        sampleavg = samplesum / 5
        samplegraph.clear()  # <- Make sure to call clear()

        # Convert the average to an integer for pixel drawing
        y_axis = int(sampleavg)

        # Shift the graph data left to simulate scrolling
        for i in range(GRAPH_WIDTH - 1):
            y_values[i] = y_values[i + 1]
        y_values[-1] = y_axis  # <- Use sampleavg as the new y value

        # Clear the OLED display
        oled.fill(0)

        # Draw the updated waveform
        for x in range(1, GRAPH_WIDTH):
            oled.line(x - 1, y_values[x - 1], x, y_values[x], 1)

        oled.show()  # Don't forget to update the screen

while y < 500:
    if not samples.empty():
        # print(y)
        number = samples.get()
        if number < minV:
            minV = number
        if number > maxV:
            maxV = number
        y += 1

    if y == 499:
        # print(y)
        average = (minV + maxV) / 2
        #print(f"Min {minV}")
        # print(f"Max {maxV}")
        # print(f"Average {average}")
        minV = 65535
        maxV = 0
        y += 1

while x < 7500:        
    if not samples.empty():
        print(x)
        if x % 500 == 0:
            number = samples.get()
            if number < minV:
                minV = number
            if number > maxV:
                maxV = number
            # print(f"min {min}")
            # print(f"max {max}")
            average = (minV + maxV) / 2 + (maxV - minV) * 0.15
            # print(f"average {average}")
            minV = 65535
            maxV = 0
            #samples.clear()
        else:
            number = samples.get()
            if number < minV:
                minV = number
            if number > maxV:
                maxV = number
                
        signal_graph(number, x)
        
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
                        show_BPM(bpm)

        last_peak = peak
        last = number
        lastX = x
        x += 1
        if x%30 == 0:
            oled.show()  

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

