"""Background daemon managing per-app touchpad scroll factors."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from .config import (
    AppConfig,
    AppRule,
    clamp_scroll_factor,
    get_config_path,
    load_config,
    make_rule_key,
    normalize_app_id,
    resolve_scroll_factor,
    save_config,
)
from .touchpad import TouchpadController

LOGGER = logging.getLogger(__name__)

DAEMON_SERVICE = "io.github.kdeperappscrolling.Daemon"
DAEMON_PATH = "/io/github/kdeperappscrolling/Daemon"
DAEMON_IFACE = "io.github.kdeperappscrolling.Daemon"

MAX_RECENT_APPS = 30
SELF_IDENTIFIERS = frozenset(
    {
        "io.github.kdeperappscrolling.gui",
        "io.github.kdeperappscrolling",
        "kde-per-app-scrolling",
    }
)


def _is_self_window(
    resource_class: str, resource_name: str, desktop_file_name: str
) -> bool:
    for raw in (desktop_file_name, resource_class, resource_name):
        norm = normalize_app_id(raw).lower()
        if norm in SELF_IDENTIFIERS:
            return True
    return False


class DaemonCore:
    """Testable core state machine for per-app touchpad scrolling."""

    def __init__(
        self,
        touchpad_controller: TouchpadController,
        config_path: Path | None = None,
        config: AppConfig | None = None,
    ) -> None:
        self._touchpads = touchpad_controller
        self._config_path = config_path
        resolved_path = config_path or get_config_path()
        self._config_existed = True if config is not None else resolved_path.exists()
        self._config = config if config is not None else load_config(config_path)

        self._active_window: dict[str, str] = {
            "resource_class": "",
            "resource_name": "",
            "desktop_file_name": "",
            "caption": "",
            "primary_id": "",
        }
        self._recent_apps: list[dict[str, str]] = []
        self._matched_rule_id: str | None = None
        self._current_factor: float = clamp_scroll_factor(
            self._config.default_scroll_factor
        )

    @property
    def config(self) -> AppConfig:
        return self._config

    def initialize(self) -> dict[str, Any]:
        """Discover touchpads, seed default speed on first run, and apply factor."""
        touchpads = self._touchpads.discover_touchpads()
        if not self._config_existed and touchpads:
            self._config.default_scroll_factor = clamp_scroll_factor(
                touchpads[0].scroll_factor
            )
            save_config(self._config, self._config_path)
            self._config_existed = True
        self._apply_for_current_window(force=True)
        return self.get_state()

    def _record_recent_app(
        self,
        resource_class: str,
        resource_name: str,
        desktop_file_name: str,
        caption: str,
    ) -> str:
        primary_id = (
            normalize_app_id(desktop_file_name)
            or normalize_app_id(resource_class)
            or normalize_app_id(resource_name)
        )
        if not primary_id:
            return ""

        key = primary_id.lower()
        self._recent_apps = [
            entry
            for entry in self._recent_apps
            if entry.get("app_id", "").lower() != key
        ]
        self._recent_apps.insert(
            0,
            {
                "app_id": primary_id,
                "resource_class": resource_class,
                "resource_name": resource_name,
                "desktop_file_name": desktop_file_name,
                "caption": caption,
            },
        )
        del self._recent_apps[MAX_RECENT_APPS:]
        return primary_id

    def _apply_for_current_window(self, force: bool = False) -> None:
        factor, rule = resolve_scroll_factor(
            self._config,
            self._active_window["resource_class"],
            self._active_window["resource_name"],
            self._active_window["desktop_file_name"],
            self._active_window["caption"],
        )
        self._matched_rule_id = (
            make_rule_key(rule.app_id, rule.caption_pattern)
            if rule is not None
            else None
        )
        self._current_factor = factor
        self._touchpads.set_scroll_factor(factor, force=force)

    def handle_active_window(
        self,
        resource_class: str,
        resource_name: str = "",
        desktop_file_name: str = "",
        caption: str = "",
    ) -> dict[str, Any]:
        """Process an active-window notification from KWin."""
        if _is_self_window(resource_class, resource_name, desktop_file_name):
            return self.get_state()

        primary_id = self._record_recent_app(
            resource_class, resource_name, desktop_file_name, caption
        )
        self._active_window = {
            "resource_class": resource_class,
            "resource_name": resource_name,
            "desktop_file_name": desktop_file_name,
            "caption": caption,
            "primary_id": primary_id,
        }
        self._apply_for_current_window(force=False)
        return self.get_state()

    def reload_config(self) -> dict[str, Any]:
        """Reload configuration from disk and force-apply to touchpads."""
        self._config = load_config(self._config_path)
        self._apply_for_current_window(force=True)
        return self.get_state()

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        """Toggle global enabled flag, persist config, and re-apply."""
        self._config.enabled = bool(enabled)
        save_config(self._config, self._config_path)
        self._apply_for_current_window(force=True)
        return self.get_state()

    def apply_factor_now(self, factor: float) -> float:
        """Directly apply a scroll factor (e.g. during live slider preview)."""
        target = clamp_scroll_factor(factor)
        self._current_factor = target
        self._touchpads.set_scroll_factor(target, force=True)
        return target

    def refresh_touchpads(self) -> dict[str, Any]:
        """Re-discover touchpads and re-apply the current scroll factor."""
        self._touchpads.invalidate_cache()
        self._touchpads.discover_touchpads()
        self._apply_for_current_window(force=True)
        return self.get_state()

    def sync_default_from_touchpad(self) -> dict[str, Any]:
        """Read current touchpad scrollFactor and store it as default_scroll_factor."""
        self._touchpads.invalidate_cache()
        touchpads = self._touchpads.discover_touchpads()
        if touchpads:
            self._config.default_scroll_factor = clamp_scroll_factor(
                touchpads[0].scroll_factor
            )
            save_config(self._config, self._config_path)
            self._config_existed = True
        self._apply_for_current_window(force=True)
        return self.get_state()

    def restore_default(self) -> None:
        """Restore touchpad scrollFactor back to default_scroll_factor on exit."""
        default_factor = clamp_scroll_factor(self._config.default_scroll_factor)
        self._current_factor = default_factor
        self._touchpads.set_scroll_factor(default_factor, force=True)

    def quick_add_active(self) -> dict[str, Any]:
        """Add a rule for the currently focused application if not already configured."""
        primary_id = str(self._active_window.get("primary_id") or "").strip()
        if primary_id and not self._is_app_configured(primary_id):
            key = make_rule_key(primary_id)
            self._config.apps[key] = AppRule(
                app_id=primary_id,
                scroll_factor=clamp_scroll_factor(self._config.default_scroll_factor),
                label="",
                enabled=True,
            )
            save_config(self._config, self._config_path)
            self._config_existed = True
            self._apply_for_current_window(force=True)
        return self.get_state()

    def _is_app_configured(self, primary_id: str) -> bool:
        target = normalize_app_id(primary_id).lower()
        return any(
            normalize_app_id(rule.app_id).lower() == target
            for rule in self._config.apps.values()
        )

    def get_state(self) -> dict[str, Any]:
        """Return a JSON-serializable state snapshot."""
        primary_id = str(self._active_window.get("primary_id") or "").strip()
        return {
            "enabled": bool(self._config.enabled),
            "default_scroll_factor": clamp_scroll_factor(
                self._config.default_scroll_factor
            ),
            "show_tray": bool(self._config.show_tray),
            "active_window": dict(self._active_window),
            "active_window_configured": (
                self._is_app_configured(primary_id) if primary_id else False
            ),
            "current_factor": self._current_factor,
            "matched_rule_id": self._matched_rule_id,
            "touchpads": [tp.to_dict() for tp in self._touchpads.get_touchpads()],
            "recent_apps": list(self._recent_apps),
        }


def _launch_gui() -> None:
    """Open the Per-App Touchpad Scrolling page in KDE System Settings."""
    for cmd in ("systemsettings", "kcmshell6"):
        exe = shutil.which(cmd)
        if exe:
            try:
                subprocess.Popen(
                    [exe, "kcm_per_app_scrolling"],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except OSError as exc:
                LOGGER.warning("Failed to launch %s kcm_per_app_scrolling: %s", cmd, exc)
    LOGGER.warning("Could not locate systemsettings or kcmshell6 to open settings")


def _build_dbus_service(
    bus: Any,
    core: DaemonCore,
    on_state_updated: Callable[[dict[str, Any]], None],
) -> Any:
    import dbus
    import dbus.service

    class DaemonDBusService(dbus.service.Object):
        """D-Bus service exposing DaemonCore methods and StateChanged signal."""

        def __init__(self) -> None:
            super().__init__(bus, DAEMON_PATH)

        def emit_state(self, state: dict[str, Any]) -> None:
            on_state_updated(state)
            self.StateChanged(json.dumps(state))

        @dbus.service.method(DAEMON_IFACE, in_signature="ssss", out_signature="")
        def NotifyActiveWindow(
            self,
            resource_class: str,
            resource_name: str,
            desktop_file_name: str,
            caption: str,
        ) -> None:
            state = core.handle_active_window(
                str(resource_class),
                str(resource_name),
                str(desktop_file_name),
                str(caption),
            )
            self.emit_state(state)

        @dbus.service.method(DAEMON_IFACE, in_signature="", out_signature="")
        def ReloadConfig(self) -> None:
            state = core.reload_config()
            self.emit_state(state)

        @dbus.service.method(DAEMON_IFACE, in_signature="b", out_signature="")
        def SetEnabled(self, enabled: bool) -> None:
            state = core.set_enabled(bool(enabled))
            self.emit_state(state)

        @dbus.service.method(DAEMON_IFACE, in_signature="d", out_signature="d")
        def ApplyFactorNow(self, factor: float) -> float:
            applied = core.apply_factor_now(float(factor))
            self.emit_state(core.get_state())
            return applied

        @dbus.service.method(DAEMON_IFACE, in_signature="", out_signature="s")
        def GetState(self) -> str:
            return json.dumps(core.get_state())

        @dbus.service.method(DAEMON_IFACE, in_signature="", out_signature="s")
        def RefreshTouchpads(self) -> str:
            state = core.refresh_touchpads()
            self.emit_state(state)
            return json.dumps(state)

        @dbus.service.method(DAEMON_IFACE, in_signature="", out_signature="s")
        def SyncDefaultFromTouchpad(self) -> str:
            state = core.sync_default_from_touchpad()
            self.emit_state(state)
            return json.dumps(state)

        @dbus.service.method(DAEMON_IFACE, in_signature="", out_signature="s")
        def Ping(self) -> str:
            return "pong"

        @dbus.service.signal(DAEMON_IFACE, signature="s")
        def StateChanged(self, _state_json: str) -> None:
            pass

    return DaemonDBusService()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="kde-per-app-scrolling-daemon",
        description="Background daemon for KDE Per-App Touchpad Scrolling",
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="Disable the KDE system tray StatusNotifierItem",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    import dbus
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib

    from .touchpad import KWIN_SERVICE, INPUT_DEVICE_MANAGER_IFACE, INPUT_DEVICE_MANAGER_PATH
    from .tray import StatusNotifierItem

    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    _bus_name = dbus.service.BusName(DAEMON_SERVICE, bus=bus)

    controller = TouchpadController()
    core = DaemonCore(touchpad_controller=controller)
    initial_state = core.initialize()

    tray_item: StatusNotifierItem | None = None
    service_holder: dict[str, Any] = {}

    def sync_tray(state: dict[str, Any]) -> None:
        nonlocal tray_item
        wants_tray = (not args.no_tray) and bool(state.get("show_tray", True))
        if wants_tray and tray_item is None:
            tray_item = StatusNotifierItem(
                bus=bus,
                on_activate=_launch_gui,
                on_toggle=_toggle_from_tray,
                on_quick_add=_quick_add_from_tray,
                on_restore_default=_restore_from_tray,
                initial_state=state,
            )
        elif not wants_tray and tray_item is not None:
            tray_item.unregister()
            tray_item = None

        if tray_item is not None:
            tray_item.update_state(state)

    def _toggle_from_tray() -> None:
        state = core.set_enabled(not core.config.enabled)
        service_holder["service"].emit_state(state)

    def _quick_add_from_tray() -> None:
        state = core.quick_add_active()
        service_holder["service"].emit_state(state)

    def _restore_from_tray() -> None:
        core.restore_default()
        service_holder["service"].emit_state(core.get_state())

    dbus_service = _build_dbus_service(bus, core, sync_tray)
    service_holder["service"] = dbus_service
    sync_tray(initial_state)

    def _on_kwin_device_change(*_args: Any) -> None:
        LOGGER.debug("KWin input device topology changed; refreshing touchpads")
        state = core.refresh_touchpads()
        dbus_service.emit_state(state)

    for sig_name in ("deviceAdded", "deviceRemoved"):
        try:
            bus.add_signal_receiver(
                _on_kwin_device_change,
                signal_name=sig_name,
                dbus_interface=INPUT_DEVICE_MANAGER_IFACE,
                bus_name=KWIN_SERVICE,
                path=INPUT_DEVICE_MANAGER_PATH,
            )
        except Exception as exc:
            LOGGER.debug("Could not attach %s signal: %s", sig_name, exc)

    loop = GLib.MainLoop()

    def _on_shutdown_signal() -> bool:
        LOGGER.info("Received shutdown signal; restoring default scroll factor")
        loop.quit()
        return False

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            GLib.unix_signal_add(GLib.PRIORITY_HIGH, sig, _on_shutdown_signal)
        except AttributeError:
            pass

    LOGGER.info("Daemon started on %s", DAEMON_SERVICE)
    try:
        loop.run()
    except KeyboardInterrupt:
        LOGGER.info("Daemon stopping")
    finally:
        core.restore_default()
        if tray_item is not None:
            tray_item.unregister()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
