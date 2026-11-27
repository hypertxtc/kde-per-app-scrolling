cmake_minimum_required(VERSION 3.20)
project(kcm_per_app_scrolling VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(ECM 6.0.0 REQUIRED NO_MODULE)
set(CMAKE_MODULE_PATH ${ECM_MODULE_PATH})

include(KDEInstallDirs)
include(KDECMakeSettings)
include(KDECompilerSettings NO_POLICY_SCOPE)

find_package(Qt6 REQUIRED COMPONENTS Core Gui Qml Quick DBus)
find_package(KF6 REQUIRED COMPONENTS KCMUtils CoreAddons I18n)

kcmutils_add_qml_kcm(kcm_per_app_scrolling
    SOURCES
        kcm.cpp
        kcm.h
)

target_link_libraries(kcm_per_app_scrolling PRIVATE
    Qt6::Core
    Qt6::Gui
    Qt6::Qml
    Qt6::Quick
    Qt6::DBus
    KF6::KCMUtils
    KF6::KCMUtilsQuick
    KF6::CoreAddons
    KF6::I18n
)
