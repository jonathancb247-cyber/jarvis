import unittest

from jarvis_core.domain import Command
from jarvis_core.planner import INVALID_DEVICE_INPUT_REASON, Planner


class PlannerTest(unittest.TestCase):
    def test_plan_returns_time_command_in_english(self):
        command = Planner().plan("what time is it?")

        self.assertEqual(command, Command(name="time.now", args={}, source="cli"))

    def test_plan_returns_time_command_in_spanish(self):
        command = Planner().plan("que hora es?")

        self.assertEqual(command, Command(name="time.now", args={}, source="cli"))

    def test_plan_preserves_adapter_source(self):
        command = Planner().plan("what time is it?", source="test-adapter")

        self.assertEqual(
            command,
            Command(name="time.now", args={}, source="test-adapter"),
        )

    def test_plan_returns_unknown_command_for_unknown_input(self):
        command = Planner().plan("turn on the lights")

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"text": "turn on the lights"})
        self.assertEqual(command.source, "cli")

    def test_plan_returns_device_read_command(self):
        command = Planner().plan("device read lamp-1 temperature", source="cli")

        self.assertEqual(command.name, "device.execute")
        self.assertEqual(
            command.args,
            {
                "device_id": "lamp-1",
                "capability": "temperature",
                "operation": "read",
                "parameters": {},
            },
        )
        self.assertEqual(command.source, "cli")

    def test_plan_returns_device_apply_command_with_parameters(self):
        command = Planner().plan(
            "device apply lamp-1 power value=on brightness=80",
            source="cli",
        )

        self.assertEqual(command.name, "device.execute")
        self.assertEqual(
            command.args,
            {
                "device_id": "lamp-1",
                "capability": "power",
                "operation": "apply",
                "parameters": {
                    "value": "on",
                    "brightness": "80",
                },
            },
        )

    def test_plan_returns_device_catalog_list_command(self):
        command = Planner().plan("device list", source="cli")

        self.assertEqual(command.name, "device.catalog")
        self.assertEqual(command.args, {"operation": "list"})
        self.assertEqual(command.source, "cli")

    def test_plan_returns_device_catalog_info_command(self):
        command = Planner().plan("device info sensor_1", source="api")

        self.assertEqual(command.name, "device.catalog")
        self.assertEqual(
            command.args,
            {"operation": "info", "device_id": "sensor_1"},
        )
        self.assertEqual(command.source, "api")

    def test_plan_returns_device_catalog_capabilities_command(self):
        command = Planner().plan("device capabilities sensor_1")

        self.assertEqual(command.name, "device.catalog")
        self.assertEqual(
            command.args,
            {"operation": "capabilities", "device_id": "sensor_1"},
        )

    def test_plan_returns_device_catalog_state_command(self):
        command = Planner().plan("device state sensor_1")

        self.assertEqual(command.name, "device.catalog")
        self.assertEqual(
            command.args,
            {"operation": "state", "device_id": "sensor_1"},
        )

    def test_plan_returns_device_lifecycle_add_command(self):
        command = Planner().plan(
            "device add lamp_1 name=Lamp type=light",
            source="cli",
        )

        self.assertEqual(command.name, "device.lifecycle")
        self.assertEqual(
            command.args,
            {
                "operation": "add",
                "device_id": "lamp_1",
                "name": "Lamp",
                "type": "light",
            },
        )
        self.assertEqual(command.source, "cli")

    def test_plan_returns_device_lifecycle_remove_command(self):
        command = Planner().plan("device remove lamp_1", source="api")

        self.assertEqual(command.name, "device.lifecycle")
        self.assertEqual(
            command.args,
            {"operation": "remove", "device_id": "lamp_1"},
        )
        self.assertEqual(command.source, "api")

    def test_plan_returns_device_discovery_command(self):
        command = Planner().plan("device discover", source="cli")

        self.assertEqual(command.name, "device.discovery")
        self.assertEqual(command.args, {"operation": "scan"})
        self.assertEqual(command.source, "cli")

    def test_plan_preserves_device_discovery_source(self):
        command = Planner().plan("device discover", source="voice")

        self.assertEqual(command.name, "device.discovery")
        self.assertEqual(command.source, "voice")

    def test_plan_rejects_device_discovery_extra_tokens(self):
        command = Planner().plan("device discover bluetooth")

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"reason": INVALID_DEVICE_INPUT_REASON})

    def test_plan_returns_device_onboarding_command(self):
        command = Planner().plan(
            "device onboard candidate-1 as lamp_1",
            source="api",
        )

        self.assertEqual(command.name, "device.onboarding")
        self.assertEqual(
            command.args,
            {
                "operation": "approve",
                "candidate_id": "candidate-1",
                "device_id": "lamp_1",
            },
        )
        self.assertEqual(command.source, "api")

    def test_plan_rejects_device_onboarding_missing_candidate_id(self):
        command = Planner().plan("device onboard as lamp_1")

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"reason": INVALID_DEVICE_INPUT_REASON})

    def test_plan_rejects_device_onboarding_missing_as(self):
        command = Planner().plan("device onboard candidate-1 lamp_1")

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"reason": INVALID_DEVICE_INPUT_REASON})

    def test_plan_rejects_device_onboarding_missing_device_id(self):
        command = Planner().plan("device onboard candidate-1 as")

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"reason": INVALID_DEVICE_INPUT_REASON})

    def test_plan_rejects_device_onboarding_extra_tokens(self):
        command = Planner().plan("device onboard candidate-1 as lamp_1 force=true")

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"reason": INVALID_DEVICE_INPUT_REASON})

    def test_plan_rejects_device_onboarding_without_raw_text(self):
        command = Planner().plan("device onboard secret-candidate as secret-device extra")

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"reason": INVALID_DEVICE_INPUT_REASON})
        self.assertNotIn("secret-candidate", str(command.args))
        self.assertNotIn("secret-device", str(command.args))

    def test_plan_rejects_device_lifecycle_add_missing_name(self):
        command = Planner().plan("device add lamp_1 type=light")

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"reason": INVALID_DEVICE_INPUT_REASON})

    def test_plan_rejects_device_lifecycle_add_missing_type(self):
        command = Planner().plan("device add lamp_1 name=Lamp")

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"reason": INVALID_DEVICE_INPUT_REASON})

    def test_plan_rejects_device_lifecycle_duplicate_parameters(self):
        command = Planner().plan("device add lamp_1 name=Lamp name=Other type=light")

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"reason": INVALID_DEVICE_INPUT_REASON})

    def test_plan_rejects_device_lifecycle_unknown_parameters(self):
        command = Planner().plan(
            "device add lamp_1 name=Lamp type=light metadata=secret"
        )

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"reason": INVALID_DEVICE_INPUT_REASON})
        self.assertNotIn("secret", str(command.args))

    def test_plan_rejects_device_lifecycle_remove_extra_tokens(self):
        command = Planner().plan("device remove lamp_1 force=true")

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"reason": INVALID_DEVICE_INPUT_REASON})

    def test_plan_rejects_device_catalog_list_with_extra_tokens(self):
        command = Planner().plan("device list extra")

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"reason": INVALID_DEVICE_INPUT_REASON})

    def test_plan_rejects_device_catalog_missing_device_id(self):
        command = Planner().plan("device info")

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"reason": INVALID_DEVICE_INPUT_REASON})

    def test_plan_rejects_device_read_with_parameters(self):
        command = Planner().plan("device read lamp-1 power value=on")

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"reason": INVALID_DEVICE_INPUT_REASON})

    def test_plan_rejects_invalid_device_operation_without_raw_text(self):
        command = Planner().plan("device toggle secret-device power token=abc")

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"reason": INVALID_DEVICE_INPUT_REASON})
        self.assertNotIn("secret-device", str(command.args))
        self.assertNotIn("token=abc", str(command.args))

    def test_plan_rejects_invalid_device_parameters_without_raw_text(self):
        command = Planner().plan("device apply lamp-1 power invalid-token")

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"reason": INVALID_DEVICE_INPUT_REASON})
        self.assertNotIn("invalid-token", str(command.args))

    def test_plan_rejects_duplicate_device_parameters(self):
        command = Planner().plan("device apply lamp-1 power value=on value=off")

        self.assertEqual(command.name, "unknown")
        self.assertEqual(command.args, {"reason": INVALID_DEVICE_INPUT_REASON})


if __name__ == "__main__":
    unittest.main()
