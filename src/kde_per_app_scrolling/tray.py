"""Native KDE StatusNotifierItem tray integration and DBusMenu over D-Bus."""

from __future__ import annotations

import logging
from typing import Any, Callable

import dbus
import dbus.service

LOGGER = logging.getLogger(__name__)

SNI_IFACE = "org.kde.StatusNotifierItem"
SNI_PATH = "/StatusNotifierItem"
MENU_PATH = "/MenuBar"
DBUSMENU_IFACE = "com.canonical.dbusmenu"
SNW_SERVICE = "org.kde.StatusNotifierWatcher"
SNW_PATH = "/StatusNotifierWatcher"
SNW_IFACE = "org.kde.StatusNotifierWatcher"
DBUS_PROPS_IFACE = "org.freedesktop.DBus.Properties"

MENU_ID_ROOT = 0
MENU_ID_STATUS = 1
MENU_ID_SEP = 2
MENU_ID_OPEN = 3
MENU_ID_TOGGLE = 4
MENU_ID_QUICK_ADD = 5
MENU_ID_RESTORE = 6


def build_menu_items(state: dict[str, Any]) -> list[tuple[int, dict[str, Any]]]:
    """Build ordered DBusMenu item definitions from a daemon state snapshot."""
    enabled = bool(state.get("enabled", True))
    factor = float(state.get("current_factor", 1.0))
    active = state.get("active_window", {}) or {}
    primary_id = str(active.get("primary_id") or "").strip()
    active_configured = bool(state.get("active_window_configured", False))
    app_name = primary_id or "Default"

    status_label = (
        f"{app_name} — {factor:.2f}x"
        if enabled
        else f"Paused — {factor:.2f}x"
    )
    can_quick_add = bool(primary_id) and not active_configured

    return [
        (
            MENU_ID_STATUS,
            {
                "label": status_label,
                "enabled": False,
                "visible": True,
            },
        ),
        (
            MENU_ID_SEP,
            {
                "type": "separator",
                "visible": True,
            },
        ),
        (
            MENU_ID_OPEN,
            {
                "label": "Open Settings",
                "icon-name": "configure",
                "enabled": True,
                "visible": True,
            },
        ),
        (
            MENU_ID_TOGGLE,
            {
                "label": (
                    "Pause Per-App Scrolling"
                    if enabled
                    else "Resume Per-App Scrolling"
                ),
                "icon-name": (
                    "media-playback-pause" if enabled else "media-playback-start"
                ),
                "enabled": True,
                "visible": True,
            },
        ),
        (
            MENU_ID_QUICK_ADD,
            {
                "label": (
                    f"Quick-Add {primary_id}" if primary_id else "Quick-Add Active App"
                ),
                "icon-name": "list-add",
                "enabled": can_quick_add,
                "visible": can_quick_add,
            },
        ),
        (
            MENU_ID_RESTORE,
            {
                "label": "Restore Default Speed",
                "icon-name": "edit-undo",
                "enabled": True,
                "visible": True,
            },
        ),
    ]


def _to_dbus_props(
    props: dict[str, Any], property_names: list[str] | None = None
) -> dbus.Dictionary:
    wanted = set(property_names) if property_names else None
    result: dict[str, Any] = {}
    for key, val in props.items():
        if wanted is not None and key not in wanted:
            continue
        if isinstance(val, bool):
            result[key] = dbus.Boolean(val)
        else:
            result[key] = dbus.String(str(val))
    return dbus.Dictionary(result, signature="sv")


