idf_component_register(
    SRCS "jarvis_mqtt_led_main.c"
    INCLUDE_DIRS "."
    REQUIRES esp_wifi mqtt esp_event esp_netif nvs_flash driver json
)
