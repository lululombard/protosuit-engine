# Protosuit Engine Hardware Documentation

This document covers all hardware aspects of the Protosuit Engine project, including the custom PCB, USB connections, GPIO pinout, displays, and Bluetooth adapter management.

## PCB Design (pcbs/ProtosuitDevBoard/)

The main PCB is designed in **KiCad 8.0** and serves as the central power distribution and interconnect board for the suit.

### Power Input

- **9-25V input** via XT60 connector
- Powered by a USB-C PD 20V to XT60 cable from a power bank, minimizing power loss between the battery and PCB

### Power Distribution

| Converter | Rating | Load |
|-----------|--------|------|
| 5V 5A low-ESR buck-boost | 25W | Shared between RPi and 2x LCD displays |
| 5V 8A buck-boost | 40W | Main PCB powering Teensy 4.0, ESP32, WS35 matrices, and LED strips |

### LED Connectors

All LED connectors are screw terminals with ferrule crimps. Power input and 5V output connectors also use ferrule crimps.

- **4x [WS35 LED matrix](https://coelacant1.gumroad.com/l/ws35) connectors** (3-pin screw terminals, Coela Can't! design)
- **5x LED strip connectors** (3-pin screw terminals):
  - 2x fins
  - 2x ears
  - 1x upper arch

### WS35 Panel Modification

Each WS35 panel has two halves, each with its own 5V, GND, and signal pins. By default, the DOUT of the last LED on the first half is connected to DIN of the first LED on the second half, daisy-chaining both halves.

**You must saw/cut the trace between the two halves.** Since there is no level shifter on the PCB, the Teensy's 3.3V signal cannot override the 5V signal coming out of DOUT on the first half. Cutting the connection allows each half to be driven independently from its own DIN pin.

### Other Connectors (JST)

- I2C header
- MAX9814 microphone input (for Teensy audio-reactive features)
- DHT22 temperature/humidity sensor connector (for ESP32)

### Custom Footprint Libraries

Custom KiCad footprint library in `Aliexpress.pretty/`:

| Footprint | Description |
|-----------|-------------|
| ESP32_MIN132_V_1_0_0 | ESP32 module |
| DC_DC_5V_5A_TPS54X60 | 5V 5A buck converter |
| DC_DC_5V_8A_CRDC2580 | 5V 8A buck converter |
| LEVEL_SHIFTER_TXS0108E | 8-channel level shifter (not used in PCB 1.1, wrong type of shifter, bypassed in 1.0) |
| GYRO_MPU6050 | 6-axis IMU (gyroscope + accelerometer), on-board but currently unused |
| TEENSY_4_0 | Teensy 4.0 module (modified from original) |

### Board Status

The current board (v1.1) is a **validation prototype** using off-the-shelf modules (buck converters, ESP32 dev board) with no SMD components, making it quite bulky. The goal is to eventually move to SMD power circuitry, an ESP32 module directly on-board, a Raspberry Pi Compute Module, and custom display driver circuitry instead of HDMI-MIPI boards.

### Manufacturing and Project Files

- Gerber manufacturing files in `gerber_v1_0/`
- `.kicad_sch` -- schematic
- `.kicad_pcb` -- PCB layout
- `.kicad_pro` -- project file

## USB Connections

### Pi to Teensy 4.0 -- USB without 5V power

- **VUSB=VIN jumper configuration**, no cut trace on Teensy
- Teensy is powered from the main PCB 5V 8A rail, NOT from Pi USB
- Only appears in `lsusb` while in bootloader/upload mode
- Used exclusively for firmware uploads

### Pi to ESP32 -- USB with 5V power

- CH341 USB-to-serial chip needs USB bus power
- CH341 is NOT powered by the ESP32 main 5V rail
- Always visible in `lsusb` as `/dev/ttyUSB0`
- Used for bidirectional serial communication (921,600 baud)

### USB Microphone Dongle

- Used for sound-reactive shader audio capture
- Captured by renderer via the sounddevice library (FFT)

### USB Wi-Fi 6 + Bluetooth Dongle

- RTL8851BU chipset, handles both Wi-Fi and Bluetooth
- Wi-Fi: used for client mode (internet access); built-in RPi Wi-Fi is used for AP mode
- Bluetooth: used for all BT devices (gamepads, audio); see [Bluetooth Adapter Management](#bluetooth-adapter-management)
- The built-in RPi radio has issues running AP + BT simultaneously, this dongle avoids that entirely

## ESP32 GPIO Pinout

| GPIO | Function | Direction | Notes |
|------|----------|-----------|-------|
| 27 | DHT22 Temperature/Humidity | Input | +/-0.5C, +/-2% RH accuracy |
| 33 | PWM Fan Control | Output | 21.6 kHz, 8-bit (0-255), inverted duty cycle |
| 35 | Fan Tachometer | Input | FALLING edge interrupts, 2 pulses/revolution |
| 21 | I2C SDA (OLED Display) | Bidirectional | SSD1306 128x64 monochrome |
| 22 | I2C SCL (OLED Display) | Bidirectional | |
| 5 | LED Strip (Upper Arch) | Output | SK6812 |
| 18 | LED Strip (Left Ear) | Output | WS2812B |
| 19 | LED Strip (Right Fin) | Output | WS2812B, 60 LEDs |
| 23 | LED Strip (Left Fin) | Output | WS2812B, 60 LEDs |
| 26 | LED Strip (Right Ear) | Output | WS2812B |
| 16 | UART RX (Teensy) | Input | 921,600 baud |
| 17 | UART TX (Teensy) | Output | 921,600 baud |

## Display Configuration

- 2x 4-inch 720x720 round displays (search "wisecoco 4 inch 720 round" on AliExpress) with HDMI-MIPI driver boards, mounted on fursuit fins
- Left display: rotated 90 degrees clockwise
- Right display: rotated 90 degrees counter-clockwise
- Extended desktop spanning both displays
- Managed by X11 via xrandr (configured by Ansible)

## Bluetooth Adapter Management

The RPi's built-in radio shares Wi-Fi and Bluetooth on the same chip. Running AP mode + Bluetooth simultaneously causes issues for both: degraded AP performance and unreliable BT connections. The [RTL8851BU USB dongle](#usb-wi-fi-6--bluetooth-dongle) handles both Wi-Fi client and Bluetooth, and can manage Wi-Fi + 3 BT devices (2 controllers + 1 speaker) simultaneously without issues.

Ideally, use separate adapters for gamepads and audio to prevent bandwidth conflicts (a shared adapter can cause audio stuttering and controller input lag), but a single USB dongle works well for most setups.

Configure in `config.yaml` under `bluetoothbridge.adapters`:

| Adapter Role | Default | Description |
|--------------|---------|-------------|
| gamepads | hci1 (USB dongle) | Adapter for controllers |
| audio | hci1 (USB dongle) | Adapter for speakers/headphones |

### Useful Commands

```bash
# List available adapters
bluetoothctl list

# Show adapter details
hciconfig -a

# Enable USB adapter
sudo rfkill unblock bluetooth && sudo hciconfig hci1 up
```

## OLED Display (on ESP32)

- SSD1306 128x64 monochrome OLED via I2C
- Updated every loop iteration (~1 second)
- Library: U8g2 (page buffer mode)

### Information Displayed

- Pi connection status
- Controller count
- Current shader
- Fan percentage
- Fan mode (Auto/Manual)
- RPM
- Temperature
- Humidity
