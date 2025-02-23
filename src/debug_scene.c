#include "scenes.h"
#include <stdio.h>
#include <time.h>
#include <sys/utsname.h>
#include <ifaddrs.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>

#ifdef __linux__
#include <sys/sysinfo.h>
#elif defined(__APPLE__)
#include <sys/sysctl.h>
#endif

static char *get_local_ip()
{
    static char ip[INET_ADDRSTRLEN];
    struct ifaddrs *ifaddr, *ifa;

    if (getifaddrs(&ifaddr) == -1)
    {
        perror("getifaddrs");
        return "Unknown";
    }

    for (ifa = ifaddr; ifa != NULL; ifa = ifa->ifa_next)
    {
        if (ifa->ifa_addr == NULL)
            continue;

        if (ifa->ifa_addr->sa_family == AF_INET)
        {
            // Skip loopback interface
#ifdef __linux__
            if (strcmp(ifa->ifa_name, "lo") == 0)
                continue;
#elif defined(__APPLE__)
            if (strcmp(ifa->ifa_name, "lo0") == 0)
                continue;
#endif

            struct sockaddr_in *addr = (struct sockaddr_in *)ifa->ifa_addr;
            inet_ntop(AF_INET, &addr->sin_addr, ip, INET_ADDRSTRLEN);
            freeifaddrs(ifaddr);
            return ip;
        }
    }

    freeifaddrs(ifaddr);
    return "Not found";
}

#ifdef __APPLE__
static time_t get_boot_time()
{
    struct timeval boottime;
    size_t len = sizeof(boottime);
    int mib[2] = {CTL_KERN, KERN_BOOTTIME};

    if (sysctl(mib, 2, &boottime, &len, NULL, 0) < 0)
    {
        return 0;
    }

    return boottime.tv_sec;
}
#endif

static void get_system_uptime(long *hours, long *minutes)
{
#ifdef __linux__
    struct sysinfo si;
    if (sysinfo(&si) == 0)
    {
        *hours = si.uptime / 3600;
        *minutes = (si.uptime % 3600) / 60;
    }
    else
    {
        *hours = 0;
        *minutes = 0;
    }
#elif defined(__APPLE__)
    time_t now = time(NULL);
    time_t boot_time = get_boot_time();
    time_t uptime = now - boot_time;
    *hours = uptime / 3600;
    *minutes = (uptime % 3600) / 60;
#endif
}

// Helper function to render centered text
static void render_centered_text(SDL_Renderer *renderer, TTF_Font *font, const char *text, int y, SDL_Color color)
{
    SDL_Surface *surface = TTF_RenderText_Blended(font, text, color);
    SDL_Texture *texture = SDL_CreateTextureFromSurface(renderer, surface);

    SDL_Rect rect = {
        .x = (WINDOW_WIDTH - surface->w) / 2,
        .y = y,
        .w = surface->w,
        .h = surface->h};

    SDL_RenderCopy(renderer, texture, NULL, &rect);

    SDL_FreeSurface(surface);
    SDL_DestroyTexture(texture);
}

void render_debug_scene(SDL_Renderer *renderer, TTF_Font *font, SDL_bool mqtt_connected)
{
    SDL_SetRenderDrawColor(renderer, 0, 0, 0, 255);
    SDL_RenderClear(renderer);

    // Get system information
    time_t now = time(NULL);
    struct tm *tm_info = localtime(&now);
    char time_str[64];
    strftime(time_str, sizeof(time_str), "%Y-%m-%d %H:%M:%S", tm_info);

    struct utsname uname_data;
    uname(&uname_data);

    // Get uptime
    long uptime_hours, uptime_minutes;
    get_system_uptime(&uptime_hours, &uptime_minutes);

    // Prepare text lines
    char lines[5][256];
    snprintf(lines[0], sizeof(lines[0]), "Date/Time: %s", time_str);
    snprintf(lines[1], sizeof(lines[1]), "Hostname: %s", uname_data.nodename);
    snprintf(lines[2], sizeof(lines[2]), "Uptime: %ldh %ldm", uptime_hours, uptime_minutes);
    snprintf(lines[3], sizeof(lines[3]), "Local IP: %s", get_local_ip());
    snprintf(lines[4], sizeof(lines[4]), "MQTT Status: %s", mqtt_connected ? "Connected" : "Disconnected");

    // Render text lines centered
    SDL_Color white = {255, 255, 255, 255};
    SDL_Color status_color = mqtt_connected ? (SDL_Color){0, 255, 0, 255} : // Green for connected
                                 (SDL_Color){255, 0, 0, 255};               // Red for disconnected

    int start_y = (WINDOW_HEIGHT - (5 * 40)) / 2; // Center all lines vertically
    for (int i = 0; i < 4; i++)
    {
        render_centered_text(renderer, font, lines[i], start_y + i * 40, white);
    }
    // Render MQTT status with color
    render_centered_text(renderer, font, lines[4], start_y + 4 * 40, status_color);
}