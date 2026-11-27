/*
    Per-App Touchpad Scrolling — KDE System Settings KCM UI
    SPDX-License-Identifier: GPL-3.0-or-later
*/

import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kcmutils as KCM
import org.kde.kirigami as Kirigami
import org.kde.kirigamiaddons.formcard as FormCard

KCM.SimpleKCM {
    id: root

    topPadding: 0
    leftPadding: 0
    rightPadding: 0

    actions: [
        Kirigami.Action {
            text: "Add Application"
            icon.name: "list-add"
            onTriggered: {
                appIdField.text = ""
                labelField.text = ""
                captionField.text = ""
                initialSpeedSpin.value = Math.round(kcm.defaultScrollFactor * 100)
                searchField.text = ""
                kcm.prepareAddDialog()
                addDialog.open()
            }
        },
        Kirigami.Action {
            text: "Refresh"
            icon.name: "view-refresh"
            onTriggered: kcm.refreshStatus()
        }
    ]

    ColumnLayout {
        spacing: 0

        FormCard.FormHeader {
            title: "Status"
        }

        FormCard.FormCard {
            FormCard.FormTextDelegate {
                text: "Background Daemon"
                description: kcm.daemonStatusText
                trailing: QQC2.Button {
                    text: "Start Daemon"
                    icon.name: "media-playback-start"
                    visible: !kcm.daemonRunning
                    onClicked: kcm.startDaemon()
                }
            }

            FormCard.FormDelegateSeparator {}

            FormCard.FormTextDelegate {
                text: "Touchpad Devices"
                description: kcm.touchpadSummary
            }

            FormCard.FormDelegateSeparator {}

            FormCard.FormTextDelegate {
                text: "Active Window"
                description: kcm.activeWindowText
                trailing: QQC2.Button {
                    text: "Add Rule"
                    icon.name: "list-add"
                    visible: kcm.canQuickAddActive
                    onClicked: kcm.quickAddActive()
                }
            }
        }

        FormCard.FormHeader {
            title: "General"
        }

        FormCard.FormCard {
            FormCard.FormSwitchDelegate {
                text: "Enable Per-App Scrolling"
                checked: kcm.enabled
                onToggled: kcm.setEnabled(checked)
            }

            FormCard.FormDelegateSeparator {}

            FormCard.AbstractFormDelegate {
                background: null
                hoverEnabled: false

                contentItem: RowLayout {
                    spacing: Kirigami.Units.smallSpacing

                    QQC2.Label {
                        text: "Default Scroll Speed"
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }

                    QQC2.Slider {
                        Layout.preferredWidth: 150
                        from: 0.1
                        to: 5.0
                        stepSize: 0.05
                        value: Math.min(kcm.defaultScrollFactor, 5.0)
                        onMoved: kcm.setDefaultScrollFactor(value)
                    }

                    QQC2.SpinBox {
                        from: 10
                        to: 2000
                        stepSize: 5
                        editable: true
                        value: Math.round(kcm.defaultScrollFactor * 100)
                        textFromValue: function(value, locale) {
                            return (value / 100.0).toFixed(2) + "x"
                        }
                        valueFromText: function(text, locale) {
                            var cleaned = text.replace(/x/gi, "").trim()
                            var parsed = parseFloat(cleaned)
                            return isNaN(parsed) ? 100 : Math.round(parsed * 100)
                        }
                        onValueModified: kcm.setDefaultScrollFactor(value / 100.0)
                    }

                    QQC2.Button {
                        text: "1.0x"
                        QQC2.ToolTip.text: "Reset default speed to 1.00x"
                        QQC2.ToolTip.visible: hovered
                        onClicked: kcm.setDefaultScrollFactor(1.0)
                    }

                    QQC2.ToolButton {
                        icon.name: "view-refresh"
                        enabled: kcm.daemonRunning
                        QQC2.ToolTip.text: "Sync default speed from current KDE touchpad setting"
                        QQC2.ToolTip.visible: hovered
                        onClicked: kcm.syncDefaultFromSystem()
                    }
                }
            }

            FormCard.FormDelegateSeparator {}

            FormCard.FormSwitchDelegate {
                text: "Show System Tray Icon"
                checked: kcm.showTray
                onToggled: kcm.setShowTray(checked)
            }
        }

        FormCard.FormHeader {
            title: "Per-Application Scroll Speeds"
        }

        FormCard.FormCard {
            FormCard.FormPlaceholderMessageDelegate {
                text: "No application rules"
                icon.name: "input-touchpad"
                visible: rulesRepeater.count === 0
            }

            Repeater {
                id: rulesRepeater
                model: kcm.rules

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
                                        ? (modelData.app_id + " • \"" + modelData.caption_pattern + "\"")
                                        : (modelData.label ? modelData.app_id : "")
                                    visible: text.length > 0
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
                                onToggled: kcm.setRuleEnabled(modelData.rule_key, checked)
                            }

                            QQC2.Slider {
                                Layout.preferredWidth: 145
                                from: 0.1
                                to: 5.0
                                stepSize: 0.05
                                value: Math.min(modelData.scroll_factor, 5.0)
                                onMoved: kcm.setRuleScrollFactor(modelData.rule_key, value)
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
                                onValueModified: kcm.setRuleScrollFactor(modelData.rule_key, value / 100.0)
                            }

                            QQC2.ToolButton {
                                icon.name: "input-touchpad"
                                QQC2.ToolTip.text: "Test this speed in the Scroll Test Pad"
                                QQC2.ToolTip.visible: hovered
                                onClicked: kcm.previewScrollFactor(modelData.scroll_factor)
                            }

                            QQC2.ToolButton {
                                icon.name: "edit-delete"
                                QQC2.ToolTip.text: "Remove rule"
                                QQC2.ToolTip.visible: hovered
                                onClicked: kcm.removeRule(modelData.rule_key)
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
                text: kcm.previewFactor.toFixed(2) + "x"
                description: kcm.previewActive ? "Previewing" : ""
                trailing: QQC2.Button {
                    text: "Restore Active"
                    icon.name: "edit-undo"
                    enabled: kcm.previewActive
                    onClicked: kcm.endPreview()
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
                            text: "Line " + (index + 1)
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
                    kcm.addRule(
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
                placeholderText: "Search applications..."
                onTextChanged: kcm.setCandidateFilter(text)
            }

            QQC2.ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: Kirigami.Units.gridUnit * 14

                ListView {
                    id: candidateList
                    clip: true
                    model: kcm.filteredCandidates

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
