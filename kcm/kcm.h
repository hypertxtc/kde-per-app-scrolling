/*
    Per-App Touchpad Scrolling — KDE System Settings KCM
    SPDX-License-Identifier: GPL-3.0-or-later
*/

#pragma once

#include <KPluginMetaData>
#include <KQuickConfigModule>
#include <QMap>
#include <QString>
#include <QTimer>
#include <QVariantList>
#include <QVariantMap>

class PerAppScrollingKcm : public KQuickConfigModule
{
    Q_OBJECT

    Q_PROPERTY(bool enabled READ enabled NOTIFY configChanged)
    Q_PROPERTY(double defaultScrollFactor READ defaultScrollFactor NOTIFY configChanged)
    Q_PROPERTY(bool showTray READ showTray NOTIFY configChanged)
    Q_PROPERTY(QVariantList rules READ rules NOTIFY configChanged)

    Q_PROPERTY(bool daemonRunning READ daemonRunning NOTIFY statusChanged)
    Q_PROPERTY(QString daemonStatusText READ daemonStatusText NOTIFY statusChanged)
    Q_PROPERTY(QString touchpadSummary READ touchpadSummary NOTIFY statusChanged)
    Q_PROPERTY(QString activeWindowText READ activeWindowText NOTIFY statusChanged)
    Q_PROPERTY(bool canQuickAddActive READ canQuickAddActive NOTIFY statusChanged)

    Q_PROPERTY(QVariantList filteredCandidates READ filteredCandidates NOTIFY candidatesChanged)

    Q_PROPERTY(double previewFactor READ previewFactor NOTIFY previewChanged)
    Q_PROPERTY(bool previewActive READ previewActive NOTIFY previewChanged)

public:
    explicit PerAppScrollingKcm(QObject *parent, const KPluginMetaData &data);
    ~PerAppScrollingKcm() override;

    bool enabled() const;
    double defaultScrollFactor() const;
    bool showTray() const;
    QVariantList rules() const;

    bool daemonRunning() const;
    QString daemonStatusText() const;
    QString touchpadSummary() const;
    QString activeWindowText() const;
    bool canQuickAddActive() const;

    QVariantList filteredCandidates() const;

    double previewFactor() const;
    bool previewActive() const;

public Q_SLOTS:
    void refreshStatus();
    void startDaemon();

    void setEnabled(bool value);
    void setDefaultScrollFactor(double value);
    void syncDefaultFromSystem();
    void setShowTray(bool value);

    void setRuleEnabled(const QString &ruleKey, bool value);
    void setRuleScrollFactor(const QString &ruleKey, double value);
    void removeRule(const QString &ruleKey);
    void addRule(const QString &appId,
                 const QString &label,
                 const QString &captionPattern,
                 double factor);
    void quickAddActive();

    void prepareAddDialog();
    void setCandidateFilter(const QString &query);

    void previewScrollFactor(double factor);
    void endPreview();

private Q_SLOTS:
    void onDbusStateChanged(const QString &stateJson);
    void flushSaveAndReload();

Q_SIGNALS:
    void configChanged();
    void statusChanged();
    void candidatesChanged();
    void previewChanged();

private:
    struct AppRule {
        QString appId;
        double scrollFactor = 1.0;
        QString label;
        bool enabled = true;
        QString captionPattern;
    };

    static double clampFactor(double value);
    static QString normalizeAppId(const QString &rawId);
    static QString makeRuleKey(const QString &appId, const QString &captionPattern = QString());
    static QString configFilePath();

    void loadConfig();
    void saveConfig() const;
    void scheduleSave();
    void saveAndReloadNow();
    void reloadDaemon();
    void applyStateVariant(const QVariantMap &state);
    QVariantMap callDaemonStateMethod(const QString &method);
    bool isAppConfigured(const QString &appId) const;
    QVariantList scanInstalledApps() const;

    bool m_enabled = true;
    double m_defaultScrollFactor = 1.0;
    bool m_showTray = true;
    QMap<QString, AppRule> m_apps;

    bool m_hasState = false;
    QVariantMap m_lastState;

    QVariantList m_allCandidates;
    QVariantList m_filteredCandidates;
    QString m_candidateFilter;

    double m_previewFactor = 1.0;
    bool m_previewActive = false;

    QTimer m_saveTimer;
};
