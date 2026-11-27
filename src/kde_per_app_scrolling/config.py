"""Configuration storage and per-app scroll factor resolution."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

MIN_SCROLL_FACTOR = 0.1
MAX_SCROLL_FACTOR = 20.0
DEFAULT_SCROLL_FACTOR = 1.0


@dataclass
class AppRule:
    """Per-application touchpad scroll factor rule."""

    app_id: str
    scroll_factor: float = DEFAULT_SCROLL_FACTOR
    label: str = ""
    enabled: bool = True
    caption_pattern: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize rule to a JSON-compatible dict."""
        return {
            "app_id": self.app_id,
            "scroll_factor": clamp_scroll_factor(self.scroll_factor),
            "label": self.label,
            "enabled": bool(self.enabled),
            "caption_pattern": self.caption_pattern.strip(),
        }


@dataclass
class AppConfig:
    """Top-level configuration for Per-App Touchpad Scrolling."""

    enabled: bool = True
    default_scroll_factor: float = DEFAULT_SCROLL_FACTOR
    show_tray: bool = True
    apps: dict[str, AppRule] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize configuration to a JSON-compatible dict."""
        return {
            "enabled": bool(self.enabled),
            "default_scroll_factor": clamp_scroll_factor(self.default_scroll_factor),
            "show_tray": bool(self.show_tray),
            "apps": {
                key: rule.to_dict()
                for key, rule in sorted(self.apps.items(), key=lambda item: item[0].lower())
            },
        }


def clamp_scroll_factor(value: float) -> float:
    """Clamp scroll factor to [MIN_SCROLL_FACTOR, MAX_SCROLL_FACTOR] and round to 2 decimals."""
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return DEFAULT_SCROLL_FACTOR
    if numeric != numeric:  # NaN check
        return DEFAULT_SCROLL_FACTOR
    clamped = max(MIN_SCROLL_FACTOR, min(MAX_SCROLL_FACTOR, numeric))
    return round(clamped, 2)


def normalize_app_id(raw_id: str) -> str:
    """Normalize an app identifier by stripping whitespace and trailing .desktop."""
    cleaned = (raw_id or "").strip()
    if cleaned.lower().endswith(".desktop"):
        cleaned = cleaned[:-8]
    return cleaned


def make_rule_key(app_id: str, caption_pattern: str = "") -> str:
    """Return a stable dictionary key for an AppRule."""
    cleaned_id = normalize_app_id(app_id)
    cleaned_cap = (caption_pattern or "").strip().lower()
    if cleaned_cap:
        return f"{cleaned_id}::{cleaned_cap}"
    return cleaned_id


def _reverse_dns_basename(app_id: str) -> str:
    """Extract the trailing component of a reverse-DNS identifier if present."""
    normalized = normalize_app_id(app_id).lower()
    if "." in normalized:
        return normalized.rsplit(".", 1)[-1]
    return normalized


def get_config_path() -> Path:
    """Return the XDG config file path for kde-per-app-scrolling."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = Path(xdg_config) if xdg_config else Path.home() / ".config"
    return base / "kde-per-app-scrolling" / "config.json"


def _parse_rule(key: str, raw: Any) -> AppRule | None:
    if not isinstance(raw, dict):
        return None
    fallback_id = key.split("::", 1)[0] if "::" in key else key
    app_id = normalize_app_id(str(raw.get("app_id") or fallback_id))
    if not app_id:
        return None
    factor = clamp_scroll_factor(raw.get("scroll_factor", DEFAULT_SCROLL_FACTOR))
    label = str(raw.get("label", "") or "")
    enabled = bool(raw.get("enabled", True))
    caption_pattern = str(raw.get("caption_pattern", "") or "").strip()
    return AppRule(
        app_id=app_id,
        scroll_factor=factor,
        label=label,
        enabled=enabled,
        caption_pattern=caption_pattern,
    )


