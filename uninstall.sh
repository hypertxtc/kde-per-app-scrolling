#!/usr/bin/env bash
set -euo pipefail

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
BIN_DIR="$HOME/.local/bin"
LIB_DIR="$DATA_HOME/kde-per-app-scrolling"
APPS_DIR="$DATA_HOME/applications"
SYSTEMD_USER_DIR="$CONFIG_HOME/systemd/user"

echo "Uninstalling kde-per-app-scrolling..."

# Stop and remove systemd user service
systemctl --user disable --now kde-per-app-scrolling.service 2>/dev/null || true
rm -f "$SYSTEMD_USER_DIR/kde-per-app-scrolling.service"
systemctl --user daemon-reload 2>/dev/null || true

# Disable and remove KWin script
kwriteconfig6 --file kwinrc --group Plugins --key kde-per-app-scrollingEnabled false 2>/dev/null || true
kpackagetool6 --type=KWin/Script -r kde-per-app-scrolling 2>/dev/null || true

if command -v qdbus-qt6 >/dev/null 2>&1; then
    qdbus-qt6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
fi

# Remove launchers, any legacy desktop entry, and library files
rm -f "$BIN_DIR/kde-per-app-scrolling"
rm -f "$BIN_DIR/kde-per-app-scrolling-daemon"
rm -f "$APPS_DIR/kde-per-app-scrolling.desktop"
rm -rf "$LIB_DIR"

echo ""
echo "Uninstallation complete."
echo "If you also installed the System Settings KCM plugin, remove it with: ./kcm/uninstall-kcm.sh"
echo "Note: Your configuration file was kept at: $CONFIG_HOME/kde-per-app-scrolling/config.json"
