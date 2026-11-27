"""Unit tests for kde_per_app_scrolling.daemon.DaemonCore."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kde_per_app_scrolling.config import (  # noqa: E402
    AppConfig,
    AppRule,
    load_config,
    make_rule_key,
    save_config,
)
from kde_per_app_scrolling.daemon import DaemonCore  # noqa: E402
from kde_per_app_scrolling.touchpad import TouchpadController  # noqa: E402
from test_touchpad import FakeKWinBackend  # noqa: E402


class DaemonCoreTests(unittest.TestCase):
    def test_window_focus_applies_matching_rule_and_ignores_self(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg = AppConfig(
                enabled=True,
                default_scroll_factor=1.0,
                apps={
                    "firefox": AppRule("firefox", 0.45, "Firefox"),
                    "org.kde.konsole": AppRule("org.kde.konsole", 2.0, "Konsole"),
                },
            )
            save_config(cfg, cfg_path)

            backend = FakeKWinBackend()
            ctrl = TouchpadController(backend=backend)
            daemon = DaemonCore(touchpad_controller=ctrl, config_path=cfg_path)
            daemon.initialize()
            self.assertEqual(backend.devices["event7"]["scrollFactor"], 1.0)

            # Focus Firefox
            state = daemon.handle_active_window("firefox", "firefox", "firefox", "Mozilla Firefox")
            self.assertEqual(state["current_factor"], 0.45)
            self.assertEqual(state["matched_rule_id"], "firefox")
            self.assertEqual(backend.devices["event7"]["scrollFactor"], 0.45)

            # Focus our own GUI -> ignored, keeps Firefox active and 0.45x
            state = daemon.handle_active_window(
                "io.github.kdeperappscrolling.Gui",
                "kde-per-app-scrolling",
                "kde-per-app-scrolling",
                "Per-App Touchpad Scrolling",
            )
            self.assertEqual(state["active_window"]["primary_id"], "firefox")
            self.assertEqual(state["current_factor"], 0.45)
            self.assertEqual(backend.devices["event7"]["scrollFactor"], 0.45)

            # Focus unconfigured app -> reverts to default
            state = daemon.handle_active_window("vlc", "vlc", "vlc", "VLC")
            self.assertEqual(state["current_factor"], 1.0)
            self.assertIsNone(state["matched_rule_id"])
            self.assertEqual([a["app_id"] for a in state["recent_apps"]], ["vlc", "firefox"])

    def test_reload_config_and_toggle_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            save_config(
                AppConfig(
                    enabled=True,
                    default_scroll_factor=1.1,
                    apps={"firefox": AppRule("firefox", 0.3, "Firefox")},
                ),
                cfg_path,
            )
            backend = FakeKWinBackend()
            daemon = DaemonCore(TouchpadController(backend=backend), config_path=cfg_path)
            daemon.initialize()
            daemon.handle_active_window("firefox", "firefox", "firefox", "Firefox")
            self.assertEqual(backend.devices["event7"]["scrollFactor"], 0.3)

            # Toggle disabled -> applies default_scroll_factor
            state = daemon.set_enabled(False)
            self.assertFalse(state["enabled"])
            self.assertEqual(backend.devices["event7"]["scrollFactor"], 1.1)

            # Edit config on disk, re-enable, and reload
            save_config(
                AppConfig(
                    enabled=True,
                    default_scroll_factor=1.1,
                    apps={"firefox": AppRule("firefox", 0.75, "Firefox")},
                ),
                cfg_path,
            )
            state = daemon.reload_config()
            self.assertTrue(state["enabled"])
            self.assertEqual(state["current_factor"], 0.75)
            self.assertEqual(backend.devices["event7"]["scrollFactor"], 0.75)

    def test_first_run_seeds_default_from_touchpad_and_restore_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "missing-config.json"
            backend = FakeKWinBackend()
            backend.devices["event7"]["scrollFactor"] = 1.75

            daemon = DaemonCore(TouchpadController(backend=backend), config_path=cfg_path)
            state = daemon.initialize()
            self.assertEqual(state["default_scroll_factor"], 1.75)
            self.assertEqual(backend.devices["event7"]["scrollFactor"], 1.75)
            self.assertEqual(load_config(cfg_path).default_scroll_factor, 1.75)

            # Add caption-specific rule and verify shutdown restore_default
            cfg = load_config(cfg_path)
            key = make_rule_key("firefox", "Figma")
            cfg.apps[key] = AppRule("firefox", 0.35, "Figma", caption_pattern="Figma")
            save_config(cfg, cfg_path)
            daemon.reload_config()

            state = daemon.handle_active_window("firefox", "firefox", "firefox", "Figma — Firefox")
            self.assertEqual(state["current_factor"], 0.35)
            self.assertEqual(state["matched_rule_id"], key)

            daemon.restore_default()
            self.assertEqual(backend.devices["event7"]["scrollFactor"], 1.75)

    def test_quick_add_active_persists_rule_and_marks_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            save_config(AppConfig(enabled=True, default_scroll_factor=1.25), cfg_path)
            backend = FakeKWinBackend()
            daemon = DaemonCore(TouchpadController(backend=backend), config_path=cfg_path)
            daemon.initialize()

            state = daemon.handle_active_window("org.kde.kate", "kate", "org.kde.kate", "Kate")
            self.assertFalse(state["active_window_configured"])

            state = daemon.quick_add_active()
            self.assertTrue(state["active_window_configured"])
            loaded = load_config(cfg_path)
            self.assertIn("org.kde.kate", loaded.apps)
            self.assertEqual(loaded.apps["org.kde.kate"].scroll_factor, 1.25)


if __name__ == "__main__":
    unittest.main()
