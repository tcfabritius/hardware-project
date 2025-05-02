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
from umqtt.simple import MQTTClient
import json

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
mItems = [
    "Measure HRV",
    "Kubios Cloud",
    "History"
]
mIndex = 0
events = Fifo(30)
i2c = I2C(1, scl=Pin(15), sda=Pin(14), freq=400000)
oled = SSD1306_I2C(128, 64, i2c)
mainMenuActive = True

# === History ===
historyIndex = 0
menuState = "main"
history_menu = ["Log 1", "Log 2", "Log 3", "Exit"]

# === Pulse Sensor Setup ===
pulse = ADC(27)
led = Pin(25, Pin.OUT)

# === HRV-variables ===
bpm = 0
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
mqtt_data = b''
id = 1
y_values = [GRAPH_HEIGHT // 2] * GRAPH_WIDTH
client = MQTTClient("timf", BROKER_IP, port=21883)
data_bytes = b''

def sub_cb(topic, msg):
    global mqtt_data
    mqtt_data = msg.decode("utf-8")  # Decode only the message part, not the tuple
    
client.set_callback(sub_cb)

def kubios_request(id, data):
    client.connect()
    request = {
            "id":id,
            "type": "RRI",
            "data": data,
            "analysis": { "type": "readiness" }
        } 
    client.publish("kubios-request", json.dumps(request))
    client.disconnect()
    
def hr_data(id, mean_hr, mean_ppi, rmssd, sdnn):
    client.connect()
    current_time = time.localtime()
    request = {
        "id": id,
        "timestamp": current_time,
        "mean_hr": mean_hr,
        "mean_ppi": mean_ppi,
        "rmssd": rmssd,
        "sdnn": sdnn
        }
    client.publish("hr-data", json.dumps(request))
    client.disconnect()

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
    menuLength = len(mItems)

    for j in range(menuLength):
        if j == mIndex:
            draw_bitmap(oled, heart_bitmap, 1, (j+1)*13)
        else:
            oled.text(" ", 1, (j+1)*13, 1)

        main = f"{j+1}. {mItems[j]}"
        oled.text(main, 10, (j+1)*13, 1)

    oled.show()

def historyMenu():
    global historyIndex, mainMenuActive, menuState

    oled.fill(0)
    oled.text("HISTORY---------", 1, 1, 1)

    # Näytä valikkokohtia
    for i, item in enumerate(history_menu):
        prefix = "> " if i == historyIndex else "  "
        oled.text(prefix + item, 1, 15 + i * 10)

    oled.show()

    while menuState == "history":
        # Pyörittimen käsittely
        if rotFifo.has_data():
            while rotFifo.has_data():
                historyIndex = (historyIndex + rotFifo.get()) % len(history_menu)
            oled.fill(0)
            oled.text("HISTORY---------", 1, 1, 1)
            for i, item in enumerate(history_menu):
                prefix = "> " if i == historyIndex else "  "
                oled.text(prefix + item, 1, 15 + i * 10)
            oled.show()

        # Napin painallus
        if events.has_data():
            event = events.get()
            if event == 0:
                if historyIndex == len(history_menu) - 1:  # Exit
                    menuState = "main"
                    mainMenuActive = True
                    updateMenu()
                    return
                else:
                    showSelection(historyIndex, 3)  # Historialogin tarkastelu

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
        oled.text("BPM:"+str(bpm), 10, 10)
        
    
# === HRV-analysis ===
def HRVAnalysis():
    global x, y, last, last_peak, peak, first_occurrence
    global hr, mean_hr, ppi, mean_ppi, rmssd, sdnn
    global minV, maxV
    #print("Time to do some measurements woohoo")
    # === Sample fifo instantiation ===
    samples = isr_fifo(750, 27)
    tmr = Piotimer(period=10, freq=250, mode=Piotimer.PERIODIC, callback=samples.handler)
    #Timer
    while y < 500 and events.empty():
        if events.has_data():
            event = events.get()
            if event == 0:
                mainMenuActive = True
                updateMenu()
                tmr.deinit()
        
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

    while x < 7500 and events.empty():
        if events.has_data():
            event = events.get()
            if event == 0:
                mainMenuActive = True
                updateMenu()
            
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
                        global bpm
                        if interval != 0:
                            bpm = int(60 / interval)
                            if 30 <= bpm <= 240:
                                hr.append(bpm)
                            
            last_peak = peak
            last = number
            lastX = x
            x += 1
            if x % 30 == 0:
                oled.show()  

    tmr.deinit()
    if len(ppi) > 0:
        global id
        #Kubios request here, maybe should be happening in kubios-menu?
        if mIndex == 1:
            kubios_request(id, ppi)
            
            client.connect()
            client.subscribe(b"kubios-response")
            client.wait_msg()
            data_dict = json.loads(mqtt_data)  # Convert string to dictionary
            kubiosCloud(data_dict)
            
        if mIndex == 0:
            id += 1
            total = 0
            for pi in ppi:
                total = total + pi
            
            mean_ppi = total / len(ppi)

            total = 0
            for h in hr:
                total = total + h
            
            if len(hr) > 0:
                mean_hr = total / len(hr)
            
            for pi in ppi:
                sdnn = sdnn + (pi - mean_ppi) ** 2
            
            sdnn = (1 / (len(ppi) - 1)) * sdnn
            sdnn = sdnn ** 0.5
            
            for r in range(len(ppi) - 1):
                rmssd = rmssd + (ppi[r + 1] - ppi[r]) ** 2
            rmssd = (1 / (len(ppi) - 1)) * rmssd
            rmssd = rmssd ** 0.5
            
            if x == 7499:
                print(f"Mean PPI: {mean_ppi}")
                print(f"Mean HR: {mean_hr}")
                print(f"SDNN: {sdnn}")
                print(f"RMSSD: {rmssd}")
            else:
                oled.fill(0)
                oled.text("Interrupted.", 1, 20, 1)
                oled.text("Wait.", 1, 30, 1)
                oled.show()
                x = 1
                y = 0
                
            #History operation here
            hr_data(id, mean_hr, mean_ppi, rmssd, sdnn)
            global id
            x = 1
            y = 0
            showResults()
        
def showSelection(index, selectionType):
    if selectionType == 0:
        # Static if-structure
        if index == 0:
            global mainMenuActive
            mainMenuActive = False
            oled.fill(0)
            oled.text("Measure HR----------",1,1,1)
            #oled.text("Rot 1: Exit.", 1, 20, 1)
            oled.show()
            while events.empty():
                oled.text("Hold the sensor.", 1,30,1)
                oled.text("Rot 1: Start",1,40,1)
                oled.show()
                time.sleep(0.01)
            events.get()
            HRVAnalysis()
            #time.sleep(1)

        elif index == 1:
            global mainMenuActive
            mainMenuActive = False
            oled.fill(0)
            oled.text("Kubios Cloud----------", 1, 1, 1)
            oled.text("Rot 1: Exit.", 1, 20, 1)
            oled.show()
            while events.empty():
                oled.text("Hold the sensor.", 1,30,1)
                oled.text("Rot 1: Start",1,40,1)
                oled.show()
                time.sleep(0.01)
            events.get()
            HRVAnalysis()
            #time.sleep(1)
        
        elif index == 2:
            global mainMenuActive, menuState
            mainMenuActive = False
            menuState = "history"
            historyMenu()
            
    elif selectionType == 3:
        #History
        if index == 0:
            global mainMenuActive
            mainMenuActive = False
            oled.fill(0)
            #For some reason only rotating the rotary takes the user back, rather than press.
            while events.empty():
                oled.text("Log 1----------",1,1,1)
                oled.text("Rot 1: Exit.", 1, 20, 1)
                oled.show()
            events.get()
            #time.sleep(1)

        elif index == 1:
            global mainMenuActive
            mainMenuActive = False
            oled.fill(0)
            #For some reason only rotating the rotary takes the user back, rather than press.
            while events.empty():
                oled.text("Log 2----------", 1, 1, 1)
                oled.text("Rot 1: Exit.", 1, 20, 1)
                oled.show()
            events.get()
            #time.sleep(1)
        
        elif index == 2:
            global mainMenuActive
            mainMenuActive = False
            oled.fill(0)
            #For some reason only rotating the rotary takes the user back, rather than press.
            while events.empty():
                oled.text("Log 3----------", 1, 1, 1)
                oled.text("Rot 1: Exit.", 1, 20, 1)
                oled.show()
            events.get()
            #time.sleep(1)

def showResults():
        global mainMenuActive
        mainMenuActive = False
        oled.fill(0)
        oled.text("Mean HR: " + str(int(mean_hr)), 1, 1, 1)
        oled.text("Mean PPI: " + str(int(mean_ppi)), 1, 10, 1)
        oled.text("RMSSD: " + str(int(rmssd)), 1, 20, 1)
        oled.text("SDNN: " + str(int(sdnn)), 1, 30, 1)
        while events.empty():
            oled.text("Rot 1: continue:", 1, 50, 1)
            oled.show()
            time.sleep(0.0001)
        #events.get()
            
def kubiosCloud(json):
    analysis = json['data']['analysis']

    kubios_mean_hr = int(analysis.get("mean_hr_bpm", 0))
    kubios_mean_rr_ms = int(analysis.get("mean_rr_ms", 0))
    kubios_rmssd = int(analysis.get("rmssd_ms", 0))
    kubios_sdnn = int(analysis.get("sdnn_ms", 0))
    kubios_pns_index = int(analysis.get("pns_index", 0))
    kubios_sns_index = int(analysis.get("sns_index", 0))

    oled.fill(0)
    oled.text("Mean HR: " + str(kubios_mean_hr), 0, 0)
    oled.text("Mean PPI: " + str(kubios_mean_rr_ms), 0, 10)
    oled.text("SDNN: " + str(kubios_sdnn), 0, 20)    
    oled.text("RMSSD: " + str(kubios_rmssd), 0, 30)
    oled.text("PNS index: " + str(kubios_pns_index), 0, 40)    
    oled.text("SNS index: " + str(kubios_sns_index), 0, 50)
    oled.show()    

# === "Main loop" ===
while True:
    if mainMenuActive:
        #Navigation
        if rotFifo.has_data():
            while rotFifo.has_data():
                mIndex = (mIndex + rotFifo.get()) % len(mItems)
                #This variable can be used to detect which option we are hovering in
                #print(mIndex)
            updateMenu()
            if mainMenuActive == False:
                updateMenu()

        #On menu
        if events.has_data():
            event = events.get()
            if event == 0:
                showSelection(mIndex, 0)
            elif event == 2:
                showSelection(hIndex, 3)
    else:
        while rotFifo.has_data():
            rotFifo.get()
            
        #Wait for button press to re-enter
        if events.has_data():
            event = events.get()
            if event == 0:
                mainMenuActive = True
                updateMenu()


