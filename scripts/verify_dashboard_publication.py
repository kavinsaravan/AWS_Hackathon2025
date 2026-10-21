#!/usr/bin/env python3
"""Wait for the existing Vercel Git integration to publish all snapshot files."""
import argparse
import hashlib
import json
import time
from pathlib import Path

import requests

FILES = ('tableau/manifest.json', 'tableau/sf-crime-incidents.csv', 'safety-analytics.json')


def verify(origin, public_dir, timeout=900):
    expected = {name: hashlib.sha256((public_dir / name).read_bytes()).hexdigest() for name in FILES}
    deadline = time.monotonic() + timeout
    while True:
        try:
            for name, digest in expected.items():
                response = requests.get(origin.rstrip('/') + '/' + name,
                    params={'refresh_check': time.time_ns()}, headers={'Cache-Control': 'no-cache'}, timeout=30)
                response.raise_for_status()
                if hashlib.sha256(response.content).hexdigest() != digest:
                    raise ValueError('Production still serves a different snapshot')
            manifest = json.loads((public_dir / FILES[0]).read_text())
            print(f"Production verified: {manifest['rows']} records, {manifest['refreshed_at_utc']}")
            return
        except (requests.RequestException, ValueError):
            if time.monotonic() >= deadline:
                raise RuntimeError('Production snapshot did not match within the deployment deadline') from None
            time.sleep(min(20, max(0, deadline - time.monotonic())))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', default='https://aws-hackathon2025.vercel.app')
    parser.add_argument('--public-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'public')
    parser.add_argument('--timeout', type=int, default=900)
    args = parser.parse_args()
    verify(args.origin, args.public_dir, args.timeout)
