/*
    Per-App Touchpad Scrolling — KDE System Settings KCM
    SPDX-License-Identifier: GPL-3.0-or-later
*/

#include "kcm.h"

#include <KPluginFactory>
#include <QDBusConnection>
#include <QDBusInterface>
#include <QDBusMessage>
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QSaveFile>
#include <QSet>
#include <QStandardPaths>
#include <QTextStream>

#include <algorithm>
#include <cmath>

namespace {

constexpr auto kDaemonService = "io.github.kdeperappscrolling.Daemon";
constexpr auto kDaemonPath = "/io/github/kdeperappscrolling/Daemon";
constexpr auto kDaemonIface = "io.github.kdeperappscrolling.Daemon";

constexpr double kMinFactor = 0.1;
constexpr double kMaxFactor = 20.0;
constexpr double kDefaultFactor = 1.0;
constexpr int kSaveDebounceMs = 120;

} // namespace

K_PLUGIN_CLASS_WITH_JSON(PerAppScrollingKcm, "kcm_per_app_scrolling.json")

PerAppScrollingKcm::PerAppScrollingKcm(QObject *parent, const KPluginMetaData &data)
    : KQuickConfigModule(parent, data)
{
    setButtons(KQuickConfigModule::NoAdditionalButton);

    loadConfig();
    m_previewFactor = m_defaultScrollFactor;

    m_saveTimer.setSingleShot(true);
    m_saveTimer.setInterval(kSaveDebounceMs);
    connect(&m_saveTimer, &QTimer::timeout, this, &PerAppScrollingKcm::flushSaveAndReload);

    QDBusConnection::sessionBus().connect(
        QString::fromLatin1(kDaemonService),
        QString::fromLatin1(kDaemonPath),
        QString::fromLatin1(kDaemonIface),
        QStringLiteral("StateChanged"),
        this,
        SLOT(onDbusStateChanged(QString)));

    refreshStatus();
}

PerAppScrollingKcm::~PerAppScrollingKcm()
{
    endPreview();
}

double PerAppScrollingKcm::clampFactor(double value)
{
    if (std::isnan(value) || std::isinf(value)) {
        return kDefaultFactor;
    }
    const double clamped = std::clamp(value, kMinFactor, kMaxFactor);
    return std::round(clamped * 100.0) / 100.0;
}

QString PerAppScrollingKcm::normalizeAppId(const QString &rawId)
{
    QString cleaned = rawId.trimmed();
    if (cleaned.endsWith(QStringLiteral(".desktop"), Qt::CaseInsensitive)) {
        cleaned.chop(8);
    }
    return cleaned;
}

QString PerAppScrollingKcm::makeRuleKey(const QString &appId, const QString &captionPattern)
{
    const QString cleanedId = normalizeAppId(appId);
    const QString cleanedCap = captionPattern.trimmed().toLower();
    if (!cleanedCap.isEmpty()) {
        return cleanedId + QStringLiteral("::") + cleanedCap;
    }
    return cleanedId;
}

QString PerAppScrollingKcm::configFilePath()
{
    const QString configBase = QStandardPaths::writableLocation(QStandardPaths::GenericConfigLocation);
    return configBase + QStringLiteral("/kde-per-app-scrolling/config.json");
}

void PerAppScrollingKcm::loadConfig()
{
    m_enabled = true;
    m_defaultScrollFactor = kDefaultFactor;
    m_showTray = true;
    m_apps.clear();

    QFile file(configFilePath());
    if (!file.exists() || !file.open(QIODevice::ReadOnly)) {
        return;
    }

    const QJsonDocument doc = QJsonDocument::fromJson(file.readAll());
    if (!doc.isObject()) {
        return;
    }

    const QJsonObject root = doc.object();
    m_enabled = root.value(QStringLiteral("enabled")).toBool(true);
    m_defaultScrollFactor = clampFactor(root.value(QStringLiteral("default_scroll_factor")).toDouble(kDefaultFactor));
    m_showTray = root.value(QStringLiteral("show_tray")).toBool(true);

    const QJsonObject appsObj = root.value(QStringLiteral("apps")).toObject();
    for (auto it = appsObj.begin(); it != appsObj.end(); ++it) {
        if (!it.value().isObject()) {
            continue;
        }
        const QJsonObject ruleObj = it.value().toObject();
        const QString keyFallback = it.key().contains(QStringLiteral("::"))
            ? it.key().section(QStringLiteral("::"), 0, 0)
            : it.key();
        const QString appId = normalizeAppId(ruleObj.value(QStringLiteral("app_id")).toString(keyFallback));
        if (appId.isEmpty()) {
            continue;
        }
        AppRule rule;
        rule.appId = appId;
        rule.scrollFactor = clampFactor(ruleObj.value(QStringLiteral("scroll_factor")).toDouble(kDefaultFactor));
        rule.label = ruleObj.value(QStringLiteral("label")).toString();
        rule.enabled = ruleObj.value(QStringLiteral("enabled")).toBool(true);
        rule.captionPattern = ruleObj.value(QStringLiteral("caption_pattern")).toString().trimmed();
        m_apps.insert(makeRuleKey(rule.appId, rule.captionPattern), rule);
    }
}

