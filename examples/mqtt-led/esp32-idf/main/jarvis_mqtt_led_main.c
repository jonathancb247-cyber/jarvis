#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "cJSON.h"
#include "driver/gpio.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "mqtt_client.h"
#include "nvs_flash.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"

#define JARVIS_LED_GPIO GPIO_NUM_2
#define JARVIS_MAX_REQUEST_BYTES 1024
#define JARVIS_MAX_RESPONSE_BYTES 512
#define WIFI_CONNECTED_BIT BIT0

static const char *TAG = "jarvis_mqtt_led";
static const char *REQUEST_TOPIC = "jarvis/lab/lamp_1/request";
static const char *RESPONSE_TOPIC = "jarvis/lab/lamp_1/response";
static EventGroupHandle_t wifi_event_group;
static bool led_power = false;

static void publish_response(
    esp_mqtt_client_handle_t client,
    const char *request_id,
    bool ok,
    bool include_power,
    bool power,
    const char *error)
{
    cJSON *root = cJSON_CreateObject();
    cJSON *semantic = cJSON_CreateObject();

    cJSON_AddStringToObject(root, "request_id", request_id);
    cJSON_AddBoolToObject(root, "ok", ok);
    if (include_power) {
        cJSON_AddBoolToObject(semantic, "power", power);
    }
    cJSON_AddItemToObject(root, "semantic", semantic);
    if (error == NULL) {
        cJSON_AddNullToObject(root, "error");
    } else {
        cJSON_AddStringToObject(root, "error", error);
    }

    char *body = cJSON_PrintUnformatted(root);
    if (body != NULL && strlen(body) <= JARVIS_MAX_RESPONSE_BYTES) {
        esp_mqtt_client_publish(client, RESPONSE_TOPIC, body, 0, 0, 0);
    }

    cJSON_free(body);
    cJSON_Delete(root);
}

static bool parse_state_value(cJSON *state_item, bool *state)
{
    if (cJSON_IsBool(state_item)) {
        *state = cJSON_IsTrue(state_item);
        return true;
    }

    if (!cJSON_IsString(state_item) || state_item->valuestring == NULL) {
        return false;
    }

    const char *value = state_item->valuestring;
    if (strcmp(value, "true") == 0 || strcmp(value, "on") == 0 || strcmp(value, "1") == 0) {
        *state = true;
        return true;
    }
    if (strcmp(value, "false") == 0 || strcmp(value, "off") == 0 || strcmp(value, "0") == 0) {
        *state = false;
        return true;
    }
    return false;
}

static bool has_only_expected_fields(cJSON *root)
{
    int count = 0;
    for (cJSON *item = root->child; item != NULL; item = item->next) {
        const char *key = item->string;
        if (key == NULL) {
            return false;
        }
        if (
            strcmp(key, "request_id") != 0 &&
            strcmp(key, "device_id") != 0 &&
            strcmp(key, "capability") != 0 &&
            strcmp(key, "operation") != 0 &&
            strcmp(key, "parameters") != 0) {
            return false;
        }
        count++;
    }
    return count == 5;
}

static void handle_request(esp_mqtt_client_handle_t client, const char *data, int data_len)
{
    if (data_len <= 0 || data_len > JARVIS_MAX_REQUEST_BYTES) {
        return;
    }

    char buffer[JARVIS_MAX_REQUEST_BYTES + 1];
    memcpy(buffer, data, (size_t)data_len);
    buffer[data_len] = '\0';

    cJSON *root = cJSON_Parse(buffer);
    if (root == NULL || !cJSON_IsObject(root) || !has_only_expected_fields(root)) {
        cJSON_Delete(root);
        return;
    }

    cJSON *request_id_item = cJSON_GetObjectItemCaseSensitive(root, "request_id");
    cJSON *device_id_item = cJSON_GetObjectItemCaseSensitive(root, "device_id");
    cJSON *capability_item = cJSON_GetObjectItemCaseSensitive(root, "capability");
    cJSON *operation_item = cJSON_GetObjectItemCaseSensitive(root, "operation");
    cJSON *parameters_item = cJSON_GetObjectItemCaseSensitive(root, "parameters");

    if (!cJSON_IsString(request_id_item) || request_id_item->valuestring == NULL ||
        strlen(request_id_item->valuestring) == 0 || strlen(request_id_item->valuestring) > 64) {
        cJSON_Delete(root);
        return;
    }
    const char *request_id = request_id_item->valuestring;

    if (!cJSON_IsString(device_id_item) || device_id_item->valuestring == NULL ||
        strcmp(device_id_item->valuestring, "lamp_1") != 0) {
        publish_response(client, request_id, false, false, led_power, "invalid_device");
        cJSON_Delete(root);
        return;
    }
    if (!cJSON_IsString(capability_item) || capability_item->valuestring == NULL ||
        !cJSON_IsString(operation_item) || operation_item->valuestring == NULL ||
        !cJSON_IsObject(parameters_item)) {
        publish_response(client, request_id, false, false, led_power, "invalid_parameters");
        cJSON_Delete(root);
        return;
    }

    const char *capability = capability_item->valuestring;
    const char *operation = operation_item->valuestring;

    if (strcmp(operation, "read") == 0 && strcmp(capability, "status.read") == 0) {
        publish_response(client, request_id, true, true, led_power, NULL);
        cJSON_Delete(root);
        return;
    }

    if (strcmp(operation, "apply") == 0 && strcmp(capability, "power.switch") == 0) {
        cJSON *state_item = cJSON_GetObjectItemCaseSensitive(parameters_item, "state");
        bool requested_state = false;
        if (!parse_state_value(state_item, &requested_state)) {
            publish_response(client, request_id, false, false, led_power, "invalid_parameters");
            cJSON_Delete(root);
            return;
        }

        led_power = requested_state;
        gpio_set_level(JARVIS_LED_GPIO, led_power ? 1 : 0);
        publish_response(client, request_id, true, true, led_power, NULL);
        cJSON_Delete(root);
        return;
    }

    publish_response(client, request_id, false, false, led_power, "operation_not_supported");
    cJSON_Delete(root);
}

