#!/bin/bash
# Package only the isolated daily-export function and its HTTP dependency.
set -euo pipefail
ANALYTICS_PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ANALYTICS_OUTPUT="${1:-$ANALYTICS_PROJECT_ROOT/backend/lambda-daily-analytics.zip}"
python3 - "$ANALYTICS_PROJECT_ROOT" "$ANALYTICS_OUTPUT" <<'PY'
import subprocess,sys,tempfile
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
root,output=Path(sys.argv[1]),Path(sys.argv[2]).resolve()
with tempfile.TemporaryDirectory(prefix='safepath-daily-package-') as folder:
    target=Path(folder)
    subprocess.run([sys.executable,'-m','pip','install','--only-binary=:all:','--platform','manylinux2014_x86_64',
                    '--python-version','3.11','--implementation','cp','--target',folder,'requests'],check=True)
    with ZipFile(output,'w',ZIP_DEFLATED) as archive:
        for item in target.rglob('*'):
            if item.is_file() and '__pycache__' not in item.parts:archive.write(item,item.relative_to(target))
        for filename in ['analytics_snapshot.py','lambda_daily_analytics.py']:archive.write(root/'backend'/filename,filename)
print('Packaged daily analytics:',output)
PY