void PerAppScrollingKcm::saveConfig() const
{
    const QString path = configFilePath();
    QDir().mkpath(QFileInfo(path).absolutePath());

    QJsonObject appsObj;
    QStringList keys = m_apps.keys();
    std::sort(keys.begin(), keys.end(), [](const QString &a, const QString &b) {
        return a.compare(b, Qt::CaseInsensitive) < 0;
    });

    for (const QString &key : keys) {
        const AppRule &rule = m_apps.value(key);
        QJsonObject ruleObj;
        ruleObj.insert(QStringLiteral("app_id"), rule.appId);
        ruleObj.insert(QStringLiteral("scroll_factor"), clampFactor(rule.scrollFactor));
        ruleObj.insert(QStringLiteral("label"), rule.label);
        ruleObj.insert(QStringLiteral("enabled"), rule.enabled);
        ruleObj.insert(QStringLiteral("caption_pattern"), rule.captionPattern.trimmed());
        appsObj.insert(key, ruleObj);
    }

    QJsonObject root;
    root.insert(QStringLiteral("enabled"), m_enabled);
    root.insert(QStringLiteral("default_scroll_factor"), clampFactor(m_defaultScrollFactor));
    root.insert(QStringLiteral("show_tray"), m_showTray);
    root.insert(QStringLiteral("apps"), appsObj);

    QSaveFile outFile(path);
    if (outFile.open(QIODevice::WriteOnly)) {
        outFile.write(QJsonDocument(root).toJson(QJsonDocument::Indented));
        outFile.commit();
    }
}

void PerAppScrollingKcm::scheduleSave()
{
    m_saveTimer.start();
}

void PerAppScrollingKcm::flushSaveAndReload()
{
    saveConfig();
    reloadDaemon();
}

void PerAppScrollingKcm::saveAndReloadNow()
{
    if (m_saveTimer.isActive()) {
        m_saveTimer.stop();
    }
    flushSaveAndReload();
}

void PerAppScrollingKcm::reloadDaemon()
{
    QDBusInterface iface(
        QString::fromLatin1(kDaemonService),
        QString::fromLatin1(kDaemonPath),
        QString::fromLatin1(kDaemonIface),
        QDBusConnection::sessionBus());
    if (iface.isValid()) {
        iface.call(QStringLiteral("ReloadConfig"));
    }
}

QVariantMap PerAppScrollingKcm::callDaemonStateMethod(const QString &method)
{
    QDBusInterface iface(
        QString::fromLatin1(kDaemonService),
        QString::fromLatin1(kDaemonPath),
        QString::fromLatin1(kDaemonIface),
        QDBusConnection::sessionBus());
    if (!iface.isValid()) {
        return {};
    }
    const QDBusMessage reply = iface.call(method);
    if (reply.type() == QDBusMessage::ErrorMessage || reply.arguments().isEmpty()) {
        return {};
    }
    const QJsonDocument doc = QJsonDocument::fromJson(reply.arguments().first().toString().toUtf8());
    if (!doc.isObject()) {
        return {};
    }
    return doc.object().toVariantMap();
}

void PerAppScrollingKcm::onDbusStateChanged(const QString &stateJson)
{
    const QJsonDocument doc = QJsonDocument::fromJson(stateJson.toUtf8());
    if (doc.isObject()) {
        applyStateVariant(doc.object().toVariantMap());
    }
}

