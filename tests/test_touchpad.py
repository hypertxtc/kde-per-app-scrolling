"""Unit tests for kde_per_app_scrolling.touchpad."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kde_per_app_scrolling.touchpad import (  # noqa: E402
    INPUT_DEVICE_IFACE,
    INPUT_DEVICE_MANAGER_IFACE,
    INPUT_DEVICE_MANAGER_PATH,
    TouchpadController,
)


class FakeKWinBackend:
    """In-memory mock of KWin's InputDevice D-Bus objects."""

    def __init__(self, use_introspect_fallback: bool = False) -> None:
        self.use_introspect_fallback = use_introspect_fallback
        self.devices: dict[str, dict[str, Any]] = {
            "event3": {"touchpad": False, "name": "AT Keyboard", "scrollFactor": 1.0},
            "event7": {"touchpad": True, "name": "SynPS/2 Synaptics TouchPad", "scrollFactor": 1.0},
        }
        self.set_calls: list[tuple[str, float]] = []
        self.fail_next_set = False

    def get_property(self, object_path: str, interface: str, prop_name: str) -> Any:
        if object_path == INPUT_DEVICE_MANAGER_PATH and interface == INPUT_DEVICE_MANAGER_IFACE:
            if prop_name == "devicesSysNames":
                if self.use_introspect_fallback:
                    raise RuntimeError("Property not exposed")
                return list(self.devices.keys())
        if interface == INPUT_DEVICE_IFACE and object_path.startswith(INPUT_DEVICE_MANAGER_PATH + "/"):
            sys_name = object_path.rsplit("/", 1)[-1]
            if sys_name not in self.devices:
                raise RuntimeError(f"Unknown device {sys_name}")
            return self.devices[sys_name][prop_name]
        raise RuntimeError(f"Unexpected get_property({object_path}, {interface}, {prop_name})")

    def set_double_property(
        self, object_path: str, interface: str, prop_name: str, value: float
    ) -> None:
        if self.fail_next_set:
            self.fail_next_set = False
            raise RuntimeError("Stale device path")
        sys_name = object_path.rsplit("/", 1)[-1]
        if sys_name not in self.devices:
            raise RuntimeError("Missing device")
        self.devices[sys_name][prop_name] = value
        self.set_calls.append((sys_name, value))

    def introspect(self, object_path: str) -> str:
        nodes = "".join(f'<node name="{name}"/>' for name in self.devices)
        return f"<node>{nodes}</node>"


class TouchpadControllerTests(unittest.TestCase):
    def test_discover_touchpads_filters_non_touchpads(self) -> None:
        backend = FakeKWinBackend()
        ctrl = TouchpadController(backend=backend)
        touchpads = ctrl.discover_touchpads()
        self.assertEqual(len(touchpads), 1)
        self.assertEqual(touchpads[0].sys_name, "event7")
        self.assertEqual(touchpads[0].name, "SynPS/2 Synaptics TouchPad")

    def test_introspect_fallback_discovers_touchpads(self) -> None:
        backend = FakeKWinBackend(use_introspect_fallback=True)
        ctrl = TouchpadController(backend=backend)
        touchpads = ctrl.discover_touchpads()
        self.assertEqual(len(touchpads), 1)
        self.assertEqual(touchpads[0].sys_name, "event7")

    def test_set_scroll_factor_deduplicates_unless_forced(self) -> None:
        backend = FakeKWinBackend()
        ctrl = TouchpadController(backend=backend)
        self.assertTrue(ctrl.set_scroll_factor(0.5))
        self.assertTrue(ctrl.set_scroll_factor(0.5))  # skipped duplicate
        self.assertEqual(len(backend.set_calls), 1)
        self.assertTrue(ctrl.set_scroll_factor(0.5, force=True))
        self.assertEqual(len(backend.set_calls), 2)
        self.assertEqual(backend.devices["event7"]["scrollFactor"], 0.5)

    def test_stale_device_refreshes_and_retries(self) -> None:
        backend = FakeKWinBackend()
        ctrl = TouchpadController(backend=backend)
        ctrl.discover_touchpads()
        backend.fail_next_set = True
        self.assertTrue(ctrl.set_scroll_factor(2.0))
        self.assertEqual(backend.devices["event7"]["scrollFactor"], 2.0)


if __name__ == "__main__":
    unittest.main()
