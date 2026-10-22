#!/usr/bin/env bash
# Build the offline deployment bundle on the internet-connected dev PC.
#
#   scripts/build-bundle.sh [VERSION]
#
# Output: dist-bundle/LanGamesHub-VERSION/ and a .zip of it, containing the backend,
# the built frontend, a wheelhouse with every pinned dependency for the target platform,
# Windows scripts, docs and .env.example. Copy the zip to the isolated host.
#
# WHEEL_PLATFORM (default win_amd64) selects the wheel platform; set e.g.
# WHEEL_PLATFORM=macosx_11_0_arm64 to build a bundle for rehearsing the install locally.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="${1:-$(date +%Y.%m.%d)}"
PLATFORM="${WHEEL_PLATFORM:-win_amd64}"
NAME="LanGamesHub-${VERSION}"
OUT="$ROOT/dist-bundle/$NAME"
PIP=(uvx --python 3.11 pip)

echo "==> Building $NAME for $PLATFORM"
rm -rf "$OUT" "$OUT.zip"
mkdir -p "$OUT"

echo "==> Frontend production build"
(cd "$ROOT/frontend" && npm ci --no-audit --no-fund && npm run build)
# Allowed: XML namespace identifiers and React's error-decoder link text, which are
# strings inside the bundle and are never fetched by the browser.
if grep -rEo 'https?://[^"'"'"' )]+' "$ROOT/frontend/dist" \
    | grep -vE 'www\.w3\.org/|react\.dev/errors/' ; then
  echo "ERROR: the frontend build references remote URLs (see above)" >&2
  exit 1
fi

echo "==> Wheelhouse (pinned versions)"
mkdir -p "$OUT/wheelhouse"
BUILD_DIR="$(mktemp -d)"
grep -vE '^[[:space:]]*(#|$)' "$ROOT/backend/requirements-windows.txt" | sed 's/[[:space:]]*;.*//' |
while read -r spec; do
  if "${PIP[@]}" download --quiet --only-binary=:all: --no-deps \
      --platform "$PLATFORM" --python-version 3.11 --implementation cp \
      "$spec" -d "$OUT/wheelhouse" 2>/dev/null; then
    continue
  fi
  # No published wheel (e.g. chess ships only an sdist): build one from the pinned
  # source. Only pure-Python results are acceptable, since they run on any platform.
  echo "    $spec: no binary wheel published; building a universal wheel from source"
  "${PIP[@]}" wheel --quiet --no-deps --no-binary :all: "$spec" -w "$BUILD_DIR"
  for wheel in "$BUILD_DIR"/*.whl; do
    case "$wheel" in
      *-py3-none-any.whl|*-py2.py3-none-any.whl) mv "$wheel" "$OUT/wheelhouse/" ;;
      *) echo "ERROR: $spec built a platform-specific wheel ($wheel); cannot use it" >&2; exit 1 ;;
    esac
  done
done
rm -rf "$BUILD_DIR"

echo "==> Verifying the wheelhouse installs with no index (offline)"
CHECK_DIR="$(mktemp -d)"
"${PIP[@]}" install --quiet --dry-run --ignore-installed --no-index \
  --find-links "$OUT/wheelhouse" --only-binary=:all: \
  --platform "$PLATFORM" --python-version 3.11 --implementation cp \
  --target "$CHECK_DIR" -r "$ROOT/backend/requirements-windows.txt"
rm -rf "$CHECK_DIR"

echo "==> Copying application files"
mkdir -p "$OUT/backend" "$OUT/frontend" "$OUT/windows"
cp -R "$ROOT/backend/app" "$ROOT/backend/alembic" "$OUT/backend/"
cp "$ROOT/backend/alembic.ini" "$ROOT/backend/requirements.in" \
   "$ROOT/backend/requirements.txt" "$ROOT/backend/requirements-windows.txt" "$OUT/backend/"
find "$OUT/backend" -name '__pycache__' -type d -prune -exec rm -rf {} +
cp -R "$ROOT/frontend/dist" "$OUT/frontend/dist"
cp -R "$ROOT/docs" "$OUT/docs"
cp "$ROOT/README.md" "$ROOT/.env.example" "$OUT/"
for script in "$ROOT"/deploy/windows/*.bat; do
  # Windows batch files must use CRLF line endings.
  sed 's/\r$//; s/$/\r/' "$script" > "$OUT/windows/$(basename "$script")"
done

echo "==> Manifest"
(cd "$OUT" && find . -type f ! -name MANIFEST.sha256 -print0 | sort -z \
  | xargs -0 shasum -a 256 > MANIFEST.sha256)

echo "==> Zip"
(cd "$ROOT/dist-bundle" && rm -f "$NAME.zip" && zip -qr "$NAME.zip" "$NAME")
echo "Bundle ready: $OUT.zip ($(du -h "$OUT.zip" | cut -f1))"
