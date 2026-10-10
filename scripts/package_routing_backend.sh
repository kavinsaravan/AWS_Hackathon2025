#!/bin/bash
# Package the data-fetching and route-scoring endpoints for Python 3.11 Lambda.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PACKAGE_DIR="$(mktemp -d)"
OUTPUT="${1:-$PROJECT_ROOT/backend/lambda-routing.zip}"
python3 -m pip install --only-binary=:all: --platform manylinux2014_x86_64 \
  --python-version 3.11 --implementation cp --target "$PACKAGE_DIR" requests
cp "$PROJECT_ROOT/backend/lambda_fetch_api.py" "$PROJECT_ROOT/backend/path_risk_analysis.py" \
   "$PROJECT_ROOT/backend/route_scoring.py" "$PROJECT_ROOT/backend/safety_data_store.py" "$PACKAGE_DIR/"
python3 - "$PACKAGE_DIR" "$OUTPUT" <<'PY'
import sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
source, output = Path(sys.argv[1]), Path(sys.argv[2]).resolve()
with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
    for path in source.rglob('*'):
        if path.is_file() and '__pycache__' not in path.parts:
            archive.write(path, path.relative_to(source))
print(f'Packaged Lambda: {output}')
PY