void PerAppScrollingKcm::applyStateVariant(const QVariantMap &state)
{
    if (state.isEmpty()) {
        m_hasState = false;
        m_lastState.clear();
        Q_EMIT statusChanged();
        return;
    }

    m_hasState = true;
    m_lastState = state;

    const bool daemonEnabled = state.value(QStringLiteral("enabled"), true).toBool();
    const double daemonDefault = clampFactor(
        state.value(QStringLiteral("default_scroll_factor"), m_defaultScrollFactor).toDouble());
    bool cfgUpdated = false;
    if (daemonEnabled != m_enabled) {
        m_enabled = daemonEnabled;
        cfgUpdated = true;
    }
    if (!m_saveTimer.isActive() && !qFuzzyCompare(daemonDefault, m_defaultScrollFactor)) {
        m_defaultScrollFactor = daemonDefault;
        cfgUpdated = true;
    }
    if (cfgUpdated) {
        Q_EMIT configChanged();
    }

    if (!m_previewActive) {
        m_previewFactor = clampFactor(
            state.value(QStringLiteral("current_factor"), m_defaultScrollFactor).toDouble());
        Q_EMIT previewChanged();
    }

    Q_EMIT statusChanged();
}

bool PerAppScrollingKcm::enabled() const
{
    return m_enabled;
}

double PerAppScrollingKcm::defaultScrollFactor() const
{
    return clampFactor(m_defaultScrollFactor);
}

bool PerAppScrollingKcm::showTray() const
{
    return m_showTray;
}

QVariantList PerAppScrollingKcm::rules() const
{
    QList<QPair<QString, AppRule>> entries;
    entries.reserve(m_apps.size());
    for (auto it = m_apps.begin(); it != m_apps.end(); ++it) {
        entries.append(qMakePair(it.key(), it.value()));
    }
    std::sort(entries.begin(), entries.end(), [](const auto &a, const auto &b) {
        const QString nameA = a.second.label.trimmed().isEmpty() ? a.second.appId : a.second.label.trimmed();
        const QString nameB = b.second.label.trimmed().isEmpty() ? b.second.appId : b.second.label.trimmed();
        const int cmp = nameA.compare(nameB, Qt::CaseInsensitive);
        if (cmp != 0) {
            return cmp < 0;
        }
        return a.second.captionPattern.compare(b.second.captionPattern, Qt::CaseInsensitive) < 0;
    });

    QVariantList out;
    out.reserve(entries.size());
    for (const auto &pair : entries) {
        QVariantMap item;
        item.insert(QStringLiteral("rule_key"), pair.first);
        item.insert(QStringLiteral("app_id"), pair.second.appId);
        item.insert(QStringLiteral("label"), pair.second.label.trimmed());
        item.insert(QStringLiteral("caption_pattern"), pair.second.captionPattern.trimmed());
        item.insert(QStringLiteral("scroll_factor"), clampFactor(pair.second.scrollFactor));
        item.insert(QStringLiteral("enabled"), pair.second.enabled);
        out.append(item);
    }
    return out;
}

bool PerAppScrollingKcm::daemonRunning() const
{
    return m_hasState;
}

QString PerAppScrollingKcm::daemonStatusText() const
{
    if (!m_hasState) {
        return QStringLiteral("Not running — start daemon to apply rules automatically");
    }
    const bool active = m_lastState.value(QStringLiteral("enabled"), true).toBool();
    const double factor = m_lastState.value(QStringLiteral("current_factor"), 1.0).toDouble();
    return QStringLiteral("Running (%1 • %2x)")
        .arg(active ? QStringLiteral("Active") : QStringLiteral("Paused"),
             QString::number(factor, 'f', 2));
}

QString PerAppScrollingKcm::touchpadSummary() const
{
    if (!m_hasState) {
        return QStringLiteral("Unavailable while daemon is stopped");
    }
    const QVariantList touchpads = m_lastState.value(QStringLiteral("touchpads")).toList();
    if (touchpads.isEmpty()) {
        return QStringLiteral("Warning: No KWin touchpad device detected");
    }
    const double currentFactor = m_lastState.value(QStringLiteral("current_factor"), 1.0).toDouble();
    QStringList parts;
    for (const QVariant &v : touchpads) {
        const QVariantMap tp = v.toMap();
        const QString name = tp.value(QStringLiteral("name"),
                                      tp.value(QStringLiteral("sys_name"), QStringLiteral("Touchpad")))
                                 .toString();
        const double f = tp.value(QStringLiteral("scroll_factor"), currentFactor).toDouble();
        parts.append(QStringLiteral("%1 (%2x)").arg(name, QString::number(f, 'f', 2)));
    }
    return parts.join(QStringLiteral(", "));
}

