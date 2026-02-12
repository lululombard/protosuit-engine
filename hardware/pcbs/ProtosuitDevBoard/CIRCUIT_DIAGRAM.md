# Protogen Controller Circuit Diagram

This diagram shows the complete power distribution and communication architecture of the Protogen controller system.

## System Architecture

```mermaid
flowchart LR
    %% Power Input
    USBCPD["USB-C PD<br/>20V"]
    XT60["XT60<br/>Connector"]
    TB_IN["2-Pin Terminal<br/>20V Input"]

    %% Buck-Boost Converters
    BB1["Buck-Boost #1<br/>5V 5A"]
    BB2["Buck-Boost #2<br/>5V 8A"]

    %% Output Terminal Blocks
    TB_OUT1["2-Pin Terminal<br/>5V Output"]

    %% Main Components
    RPI["Raspberry Pi"]
    LCD1["LCD Display 1"]
    LCD2["LCD Display 2"]
    PCB["Main PCB<br/>5V 8A Rail"]
    TEENSY["Teensy 4.0"]
    ESP32["ESP32"]

    %% Teensy Peripherals
    LED_MAT_FL["LED Matrix Front Left"]
    LED_MAT_FR["LED Matrix Front Right"]
    LED_MAT_BL["LED Matrix Back Left"]
    LED_MAT_BR["LED Matrix Back Right"]
    T_I2C1["I2C Boop Sensor"]
    T_I2C2["I2C Gyroscope"]
    MIC["Microphone"]

    %% Raspberry Pi USB Peripherals
    USB_Wi-Fi["USB Wi-Fi/Bluetooth Adapter"]
    USB_MIC["USB Ambient Microphone"]
    USB_SPEAKER["USB Speaker"]

    %% ESP32 Peripherals
    LED_STRIP_UPPER_ARCH["Upper Arch LED Strip"]
    LED_STRIP_LEFT_FIN["Left Fin LED Strip"]
    LED_STRIP_RIGHT_FIN["Right Fin LED Strip"]
    LED_STRIP_LEFT_EAR["Left Ear LED Strip"]
    LED_STRIP_RIGHT_EAR["Right Ear LED Strip"]
    E_I2C1["I2C Display"]
    E_I2C2["I2C Future Expansion"]

    %% Power Flow
    USBCPD -->|20V| XT60
    XT60 -->|20V| TB_IN
    TB_IN -->|20V| BB1
    TB_IN -->|20V| BB2

    BB1 -->|5V 5A| TB_OUT1
    TB_OUT1 -->|Power| RPI
    TB_OUT1 -->|Power| LCD1
    TB_OUT1 -->|Power| LCD2

    BB2 -->|5V 8A| PCB
    PCB -->|Power| TEENSY
    PCB -->|Power| ESP32

    %% Communication Links
    RPI -.->|HDMI| LCD1
    RPI -.->|HDMI| LCD2
    RPI -.->|USB| ESP32
    RPI -.->|USB| USB_Wi-Fi
    RPI -.->|USB| USB_MIC
    RPI -.->|USB| USB_SPEAKER
    TEENSY -.->|UART| ESP32

    %% Teensy Connections
    TEENSY -->|"3-Pin Terminal (Data IO5+5V)"| LED_MAT_FL
    TEENSY -->|"3-Pin Terminal (Data IO6+5V)"| LED_MAT_FR
    TEENSY -->|"3-Pin Terminal (Data IO20+5V)"| LED_MAT_BL
    TEENSY -->|"3-Pin Terminal (Data IO21+5V)"| LED_MAT_BR
    TEENSY -->|JST 4-Pin I2C| T_I2C1
    TEENSY -->|JST 4-Pin I2C| T_I2C2
    TEENSY -->|JST 3-Pin| MIC

    %% ESP32 Connections
    ESP32 -->|"3-Pin Terminal (Data+5V)"| LED_STRIP_UPPER_ARCH
    ESP32 -->|"3-Pin Terminal (Data+5V)"| LED_STRIP_LEFT_FIN
    ESP32 -->|"3-Pin Terminal (Data+5V)"| LED_STRIP_RIGHT_FIN
    ESP32 -->|"3-Pin Terminal (Data+5V)"| LED_STRIP_LEFT_EAR
    ESP32 -->|"3-Pin Terminal (Data+5V)"| LED_STRIP_RIGHT_EAR
    ESP32 -->|JST 4-Pin I2C| E_I2C1
    ESP32 -->|JST 4-Pin I2C| E_I2C2
```

