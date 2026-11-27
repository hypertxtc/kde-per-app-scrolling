"""KWin D-Bus controller for touchpad scrollFactor."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Protocol

from .config import clamp_scroll_factor

LOGGER = logging.getLogger(__name__)

KWIN_SERVICE = "org.kde.KWin"
INPUT_DEVICE_MANAGER_PATH = "/org/kde/KWin/InputDevice"
INPUT_DEVICE_MANAGER_IFACE = "org.kde.KWin.InputDeviceManager"
INPUT_DEVICE_IFACE = "org.kde.KWin.InputDevice"
DBUS_PROPERTIES_IFACE = "org.freedesktop.DBus.Properties"
DBUS_INTROSPECTABLE_IFACE = "org.freedesktop.DBus.Introspectable"


@dataclass
class TouchpadDevice:
    """Represents a KWin libinput touchpad device."""

    sys_name: str
    dbus_path: str
    name: str
    scroll_factor: float

    def to_dict(self) -> dict[str, Any]:
        """Serialize device info for status reporting."""
        return {
            "sys_name": self.sys_name,
            "dbus_path": self.dbus_path,
            "name": self.name,
            "scroll_factor": self.scroll_factor,
        }


class KWinDBusBackend(Protocol):
    """Protocol abstracting KWin InputDevice D-Bus calls for testability."""

    def get_property(self, object_path: str, interface: str, prop_name: str) -> Any:
        ...

    def set_double_property(
        self, object_path: str, interface: str, prop_name: str, value: float
    ) -> None:
        ...

    def introspect(self, object_path: str) -> str:
        ...


class SessionBusKWinBackend:
    """Live D-Bus backend talking to org.kde.KWin on the session bus."""

    def __init__(self, bus: Any | None = None) -> None:
        import dbus

        self._dbus = dbus
        self._bus = bus if bus is not None else dbus.SessionBus()

    def get_property(self, object_path: str, interface: str, prop_name: str) -> Any:
        proxy = self._bus.get_object(KWIN_SERVICE, object_path)
        props = self._dbus.Interface(proxy, DBUS_PROPERTIES_IFACE)
        return props.Get(interface, prop_name)

    def set_double_property(
        self, object_path: str, interface: str, prop_name: str, value: float
    ) -> None:
        proxy = self._bus.get_object(KWIN_SERVICE, object_path)
        props = self._dbus.Interface(proxy, DBUS_PROPERTIES_IFACE)
        props.Set(interface, prop_name, self._dbus.Double(value))

    def introspect(self, object_path: str) -> str:
        proxy = self._bus.get_object(KWIN_SERVICE, object_path)
        introspectable = self._dbus.Interface(proxy, DBUS_INTROSPECTABLE_IFACE)
        return str(introspectable.Introspect())


class TouchpadController:
    """Discovers KWin touchpad devices and applies scrollFactor changes."""

    def __init__(self, backend: KWinDBusBackend | None = None) -> None:
        self._backend: KWinDBusBackend = (
            backend if backend is not None else SessionBusKWinBackend()
        )
        self._touchpads: list[TouchpadDevice] = []
        self._last_applied: float | None = None

    def _list_device_sys_names(self) -> list[str]:
        try:
            names = self._backend.get_property(
                INPUT_DEVICE_MANAGER_PATH,
                INPUT_DEVICE_MANAGER_IFACE,
                "devicesSysNames",
            )
            if names is not None:
                return [str(item) for item in names if str(item)]
        except Exception as exc:
            LOGGER.debug("devicesSysNames property unavailable, trying introspect: %s", exc)

        try:
            xml_str = self._backend.introspect(INPUT_DEVICE_MANAGER_PATH)
            root = ET.fromstring(xml_str)
            return [
                node.attrib["name"]
                for node in root.findall("node")
                if node.attrib.get("name")
            ]
        except Exception as exc:
            LOGGER.warning("Failed to list KWin input devices: %s", exc)
            return []

    def discover_touchpads(self) -> list[TouchpadDevice]:
        """Discover all KWin input devices identified as touchpads."""
        found: list[TouchpadDevice] = []
        for sys_name in self._list_device_sys_names():
            dbus_path = f"{INPUT_DEVICE_MANAGER_PATH}/{sys_name}"
            try:
                is_touchpad = bool(
                    self._backend.get_property(dbus_path, INPUT_DEVICE_IFACE, "touchpad")
                )
                if not is_touchpad:
                    continue
                name = str(
                    self._backend.get_property(dbus_path, INPUT_DEVICE_IFACE, "name")
                    or sys_name
                )
                raw_factor = self._backend.get_property(
                    dbus_path, INPUT_DEVICE_IFACE, "scrollFactor"
                )
                scroll_factor = clamp_scroll_factor(float(raw_factor))
                found.append(
                    TouchpadDevice(
                        sys_name=sys_name,
                        dbus_path=dbus_path,
                        name=name,
                        scroll_factor=scroll_factor,
                    )
                )
            except Exception as exc:
                LOGGER.debug("Skipping input device %s: %s", dbus_path, exc)

        self._touchpads = found
        return list(found)

    def get_touchpads(self) -> list[TouchpadDevice]:
        """Return cached touchpads, discovering them first if none are cached."""
        if not self._touchpads:
            return self.discover_touchpads()
        return list(self._touchpads)

    def set_scroll_factor(self, factor: float, force: bool = False) -> bool:
        """Apply scrollFactor to all discovered touchpads."""
        target = clamp_scroll_factor(factor)
        if not force and self._last_applied == target:
            return True

        if not self._touchpads:
            self.discover_touchpads()

        if not self._touchpads:
            LOGGER.warning("No KWin touchpad devices found to set scrollFactor=%s", target)
            return False

        success = self._apply_to_cached(target)
        if not success:
            # Refresh once in case a device path went stale (e.g. suspend/resume).
            self.discover_touchpads()
            if self._touchpads:
                success = self._apply_to_cached(target)

        if success:
            self._last_applied = target
        return success

    def _apply_to_cached(self, target: float) -> bool:
        all_ok = True
        for device in self._touchpads:
            try:
                self._backend.set_double_property(
                    device.dbus_path, INPUT_DEVICE_IFACE, "scrollFactor", target
                )
                device.scroll_factor = target
            except Exception as exc:
                LOGGER.warning(
                    "Failed setting scrollFactor=%s on %s: %s",
                    target,
                    device.dbus_path,
                    exc,
                )
                all_ok = False
        return all_ok

    def invalidate_cache(self) -> None:
        """Clear cached devices and last applied factor."""
        self._touchpads = []
        self._last_applied = None
