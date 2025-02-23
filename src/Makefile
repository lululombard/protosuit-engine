CC = gcc
CFLAGS = -Wall -Wextra $(shell sdl2-config --cflags) $(shell pkg-config --cflags SDL2_ttf)
LDFLAGS = $(shell sdl2-config --libs) $(shell pkg-config --libs SDL2_ttf) -lm -lmosquitto

# ARM cross-compilation settings
ARM_CC = arm-linux-gnueabihf-gcc
ARM_CFLAGS = -Wall -Wextra
ARM_LDFLAGS = -lSDL2 -lSDL2_ttf -lm -lmosquitto
ARM_TARGET = $(TARGET)_armhf

SRCS = main.c debug_scene.c idle_scene.c transitions.c doom_scene.c embedded_assets.c
OBJS = $(SRCS:.c=.o)
ARM_OBJS = $(SRCS:.c=.armhf.o)
TARGET = sdl_app

all: embedded_assets.c $(TARGET)

embedded_assets.c: ../assets/RobotoMono-Regular.ttf
	echo '#include "embedded_assets.h"' > $@
	echo 'const unsigned char roboto_mono_regular_ttf[] = {' >> $@
	xxd -i < $< >> $@
	echo '};' >> $@
	echo 'const unsigned int roboto_mono_regular_ttf_len = sizeof(roboto_mono_regular_ttf);' >> $@

$(TARGET): $(OBJS)
	$(CC) $(OBJS) -o $(TARGET) $(LDFLAGS)

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

# ARM build rules
armhf: embedded_assets.c $(ARM_TARGET)

$(ARM_TARGET): $(ARM_OBJS)
	$(ARM_CC) $(ARM_OBJS) -o $(ARM_TARGET) $(ARM_LDFLAGS)

%.armhf.o: %.c
	$(ARM_CC) $(ARM_CFLAGS) -c $< -o $@

dev: $(TARGET)
	MQTT_BROKER=10.0.1.133 DOOM_IWAD=~/Downloads/freedoom-0.13.0/freedoom1.wad ./$(TARGET)

clean:
	rm -f $(OBJS) $(ARM_OBJS) $(TARGET) $(ARM_TARGET) embedded_assets.c

.PHONY: all clean dev armhf