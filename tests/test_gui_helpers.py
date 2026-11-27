"""Unit tests for kde_per_app_scrolling.gui helpers and Kirigami QML."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from kde_per_app_scrolling.config import AppConfig, AppRule  # noqa: E402
from kde_per_app_scrolling.desktop_apps import DesktopApp  # noqa: E402
from kde_per_app_scrolling.gui import (  # noqa: E402
    QML_MAIN_PATH,
    build_candidate_list,
    filter_candidates,
    format_status_summary,
    serialize_rules,
)


class GuiHelpersTests(unittest.TestCase):
    def test_qml_main_exists_and_uses_kirigami(self) -> None:
        self.assertTrue(QML_MAIN_PATH.is_file(), f"Missing {QML_MAIN_PATH}")
        qml_text = QML_MAIN_PATH.read_text(encoding="utf-8")
        self.assertIn("import org.kde.kirigami as Kirigami", qml_text)
        self.assertIn("import org.kde.kirigamiaddons.formcard as FormCard", qml_text)
        self.assertIn("Scroll Test Pad", qml_text)
        self.assertIn("captionField", qml_text)
        self.assertEqual(qml_text.count("{"), qml_text.count("}"))

    def test_serialize_rules_sorted(self) -> None:
        cfg = AppConfig(
            apps={
                "vlc": AppRule("vlc", 1.5, "VLC"),
                "firefox": AppRule("firefox", 0.45, "Firefox", enabled=False),
                "firefox::maps": AppRule(
                    "firefox", 0.25, "Maps", enabled=True, caption_pattern="Maps"
                ),
            }
        )
        rows = serialize_rules(cfg)
        self.assertEqual([r["rule_key"] for r in rows], ["firefox", "firefox::maps", "vlc"])
        self.assertFalse(rows[0]["enabled"])
        self.assertEqual(rows[0]["scroll_factor"], 0.45)
        self.assertEqual(rows[1]["caption_pattern"], "Maps")

    def test_build_and_filter_candidates(self) -> None:
        recent = [
            {"app_id": "firefox", "caption": "Mozilla Firefox"},
            {"app_id": "alacritty", "caption": "Terminal"},
        ]
        installed = [
            DesktopApp("firefox", "Firefox", "firefox", "firefox"),
            DesktopApp("org.kde.dolphin", "Dolphin", "system-file-manager", ""),
        ]
        candidates = build_candidate_list(recent, installed, {"firefox"})
        self.assertEqual([c["app_id"] for c in candidates], ["firefox", "alacritty", "org.kde.dolphin"])
        self.assertTrue(candidates[0]["configured"])
        self.assertFalse(candidates[1]["configured"])

        filtered = filter_candidates(candidates, "dolph")
        self.assertEqual([c["app_id"] for c in filtered], ["org.kde.dolphin"])

    def test_format_status_summary(self) -> None:
        stopped = format_status_summary(None, set())
        self.assertFalse(stopped["daemon_running"])
        self.assertFalse(stopped["can_quick_add_active"])

        running = format_status_summary(
            {
                "enabled": True,
                "current_factor": 0.6,
                "matched_rule_id": None,
                "touchpads": [{"name": "Synaptics", "scroll_factor": 0.6}],
                "active_window": {"primary_id": "org.kde.kate"},
            },
            set(),
        )
        self.assertTrue(running["daemon_running"])
        self.assertTrue(running["can_quick_add_active"])
        self.assertIn("Synaptics", running["touchpad_summary"])
        self.assertIn("org.kde.kate", running["active_window_text"])

    def test_kcm_files_metadata_and_qml(self) -> None:
        kcm_dir = ROOT_DIR / "kcm"
        for rel in ("CMakeLists.txt", "kcm.h", "kcm.cpp", "kcm_per_app_scrolling.json"):
            self.assertTrue((kcm_dir / rel).is_file(), f"Missing kcm/{rel}")

        meta = json.loads((kcm_dir / "kcm_per_app_scrolling.json").read_text(encoding="utf-8"))
        self.assertEqual(meta["X-KDE-System-Settings-Parent-Category"], "pointing-devices")
        self.assertEqual(meta["KPlugin"]["Icon"], "input-touchpad")

        kcm_qml = (kcm_dir / "ui" / "main.qml").read_text(encoding="utf-8")
        self.assertIn("import org.kde.kcmutils as KCM", kcm_qml)
        self.assertIn("KCM.SimpleKCM", kcm_qml)
        self.assertEqual(kcm_qml.count("{"), kcm_qml.count("}"))


if __name__ == "__main__":
    unittest.main()
