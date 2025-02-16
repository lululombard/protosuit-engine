set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR arm)

set(CMAKE_SYSROOT /usr/arm-linux-gnueabihf)
set(CMAKE_STAGING_PREFIX /usr/arm-linux-gnueabihf)

set(tools /usr)
set(CMAKE_C_COMPILER ${tools}/bin/arm-linux-gnueabihf-gcc)
set(CMAKE_CXX_COMPILER ${tools}/bin/arm-linux-gnueabihf-g++)
set(CMAKE_ASM_COMPILER ${tools}/bin/arm-linux-gnueabihf-gcc)

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)

set(CMAKE_LIBRARY_PATH /usr/arm-linux-gnueabihf/lib)
set(CMAKE_INCLUDE_PATH /usr/arm-linux-gnueabihf/include)

# Force SDL to use our cross-compiler
set(SDL_FORCE_CROSSCOMPILE ON)
set(SDL2_DIR /usr/arm-linux-gnueabihf/lib/cmake/SDL2)

# Force static build
set(SDL_SHARED OFF CACHE BOOL "Build a shared version of the library")
set(SDL_STATIC ON CACHE BOOL "Build a static version of the library")

# Enable X11 only
set(SDL_X11 ON CACHE BOOL "Enable X11 support")
set(SDL_X11_SHARED OFF CACHE BOOL "Build X11 support as shared library")

# Disable audio backends
set(SDL_PULSEAUDIO OFF CACHE BOOL "Disable PulseAudio")
set(SDL_ALSA OFF CACHE BOOL "Disable ALSA")
set(SDL_JACK OFF CACHE BOOL "Disable JACK")
set(SDL_ESD OFF CACHE BOOL "Disable ESD")
set(SDL_PIPEWIRE OFF CACHE BOOL "Disable PipeWire")
set(SDL_OSS OFF CACHE BOOL "Disable OSS")

# Disable Wayland
set(SDL_WAYLAND OFF CACHE BOOL "Disable Wayland")

# Additional include paths for X11 and dependencies
include_directories(SYSTEM
  /usr/arm-linux-gnueabihf/include
  /usr/include/X11
  /usr/include/X11/extensions
  /usr/include/GL
  /usr/include/GLES
  /usr/include/GLES2
  /usr/include/EGL
)

# Set pkg-config paths
set(ENV{PKG_CONFIG_PATH} "/usr/lib/arm-linux-gnueabihf/pkgconfig")
set(ENV{PKG_CONFIG_SYSROOT_DIR} "/usr/arm-linux-gnueabihf")
set(ENV{PKG_CONFIG_LIBDIR} "/usr/lib/arm-linux-gnueabihf/pkgconfig")