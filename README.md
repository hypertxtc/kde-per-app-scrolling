# KDE Per-App Touchpad Scrolling

Configure touchpad scroll speed (`scrollFactor`) on a per-application basis on **KDE Plasma 6 (Wayland)**.

## Architecture

1. **KWin Script (`kwin-script/`)**: Listens for `workspace.windowActivated` events in KWin and sends the focused window's `resourceClass`, `resourceName`, `desktopFileName`, and `caption` to the daemon via `callDBus`.
2. **Background Daemon (`kde-per-app-scrolling-daemon`)**: Receives window-focus notifications on `io.github.kdeperappscrolling.Daemon`, matches the active window against your rules in `~/.config/kde-per-app-scrolling/config.json`, and updates `scrollFactor` on all KWin libinput touchpad devices (`/org/kde/KWin/InputDevice/<sysName>`). Also provides an optional native KDE system tray icon (`org.kde.StatusNotifierItem`).
3. **Standalone KDE GUI (`kde-per-app-scrolling`)**: Native **Qt6 / Kirigami + FormCard** (`PyQt6` + QML) configuration app matching KDE System Settings, allowing you to pick installed or recently focused apps, adjust per-app scroll speed sliders (`0.1x`–`20.0x`), set the default fallback speed, and monitor live status.

## Requirements

- Pre-installed on Fedora KDE Plasma 6:
  - `python3`, `python3-dbus`
  - `kf6-kirigami`, `kf6-kirigami-addons`, `qt6-qtdeclarative`
  - `kpackagetool6`, `kwriteconfig6`, `qdbus-qt6`
- Required for the PyQt6 + Kirigami GUI:
  - `python3-pyqt6` (`sudo dnf install python3-pyqt6`)

## Installation

```bash
./install.sh
```

This installs:
- Package files (including `qml/Main.qml`) into `~/.local/share/kde-per-app-scrolling/lib/`
- Launchers into `~/.local/bin/kde-per-app-scrolling` and `~/.local/bin/kde-per-app-scrolling-daemon`
- Desktop entry into `~/.local/share/applications/kde-per-app-scrolling.desktop`
- KWin script `kde-per-app-scrolling` (enabled in `kwinrc`)
- User systemd service `kde-per-app-scrolling.service` (enabled and started)

## Usage

- Open **Per-App Touchpad Scrolling** from your KDE application menu (or run `~/.local/bin/kde-per-app-scrolling`, or click the touchpad tray icon).
- Click **Add Application** in the toolbar to select an installed or recently focused application (or enter a custom `resourceClass` / `.desktop` name).
- Adjust the speed slider/spinbox for each app (`1.00x` is Plasma's default; `< 1.0` slows scrolling, `> 1.0` speeds it up).
- Left-click the tray icon to open settings, or middle-click (`SecondaryActivate`) to toggle per-app rules on/off.

## KDE System Settings Integration (KCM)

To integrate directly inside **System Settings -> Input & Output -> Mouse & Touchpad** (right next to *Touchpad*) instead of using a standalone window:

1. Install the Qt6 / KF6 C++ build dependencies (Fedora):
   ```bash
   sudo dnf install cmake gcc-c++ extra-cmake-modules qt6-qtbase-devel qt6-qtdeclarative-devel kf6-kcmutils-devel kf6-kcoreaddons-devel kf6-ki18n-devel
   ```
2. Build and install the System Settings module:
   ```bash
   ./kcm/install-kcm.sh
   ```
3. Launch directly anytime with `systemsettings kcm_per_app_scrolling` (the system tray icon will also automatically open System Settings once installed).

To remove the System Settings module later:
```bash
./kcm/uninstall-kcm.sh
```

## RPM Packaging & GitHub Actions

A Fedora RPM spec and local build helper live under `packaging/rpm/`:

```bash
sudo dnf install rpm-build
./packaging/rpm/build-local-rpm.sh
```

After installing a built `.rpm` (`sudo dnf install ./rpmbuild/RPMS/x86_64/kde-per-app-scrolling-*.rpm`), enable the KWin script and start the user service in your Plasma session:

```bash
kwriteconfig6 --file kwinrc --group Plugins --key kde-per-app-scrollingEnabled true
qdbus-qt6 org.kde.KWin /KWin reconfigure
systemctl --user enable --now kde-per-app-scrolling.service
```

The GitHub Actions workflow in [.github/workflows/build-rpm.yml](.github/workflows/build-rpm.yml) builds and tests RPMs on Fedora `latest` and `rawhide` on pushes/PRs, and automatically attaches the `latest` RPM and SRPM to a GitHub Release when pushing a `v*` tag (e.g., `git tag v0.1.0 && git push origin v0.1.0`).

## Troubleshooting

- **Check daemon logs:**
  ```bash
  journalctl --user -u kde-per-app-scrolling.service -f
  ```
- **Check KWin script logs:**
  ```bash
  journalctl --user -u plasma-kwin_wayland -f
  ```
- **Verify KWin touchpad devices via D-Bus:**
  ```bash
  qdbus-qt6 org.kde.KWin /org/kde/KWin/InputDevice
  ```

## Uninstall

```bash
./uninstall.sh
```

Your saved rules in `~/.config/kde-per-app-scrolling/config.json` are preserved.
