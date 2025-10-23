TARGET = protosuit-remote-control
OBJS = src/main.o src/wifi.o src/wifi_menu.o src/mqtt.o src/input.o src/ui.o src/config_loader.o

INCDIR =
CFLAGS = -O2 -G0 -Wall -Iinclude -I.
CXXFLAGS = $(CFLAGS) -fno-exceptions -fno-rtti
ASFLAGS = $(CFLAGS)

LIBDIR =
LDFLAGS =
LIBS = -lpsputility -lpspgu -lpsppower -lpspnet_inet -lpspnet_apctl -lpspnet

EXTRA_TARGETS = EBOOT.PBP
PSP_EBOOT_TITLE = Protosuit Remote Control
PSP_EBOOT_ICON = NULL
PSP_EBOOT_PIC1 = NULL

PSPSDK=$(shell psp-config --pspsdk-path)
include $(PSPSDK)/lib/build.mak
