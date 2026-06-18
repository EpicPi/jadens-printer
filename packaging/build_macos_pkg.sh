#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${JADENS_VERSION:-0.1.2}"
DIST_ROOT="$ROOT/dist"
RELEASE="$DIST_ROOT/JadensPrinterApp-$VERSION"
PKG_WORK="$ROOT/build/macos-pkg"
PKG_ROOT="$PKG_WORK/root"
PKG_SCRIPTS="$PKG_WORK/scripts"
PKG_PACKAGES="$PKG_WORK/packages"
PKG_APP_ROOT="$PKG_ROOT/Library/Application Support/JadensPrinterApp"
PKG_APP_PAYLOAD="$PKG_APP_ROOT/package-payload/app"
APP_COMPONENT_PKG="$PKG_PACKAGES/JadensPrinterApp-component.pkg"
DISTRIBUTION="$PKG_WORK/Distribution.xml"
OUTPUT_PKG="$DIST_ROOT/JadensPrinterApp-$VERSION.pkg"
IDENTIFIER="com.kancharlawar.jadensprinter"

export COPYFILE_DISABLE=1

if [[ ! -d "$RELEASE/app" ]]; then
  echo "Missing release payload: $RELEASE/app" >&2
  echo "Run ./packaging/package_release.sh first." >&2
  exit 1
fi

rm -rf "$PKG_WORK" "$OUTPUT_PKG"
mkdir -p "$PKG_APP_ROOT" "$PKG_APP_PAYLOAD" "$PKG_SCRIPTS" "$PKG_PACKAGES"

printf "%s\n" "$VERSION" > "$PKG_APP_ROOT/.package-version"
ditto --norsrc --noextattr --noqtn "$RELEASE/app" "$PKG_APP_PAYLOAD"

cp "$ROOT/packaging/pkg_postinstall.sh" "$PKG_SCRIPTS/postinstall"
chmod +x "$PKG_SCRIPTS/postinstall"
xattr -cr "$PKG_ROOT" "$PKG_SCRIPTS" 2>/dev/null || true

pkgbuild \
  --root "$PKG_ROOT" \
  --scripts "$PKG_SCRIPTS" \
  --identifier "$IDENTIFIER" \
  --version "$VERSION" \
  --install-location "/" \
  "$APP_COMPONENT_PKG"

productbuild \
  --synthesize \
  --package "$APP_COMPONENT_PKG" \
  "$DISTRIBUTION"

perl -0pi -e 's/(<installer-gui-script[^>]*>\n)/$1    <title>JADENS Printer App<\/title>\n/' "$DISTRIBUTION"
perl -0pi -e 's/hostArchitectures="[^"]+"/hostArchitectures="arm64"/' "$DISTRIBUTION"

productbuild \
  --distribution "$DISTRIBUTION" \
  --package-path "$PKG_PACKAGES" \
  "$OUTPUT_PKG"

echo "Built macOS installer:"
echo "  $OUTPUT_PKG"
