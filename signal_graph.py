from machine import ADC, Pin, I2C
from ssd1306 import SSD1306_I2C
from time import sleep_ms
import micropython

# Allocate emergency exception buffer
micropython.alloc_emergency_exception_buf(100)

# === OLED Setup ===
i2c = I2C(1, scl=Pin(15), sda=Pin(14))
oled = SSD1306_I2C(128, 64, i2c)

# === Pulse Sensor Setup ===
pulse = ADC(27)
led = Pin(25, Pin.OUT)

# === Graph Setup ===
GRAPH_HEIGHT = 64
GRAPH_WIDTH = 128
y_values = [GRAPH_HEIGHT // 2] * GRAPH_WIDTH  # Initialize with a flat line


def signal_graph():

    # === Scaling Function ===
    def scale(value, min_val=25000, max_val=65000, height=64):
        """
        Scales the raw ADC value to fit within the OLED display height.
        """
        # Clamp the value to the specified range
        value = max(min_val, min(max_val, value))
        # Scale the value to the display height
        scaled = int((value - min_val) * (height - 1) / (max_val - min_val))
        return height - 1 - scaled  # Invert to match OLED top-to-bottom orientation

    # === Main Loop ===
    print("Starting real-time pulse graph...")
    while True:
        val = pulse.read_u16()
        y = scale(val)

        # Shift the graph to the left
        for i in range(GRAPH_WIDTH - 1):
            y_values[i] = y_values[i + 1]
        y_values[-1] = y

        # Clear the display
        oled.fill(0)

        # Draw the waveform
        for x in range(1, GRAPH_WIDTH):
            oled.line(x - 1, y_values[x - 1], x, y_values[x], 1)

        # Display the "BPM" label at the top-left corner
        oled.text("BPM", 0, 0)

        # Update the display
        oled.show()

        # Delay to control the frame rate (~50 FPS)
        sleep_ms(20)

signal_graph()