static void mqtt_event_handler(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
    (void)handler_args;
    (void)base;
    esp_mqtt_event_handle_t event = event_data;
    esp_mqtt_client_handle_t client = event->client;

    switch ((esp_mqtt_event_id_t)event_id) {
    case MQTT_EVENT_CONNECTED:
        ESP_LOGI(TAG, "MQTT connected");
        esp_mqtt_client_subscribe(client, REQUEST_TOPIC, 0);
        break;
    case MQTT_EVENT_DATA:
        if (event->topic_len == (int)strlen(REQUEST_TOPIC) &&
            strncmp(event->topic, REQUEST_TOPIC, (size_t)event->topic_len) == 0) {
            handle_request(client, event->data, event->data_len);
        }
        break;
    case MQTT_EVENT_DISCONNECTED:
        ESP_LOGW(TAG, "MQTT disconnected");
        break;
    default:
        break;
    }
}

static void wifi_event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data)
{
    (void)arg;
    (void)event_data;

    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        ESP_LOGW(TAG, "Wi-Fi disconnected; reconnecting");
        esp_wifi_connect();
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        xEventGroupSetBits(wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

static void wifi_init_sta(void)
{
    wifi_event_group = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, NULL));

    wifi_config_t wifi_config = {0};
    strncpy((char *)wifi_config.sta.ssid, CONFIG_JARVIS_MQTT_WIFI_SSID, sizeof(wifi_config.sta.ssid) - 1);
    strncpy((char *)wifi_config.sta.password, CONFIG_JARVIS_MQTT_WIFI_PASSWORD, sizeof(wifi_config.sta.password) - 1);
    wifi_config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;

    if (strlen(CONFIG_JARVIS_MQTT_WIFI_PASSWORD) == 0) {
        wifi_config.sta.threshold.authmode = WIFI_AUTH_OPEN;
    }

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    xEventGroupWaitBits(wifi_event_group, WIFI_CONNECTED_BIT, pdFALSE, pdTRUE, portMAX_DELAY);
}

static void gpio_init_led(void)
{
    gpio_config_t io_conf = {
        .pin_bit_mask = 1ULL << JARVIS_LED_GPIO,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&io_conf));
    gpio_set_level(JARVIS_LED_GPIO, 0);
}

static void start_mqtt_client(void)
{
    char broker_uri[128];
    snprintf(
        broker_uri,
        sizeof(broker_uri),
        "mqtt://%s:%d",
        CONFIG_JARVIS_MQTT_BROKER_HOST,
        CONFIG_JARVIS_MQTT_BROKER_PORT);

    esp_mqtt_client_config_t mqtt_cfg = {
        .broker.address.uri = broker_uri,
        .credentials.client_id = CONFIG_JARVIS_MQTT_CLIENT_ID,
    };
    esp_mqtt_client_handle_t client = esp_mqtt_client_init(&mqtt_cfg);
    ESP_ERROR_CHECK(esp_mqtt_client_register_event(client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL));
    ESP_ERROR_CHECK(esp_mqtt_client_start(client));
}

void app_main(void)
{
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    gpio_init_led();
    wifi_init_sta();
    start_mqtt_client();
}