QString PerAppScrollingKcm::activeWindowText() const
{
    if (!m_hasState) {
        return QStringLiteral("Unavailable while daemon is stopped");
    }
    const QVariantMap active = m_lastState.value(QStringLiteral("active_window")).toMap();
    const QString primaryId = active.value(QStringLiteral("primary_id")).toString().trimmed();
    if (primaryId.isEmpty()) {
        return QStringLiteral("Waiting for a window focus change...");
    }
    const double factor = m_lastState.value(QStringLiteral("current_factor"), 1.0).toDouble();
    const QString matched = m_lastState.value(QStringLiteral("matched_rule_id")).toString().trimmed();
    const QString ruleText = matched.isEmpty()
        ? QStringLiteral("Using default speed")
        : QStringLiteral("Matched rule: %1").arg(matched);
    return QStringLiteral("%1 • %2x (%3)")
        .arg(primaryId, QString::number(factor, 'f', 2), ruleText);
}

bool PerAppScrollingKcm::isAppConfigured(const QString &appId) const
{
    const QString needle = normalizeAppId(appId).toLower();
    for (const AppRule &rule : m_apps) {
        if (normalizeAppId(rule.appId).toLower() == needle) {
            return true;
        }
    }
    return false;
}

bool PerAppScrollingKcm::canQuickAddActive() const
{
    if (!m_hasState) {
        return false;
    }
    const QVariantMap active = m_lastState.value(QStringLiteral("active_window")).toMap();
    const QString primaryId = active.value(QStringLiteral("primary_id")).toString().trimmed();
    return !primaryId.isEmpty() && !isAppConfigured(primaryId);
}

QVariantList PerAppScrollingKcm::filteredCandidates() const
{
    return m_filteredCandidates;
}

double PerAppScrollingKcm::previewFactor() const
{
    return m_previewFactor;
}

bool PerAppScrollingKcm::previewActive() const
{
    return m_previewActive;
}

void PerAppScrollingKcm::refreshStatus()
{
    QVariantMap state = callDaemonStateMethod(QStringLiteral("RefreshTouchpads"));
    if (state.isEmpty()) {
        state = callDaemonStateMethod(QStringLiteral("GetState"));
    }
    applyStateVariant(state);
}

void PerAppScrollingKcm::startDaemon()
{
    QString exe = QStandardPaths::findExecutable(QStringLiteral("kde-per-app-scrolling-daemon"));
    if (exe.isEmpty()) {
        const QString localCandidate = QDir::homePath() + QStringLiteral("/.local/bin/kde-per-app-scrolling-daemon");
        if (QFileInfo::exists(localCandidate)) {
            exe = localCandidate;
        }
    }
    if (!exe.isEmpty()) {
        QProcess::startDetached(exe, {});
        QTimer::singleShot(600, this, &PerAppScrollingKcm::refreshStatus);
    }
}

void PerAppScrollingKcm::setEnabled(bool value)
{
    m_enabled = value;
    Q_EMIT configChanged();
    saveAndReloadNow();
}

void PerAppScrollingKcm::setDefaultScrollFactor(double value)
{
    m_defaultScrollFactor = clampFactor(value);
    Q_EMIT configChanged();
    scheduleSave();
}

void PerAppScrollingKcm::syncDefaultFromSystem()
{
    const QVariantMap state = callDaemonStateMethod(QStringLiteral("SyncDefaultFromTouchpad"));
    if (!state.isEmpty()) {
        m_defaultScrollFactor = clampFactor(
            state.value(QStringLiteral("default_scroll_factor"), m_defaultScrollFactor).toDouble());
        Q_EMIT configChanged();
        applyStateVariant(state);
    }
}

void PerAppScrollingKcm::setShowTray(bool value)
{
    m_showTray = value;
    Q_EMIT configChanged();
    saveAndReloadNow();
}

void PerAppScrollingKcm::setRuleEnabled(const QString &ruleKey, bool value)
{
    auto it = m_apps.find(ruleKey);
    if (it == m_apps.end()) {
        return;
    }
    it->enabled = value;
    Q_EMIT configChanged();
    saveAndReloadNow();
}

void PerAppScrollingKcm::setRuleScrollFactor(const QString &ruleKey, double value)
{
    auto it = m_apps.find(ruleKey);
    if (it == m_apps.end()) {
        return;
    }
    const double clamped = clampFactor(value);
    it->scrollFactor = clamped;
    Q_EMIT configChanged();
    scheduleSave();
    previewScrollFactor(clamped);
}

