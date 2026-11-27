"""Unit tests for kde_per_app_scrolling.desktop_apps."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kde_per_app_scrolling.desktop_apps import scan_installed_apps  # noqa: E402


class DesktopAppsTests(unittest.TestCase):
    def test_scan_filters_hidden_and_sorts_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dir1 = Path(tmp) / "dir1"
            dir2 = Path(tmp) / "dir2"
            dir1.mkdir()
            dir2.mkdir()

            (dir1 / "org.mozilla.firefox.desktop").write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Firefox\n"
                "Icon=firefox\n"
                "StartupWMClass=firefox\n",
                encoding="utf-8",
            )
            (dir1 / "hidden.desktop").write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Hidden App\n"
                "NoDisplay=true\n",
                encoding="utf-8",
            )
            (dir1 / "link.desktop").write_text(
                "[Desktop Entry]\n"
                "Type=Link\n"
                "Name=Some Link\n",
                encoding="utf-8",
            )
            (dir2 / "alacritty.desktop").write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Alacritty\n"
                "Icon=Alacritty\n",
                encoding="utf-8",
            )
            # Duplicate firefox in dir2 should be ignored
            (dir2 / "firefox-dup.desktop").write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Firefox Duplicate\n"
                "StartupWMClass=Firefox\n",
                encoding="utf-8",
            )

            apps = scan_installed_apps([dir1, dir2, Path(tmp) / "missing"])
            self.assertEqual([a.name for a in apps], ["Alacritty", "Firefox"])
            self.assertEqual(apps[0].app_id, "alacritty")
            self.assertEqual(apps[1].app_id, "firefox")
            self.assertEqual(apps[1].icon_name, "firefox")


if __name__ == "__main__":
    unittest.main()
