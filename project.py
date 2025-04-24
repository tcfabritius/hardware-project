from ssd1306 import SSD1306_I2C
from led import Led
from piotimer import Piotimer
import filefifo
from machine import Pin, ADC, I2C
from fifo import Fifo
import time
import micropython
import mip
import network
from time import sleep


micropython.alloc_emergency_exception_buf(200)


# Replace these values with your own
SSID = "KMD657_Group_4"
PASSWORD = "TattiVanukas365#"
BROKER_IP = "192.168.4.253"

# Function to connect to WLAN
def connect_wlan():
    # Connecting to the group WLAN
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.connect(SSID, PASSWORD)

    # Attempt to connect once per second
    while wlan.isconnected() == False:
        print("Connecting... ")
        sleep(1)

    # Print the IP address of the Pico
    print("Connection successful. Pico IP:", wlan.ifconfig()[0])

# Main program
connect_wlan()


# === Menu and OLED ===
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

# === Pulse Sensor Setup ===
pulse = ADC(27)
led = Pin(25, Pin.OUT)

# === HRV-variables ===
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

# === Menu functionality ===
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
  
# === HRV-Functionality ===
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
    oled.show()

def signal_graph(val, x):
    samplegraph.append(val)
    if len(samplegraph) == 5:
        samplesum = sum(samplegraph)
        sampleavg = samplesum / 5
        samplegraph.clear()  # <- Make sure to call clear()
        # Convert the average to an integer for pixel drawing
        y_axis = scale(sampleavg)
        # Shift the graph data left to simulate scrolling
        for i in range(GRAPH_WIDTH - 1):
            y_values[i] = y_values[i + 1]
        y_values[-1] = y_axis  # <- Use sampleavg as the new y value
        # Clear the OLED display
        oled.fill(0)
        # Draw the updated waveform
        for x in range(1, GRAPH_WIDTH):
            oled.line(x - 1, y_values[x - 1], x, y_values[x], 1)
        #oled.show()  # Don't forget to update the screen

# === HRV-analysis ===
def HRVAnalysis():
    global x, y, last, last_peak, peak, first_occurrence
    global hr, mean_hr, ppi, mean_ppi, rmssd, sdnn
    global minV, maxV
    print("Time to do some measurements woohoo")
    # === Sample fifo instantiation ===
    samples = isr_fifo(750, 27)
    tmr = Piotimer(period=10, freq=250, mode=Piotimer.PERIODIC, callback=samples.handler)
    #Timer
    while y < 500:
        if not samples.empty():
            number = samples.get()
            if number < minV:
                minV = number
            if number > maxV:
                maxV = number
            y += 1
        if y == 499:
            average = (minV + maxV) / 2
            minV = 65535
            maxV = 0
            y += 1

    while x < 7500:        
        if not samples.empty():
            if x % 500 == 0:
                number = samples.get()
                if number < minV:
                    minV = number
                if number > maxV:
                    maxV = number
                average = (minV + maxV) / 2 + (maxV - minV) * 0.15
                minV = 65535
                maxV = 0
            else:
                number = samples.get()
                if number < minV:
                    minV = number
                if number > maxV:
                    maxV = number
            signal_graph(number, x)
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
                        ppi.append(interval * 1000)
                        bpm = int(60 / interval)
                        if 30 <= bpm <= 240:
                            hr.append(bpm)
                            show_BPM(bpm)
            last_peak = peak
            last = number
            lastX = x
            x += 1
            if x % 30 == 0:
                oled.show()  

    tmr.deinit()
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
    #print to oled
    calcValues = f"MPPI:{mean_ppi}\nMHR:{mean_hr}\nSDNN:{sdnn}\nRMSSD:{rmssd}\nR1 - Exit"
    oled.text(calcValues,1,5,1)

def showSelection(index):
# Static if-structure
    if index == 0:
        global mainMenuActive
        mainMenuActive = False
        oled.fill(0)
        oled.text("Measure HR----------", 1, 1, 1)
        oled.text("Rot 1: Exit.", 1, 20, 1)
        oled.show()
        HRVAnalysis()
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

# === "Main loop" ===
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