void PerAppScrollingKcm::removeRule(const QString &ruleKey)
{
    if (m_apps.remove(ruleKey) > 0) {
        Q_EMIT configChanged();
        Q_EMIT statusChanged();
        saveAndReloadNow();
    }
}

void PerAppScrollingKcm::addRule(const QString &appId,
                                 const QString &label,
                                 const QString &captionPattern,
                                 double factor)
{
    const QString cleanedId = normalizeAppId(appId);
    if (cleanedId.isEmpty()) {
        return;
    }
    const QString cleanedCap = captionPattern.trimmed();
    const QString ruleKey = makeRuleKey(cleanedId, cleanedCap);

    AppRule rule;
    rule.appId = cleanedId;
    rule.scrollFactor = clampFactor(factor);
    rule.label = label.trimmed();
    rule.enabled = true;
    rule.captionPattern = cleanedCap;

    m_apps.insert(ruleKey, rule);
    Q_EMIT configChanged();
    Q_EMIT statusChanged();
    saveAndReloadNow();
}

void PerAppScrollingKcm::quickAddActive()
{
    if (!m_hasState) {
        return;
    }
    const QVariantMap active = m_lastState.value(QStringLiteral("active_window")).toMap();
    const QString primaryId = active.value(QStringLiteral("primary_id")).toString().trimmed();
    if (!primaryId.isEmpty()) {
        addRule(primaryId, QString(), QString(), m_defaultScrollFactor);
    }
}

QVariantList PerAppScrollingKcm::scanInstalledApps() const
{
    const QString dataHome = QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation);
    const QStringList dirs = {
        dataHome + QStringLiteral("/applications"),
        QStringLiteral("/usr/share/applications"),
        QStringLiteral("/var/lib/flatpak/exports/share/applications"),
    };

    struct Entry {
        QString appId;
        QString name;
        QString iconName;
    };

    QSet<QString> seen;
    QList<Entry> entries;

    for (const QString &dirPath : dirs) {
        QDir dir(dirPath);
        if (!dir.exists()) {
            continue;
        }
        const QStringList files = dir.entryList({QStringLiteral("*.desktop")}, QDir::Files, QDir::Name);
        for (const QString &fileName : files) {
            QFile f(dir.filePath(fileName));
            if (!f.open(QIODevice::ReadOnly | QIODevice::Text)) {
                continue;
            }
            bool inDesktopEntry = false;
            QString type;
            bool noDisplay = false;
            bool hidden = false;
            QString name;
            QString iconName;
            QString startupWmClass;

            QTextStream in(&f);
            while (!in.atEnd()) {
                const QString line = in.readLine().trimmed();
                if (line.isEmpty() || line.startsWith(QLatin1Char('#'))) {
                    continue;
                }
                if (line.startsWith(QLatin1Char('['))) {
                    if (inDesktopEntry) {
                        break;
                    }
                    inDesktopEntry = (line == QStringLiteral("[Desktop Entry]"));
                    continue;
                }
                if (!inDesktopEntry) {
                    continue;
                }
                const int eq = line.indexOf(QLatin1Char('='));
                if (eq <= 0) {
                    continue;
                }
                const QString key = line.left(eq).trimmed();
                const QString val = line.mid(eq + 1).trimmed();
                if (key == QStringLiteral("Type")) {
                    type = val;
                } else if (key == QStringLiteral("NoDisplay")) {
                    noDisplay = (val.compare(QStringLiteral("true"), Qt::CaseInsensitive) == 0);
                } else if (key == QStringLiteral("Hidden")) {
                    hidden = (val.compare(QStringLiteral("true"), Qt::CaseInsensitive) == 0);
                } else if (key == QStringLiteral("Name")) {
                    name = val;
                } else if (key == QStringLiteral("Icon")) {
                    iconName = val;
                } else if (key == QStringLiteral("StartupWMClass")) {
                    startupWmClass = normalizeAppId(val);
                }
            }

            if (type != QStringLiteral("Application") || noDisplay || hidden || name.isEmpty()) {
                continue;
            }
            const QString stem = normalizeAppId(QFileInfo(fileName).completeBaseName());
            const QString appId = startupWmClass.isEmpty() ? stem : startupWmClass;
            if (appId.isEmpty()) {
                continue;
            }
            const QString lowerId = appId.toLower();
            if (seen.contains(lowerId)) {
                continue;
            }
            seen.insert(lowerId);
            entries.append({appId, name, iconName.isEmpty() ? QStringLiteral("application-x-executable") : iconName});
        }
    }

    std::sort(entries.begin(), entries.end(), [](const Entry &a, const Entry &b) {
        const int cmp = a.name.compare(b.name, Qt::CaseInsensitive);
        return cmp != 0 ? (cmp < 0) : (a.appId.compare(b.appId, Qt::CaseInsensitive) < 0);
    });

    QVariantList result;
    result.reserve(entries.size());
    for (const Entry &e : entries) {
        QVariantMap map;
        map.insert(QStringLiteral("app_id"), e.appId);
        map.insert(QStringLiteral("label"), e.name);
        map.insert(QStringLiteral("subtitle"), e.appId);
        map.insert(QStringLiteral("icon_name"), e.iconName);
        map.insert(QStringLiteral("configured"), isAppConfigured(e.appId));
        result.append(map);
    }
    return result;
}

