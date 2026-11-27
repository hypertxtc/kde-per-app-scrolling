"""Validation tests for the KDE System Settings KCM and RPM packaging."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


class KcmAndPackagingTests(unittest.TestCase):
    def test_kcm_files_metadata_and_qml(self) -> None:
        kcm_dir = ROOT_DIR / "kcm"
        for rel in ("CMakeLists.txt", "kcm.h", "kcm.cpp", "kcm_per_app_scrolling.json"):
            self.assertTrue((kcm_dir / rel).is_file(), f"Missing kcm/{rel}")

        meta = json.loads(
            (kcm_dir / "kcm_per_app_scrolling.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            meta["X-KDE-System-Settings-Parent-Category"], "pointing-devices"
        )
        self.assertEqual(meta["KPlugin"]["Icon"], "input-touchpad")

        kcm_qml = (kcm_dir / "ui" / "main.qml").read_text(encoding="utf-8")
        self.assertIn("import org.kde.kcmutils as KCM", kcm_qml)
        self.assertIn("KCM.SimpleKCM", kcm_qml)
        self.assertIn("Scroll Test Pad", kcm_qml)
        self.assertIn("captionField", kcm_qml)
        self.assertEqual(kcm_qml.count("{"), kcm_qml.count("}"))

    def test_no_standalone_gui_in_spec_or_package(self) -> None:
        spec = (
            ROOT_DIR / "packaging" / "rpm" / "kde-per-app-scrolling.spec"
        ).read_text(encoding="utf-8")
        self.assertNotIn("python3-pyqt6", spec)
        self.assertNotIn("kde-per-app-scrolling.desktop", spec)
        self.assertNotIn("%{_bindir}/kde-per-app-scrolling\n", spec)
        self.assertIn("kcm_per_app_scrolling.so", spec)
        self.assertIn("kcm_per_app_scrolling.desktop", spec)
        self.assertIn("%{_bindir}/kde-per-app-scrolling-daemon", spec)


if __name__ == "__main__":
    unittest.main()
