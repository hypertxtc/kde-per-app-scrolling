#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
BIN_DIR="$HOME/.local/bin"
LIB_DIR="$DATA_HOME/kde-per-app-scrolling/lib"
APPS_DIR="$DATA_HOME/applications"
SYSTEMD_USER_DIR="$CONFIG_HOME/systemd/user"

echo "Installing kde-per-app-scrolling..."

mkdir -p "$BIN_DIR" "$LIB_DIR" "$APPS_DIR" "$SYSTEMD_USER_DIR"

# Install Python package
rm -rf "$LIB_DIR/kde_per_app_scrolling"
cp -r "$SCRIPT_DIR/src/kde_per_app_scrolling" "$LIB_DIR/"

# Install CLI / GUI wrapper scripts
install -m 0755 "$SCRIPT_DIR/bin/kde-per-app-scrolling" "$BIN_DIR/kde-per-app-scrolling"
install -m 0755 "$SCRIPT_DIR/bin/kde-per-app-scrolling-daemon" "$BIN_DIR/kde-per-app-scrolling-daemon"

# Install desktop entry
install -m 0644 "$SCRIPT_DIR/data/kde-per-app-scrolling.desktop" "$APPS_DIR/kde-per-app-scrolling.desktop"

# Install and enable KWin script
kpackagetool6 --type=KWin/Script -u "$SCRIPT_DIR/kwin-script" 2>/dev/null \
    || kpackagetool6 --type=KWin/Script -i "$SCRIPT_DIR/kwin-script"

kwriteconfig6 --file kwinrc --group Plugins --key kde-per-app-scrollingEnabled true

if command -v qdbus-qt6 >/dev/null 2>&1; then
    qdbus-qt6 org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true
fi

# Install and start systemd user service
install -m 0644 "$SCRIPT_DIR/data/kde-per-app-scrolling.service" "$SYSTEMD_USER_DIR/kde-per-app-scrolling.service"
systemctl --user daemon-reload
systemctl --user enable --now kde-per-app-scrolling.service

echo ""
echo "Installation complete!"
if ! python3 -c "import PyQt6" >/dev/null 2>&1; then
    echo "  ! Note: PyQt6 is required for the KDE Kirigami GUI. Install it with:"
    echo "      sudo dnf install python3-pyqt6"
fi
echo "  - Run GUI: $BIN_DIR/kde-per-app-scrolling (or launch 'Per-App Touchpad Scrolling' from the app menu)"
echo "  - Service status: systemctl --user status kde-per-app-scrolling.service"