void PerAppScrollingKcm::prepareAddDialog()
{
    m_allCandidates.clear();
    QSet<QString> seen;

    if (m_hasState) {
        const QVariantList recent = m_lastState.value(QStringLiteral("recent_apps")).toList();
        for (const QVariant &v : recent) {
            const QVariantMap item = v.toMap();
            const QString appId = item.value(QStringLiteral("app_id")).toString().trimmed();
            if (appId.isEmpty() || seen.contains(appId.toLower())) {
                continue;
            }
            seen.insert(appId.toLower());
            const QString caption = item.value(QStringLiteral("caption")).toString().trimmed();
            const QString subtitle = caption.isEmpty()
                ? QStringLiteral("Recent window • %1").arg(appId)
                : QStringLiteral("Recent • %1 — %2").arg(appId, caption.left(40));

            QVariantMap candidate;
            candidate.insert(QStringLiteral("app_id"), appId);
            candidate.insert(QStringLiteral("label"), appId);
            candidate.insert(QStringLiteral("subtitle"), subtitle);
            candidate.insert(QStringLiteral("icon_name"), QStringLiteral("window-new"));
            candidate.insert(QStringLiteral("configured"), isAppConfigured(appId));
            m_allCandidates.append(candidate);
        }
    }

    const QVariantList installed = scanInstalledApps();
    for (const QVariant &v : installed) {
        const QVariantMap item = v.toMap();
        const QString lowerId = item.value(QStringLiteral("app_id")).toString().toLower();
        if (seen.contains(lowerId)) {
            continue;
        }
        seen.insert(lowerId);
        m_allCandidates.append(item);
    }

    m_candidateFilter.clear();
    m_filteredCandidates = m_allCandidates;
    Q_EMIT candidatesChanged();
}

void PerAppScrollingKcm::setCandidateFilter(const QString &query)
{
    m_candidateFilter = query.trimmed().toLower();
    if (m_candidateFilter.isEmpty()) {
        m_filteredCandidates = m_allCandidates;
    } else {
        m_filteredCandidates.clear();
        for (const QVariant &v : m_allCandidates) {
            const QVariantMap item = v.toMap();
            const QString appId = item.value(QStringLiteral("app_id")).toString().toLower();
            const QString label = item.value(QStringLiteral("label")).toString().toLower();
            const QString subtitle = item.value(QStringLiteral("subtitle")).toString().toLower();
            if (appId.contains(m_candidateFilter)
                || label.contains(m_candidateFilter)
                || subtitle.contains(m_candidateFilter)) {
                m_filteredCandidates.append(item);
            }
        }
    }
    Q_EMIT candidatesChanged();
}

void PerAppScrollingKcm::previewScrollFactor(double factor)
{
    const double clamped = clampFactor(factor);
    m_previewFactor = clamped;
    m_previewActive = true;
    Q_EMIT previewChanged();

    QDBusInterface iface(
        QString::fromLatin1(kDaemonService),
        QString::fromLatin1(kDaemonPath),
        QString::fromLatin1(kDaemonIface),
        QDBusConnection::sessionBus());
    if (iface.isValid()) {
        iface.call(QStringLiteral("ApplyFactorNow"), clamped);
    }
}

void PerAppScrollingKcm::endPreview()
{
    if (!m_previewActive) {
        return;
    }
    m_previewActive = false;
    reloadDaemon();
    const QVariantMap state = callDaemonStateMethod(QStringLiteral("GetState"));
    applyStateVariant(state);
}

#include "kcm.moc"
