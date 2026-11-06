#!/usr/bin/env bash
# Download the pinned official validators into tools/ (gitignored).
# Versions are pinned here and in the README; bump them deliberately.
set -euo pipefail
KOSIT_VERSION="${KOSIT_VERSION:-1.6.3}"
XR_CONFIG_TAG="${XR_CONFIG_TAG:-v2026-08-31}"
XR_CONFIG_ZIP="${XR_CONFIG_ZIP:-xrechnung-3.0.2-validator-configuration-2026-08-31.zip}"
MUSTANG_VERSION="${MUSTANG_VERSION:-2.26.0}"

TOOLS="${TOOLS_DIR:-$(cd "$(dirname "$0")/.." && pwd)/tools}"
mkdir -p "$TOOLS"
cd "$TOOLS"

if [ ! -f "validator-${KOSIT_VERSION}-standalone.jar" ]; then
  curl -fsSL -o "validator-${KOSIT_VERSION}-standalone.jar" \
    "https://github.com/itplr-kosit/validator/releases/download/v${KOSIT_VERSION}/validator-${KOSIT_VERSION}-standalone.jar"
fi
if [ ! -d xrechnung-config ]; then
  curl -fsSL -o xr-config.zip \
    "https://github.com/itplr-kosit/validator-configuration-xrechnung/releases/download/${XR_CONFIG_TAG}/${XR_CONFIG_ZIP}"
  mkdir -p xrechnung-config && (cd xrechnung-config && unzip -q ../xr-config.zip) && rm xr-config.zip
fi
if [ ! -f "Mustang-CLI-${MUSTANG_VERSION}.jar" ]; then
  curl -fsSL -o "Mustang-CLI-${MUSTANG_VERSION}.jar" \
    "https://github.com/ZUGFeRD/mustangproject/releases/download/core-${MUSTANG_VERSION}/Mustang-CLI-${MUSTANG_VERSION}.jar"
fi
ln -sf "validator-${KOSIT_VERSION}-standalone.jar" validator.jar 2>/dev/null || cp "validator-${KOSIT_VERSION}-standalone.jar" validator.jar
ln -sf "Mustang-CLI-${MUSTANG_VERSION}.jar" mustang.jar 2>/dev/null || cp "Mustang-CLI-${MUSTANG_VERSION}.jar" mustang.jar
echo "Validators ready in $TOOLS"
