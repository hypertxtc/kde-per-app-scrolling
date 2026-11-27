#!/usr/bin/env bash
set -euo pipefail

echo "Removing kcm_per_app_scrolling from KDE System Settings (requires sudo)..."
sudo rm -f \
    /usr/lib64/qt6/plugins/plasma/kcms/systemsettings/kcm_per_app_scrolling.so \
    /usr/lib/qt6/plugins/plasma/kcms/systemsettings/kcm_per_app_scrolling.so \
    /usr/share/applications/kcm_per_app_scrolling.desktop

if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
fi

echo "KCM plugin uninstalled."
