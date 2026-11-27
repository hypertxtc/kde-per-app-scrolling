/*
    Per-App Touchpad Scrolling KWin Script
    Reports active window metadata and title changes over D-Bus.
    SPDX-License-Identifier: GPL-3.0-or-later
*/

var trackedWindow = null;

function isIgnoredWindow(window) {
    return (
        window.desktopWindow ||
        window.dock ||
        window.popupWindow ||
        window.notification ||
        window.onScreenDisplay
    );
}

function reportWindow(window) {
    if (!window || isIgnoredWindow(window)) {
        return;
    }

    var resourceClass = String(window.resourceClass || "");
    var resourceName = String(window.resourceName || "");
    var desktopFileName = String(window.desktopFileName || "");
    var caption = String(window.caption || "");

    if (!resourceClass && !resourceName && !desktopFileName) {
        return;
    }

    callDBus(
        "io.github.kdeperappscrolling.Daemon",
        "/io/github/kdeperappscrolling/Daemon",
        "io.github.kdeperappscrolling.Daemon",
        "NotifyActiveWindow",
        resourceClass,
        resourceName,
        desktopFileName,
        caption
    );
}

function onTrackedCaptionChanged() {
    if (trackedWindow) {
        reportWindow(trackedWindow);
    }
}

function detachTrackedWindow() {
    if (trackedWindow) {
        try {
            trackedWindow.captionChanged.disconnect(onTrackedCaptionChanged);
        } catch (err) {
            // Window may already be destroyed.
        }
        trackedWindow = null;
    }
}

function onWindowActivated(window) {
    detachTrackedWindow();
    if (!window || isIgnoredWindow(window)) {
        return;
    }
    trackedWindow = window;
    try {
        trackedWindow.captionChanged.connect(onTrackedCaptionChanged);
    } catch (err) {
        // Ignore if signal connection is unavailable for this window type.
    }
    reportWindow(trackedWindow);
}

workspace.windowActivated.connect(onWindowActivated);
workspace.windowRemoved.connect(function (window) {
    if (window === trackedWindow) {
        trackedWindow = null;
    }
});

if (workspace.activeWindow) {
    onWindowActivated(workspace.activeWindow);
}
