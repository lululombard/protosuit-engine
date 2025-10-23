TARGET = psp-mqtt-controller
OBJS = src/main.o src/wifi.o src/mqtt.o src/input.o src/ui.o

INCDIR = include
CFLAGS = -O2 -G0 -Wall -I$(INCDIR)
CXXFLAGS = $(CFLAGS) -fno-exceptions -fno-rtti
ASFLAGS = $(CFLAGS)

LIBDIR =
LDFLAGS =
LIBS = -lpspnet_inet -lpspnet_apctl -lpsputility -lpspgu -lpsppower

EXTRA_TARGETS = EBOOT.PBP
PSP_EBOOT_TITLE = PSP MQTT Controller
PSP_EBOOT_ICON = NULL
PSP_EBOOT_PIC1 = NULL

PSPSDK=$(shell psp-config --pspsdk-path)
include $(PSPSDK)/lib/build.mak

