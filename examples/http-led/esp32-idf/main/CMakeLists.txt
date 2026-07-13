idf_component_register(
    SRCS "jarvis_http_led_main.c"
    INCLUDE_DIRS "."
    REQUIRES esp_wifi esp_http_server esp_event esp_netif nvs_flash driver json
)