## Power Distribution Summary

### Input Power
- **Source**: USB-C Power Delivery (PD)
- **Voltage**: 20V
- **Connector Chain**: USB-C → XT60 → 2-Pin Terminal Block

### Buck-Boost Converters

#### Converter #1 (5V 5A Rail)
- **Input**: 20V from main terminal block
- **Output**: 5V @ 5A (25W max)
- **Powers**:
  - Raspberry Pi
  - 2× LCD Displays
- **Connection**: Via 2-pin terminal block

#### Converter #2 (5V 8A Rail)
- **Input**: 20V from main terminal block
- **Output**: 5V @ 8A (40W max)
- **Powers**:
  - Main PCB
  - Teensy 4.0
  - ESP32
  - All LED matrices and strips (through microcontrollers)

## Communication Architecture

### Inter-Device Communication
| From | To | Protocol | Purpose |
|------|-----|----------|---------|
| Raspberry Pi | LCD Display 1 | HDMI | Video output |
| Raspberry Pi | LCD Display 2 | HDMI | Video output |
| Raspberry Pi | ESP32 | USB | Data communication/control |
| Raspberry Pi | Wi-Fi/Bluetooth Adapter | USB | Wireless connectivity |
| Raspberry Pi | Ambient Microphone | USB | Audio input |
| Raspberry Pi | Speaker | USB | Audio output |
| Teensy 4.0 | ESP32 | UART | Inter-microcontroller communication |

### Raspberry Pi USB Peripherals
| Quantity | Connector Type | Device | Purpose |
|----------|----------------|---------|---------|
| 1× | USB | ESP32 | Microcontroller communication/control |
| 1× | USB | Wi-Fi/Bluetooth Adapter | Wireless connectivity |
| 1× | USB | Ambient Microphone | Environmental audio input |
| 1× | USB | Speaker | Audio output |

### Teensy 4.0 Peripherals
| Quantity | Connector Type | Device | Purpose |
|----------|----------------|---------|---------|
| 4× | 3-Pin Terminal Block | LED Matrices | Display control (Data + 5V + GND) |
| 2× | JST 4-Pin | I2C Devices | Sensor/peripheral bus |
| 1× | JST 3-Pin | Microphone | Audio input |

### ESP32 Peripherals
| Quantity | Connector Type | Device | Purpose |
|----------|----------------|---------|---------|
| 5× | 3-Pin Terminal Block | LED Strips | Lighting control (Data + 5V + GND) |
| 2× | JST 4-Pin | I2C Devices | Display interface and future expansion |

## Connector Specifications

### Terminal Blocks
- **2-Pin**: Power distribution (VCC + GND)
- **3-Pin**: LED control (Data + VCC + GND) or single-wire protocols

### JST Connectors
- **JST 4-Pin**: I2C bus (SDA, SCL, VCC, GND)
- **JST 3-Pin**: UART/Serial or single signal (TX/RX/Signal + VCC + GND)

## Notes

- All LED matrices and LED strips are powered through the 5V 8A rail via their respective microcontrollers
- Total system power budget: ~65W (25W + 40W from both converters)
- Communication links (HDMI, USB, UART) are shown with dotted lines in the diagram
- Power connections are shown with solid lines
- The main PCB houses both the Teensy 4.0 and ESP32, sharing the 5V 8A power rail
- Raspberry Pi has 4 USB devices connected (ESP32, Wi-Fi/Bluetooth adapter, ambient microphone, speaker)