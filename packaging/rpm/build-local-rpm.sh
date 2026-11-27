#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SPEC_PATH="$REPO_ROOT/packaging/rpm/kde-per-app-scrolling.spec"
RPMBUILD_DIR="${RPMBUILD_DIR:-$HOME/rpmbuild}"

if ! command -v rpmbuild >/dev/null 2>&1; then
    echo "rpmbuild is required. Install it on Fedora with:"
    echo "  sudo dnf install rpm-build"
    exit 1
fi

VERSION="$(awk '/^Version:/ { print $2; exit }' "$SPEC_PATH")"
NAME="kde-per-app-scrolling"
TARBALL="$RPMBUILD_DIR/SOURCES/${NAME}-${VERSION}.tar.gz"

mkdir -p "$RPMBUILD_DIR"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}

cp "$SPEC_PATH" "$RPMBUILD_DIR/SPECS/${NAME}.spec"

tar \
    --exclude=".git" \
    --exclude="kcm/build" \
    --exclude="rpmbuild" \
    --exclude="__pycache__" \
    --exclude="*.pyc" \
    --transform="s,^\.,${NAME}-${VERSION}," \
    -czf "$TARBALL" \
    -C "$REPO_ROOT" .

rpmbuild --define "_topdir $RPMBUILD_DIR" -ba "$RPMBUILD_DIR/SPECS/${NAME}.spec"

echo ""
echo "RPM build complete:"
find "$RPMBUILD_DIR/RPMS" "$RPMBUILD_DIR/SRPMS" -name '*.rpm' -print
