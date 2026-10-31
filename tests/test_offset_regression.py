"""Dependency-free regression tests of the integration's actual setup methods.

Compile the selected methods directly from source so the tests can run without
installing Home Assistant. External HA/WM services are test doubles; these are
not full Home Assistant integration or live Waste Management API tests.
"""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1] / "custom_components/waste_management"


def load_method(filename, name, namespace, class_name=None):
    tree = ast.parse((ROOT / filename).read_text(encoding="utf-8"))
    body = tree.body
    if class_name:
        body = next(node for node in body if isinstance(node, ast.ClassDef)
                    and node.name == class_name).body
    method = next(node for node in body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and node.name == name)
    module = ast.Module(body=[method], type_ignores=[])
    # Postpone annotations, as Home Assistant's types are not installed here.
    import __future__
    exec(compile(module, str(ROOT / filename), "exec",
                 flags=__future__.annotations.compiler_flag), namespace)
    return namespace[name]


class OffsetRegression(unittest.IsolatedAsyncioTestCase):
    async def test_existing_entries_with_missing_none_zero_and_signed_offsets(self):
        for value in ("missing", None, 0, -2, 3):
            with self.subTest(offset=value):
                data = dict(username="test", password="test", account="account", services=["trash"])
                if value != "missing":
                    data["offset_days"] = value
                client = SimpleNamespace(
                    async_authenticate=AsyncMock(), async_okta_authorize=AsyncMock(),
                    async_get_services=AsyncMock(return_value=[SimpleNamespace(id="trash", name="Trash")]))
                # Use the real entity constructor to exercise None normalization.
                constructor = load_method("sensor.py", "__init__", {
                    "homeassistant": SimpleNamespace(helpers=SimpleNamespace(event=SimpleNamespace(
                        async_track_utc_time_change=Mock())))}, "WasteManagementSensorEntity")
                entity_type = type("Sensor", (), {"__init__": constructor, "timer_callback": AsyncMock()})
                setup = load_method("sensor.py", "async_setup_entry", {
                    "CONF_USERNAME": "username", "CONF_PASSWORD": "password",
                    "CONF_ACCOUNT": "account", "CONF_SERVICES": "services",
                    "CONF_OFFSET_DAYS": "offset_days", "WMClient": Mock(return_value=client),
                    "get_async_client": Mock(), "WasteManagementSensorEntity": entity_type,
                    "PlatformNotReady": RuntimeError, "_LOGGER": Mock()})
                added = Mock()
                await setup(object(), SimpleNamespace(data=data), added)
                added.assert_called_once()
                entity = added.call_args.args[0][0]
                self.assertEqual(entity.offset, 0 if value in ("missing", None) else value)
                self.assertEqual(entity._attr_unique_id, "account_trash")

    async def test_new_entries_with_omitted_none_and_signed_offsets(self):
        for value in ("missing", None, 0, -2, 3):
            with self.subTest(offset=value):
                data = dict(username="test", password="test")
                if value != "missing":
                    data["offset_days"] = value
                flow = SimpleNamespace(hass=object(), data={}, async_step_accounts=AsyncMock(return_value="accounts"))
                step = load_method("config_flow.py", "async_step_user", {
                    "CONF_USERNAME": "username", "CONF_PASSWORD": "password",
                    "CONF_OFFSET_DAYS": "offset_days", "validate_input": AsyncMock(),
                    "InvalidAuth": RuntimeError, "_LOGGER": Mock()}, "ConfigFlow")
                self.assertEqual(await step(flow, data), "accounts")
                self.assertEqual(flow.data["offset_days"], 0 if value in ("missing", None) else value)


if __name__ == "__main__":
    unittest.main()