class TrayMenu(dbus.service.Object):
    """Implements com.canonical.dbusmenu for Plasma's tray right-click menu."""

    def __init__(
        self,
        bus: dbus.SessionBus,
        initial_state: dict[str, Any],
        on_activate: Callable[[], None],
        on_toggle: Callable[[], None],
        on_quick_add: Callable[[], None] | None = None,
        on_restore_default: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(bus, MENU_PATH)
        self._on_activate = on_activate
        self._on_toggle = on_toggle
        self._on_quick_add = on_quick_add
        self._on_restore_default = on_restore_default
        self._revision = 1
        self._items: list[tuple[int, dict[str, Any]]] = build_menu_items(initial_state)

    def update_state(self, state: dict[str, Any]) -> None:
        new_items = build_menu_items(state)
        if new_items != self._items:
            self._items = new_items
            self._revision += 1
            self.LayoutUpdated(dbus.UInt32(self._revision), dbus.Int32(MENU_ID_ROOT))

    def _find_props(self, item_id: int) -> dict[str, Any]:
        if item_id == MENU_ID_ROOT:
            return {"children-display": "submenu"}
        for candidate_id, props in self._items:
            if candidate_id == item_id:
                return props
        return {}

    def _build_layout_node(
        self,
        item_id: int,
        recursion_depth: int,
        property_names: list[str],
    ) -> dbus.Struct:
        props = _to_dbus_props(self._find_props(item_id), property_names)
        children: list[dbus.Struct] = []
        if item_id == MENU_ID_ROOT and recursion_depth != 0:
            next_depth = -1 if recursion_depth < 0 else recursion_depth - 1
            for child_id, _child_props in self._items:
                children.append(
                    self._build_layout_node(child_id, next_depth, property_names)
                )
        return dbus.Struct(
            (dbus.Int32(item_id), props, dbus.Array(children, signature="v")),
            signature="ia{sv}av",
        )

    def _handle_click(self, item_id: int) -> None:
        if item_id == MENU_ID_OPEN:
            self._on_activate()
        elif item_id == MENU_ID_TOGGLE:
            self._on_toggle()
        elif item_id == MENU_ID_QUICK_ADD and self._on_quick_add is not None:
            self._on_quick_add()
        elif item_id == MENU_ID_RESTORE and self._on_restore_default is not None:
            self._on_restore_default()

    @dbus.service.method(DBUS_PROPS_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface_name: str, property_name: str) -> Any:
        props = self.GetAll(interface_name)
        if property_name not in props:
            raise dbus.exceptions.DBusException(
                f"Unknown property {property_name}",
                name="org.freedesktop.DBus.Error.InvalidArgs",
            )
        return props[property_name]

    @dbus.service.method(DBUS_PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface_name: str) -> dict[str, Any]:
        if interface_name != DBUSMENU_IFACE:
            return {}
        return {
            "Version": dbus.UInt32(3),
            "TextDirection": "ltr",
            "Status": "normal",
            "IconThemePath": dbus.Array([], signature="s"),
        }

    @dbus.service.method(DBUS_PROPS_IFACE, in_signature="ssv", out_signature="")
    def Set(self, _interface_name: str, _property_name: str, _value: Any) -> None:
        return None

    @dbus.service.method(
        DBUSMENU_IFACE, in_signature="iias", out_signature="u(ia{sv}av)"
    )
    def GetLayout(
        self, parent_id: int, recursion_depth: int, property_names: list[str]
    ) -> tuple[dbus.UInt32, dbus.Struct]:
        node = self._build_layout_node(
            int(parent_id), int(recursion_depth), [str(p) for p in property_names]
        )
        return dbus.UInt32(self._revision), node

    @dbus.service.method(
        DBUSMENU_IFACE, in_signature="aias", out_signature="a(ia{sv})"
    )
    def GetGroupProperties(
        self, ids: list[int], property_names: list[str]
    ) -> dbus.Array:
        wanted = [str(p) for p in property_names]
        rows = [
            dbus.Struct(
                (dbus.Int32(int(item_id)), _to_dbus_props(self._find_props(int(item_id)), wanted)),
                signature="ia{sv}",
            )
            for item_id in ids
        ]
        return dbus.Array(rows, signature="(ia{sv})")

    @dbus.service.method(DBUSMENU_IFACE, in_signature="is", out_signature="v")
    def GetProperty(self, item_id: int, name: str) -> Any:
        props = _to_dbus_props(self._find_props(int(item_id)), [str(name)])
        return props.get(str(name), dbus.String(""))

    @dbus.service.method(DBUSMENU_IFACE, in_signature="isvu", out_signature="")
    def Event(
        self, item_id: int, event_id: str, _data: Any, _timestamp: int
    ) -> None:
        if str(event_id) == "clicked":
            self._handle_click(int(item_id))

    @dbus.service.method(DBUSMENU_IFACE, in_signature="a(isvu)", out_signature="ai")
    def EventGroup(self, events: list[tuple[int, str, Any, int]]) -> dbus.Array:
        for item_id, event_id, _data, _timestamp in events:
            if str(event_id) == "clicked":
                self._handle_click(int(item_id))
        return dbus.Array([], signature="i")

    @dbus.service.method(DBUSMENU_IFACE, in_signature="i", out_signature="b")
    def AboutToShow(self, _item_id: int) -> bool:
        return False

    @dbus.service.method(DBUSMENU_IFACE, in_signature="ai", out_signature="aiai")
    def AboutToShowGroup(self, _ids: list[int]) -> tuple[dbus.Array, dbus.Array]:
        return dbus.Array([], signature="i"), dbus.Array([], signature="i")

    @dbus.service.signal(DBUSMENU_IFACE, signature="ui")
    def LayoutUpdated(self, _revision: int, _parent: int) -> None:
        pass


class StatusNotifierItem(dbus.service.Object):
    """Implements org.kde.StatusNotifierItem for KDE Plasma's system tray."""

    def __init__(
        self,
        bus: dbus.SessionBus,
        on_activate: Callable[[], None],
        on_toggle: Callable[[], None],
        on_quick_add: Callable[[], None] | None = None,
        on_restore_default: Callable[[], None] | None = None,
        initial_state: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(bus, SNI_PATH)
        self._bus = bus
        self._on_activate = on_activate
        self._on_toggle = on_toggle
        self._registered = False

        self._title = "Per-App Touchpad Scrolling"
        self._subtitle = "Active"
        self._status = "Active"
        self._icon_name = "input-touchpad"

        self._menu = TrayMenu(
            bus=bus,
            initial_state=initial_state or {},
            on_activate=on_activate,
            on_toggle=on_toggle,
            on_quick_add=on_quick_add,
            on_restore_default=on_restore_default,
        )

        self._watcher_match = self._bus.add_signal_receiver(
            self._on_name_owner_changed,
            signal_name="NameOwnerChanged",
            dbus_interface="org.freedesktop.DBus",
            bus_name="org.freedesktop.DBus",
            path="/org/freedesktop/DBus",
            arg0=SNW_SERVICE,
        )
        self.register_with_watcher()

    def _tooltip_struct(self) -> dbus.Struct:
        return dbus.Struct(
            (
                self._icon_name,
                dbus.Array([], signature="(iiay)"),
                self._title,
                self._subtitle,
            ),
            signature="sa(iiay)ss",
        )

    def _all_properties(self) -> dict[str, Any]:
        return {
            "Category": "ApplicationStatus",
            "Id": "kde-per-app-scrolling",
            "Title": self._title,
            "Status": self._status,
            "WindowId": dbus.UInt32(0),
            "IconName": self._icon_name,
            "IconThemePath": "",
            "OverlayIconName": "",
            "AttentionIconName": "",
            "AttentionMovieName": "",
            "ItemIsMenu": False,
            "Menu": dbus.ObjectPath(MENU_PATH),
            "ToolTip": self._tooltip_struct(),
        }

    def register_with_watcher(self) -> bool:
        """Register this StatusNotifierItem with Plasma's StatusNotifierWatcher."""
        try:
            watcher = self._bus.get_object(SNW_SERVICE, SNW_PATH)
            iface = dbus.Interface(watcher, SNW_IFACE)
            iface.RegisterStatusNotifierItem(self._bus.get_unique_name())
            self._registered = True
            LOGGER.debug("Registered StatusNotifierItem with %s", SNW_SERVICE)
            return True
        except dbus.DBusException as exc:
            self._registered = False
            LOGGER.debug("StatusNotifierWatcher not ready: %s", exc)
            return False

    def _on_name_owner_changed(
        self, _name: str, _old_owner: str, new_owner: str
    ) -> None:
        if new_owner:
            self.register_with_watcher()

    def update_tooltip(self, title: str, subtitle: str, active: bool = True) -> None:
        """Update tray tooltip and status, emitting Plasma notification signals."""
        self._title = title
        self._subtitle = subtitle
        new_status = "Active" if active else "Passive"
        if new_status != self._status:
            self._status = new_status
            self.NewStatus(self._status)
        self.NewToolTip()

    def update_state(self, state: dict[str, Any]) -> None:
        """Update both tooltip/status and the right-click DBusMenu from state."""
        enabled = bool(state.get("enabled", True))
        active = state.get("active_window", {}) or {}
        app_name = active.get("primary_id") or "Default"
        factor = float(state.get("current_factor", 1.0))
        subtitle = f"{app_name}: {factor:.2f}x" if enabled else f"Paused ({factor:.2f}x)"
        self.update_tooltip("Per-App Touchpad Scrolling", subtitle, active=enabled)
        self._menu.update_state(state)

    def unregister(self) -> None:
        """Remove D-Bus objects and signal receiver."""
        if self._watcher_match is not None:
            try:
                self._watcher_match.remove()
            except Exception:
                pass
            self._watcher_match = None
        try:
            self._menu.remove_from_connection()
        except Exception:
            pass
        try:
            self.remove_from_connection()
        except Exception:
            pass

    @dbus.service.method(DBUS_PROPS_IFACE, in_signature="ss", out_signature="v")
    def Get(self, interface_name: str, property_name: str) -> Any:
        if interface_name != SNI_IFACE:
            raise dbus.exceptions.DBusException(
                f"Unknown interface {interface_name}",
                name="org.freedesktop.DBus.Error.InvalidArgs",
            )
        props = self._all_properties()
        if property_name not in props:
            raise dbus.exceptions.DBusException(
                f"Unknown property {property_name}",
                name="org.freedesktop.DBus.Error.InvalidArgs",
            )
        return props[property_name]

    @dbus.service.method(DBUS_PROPS_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface_name: str) -> dict[str, Any]:
        if interface_name != SNI_IFACE:
            return {}
        return self._all_properties()

    @dbus.service.method(DBUS_PROPS_IFACE, in_signature="ssv", out_signature="")
    def Set(self, _interface_name: str, _property_name: str, _value: Any) -> None:
        return None

    @dbus.service.method(SNI_IFACE, in_signature="ii", out_signature="")
    def Activate(self, _x: int, _y: int) -> None:
        self._on_activate()

    @dbus.service.method(SNI_IFACE, in_signature="ii", out_signature="")
    def SecondaryActivate(self, _x: int, _y: int) -> None:
        self._on_toggle()

    @dbus.service.method(SNI_IFACE, in_signature="ii", out_signature="")
    def ContextMenu(self, _x: int, _y: int) -> None:
        self._on_activate()

    @dbus.service.method(SNI_IFACE, in_signature="is", out_signature="")
    def Scroll(self, _delta: int, _orientation: str) -> None:
        return None

    @dbus.service.signal(SNI_IFACE, signature="")
    def NewToolTip(self) -> None:
        pass

    @dbus.service.signal(SNI_IFACE, signature="s")
    def NewStatus(self, _status: str) -> None:
        pass

    @dbus.service.signal(SNI_IFACE, signature="")
    def NewIcon(self) -> None:
        pass
