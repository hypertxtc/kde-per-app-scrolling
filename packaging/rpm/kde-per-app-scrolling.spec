Name:           kde-per-app-scrolling
Version:        0.1.1
Release:        1%{?dist}
Summary:        Per-application touchpad scroll speed for KDE Plasma 6

License:        GPL-3.0-or-later
URL:            https://github.com/hypertxtc/kde-per-app-scrolling
Source0:        %{name}-%{version}.tar.gz

BuildRequires:  cmake >= 3.20
BuildRequires:  extra-cmake-modules
BuildRequires:  gcc-c++
BuildRequires:  kf6-kcmutils-devel
BuildRequires:  kf6-kcoreaddons-devel
BuildRequires:  kf6-ki18n-devel
BuildRequires:  python3-devel
BuildRequires:  qt6-qtbase-devel
BuildRequires:  qt6-qtdeclarative-devel
BuildRequires:  systemd-rpm-macros

Requires:       kf6-kirigami
Requires:       kf6-kirigami-addons
Requires:       kwin
Requires:       python3
Requires:       python3-dbus
Requires:       python3-gobject-base

%description
Allows setting touchpad scroll speed (scrollFactor) on a per-application
(and per-window-title) basis in KDE Plasma 6 (Wayland). Includes a KWin
script, a background D-Bus daemon with a KDE System Tray icon, and a native
KDE System Settings module under Mouse & Touchpad.

%prep
%autosetup -n %{name}-%{version}

%build
cmake -B kcm/build -S kcm \
    -DCMAKE_INSTALL_PREFIX=%{_prefix} \
    -DKDE_INSTALL_USE_QT_SYS_PATHS=ON \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build kcm/build %{?_smp_mflags}

%check
python3 -m unittest discover -s tests -v

%install
DESTDIR=%{buildroot} cmake --install kcm/build

install -d %{buildroot}%{python3_sitelib}
cp -a src/kde_per_app_scrolling %{buildroot}%{python3_sitelib}/
find %{buildroot}%{python3_sitelib}/kde_per_app_scrolling -name '__pycache__' -exec rm -rf {} +

install -Dpm 0755 bin/kde-per-app-scrolling-daemon %{buildroot}%{_bindir}/kde-per-app-scrolling-daemon

install -d %{buildroot}%{_datadir}/kwin/scripts/%{name}
cp -a kwin-script/. %{buildroot}%{_datadir}/kwin/scripts/%{name}/

install -d %{buildroot}%{_userunitdir}
sed -e 's|%h/.local/bin/|%{_bindir}/|g' data/kde-per-app-scrolling.service \
    > %{buildroot}%{_userunitdir}/kde-per-app-scrolling.service

%post
%systemd_user_post %{name}.service

%preun
%systemd_user_preun %{name}.service

%postun
%systemd_user_postun_with_restart %{name}.service

%files
%doc README.md
%{_bindir}/kde-per-app-scrolling-daemon
%{python3_sitelib}/kde_per_app_scrolling/
%{_libdir}/qt6/plugins/plasma/kcms/systemsettings/kcm_per_app_scrolling.so
%{_datadir}/applications/kcm_per_app_scrolling.desktop
%{_datadir}/kwin/scripts/%{name}/
%{_userunitdir}/kde-per-app-scrolling.service

%changelog
* Fri Nov 27 2026 kde-per-app-scrolling <noreply@example.com> - 0.1.1-1
- Remove standalone GUI app and ship only the KDE System Settings KCM

* Fri Nov 27 2026 kde-per-app-scrolling <noreply@example.com> - 0.1.0-1
- Initial Fedora RPM package with KWin script, daemon, tray, and Plasma 6 KCM
