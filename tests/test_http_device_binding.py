import unittest

from jarvis_core.http_driver import HttpDeviceBinding, HttpDeviceBindingStore


class HttpDeviceBindingTests(unittest.TestCase):
    def test_valid_binding(self):
        binding = HttpDeviceBinding(
            device_id="lamp_1",
            base_url="http://localhost:8080",
        )

        self.assertEqual("lamp_1", binding.device_id)
        self.assertEqual("/device/read", binding.read_path)
        self.assertEqual("/device/apply", binding.apply_path)

    def test_rejects_invalid_device_id(self):
        with self.assertRaises(ValueError):
            HttpDeviceBinding(device_id="", base_url="http://localhost")

    def test_rejects_invalid_scheme(self):
        with self.assertRaises(ValueError):
            HttpDeviceBinding(device_id="lamp_1", base_url="https://localhost")

    def test_rejects_missing_host(self):
        with self.assertRaises(ValueError):
            HttpDeviceBinding(device_id="lamp_1", base_url="http:///device")

    def test_rejects_embedded_credentials(self):
        with self.assertRaises(ValueError):
            HttpDeviceBinding(device_id="lamp_1", base_url="http://user:pass@localhost")

    def test_rejects_query_and_fragment(self):
        with self.assertRaises(ValueError):
            HttpDeviceBinding(device_id="lamp_1", base_url="http://localhost?x=1")
        with self.assertRaises(ValueError):
            HttpDeviceBinding(device_id="lamp_1", base_url="http://localhost#secret")

    def test_rejects_invalid_timeout(self):
        for timeout in [0, -1, 11]:
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    HttpDeviceBinding(
                        device_id="lamp_1",
                        base_url="http://localhost",
                        timeout_seconds=timeout,
                    )

    def test_rejects_invalid_port(self):
        with self.assertRaises(ValueError):
            HttpDeviceBinding(device_id="lamp_1", base_url="http://localhost:99999")

    def test_rejects_invalid_paths(self):
        invalid_paths = [
            "device/read",
            "/device/../secret",
            "http://localhost/device/read",
            "/device/read?token=1",
            "/device/read#fragment",
        ]

        for path in invalid_paths:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    HttpDeviceBinding(
                        device_id="lamp_1",
                        base_url="http://localhost",
                        read_path=path,
                    )

    def test_host_policy_allows_localhost_loopback_private_and_local_name(self):
        allowed = [
            "http://localhost",
            "http://127.0.0.1:8000",
            "http://192.168.1.10",
            "http://10.0.0.2",
            "http://esp32-light.local",
            "http://esp32-light",
        ]

        for url in allowed:
            with self.subTest(url=url):
                self.assertIsInstance(
                    HttpDeviceBinding(device_id="lamp_1", base_url=url),
                    HttpDeviceBinding,
                )

    def test_host_policy_rejects_multicast_broadcast_and_unspecified(self):
        rejected = [
            "http://224.0.0.1",
            "http://255.255.255.255",
            "http://0.0.0.0",
            "http://example.com",
        ]

        for url in rejected:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    HttpDeviceBinding(device_id="lamp_1", base_url=url)


class HttpDeviceBindingStoreTests(unittest.TestCase):
    def test_register_get_has_list_and_remove(self):
        store = HttpDeviceBindingStore()
        binding = HttpDeviceBinding("lamp_1", "http://localhost")

        store.register(binding)

        self.assertTrue(store.has("lamp_1"))
        self.assertIs(store.get("lamp_1"), binding)
        self.assertEqual([binding], store.list())
        self.assertIs(store.remove("lamp_1"), binding)
        self.assertFalse(store.has("lamp_1"))

    def test_register_rejects_non_binding(self):
        store = HttpDeviceBindingStore()

        with self.assertRaises(TypeError):
            store.register(object())

    def test_register_rejects_duplicate(self):
        store = HttpDeviceBindingStore()
        binding = HttpDeviceBinding("lamp_1", "http://localhost")

        store.register(binding)

        with self.assertRaises(ValueError):
            store.register(binding)

    def test_get_and_remove_missing_raise_key_error(self):
        store = HttpDeviceBindingStore()

        with self.assertRaises(KeyError):
            store.get("missing")
        with self.assertRaises(KeyError):
            store.remove("missing")

    def test_store_is_not_device_registry_or_persistence(self):
        store = HttpDeviceBindingStore()

        self.assertFalse(hasattr(store, "devices"))
        self.assertFalse(hasattr(store, "register_device"))
        self.assertFalse(hasattr(store, "save"))


if __name__ == "__main__":
    unittest.main()