def load_config(path: Path | None = None) -> AppConfig:
    """Load configuration from disk, returning defaults if missing or malformed."""
    config_path = path or get_config_path()
    if not config_path.exists():
        return AppConfig()

    try:
        raw_text = config_path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except (OSError, ValueError) as exc:
        LOGGER.warning("Failed to load config from %s: %s", config_path, exc)
        return AppConfig()

    if not isinstance(data, dict):
        LOGGER.warning("Ignoring non-object config in %s", config_path)
        return AppConfig()

    enabled = bool(data.get("enabled", True))
    default_factor = clamp_scroll_factor(
        data.get("default_scroll_factor", DEFAULT_SCROLL_FACTOR)
    )
    show_tray = bool(data.get("show_tray", True))

    apps: dict[str, AppRule] = {}
    raw_apps = data.get("apps", {})
    if isinstance(raw_apps, dict):
        for key, raw_rule in raw_apps.items():
            rule = _parse_rule(str(key), raw_rule)
            if rule is not None:
                apps[make_rule_key(rule.app_id, rule.caption_pattern)] = rule

    return AppConfig(
        enabled=enabled,
        default_scroll_factor=default_factor,
        show_tray=show_tray,
        apps=apps,
    )


def save_config(config: AppConfig, path: Path | None = None) -> None:
    """Atomically write configuration JSON to disk."""
    config_path = path or get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config.to_dict(), indent=2, sort_keys=False) + "\n"

    fd, tmp_name = tempfile.mkstemp(
        dir=str(config_path.parent),
        prefix=".config-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, config_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _match_rules(
    candidates: list[str], rules: list[tuple[str, AppRule]]
) -> AppRule | None:
    """Match normalized window identifiers against a list of (norm_app_id, AppRule)."""
    if not rules:
        return None

    # Pass 1: exact case-insensitive match in priority order.
    by_exact: dict[str, AppRule] = {}
    for norm_key, rule in rules:
        by_exact.setdefault(norm_key, rule)
    for candidate in candidates:
        if candidate in by_exact:
            return by_exact[candidate]

    # Pass 2: basename match for reverse-DNS IDs (e.g. org.mozilla.firefox <-> firefox).
    for candidate in candidates:
        cand_base = _reverse_dns_basename(candidate)
        for rule_key, rule in rules:
            rule_base = _reverse_dns_basename(rule_key)
            if cand_base and (cand_base == rule_key or rule_base == candidate or cand_base == rule_base):
                if "." in candidate or "." in rule_key:
                    return rule
    return None


def resolve_scroll_factor(
    config: AppConfig,
    resource_class: str,
    resource_name: str = "",
    desktop_file_name: str = "",
    caption: str = "",
) -> tuple[float, AppRule | None]:
    """Resolve the scroll factor and matching rule for a window's identifiers and title."""
    default_factor = clamp_scroll_factor(config.default_scroll_factor)
    if not config.enabled:
        return default_factor, None

    candidates: list[str] = []
    for raw in (desktop_file_name, resource_class, resource_name):
        norm = normalize_app_id(raw).lower()
        if norm and norm not in candidates:
            candidates.append(norm)

    if not candidates:
        return default_factor, None

    caption_lower = (caption or "").lower()
    title_rules: list[tuple[str, AppRule]] = []
    general_rules: list[tuple[str, AppRule]] = []

    for rule in config.apps.values():
        norm_id = normalize_app_id(rule.app_id).lower()
        if not rule.enabled or not norm_id:
            continue
        pattern = rule.caption_pattern.strip().lower()
        if pattern:
            if pattern in caption_lower:
                title_rules.append((norm_id, rule))
        else:
            general_rules.append((norm_id, rule))

    # Prefer title-specific rules over general app rules.
    matched = _match_rules(candidates, title_rules) or _match_rules(
        candidates, general_rules
    )
    if matched is not None:
        return clamp_scroll_factor(matched.scroll_factor), matched

    return default_factor, None
