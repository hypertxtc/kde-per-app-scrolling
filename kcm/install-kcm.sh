#!/usr/bin/env bash
set -euo pipefail

KCM_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$KCM_DIR/build"

missing=()
command -v cmake >/dev/null 2>&1 || missing+=("cmake")
command -v g++ >/dev/null 2>&1 || missing+=("gcc-c++")

if [[ ${#missing[@]} -gt 0 ]] || [[ ! -d /usr/share/ECM/cmake ]]; then
    echo "Missing build dependencies required to compile the KDE System Settings KCM plugin."
    echo "Install them on Fedora with:"
    echo "  sudo dnf install cmake gcc-c++ extra-cmake-modules qt6-qtbase-devel qt6-qtdeclarative-devel kf6-kcmutils-devel kf6-kcoreaddons-devel kf6-ki18n-devel"
    exit 1
fi

echo "Building kcm_per_app_scrolling..."
cmake -B "$BUILD_DIR" -S "$KCM_DIR" -DCMAKE_BUILD_TYPE=Release
cmake --build "$BUILD_DIR" -j"$(nproc)"

echo "Installing KCM plugin into KDE System Settings (requires sudo)..."
sudo cmake --install "$BUILD_DIR"

if command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
fi

echo ""
echo "KCM installed! Open it in System Settings -> Input & Output -> Mouse & Touchpad,"
echo "or launch directly with:"
echo "  systemsettings kcm_per_app_scrolling"
