"""Scan installed XDG desktop application entries."""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

from .config import normalize_app_id


@dataclass(frozen=True)
class DesktopApp:
    """Metadata for an installed desktop application."""

    app_id: str
    name: str
    icon_name: str
    startup_wm_class: str


def default_application_dirs() -> list[Path]:
    """Return standard XDG and Flatpak application desktop directories."""
    xdg_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    local_share = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local/share"
    return [
        local_share / "applications",
        Path("/usr/share/applications"),
        Path("/var/lib/flatpak/exports/share/applications"),
    ]


def _parse_desktop_file(desktop_path: Path) -> DesktopApp | None:
    parser = configparser.RawConfigParser(interpolation=None)
    parser.optionxform = str  # preserve case
    try:
        read_ok = parser.read(desktop_path, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return None
    if not read_ok or not parser.has_section("Desktop Entry"):
        return None

    section = parser["Desktop Entry"]
    if section.get("Type", "").strip() != "Application":
        return None
    if section.get("NoDisplay", "").strip().lower() == "true":
        return None
    if section.get("Hidden", "").strip().lower() == "true":
        return None

    name = section.get("Name", "").strip()
    if not name:
        return None

    startup_wm_class = normalize_app_id(section.get("StartupWMClass", ""))
    stem = normalize_app_id(desktop_path.stem)
    app_id = startup_wm_class or stem
    if not app_id:
        return None

    icon_name = section.get("Icon", "").strip() or "application-x-executable"
    return DesktopApp(
        app_id=app_id,
        name=name,
        icon_name=icon_name,
        startup_wm_class=startup_wm_class,
    )


def scan_installed_apps(search_dirs: list[Path] | None = None) -> list[DesktopApp]:
    """Scan directories for visible desktop applications, deduplicated and sorted by name."""
    dirs = search_dirs if search_dirs is not None else default_application_dirs()
    seen: dict[str, DesktopApp] = {}

    for directory in dirs:
        if not directory.is_dir():
            continue
        try:
            entries = sorted(directory.glob("*.desktop"))
        except OSError:
            continue
        for desktop_file in entries:
            app = _parse_desktop_file(desktop_file)
            if app is None:
                continue
            key = app.app_id.lower()
            if key not in seen:
                seen[key] = app

    return sorted(seen.values(), key=lambda app: (app.name.lower(), app.app_id.lower()))
