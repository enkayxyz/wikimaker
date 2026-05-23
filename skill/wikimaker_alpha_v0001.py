#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 3:
        print('Usage: wikimaker_alpha_v0001.py <corpus_root> <output_root>')
        sys.exit(1)

    script = Path(__file__).with_name('generate_alpha_v0001.py')
    cmd = [sys.executable, str(script), sys.argv[1], sys.argv[2]]
    raise SystemExit(subprocess.call(cmd))


if __name__ == '__main__':
    main()
