/*
 * Protosuit Remote Control - Configuration Loader Header
 */

#ifndef CONFIG_LOADER_H
#define CONFIG_LOADER_H

typedef struct {
    char mqtt_broker_ip[32];
    int mqtt_broker_port;
    char mqtt_client_id[32];
    char mqtt_topic[128];
    int mqtt_keepalive;
} app_config_t;

// Load configuration from file (returns 1 if file exists, 0 if using defaults)
int load_config(app_config_t *config);

// Save a default config file template
int save_default_config();

#endif // CONFIG_LOADER_H
