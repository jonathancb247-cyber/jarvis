#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>

#include "cJSON.h"
#include "driver/gpio.h"
#include "esp_event.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "nvs_flash.h"

#define JARVIS_LED_GPIO GPIO_NUM_2
#define JARVIS_MAX_BODY_BYTES 1024
#define WIFI_CONNECTED_BIT BIT0

static const char *TAG = "jarvis_http_led";
static EventGroupHandle_t wifi_event_group;
static bool led_power = false;

static void send_json_response(httpd_req_t *req, bool success, bool power, const char *error)
{
    cJSON *root = cJSON_CreateObject();
    cJSON *observations = cJSON_CreateObject();

    cJSON_AddBoolToObject(root, "success", success);
    cJSON_AddBoolToObject(observations, "power", power);
    cJSON_AddItemToObject(root, "observations", observations);
    if (error == NULL) {
        cJSON_AddNullToObject(root, "error");
    } else {
        cJSON_AddStringToObject(root, "error", error);
    }

    char *body = cJSON_PrintUnformatted(root);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_send(req, body, HTTPD_RESP_USE_STRLEN);

    cJSON_free(body);
    cJSON_Delete(root);
}

static bool read_request_body(httpd_req_t *req, char *buffer, size_t buffer_size)
{
    if (req->content_len == 0 || req->content_len >= buffer_size) {
        return false;
    }

    size_t received = 0;
    while (received < req->content_len) {
        int ret = httpd_req_recv(req, buffer + received, req->content_len - received);
        if (ret <= 0) {
            return false;
        }
        received += (size_t)ret;
    }
    buffer[received] = '\0';
    return true;
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

static esp_err_t apply_handler(httpd_req_t *req)
{
    char buffer[JARVIS_MAX_BODY_BYTES + 1];
    if (!read_request_body(req, buffer, sizeof(buffer))) {
        send_json_response(req, false, led_power, "invalid_request");
        return ESP_OK;
    }

    cJSON *root = cJSON_Parse(buffer);
    if (root == NULL || !cJSON_IsObject(root)) {
        cJSON_Delete(root);
        send_json_response(req, false, led_power, "invalid_json");
        return ESP_OK;
    }

    cJSON *capability = cJSON_GetObjectItemCaseSensitive(root, "capability");
    if (!cJSON_IsString(capability) || capability->valuestring == NULL ||
        strcmp(capability->valuestring, "power.switch") != 0) {
        cJSON_Delete(root);
        send_json_response(req, false, led_power, "operation_not_supported");
        return ESP_OK;
    }

    cJSON *parameters = cJSON_GetObjectItemCaseSensitive(root, "parameters");
    cJSON *state_item = cJSON_IsObject(parameters)
        ? cJSON_GetObjectItemCaseSensitive(parameters, "state")
        : NULL;

    bool requested_state = false;
    if (!parse_state_value(state_item, &requested_state)) {
        cJSON_Delete(root);
        send_json_response(req, false, led_power, "invalid_parameters");
        return ESP_OK;
    }

    led_power = requested_state;
    gpio_set_level(JARVIS_LED_GPIO, led_power ? 1 : 0);
    cJSON_Delete(root);
    send_json_response(req, true, led_power, NULL);
    return ESP_OK;
}

static esp_err_t read_handler(httpd_req_t *req)
{
    char buffer[JARVIS_MAX_BODY_BYTES + 1];
    if (!read_request_body(req, buffer, sizeof(buffer))) {
        send_json_response(req, false, led_power, "invalid_request");
        return ESP_OK;
    }

    cJSON *root = cJSON_Parse(buffer);
    if (root == NULL || !cJSON_IsObject(root)) {
        cJSON_Delete(root);
        send_json_response(req, false, led_power, "invalid_json");
        return ESP_OK;
    }

    cJSON *capability = cJSON_GetObjectItemCaseSensitive(root, "capability");
    if (!cJSON_IsString(capability) || capability->valuestring == NULL ||
        strcmp(capability->valuestring, "status.read") != 0) {
        cJSON_Delete(root);
        send_json_response(req, false, led_power, "operation_not_supported");
        return ESP_OK;
    }

    cJSON_Delete(root);
    send_json_response(req, true, led_power, NULL);
    return ESP_OK;
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
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "Got IP: " IPSTR, IP2STR(&event->ip_info.ip));
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
    strncpy((char *)wifi_config.sta.ssid, CONFIG_JARVIS_WIFI_SSID, sizeof(wifi_config.sta.ssid) - 1);
    strncpy((char *)wifi_config.sta.password, CONFIG_JARVIS_WIFI_PASSWORD, sizeof(wifi_config.sta.password) - 1);
    wifi_config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;

    if (strlen(CONFIG_JARVIS_WIFI_PASSWORD) == 0) {
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

static void start_http_server(void)
{
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    httpd_handle_t server = NULL;
    ESP_ERROR_CHECK(httpd_start(&server, &config));

    httpd_uri_t apply_uri = {
        .uri = "/device/apply",
        .method = HTTP_POST,
        .handler = apply_handler,
        .user_ctx = NULL,
    };
    httpd_uri_t read_uri = {
        .uri = "/device/read",
        .method = HTTP_POST,
        .handler = read_handler,
        .user_ctx = NULL,
    };

    ESP_ERROR_CHECK(httpd_register_uri_handler(server, &apply_uri));
    ESP_ERROR_CHECK(httpd_register_uri_handler(server, &read_uri));
    ESP_LOGI(TAG, "JarvisOS HTTP LED server started");
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
    start_http_server();
}

