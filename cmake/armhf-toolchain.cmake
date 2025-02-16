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

# Additional include paths for D-Bus and other dependencies
include_directories(SYSTEM
  /usr/arm-linux-gnueabihf/include
  /usr/include/dbus-1.0
  /usr/lib/arm-linux-gnueabihf/dbus-1.0/include
  /usr/include/wayland
  /usr/include/glib-2.0
  /usr/lib/arm-linux-gnueabihf/glib-2.0/include
)