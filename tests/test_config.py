"""Unit tests for kde_per_app_scrolling.config."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kde_per_app_scrolling.config import (  # noqa: E402
    DEFAULT_SCROLL_FACTOR,
    MAX_SCROLL_FACTOR,
    MIN_SCROLL_FACTOR,
    AppConfig,
    AppRule,
    clamp_scroll_factor,
    get_config_path,
    load_config,
    make_rule_key,
    resolve_scroll_factor,
    save_config,
)


class ConfigTests(unittest.TestCase):
    def test_clamp_scroll_factor(self) -> None:
        self.assertEqual(clamp_scroll_factor(0.0), MIN_SCROLL_FACTOR)
        self.assertEqual(clamp_scroll_factor(-5.0), MIN_SCROLL_FACTOR)
        self.assertEqual(clamp_scroll_factor(99.0), MAX_SCROLL_FACTOR)
        self.assertEqual(clamp_scroll_factor(1.236), 1.24)
        self.assertEqual(clamp_scroll_factor(float("nan")), DEFAULT_SCROLL_FACTOR)
        self.assertEqual(clamp_scroll_factor("invalid"), DEFAULT_SCROLL_FACTOR)  # type: ignore[arg-type]

    def test_load_missing_returns_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(Path(tmp) / "nonexistent.json")
            self.assertTrue(cfg.enabled)
            self.assertEqual(cfg.default_scroll_factor, 1.0)
            self.assertTrue(cfg.show_tray)
            self.assertEqual(cfg.apps, {})

    def test_load_corrupt_json_returns_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{not valid json", encoding="utf-8")
            cfg = load_config(path)
            self.assertTrue(cfg.enabled)
            self.assertEqual(cfg.default_scroll_factor, 1.0)
            self.assertEqual(cfg.apps, {})

    def test_save_and_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "config.json"
            original = AppConfig(
                enabled=False,
                default_scroll_factor=1.5,
                show_tray=False,
                apps={
                    "firefox": AppRule(
                        app_id="firefox",
                        scroll_factor=0.65,
                        label="Firefox",
                        enabled=True,
                    ),
                    "org.kde.konsole": AppRule(
                        app_id="org.kde.konsole",
                        scroll_factor=2.25,
                        label="Konsole",
                        enabled=False,
                    ),
                },
            )
            save_config(original, path)
            loaded = load_config(path)
            self.assertEqual(loaded.enabled, False)
            self.assertEqual(loaded.default_scroll_factor, 1.5)
            self.assertEqual(loaded.show_tray, False)
            self.assertIn("firefox", loaded.apps)
            self.assertEqual(loaded.apps["firefox"].scroll_factor, 0.65)
            self.assertEqual(loaded.apps["firefox"].label, "Firefox")
            self.assertFalse(loaded.apps["org.kde.konsole"].enabled)

    def test_get_config_path_uses_xdg_config_home(self) -> None:
        old = os.environ.get("XDG_CONFIG_HOME")
        try:
            os.environ["XDG_CONFIG_HOME"] = "/tmp/custom-xdg-cfg"
            self.assertEqual(
                get_config_path(),
                Path("/tmp/custom-xdg-cfg/kde-per-app-scrolling/config.json"),
            )
        finally:
            if old is None:
                os.environ.pop("XDG_CONFIG_HOME", None)
            else:
                os.environ["XDG_CONFIG_HOME"] = old

    def test_resolve_exact_and_priority_order(self) -> None:
        cfg = AppConfig(
            enabled=True,
            default_scroll_factor=1.2,
            apps={
                "org.kde.dolphin": AppRule("org.kde.dolphin", 2.5, "Dolphin"),
                "firefox": AppRule("firefox", 0.5, "Firefox"),
                "disabled_app": AppRule("disabled_app", 4.0, "Disabled", enabled=False),
            },
        )
        # Matches desktopFileName with .desktop suffix stripped, case-insensitively
        factor, rule = resolve_scroll_factor(
            cfg,
            resource_class="dolphin",
            resource_name="dolphin",
            desktop_file_name="ORG.KDE.DOLPHIN.desktop",
        )
        self.assertEqual(factor, 2.5)
        self.assertIsNotNone(rule)
        assert rule is not None
        self.assertEqual(rule.app_id, "org.kde.dolphin")

        # Disabled rule falls back to default
        factor, rule = resolve_scroll_factor(cfg, resource_class="disabled_app")
        self.assertEqual(factor, 1.2)
        self.assertIsNone(rule)

    def test_resolve_reverse_dns_basename_matching(self) -> None:
        cfg = AppConfig(
            enabled=True,
            default_scroll_factor=1.0,
            apps={
                "firefox": AppRule("firefox", 0.4, "Firefox"),
                "org.kde.kate": AppRule("org.kde.kate", 3.0, "Kate"),
            },
        )
        # Window reports org.mozilla.firefox, rule is keyed firefox
        factor, rule = resolve_scroll_factor(
            cfg,
            resource_class="org.mozilla.firefox",
            desktop_file_name="org.mozilla.firefox",
        )
        self.assertEqual(factor, 0.4)
        self.assertIsNotNone(rule)

        # Window reports kate, rule is keyed org.kde.kate
        factor, rule = resolve_scroll_factor(cfg, resource_class="kate")
        self.assertEqual(factor, 3.0)
        self.assertIsNotNone(rule)

    def test_resolve_when_globally_disabled(self) -> None:
        cfg = AppConfig(
            enabled=False,
            default_scroll_factor=1.35,
            apps={"firefox": AppRule("firefox", 0.4)},
        )
        factor, rule = resolve_scroll_factor(cfg, resource_class="firefox")
        self.assertEqual(factor, 1.35)
        self.assertIsNone(rule)

    def test_caption_pattern_round_trip_and_resolution(self) -> None:
        self.assertEqual(make_rule_key("firefox"), "firefox")
        self.assertEqual(make_rule_key("firefox", " Google Maps "), "firefox::google maps")

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            general_key = make_rule_key("firefox")
            maps_key = make_rule_key("firefox", "Google Maps")
            cfg = AppConfig(
                enabled=True,
                default_scroll_factor=1.0,
                apps={
                    general_key: AppRule("firefox", 0.6, "Firefox"),
                    maps_key: AppRule(
                        "firefox", 0.25, "Google Maps", caption_pattern="Google Maps"
                    ),
                },
            )
            save_config(cfg, path)
            loaded = load_config(path)
            self.assertIn(general_key, loaded.apps)
            self.assertIn(maps_key, loaded.apps)
            self.assertEqual(loaded.apps[maps_key].caption_pattern, "Google Maps")

            # Matching title overrides general Firefox rule
            factor, rule = resolve_scroll_factor(
                loaded,
                resource_class="firefox",
                caption="Google Maps — Mozilla Firefox",
            )
            self.assertEqual(factor, 0.25)
            self.assertIsNotNone(rule)
            assert rule is not None
            self.assertEqual(rule.label, "Google Maps")

            # Non-matching title falls back to general Firefox rule
            factor, rule = resolve_scroll_factor(
                loaded,
                resource_class="firefox",
                caption="Wikipedia — Mozilla Firefox",
            )
            self.assertEqual(factor, 0.6)
            self.assertIsNotNone(rule)
            assert rule is not None
            self.assertEqual(rule.label, "Firefox")


if __name__ == "__main__":
    unittest.main()
