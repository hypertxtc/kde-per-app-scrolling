/*
    Per-App Touchpad Scrolling — Native KDE Kirigami UI
    SPDX-License-Identifier: GPL-3.0-or-later
*/

import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami
import org.kde.kirigamiaddons.formcard as FormCard

Kirigami.ApplicationWindow {
    id: root

    title: "Per-App Touchpad Scrolling"
    width: 740
    height: 780
    minimumWidth: 520
    minimumHeight: 540

    pageStack.initialPage: FormCard.FormCardPage {
        id: mainPage
        title: "Per-App Touchpad Scrolling"

        actions: [
            Kirigami.Action {
                text: "Add Application"
                icon.name: "list-add"
                onTriggered: {
                    appIdField.text = ""
                    labelField.text = ""
                    captionField.text = ""
                    initialSpeedSpin.value = Math.round(backend.defaultScrollFactor * 100)
                    searchField.text = ""
                    backend.prepareAddDialog()
                    addDialog.open()
                }
            },
            Kirigami.Action {
                text: "Refresh"
                icon.name: "view-refresh"
                onTriggered: backend.refreshStatus()
            }
        ]

        FormCard.FormHeader {
            title: "Status"
        }

        FormCard.FormCard {
            FormCard.FormTextDelegate {
                text: "Background Daemon"
                description: backend.daemonStatusText
                trailing: QQC2.Button {
                    text: "Start Daemon"
                    icon.name: "media-playback-start"
                    visible: !backend.daemonRunning
                    onClicked: backend.startDaemon()
                }
            }

            FormCard.FormDelegateSeparator {}

            FormCard.FormTextDelegate {
                text: "Touchpad Devices"
                description: backend.touchpadSummary
            }

            FormCard.FormDelegateSeparator {}

            FormCard.FormTextDelegate {
                text: "Active Window"
                description: backend.activeWindowText
                trailing: QQC2.Button {
                    text: "Add Rule"
                    icon.name: "list-add"
                    visible: backend.canQuickAddActive
                    onClicked: backend.quickAddActive()
                }
            }
        }

        FormCard.FormHeader {
            title: "General"
        }

        FormCard.FormCard {
            FormCard.FormSwitchDelegate {
                text: "Enable Per-App Scrolling"
                description: "Automatically switch touchpad scroll speed when changing windows"
                checked: backend.enabled
                onToggled: backend.setEnabled(checked)
            }

            FormCard.FormDelegateSeparator {}

            FormCard.AbstractFormDelegate {
                background: null
                hoverEnabled: false

                contentItem: RowLayout {
                    spacing: Kirigami.Units.smallSpacing

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2

                        QQC2.Label {
                            text: "Default Scroll Speed"
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                        }

                        QQC2.Label {
                            text: "Fallback speed used when no application rule matches"
                            font: Kirigami.Theme.smallFont
                            opacity: 0.7
                            Layout.fillWidth: true
                            wrapMode: Text.WordWrap
                        }
                    }

                    QQC2.Slider {
                        id: defaultSlider
                        Layout.preferredWidth: 160
                        from: 0.1
                        to: 5.0
                        stepSize: 0.05
                        value: Math.min(backend.defaultScrollFactor, 5.0)
                        onMoved: backend.setDefaultScrollFactor(value)
                    }

                    QQC2.SpinBox {
                        id: defaultSpin
                        from: 10
                        to: 2000
                        stepSize: 5
                        editable: true
                        value: Math.round(backend.defaultScrollFactor * 100)
                        textFromValue: function(value, locale) {
                            return (value / 100.0).toFixed(2) + "x"
                        }
                        valueFromText: function(text, locale) {
                            var cleaned = text.replace(/x/gi, "").trim()
                            var parsed = parseFloat(cleaned)
                            return isNaN(parsed) ? 100 : Math.round(parsed * 100)
                        }
                        onValueModified: backend.setDefaultScrollFactor(value / 100.0)
                    }

                    QQC2.Button {
                        text: "1.0x"
                        QQC2.ToolTip.text: "Reset default speed to 1.00x"
                        QQC2.ToolTip.visible: hovered
                        onClicked: backend.setDefaultScrollFactor(1.0)
                    }
                }
            }

            FormCard.FormDelegateSeparator {}

            FormCard.FormSwitchDelegate {
                text: "Show System Tray Icon"
                description: "Display live active app speed in Plasma's system tray"
                checked: backend.showTray
                onToggled: backend.setShowTray(checked)
            }
        }

        FormCard.FormHeader {
            title: "Per-Application Scroll Speeds"
        }

        FormCard.FormCard {
            FormCard.FormPlaceholderMessageDelegate {
                text: "No application rules yet"
                explanation: "Click 'Add Application' in the toolbar to configure an app's scroll speed."
                icon.name: "input-touchpad"
                visible: rulesRepeater.count === 0
            }

            Repeater {
                id: rulesRepeater
                model: backend.rules

                delegate: ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0

                    FormCard.FormDelegateSeparator {
                        visible: index > 0
                    }

                    FormCard.AbstractFormDelegate {
                        background: null
                        hoverEnabled: false

                        contentItem: RowLayout {
                            spacing: Kirigami.Units.smallSpacing

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2

                                QQC2.Label {
                                    text: modelData.label ? modelData.label : modelData.app_id
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }

                                QQC2.Label {
                                    text: modelData.caption_pattern
                                        ? (modelData.app_id + " • title contains \"" + modelData.caption_pattern + "\"")
                                        : (modelData.label ? modelData.app_id : "Matched by app ID")
                                    font: Kirigami.Theme.smallFont
                                    opacity: 0.7
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }
                            }

                            QQC2.Switch {
                                checked: modelData.enabled
                                QQC2.ToolTip.text: "Enable rule"
                                QQC2.ToolTip.visible: hovered
                                onToggled: backend.setRuleEnabled(modelData.rule_key, checked)
                            }

                            QQC2.Slider {
                                Layout.preferredWidth: 145
                                from: 0.1
                                to: 5.0
                                stepSize: 0.05
                                value: Math.min(modelData.scroll_factor, 5.0)
                                onMoved: backend.setRuleScrollFactor(modelData.rule_key, value)
                            }

                            QQC2.SpinBox {
                                from: 10
                                to: 2000
                                stepSize: 5
                                editable: true
                                value: Math.round(modelData.scroll_factor * 100)
                                textFromValue: function(value, locale) {
                                    return (value / 100.0).toFixed(2) + "x"
                                }
                                valueFromText: function(text, locale) {
                                    var cleaned = text.replace(/x/gi, "").trim()
                                    var parsed = parseFloat(cleaned)
                                    return isNaN(parsed) ? 100 : Math.round(parsed * 100)
                                }
                                onValueModified: backend.setRuleScrollFactor(modelData.rule_key, value / 100.0)
                            }

                            QQC2.ToolButton {
                                icon.name: "input-touchpad"
                                QQC2.ToolTip.text: "Test this speed in the Scroll Test Pad"
                                QQC2.ToolTip.visible: hovered
                                onClicked: backend.previewScrollFactor(modelData.scroll_factor)
                            }

                            QQC2.ToolButton {
                                icon.name: "edit-delete"
                                QQC2.ToolTip.text: "Remove rule"
                                QQC2.ToolTip.visible: hovered
                                onClicked: backend.removeRule(modelData.rule_key)
                            }
                        }
                    }
                }
            }
        }

        FormCard.FormHeader {
            title: "Scroll Test Pad"
        }

        FormCard.FormCard {
            FormCard.FormTextDelegate {
                text: "Live Scroll Preview"
                description: "Test speed: " + backend.previewFactor.toFixed(2) + "x" + (backend.previewActive ? " (previewing)" : " (live)")
                trailing: QQC2.Button {
                    text: "Restore Active"
                    icon.name: "edit-undo"
                    enabled: backend.previewActive
                    onClicked: backend.endPreview()
                }
            }

            FormCard.FormDelegateSeparator {}

            FormCard.AbstractFormDelegate {
                background: null
                hoverEnabled: false

                contentItem: QQC2.ScrollView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 165
                    clip: true

                    ListView {
                        model: 30
                        spacing: 4

                        delegate: QQC2.Label {
                            width: ListView.view.width - Kirigami.Units.largeSpacing
                            text: "Scroll test line " + (index + 1) + " — two-finger scroll here to feel " + backend.previewFactor.toFixed(2) + "x"
                            opacity: 0.85
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }
    }

    Kirigami.Dialog {
        id: addDialog
        title: "Add Application Rule"
        preferredWidth: Kirigami.Units.gridUnit * 30
        preferredHeight: Kirigami.Units.gridUnit * 34
        padding: Kirigami.Units.largeSpacing
        standardButtons: Kirigami.Dialog.Cancel

        customFooterActions: [
            Kirigami.Action {
                text: "Add Rule"
                icon.name: "list-add"
                enabled: appIdField.text.trim().length > 0
                onTriggered: {
                    backend.addRule(
                        appIdField.text,
                        labelField.text,
                        captionField.text,
                        initialSpeedSpin.value / 100.0
                    )
                    addDialog.close()
                }
            }
        ]

        ColumnLayout {
            spacing: Kirigami.Units.smallSpacing

            GridLayout {
                columns: 2
                columnSpacing: Kirigami.Units.smallSpacing
                rowSpacing: Kirigami.Units.smallSpacing
                Layout.fillWidth: true

                QQC2.Label {
                    text: "App ID:"
                }
                QQC2.TextField {
                    id: appIdField
                    Layout.fillWidth: true
                    placeholderText: "e.g. firefox, org.kde.konsole"
                }

                QQC2.Label {
                    text: "Display Name:"
                }
                QQC2.TextField {
                    id: labelField
                    Layout.fillWidth: true
                    placeholderText: "Optional friendly name"
                }

                QQC2.Label {
                    text: "Title Contains:"
                }
                QQC2.TextField {
                    id: captionField
                    Layout.fillWidth: true
                    placeholderText: "Optional (e.g. Google Maps, Figma)"
                }

                QQC2.Label {
                    text: "Initial Speed:"
                }
                QQC2.SpinBox {
                    id: initialSpeedSpin
                    from: 10
                    to: 2000
                    stepSize: 5
                    editable: true
                    value: 100
                    textFromValue: function(value, locale) {
                        return (value / 100.0).toFixed(2) + "x"
                    }
                    valueFromText: function(text, locale) {
                        var cleaned = text.replace(/x/gi, "").trim()
                        var parsed = parseFloat(cleaned)
                        return isNaN(parsed) ? 100 : Math.round(parsed * 100)
                    }
                }
            }

            Kirigami.SearchField {
                id: searchField
                Layout.fillWidth: true
                placeholderText: "Search recent windows or installed applications..."
                onTextChanged: backend.setCandidateFilter(text)
            }

            QQC2.ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: Kirigami.Units.gridUnit * 14

                ListView {
                    id: candidateList
                    clip: true
                    model: backend.filteredCandidates

                    delegate: QQC2.ItemDelegate {
                        width: candidateList.width

                        onClicked: {
                            appIdField.text = modelData.app_id
                            labelField.text = (modelData.label !== modelData.app_id) ? modelData.label : ""
                        }

                        contentItem: RowLayout {
                            spacing: Kirigami.Units.smallSpacing

                            Kirigami.Icon {
                                source: modelData.icon_name
                                Layout.preferredWidth: Kirigami.Units.iconSizes.smallMedium
                                Layout.preferredHeight: Kirigami.Units.iconSizes.smallMedium
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 1

                                QQC2.Label {
                                    text: modelData.label
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }

                                QQC2.Label {
                                    text: modelData.subtitle
                                    font: Kirigami.Theme.smallFont
                                    opacity: 0.7
                                    Layout.fillWidth: true
                                    elide: Text.ElideRight
                                }
                            }

                            QQC2.Label {
                                text: "Configured"
                                visible: modelData.configured
                                font: Kirigami.Theme.smallFont
                                opacity: 0.7
                            }
                        }
                    }
                }
            }
        }
    }
}
