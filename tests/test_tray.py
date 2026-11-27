"""Unit tests for kde_per_app_scrolling.tray menu builder and KWin script."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from kde_per_app_scrolling.tray import (  # noqa: E402
    MENU_ID_OPEN,
    MENU_ID_QUICK_ADD,
    MENU_ID_RESTORE,
    MENU_ID_STATUS,
    MENU_ID_TOGGLE,
    build_menu_items,
)


class TrayAndKWinScriptTests(unittest.TestCase):
    def test_build_menu_items_enabled_unconfigured(self) -> None:
        items = dict(
            build_menu_items(
                {
                    "enabled": True,
                    "current_factor": 0.45,
                    "active_window": {"primary_id": "firefox"},
                    "active_window_configured": False,
                }
            )
        )
        self.assertIn("firefox — 0.45x", items[MENU_ID_STATUS]["label"])
        self.assertFalse(items[MENU_ID_STATUS]["enabled"])
        self.assertEqual(items[MENU_ID_OPEN]["label"], "Open Settings")
        self.assertEqual(items[MENU_ID_TOGGLE]["label"], "Pause Per-App Scrolling")
        self.assertEqual(items[MENU_ID_QUICK_ADD]["label"], "Quick-Add firefox")
        self.assertTrue(items[MENU_ID_QUICK_ADD]["visible"])
        self.assertTrue(items[MENU_ID_QUICK_ADD]["enabled"])
        self.assertEqual(items[MENU_ID_RESTORE]["label"], "Restore Default Speed")

    def test_build_menu_items_paused_and_configured(self) -> None:
        items = dict(
            build_menu_items(
                {
                    "enabled": False,
                    "current_factor": 1.0,
                    "active_window": {"primary_id": "org.kde.konsole"},
                    "active_window_configured": True,
                }
            )
        )
        self.assertEqual(items[MENU_ID_STATUS]["label"], "Paused — 1.00x")
        self.assertEqual(items[MENU_ID_TOGGLE]["label"], "Resume Per-App Scrolling")
        self.assertFalse(items[MENU_ID_QUICK_ADD]["visible"])
        self.assertFalse(items[MENU_ID_QUICK_ADD]["enabled"])

    def test_kwin_script_tracks_caption_and_cleanup(self) -> None:
        js_path = ROOT_DIR / "kwin-script" / "contents" / "code" / "main.js"
        js_text = js_path.read_text(encoding="utf-8")
        self.assertIn("captionChanged", js_text)
        self.assertIn("windowRemoved", js_text)
        self.assertIn("detachTrackedWindow", js_text)
        self.assertEqual(js_text.count("{"), js_text.count("}"))


if __name__ == "__main__":
    unittest.main()
