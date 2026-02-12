/*
 * Protosuit Remote Control - Configuration Loader
 * Reads settings from ms0:/PSP/GAME/ProtosuitRemote/config.txt
 */

#include "config_loader.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define CONFIG_PATH "ms0:/PSP/GAME/ProtosuitRemote/config.txt"
#define MAX_LINE 256

// Trim whitespace from string
static void trim(char *str) {
    char *start = str;
    char *end;

    // Trim leading space
    while (*start == ' ' || *start == '\t') start++;

    // All spaces?
    if (*start == 0) {
        str[0] = 0;
        return;
    }

    // Trim trailing space
    end = start + strlen(start) - 1;
    while (end > start && (*end == ' ' || *end == '\t' || *end == '\r' || *end == '\n')) {
        end--;
    }

    // Write new null terminator
    *(end + 1) = 0;

    // Move trimmed string to beginning
    if (start != str) {
        memmove(str, start, strlen(start) + 1);
    }
}

// Parse a config line (key=value)
static void parse_line(char *line, app_config_t *config) {
    char *equals = strchr(line, '=');
    if (!equals) return;

    *equals = 0;
    char *key = line;
    char *value = equals + 1;

    trim(key);
    trim(value);

    // Skip empty or comment lines
    if (key[0] == 0 || key[0] == '#') return;

    // Parse known keys
    if (strcmp(key, "mqtt_broker_ip") == 0) {
        strncpy(config->mqtt_broker_ip, value, sizeof(config->mqtt_broker_ip) - 1);
    }
    else if (strcmp(key, "mqtt_broker_port") == 0) {
        config->mqtt_broker_port = atoi(value);
        if (config->mqtt_broker_port <= 0) {
            config->mqtt_broker_port = 1883;
        }
    }
    else if (strcmp(key, "mqtt_client_id") == 0) {
        strncpy(config->mqtt_client_id, value, sizeof(config->mqtt_client_id) - 1);
    }
    else if (strcmp(key, "mqtt_topic") == 0) {
        strncpy(config->mqtt_topic, value, sizeof(config->mqtt_topic) - 1);
    }
    else if (strcmp(key, "mqtt_keepalive") == 0) {
        config->mqtt_keepalive = atoi(value);
        if (config->mqtt_keepalive < 10) {
            config->mqtt_keepalive = 60;
        }
    }
}

int load_config(app_config_t *config) {
    // Set defaults first
    strncpy(config->mqtt_broker_ip, "192.168.1.100", sizeof(config->mqtt_broker_ip) - 1);
    config->mqtt_broker_port = 1883;
    strncpy(config->mqtt_client_id, "psp-controller", sizeof(config->mqtt_client_id) - 1);
    strncpy(config->mqtt_topic, "protogen/fins/launcher/input/exec", sizeof(config->mqtt_topic) - 1);
    config->mqtt_keepalive = 60;

    // Try to open config file
    FILE *f = fopen(CONFIG_PATH, "r");
    if (!f) {
        // Config file doesn't exist, use defaults
        return 0;
    }

    // Read and parse each line
    char line[MAX_LINE];
    while (fgets(line, sizeof(line), f)) {
        parse_line(line, config);
    }

    fclose(f);
    return 1;
}

int save_default_config() {
    FILE *f = fopen(CONFIG_PATH, "w");
    if (!f) {
        return -1;
    }

    fprintf(f, "# Protosuit Remote Control Configuration\n");
    fprintf(f, "# Edit these values to match your setup\n");
    fprintf(f, "\n");
    fprintf(f, "# Note: Wi-Fi profile is selected on startup\n");
    fprintf(f, "\n");
    fprintf(f, "# MQTT Broker Settings\n");
    fprintf(f, "mqtt_broker_ip=192.168.1.100\n");
    fprintf(f, "mqtt_broker_port=1883\n");
    fprintf(f, "mqtt_client_id=psp-controller\n");
    fprintf(f, "mqtt_topic=protogen/fins/launcher/input/exec\n");
    fprintf(f, "mqtt_keepalive=60\n");
    fprintf(f, "\n");
    fprintf(f, "# Note: Restart the app after editing this file\n");

    fclose(f);
    return 0;
}
