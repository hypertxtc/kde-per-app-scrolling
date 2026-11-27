"""Native KDE Plasma 6 (PyQt6 + Kirigami QML) GUI for Per-App Touchpad Scrolling."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .config import (
    AppConfig,
    AppRule,
    clamp_scroll_factor,
    load_config,
    make_rule_key,
    normalize_app_id,
    save_config,
)
from .daemon import DAEMON_IFACE, DAEMON_PATH, DAEMON_SERVICE
from .desktop_apps import DesktopApp, scan_installed_apps

LOGGER = logging.getLogger(__name__)

APP_ID = "io.github.kdeperappscrolling.Gui"
SAVE_DEBOUNCE_MS = 120
QML_MAIN_PATH = Path(__file__).resolve().parent / "qml" / "Main.qml"


def daemon_executable() -> str | None:
    """Locate the daemon executable alongside the GUI or in PATH / ~/.local/bin."""
    candidates = [
        str(Path(sys.argv[0]).resolve().parent / "kde-per-app-scrolling-daemon"),
        shutil.which("kde-per-app-scrolling-daemon") or "",
        str(Path.home() / ".local/bin/kde-per-app-scrolling-daemon"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def serialize_rules(config: AppConfig) -> list[dict[str, Any]]:
    """Return sorted QML-friendly list of configured application rules."""
    rules = sorted(
        config.apps.values(),
        key=lambda r: ((r.label or r.app_id).lower(), r.caption_pattern.lower()),
    )
    return [
        {
            "rule_key": make_rule_key(rule.app_id, rule.caption_pattern),
            "app_id": rule.app_id,
            "label": rule.label.strip(),
            "caption_pattern": rule.caption_pattern.strip(),
            "scroll_factor": clamp_scroll_factor(rule.scroll_factor),
            "enabled": bool(rule.enabled),
        }
        for rule in rules
    ]


def build_candidate_list(
    recent_apps: list[dict[str, str]],
    installed_apps: list[DesktopApp],
    existing_ids: set[str],
) -> list[dict[str, Any]]:
    """Merge recent windows and installed desktop apps into a deduplicated picker model."""
    existing_lower = {item.lower() for item in existing_ids}
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []

    for item in recent_apps:
        app_id = str(item.get("app_id") or "").strip()
        if not app_id or app_id.lower() in seen:
            continue
        seen.add(app_id.lower())
        caption = str(item.get("caption") or "").strip()
        subtitle = f"Recent • {app_id} — {caption[:40]}" if caption else f"Recent window • {app_id}"
        candidates.append(
            {
                "app_id": app_id,
                "label": app_id,
                "subtitle": subtitle,
                "icon_name": "window-new",
                "configured": app_id.lower() in existing_lower,
            }
        )

    for app in installed_apps:
        key = app.app_id.lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "app_id": app.app_id,
                "label": app.name,
                "subtitle": app.app_id,
                "icon_name": app.icon_name or "application-x-executable",
                "configured": key in existing_lower,
            }
        )

    return candidates


def filter_candidates(
    candidates: list[dict[str, Any]], query: str
) -> list[dict[str, Any]]:
    """Filter candidate dicts by case-insensitive substring match."""
    needle = (query or "").strip().lower()
    if not needle:
        return list(candidates)
    return [
        item
        for item in candidates
        if needle in str(item.get("app_id", "")).lower()
        or needle in str(item.get("label", "")).lower()
        or needle in str(item.get("subtitle", "")).lower()
    ]


def format_status_summary(
    state: dict[str, Any] | None, configured_ids: set[str]
) -> dict[str, Any]:
    """Compute UI-friendly status fields from a daemon state snapshot."""
    if state is None:
        return {
            "daemon_running": False,
            "daemon_status_text": "Not running — start daemon to apply rules automatically",
            "touchpad_summary": "Unavailable while daemon is stopped",
            "active_window_text": "Unavailable while daemon is stopped",
            "can_quick_add_active": False,
            "active_primary_id": "",
        }

    enabled = bool(state.get("enabled", True))
    factor = float(state.get("current_factor", 1.0))
    daemon_status_text = f"Running ({'Active' if enabled else 'Paused'} • {factor:.2f}x)"

    touchpads = state.get("touchpads", [])
    if touchpads:
        touchpad_summary = ", ".join(
            f"{tp.get('name', tp.get('sys_name', 'Touchpad'))} ({float(tp.get('scroll_factor', factor)):.2f}x)"
            for tp in touchpads
        )
    else:
        touchpad_summary = "Warning: No KWin touchpad device detected"

    active = state.get("active_window", {})
    primary_id = str(active.get("primary_id") or "").strip()
    matched_id = state.get("matched_rule_id")
    if primary_id:
        rule_text = f"Matched rule: {matched_id}" if matched_id else "Using default speed"
        active_window_text = f"{primary_id} • {factor:.2f}x ({rule_text})"
        can_quick_add = primary_id.lower() not in {c.lower() for c in configured_ids}
    else:
        active_window_text = "Waiting for a window focus change..."
        can_quick_add = False

    return {
        "daemon_running": True,
        "daemon_status_text": daemon_status_text,
        "touchpad_summary": touchpad_summary,
        "active_window_text": active_window_text,
        "can_quick_add_active": can_quick_add,
        "active_primary_id": primary_id,
    }


def _notify_missing_pyqt6(error: ImportError) -> None:
    msg = (
        "PyQt6 is required for the native KDE GUI.\n"
        "Install it with: sudo dnf install python3-pyqt6"
    )
    print(f"Error: {msg}\n({error})", file=sys.stderr)
    kdialog = shutil.which("kdialog")
    if kdialog:
        try:
            subprocess.run(
                [kdialog, "--title", "Per-App Touchpad Scrolling", "--error", msg],
                check=False,
            )
        except OSError:
            pass


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
        from PyQt6.QtDBus import QDBusConnection, QDBusInterface, QDBusMessage
        from PyQt6.QtGui import QGuiApplication, QIcon
        from PyQt6.QtQml import QQmlApplicationEngine
        from PyQt6.QtWidgets import QApplication
    except ImportError as exc:
        _notify_missing_pyqt6(exc)
        return 1

    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "org.kde.desktop")

    class AppBridge(QObject):
        """QML context bridge backed by AppConfig and QtDBus daemon calls."""

        configChanged = pyqtSignal()
        statusChanged = pyqtSignal()
        candidatesChanged = pyqtSignal()
        previewChanged = pyqtSignal()

        def __init__(self, parent: QObject | None = None) -> None:
            super().__init__(parent)
            self._config: AppConfig = load_config()
            self._last_state: dict[str, Any] | None = None
            self._all_candidates: list[dict[str, Any]] = []
            self._filtered_candidates: list[dict[str, Any]] = []
            self._candidate_filter = ""
            self._preview_factor: float = clamp_scroll_factor(
                self._config.default_scroll_factor
            )
            self._preview_active = False

            self._save_timer = QTimer(self)
            self._save_timer.setSingleShot(True)
            self._save_timer.setInterval(SAVE_DEBOUNCE_MS)
            self._save_timer.timeout.connect(self._flush_save_and_reload)

            self._bus = QDBusConnection.sessionBus()
            self._bus.connect(
                DAEMON_SERVICE,
                DAEMON_PATH,
                DAEMON_IFACE,
                "StateChanged",
                self._on_dbus_state_changed,
            )
            self.refreshStatus()

        def _daemon_interface(self) -> QDBusInterface:
            return QDBusInterface(
                DAEMON_SERVICE,
                DAEMON_PATH,
                DAEMON_IFACE,
                self._bus,
            )

        def _call_daemon_state(self, method: str) -> dict[str, Any] | None:
            iface = self._daemon_interface()
            if not iface.isValid():
                return None
            reply = iface.call(method)
            if reply.type() == QDBusMessage.MessageType.ErrorMessage:
                return None
            args = reply.arguments()
            if not args:
                return None
            try:
                return json.loads(str(args[0]))
            except ValueError:
                return None

        def _reload_daemon(self) -> None:
            iface = self._daemon_interface()
            if iface.isValid():
                iface.call("ReloadConfig")

        @pyqtSlot(str)
        def _on_dbus_state_changed(self, state_json: str) -> None:
            try:
                state = json.loads(state_json)
            except ValueError:
                return
            self._apply_state(state)

        def _apply_state(self, state: dict[str, Any] | None) -> None:
            self._last_state = state
            if state is not None:
                daemon_enabled = bool(state.get("enabled", True))
                if daemon_enabled != self._config.enabled:
                    self._config.enabled = daemon_enabled
                    self.configChanged.emit()
                if not self._preview_active:
                    self._preview_factor = clamp_scroll_factor(
                        state.get("current_factor", self._config.default_scroll_factor)
                    )
                    self.previewChanged.emit()
            self.statusChanged.emit()

        def _status_dict(self) -> dict[str, Any]:
            configured_app_ids = {rule.app_id for rule in self._config.apps.values()}
            return format_status_summary(self._last_state, configured_app_ids)

        def _schedule_save(self) -> None:
            self._save_timer.start()

        def _flush_save_and_reload(self) -> None:
            save_config(self._config)
            self._reload_daemon()

        def _save_now(self) -> None:
            if self._save_timer.isActive():
                self._save_timer.stop()
            self._flush_save_and_reload()

        # --- QML Properties ---

        @pyqtProperty(bool, notify=configChanged)
        def enabled(self) -> bool:
            return bool(self._config.enabled)

        @pyqtProperty(float, notify=configChanged)
        def defaultScrollFactor(self) -> float:
            return clamp_scroll_factor(self._config.default_scroll_factor)

        @pyqtProperty(bool, notify=configChanged)
        def showTray(self) -> bool:
            return bool(self._config.show_tray)

        @pyqtProperty("QVariantList", notify=configChanged)
        def rules(self) -> list[dict[str, Any]]:
            return serialize_rules(self._config)

        @pyqtProperty(bool, notify=statusChanged)
        def daemonRunning(self) -> bool:
            return bool(self._status_dict()["daemon_running"])

        @pyqtProperty(str, notify=statusChanged)
        def daemonStatusText(self) -> str:
            return str(self._status_dict()["daemon_status_text"])

        @pyqtProperty(str, notify=statusChanged)
        def touchpadSummary(self) -> str:
            return str(self._status_dict()["touchpad_summary"])

        @pyqtProperty(str, notify=statusChanged)
        def activeWindowText(self) -> str:
            return str(self._status_dict()["active_window_text"])

        @pyqtProperty(bool, notify=statusChanged)
        def canQuickAddActive(self) -> bool:
            return bool(self._status_dict()["can_quick_add_active"])

        @pyqtProperty("QVariantList", notify=candidatesChanged)
        def filteredCandidates(self) -> list[dict[str, Any]]:
            return self._filtered_candidates

        @pyqtProperty(float, notify=previewChanged)
        def previewFactor(self) -> float:
            return self._preview_factor

        @pyqtProperty(bool, notify=previewChanged)
        def previewActive(self) -> bool:
            return self._preview_active

        # --- QML Slots ---

        @pyqtSlot()
        def refreshStatus(self) -> None:
            state = self._call_daemon_state("RefreshTouchpads")
            if state is None:
                state = self._call_daemon_state("GetState")
            self._apply_state(state)

        @pyqtSlot()
        def startDaemon(self) -> None:
            exe = daemon_executable()
            if exe is None:
                LOGGER.warning("Could not locate kde-per-app-scrolling-daemon")
                return
            try:
                subprocess.Popen(
                    [exe],
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                QTimer.singleShot(600, self.refreshStatus)
            except OSError as exc:
                LOGGER.warning("Failed to start daemon: %s", exc)

        @pyqtSlot(bool)
        def setEnabled(self, value: bool) -> None:
            self._config.enabled = bool(value)
            self.configChanged.emit()
            self._save_now()

        @pyqtSlot(float)
        def setDefaultScrollFactor(self, value: float) -> None:
            self._config.default_scroll_factor = clamp_scroll_factor(value)
            self.configChanged.emit()
            self._schedule_save()

        @pyqtSlot(bool)
        def setShowTray(self, value: bool) -> None:
            self._config.show_tray = bool(value)
            self.configChanged.emit()
            self._save_now()

        @pyqtSlot(float)
        def previewScrollFactor(self, factor: float) -> None:
            clamped = clamp_scroll_factor(factor)
            self._preview_factor = clamped
            self._preview_active = True
            self.previewChanged.emit()
            iface = self._daemon_interface()
            if iface.isValid():
                iface.call("ApplyFactorNow", float(clamped))

        @pyqtSlot()
        def endPreview(self) -> None:
            if not self._preview_active:
                return
            self._preview_active = False
            self._reload_daemon()
            state = self._call_daemon_state("GetState")
            self._apply_state(state)

        @pyqtSlot(str, bool)
        def setRuleEnabled(self, rule_key: str, value: bool) -> None:
            rule = self._config.apps.get(rule_key)
            if rule is None:
                return
            rule.enabled = bool(value)
            self.configChanged.emit()
            self._save_now()

        @pyqtSlot(str, float)
        def setRuleScrollFactor(self, rule_key: str, value: float) -> None:
            rule = self._config.apps.get(rule_key)
            if rule is None:
                return
            clamped = clamp_scroll_factor(value)
            rule.scroll_factor = clamped
            self.configChanged.emit()
            self._schedule_save()
            self.previewScrollFactor(clamped)

        @pyqtSlot(str)
        def removeRule(self, rule_key: str) -> None:
            if rule_key in self._config.apps:
                self._config.apps.pop(rule_key, None)
                self.configChanged.emit()
                self.statusChanged.emit()
                self._save_now()

        @pyqtSlot(str, str, str, float)
        def addRule(
            self, app_id: str, label: str, caption_pattern: str, factor: float
        ) -> None:
            cleaned_id = normalize_app_id(app_id)
            if not cleaned_id:
                return
            cleaned_caption = (caption_pattern or "").strip()
            rule_key = make_rule_key(cleaned_id, cleaned_caption)
            self._config.apps[rule_key] = AppRule(
                app_id=cleaned_id,
                scroll_factor=clamp_scroll_factor(factor),
                label=label.strip(),
                enabled=True,
                caption_pattern=cleaned_caption,
            )
            self.configChanged.emit()
            self.statusChanged.emit()
            self._save_now()

        @pyqtSlot()
        def quickAddActive(self) -> None:
            primary_id = str(self._status_dict()["active_primary_id"]).strip()
            if primary_id:
                self.addRule(primary_id, "", "", self._config.default_scroll_factor)

        @pyqtSlot()
        def prepareAddDialog(self) -> None:
            recent = (
                list(self._last_state.get("recent_apps", []))
                if self._last_state is not None
                else []
            )
            installed = scan_installed_apps()
            configured_app_ids = {rule.app_id for rule in self._config.apps.values()}
            self._all_candidates = build_candidate_list(
                recent, installed, configured_app_ids
            )
            self._candidate_filter = ""
            self._filtered_candidates = list(self._all_candidates)
            self.candidatesChanged.emit()

        @pyqtSlot(str)
        def setCandidateFilter(self, query: str) -> None:
            self._candidate_filter = query
            self._filtered_candidates = filter_candidates(
                self._all_candidates, query
            )
            self.candidatesChanged.emit()

    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("Per-App Touchpad Scrolling")
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon.fromTheme("input-touchpad"))
    QGuiApplication.setApplicationDisplayName("Per-App Touchpad Scrolling")

    engine = QQmlApplicationEngine()
    bridge = AppBridge(engine)
    app.aboutToQuit.connect(bridge.endPreview)
    engine.rootContext().setContextProperty("backend", bridge)
    engine.load(QUrl.fromLocalFile(str(QML_MAIN_PATH)))

    if not engine.rootObjects():
        print(f"Error: Failed to load QML interface from {QML_MAIN_PATH}", file=sys.stderr)
        return 1

    return int(app.exec())


if __name__ == "__main__":
    raise SystemExit(main())
