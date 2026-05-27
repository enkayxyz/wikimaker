#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path("/Users/enkay/dev/wikimaker")
RUNNER = REPO_ROOT / "wikimaker.py"
CONDA_ENV = "wikimaker"


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: wikimaker_alpha_v0001.py <corpus_root> [output_root] [extra wikimaker.py args...]")
        print("   or: wikimaker_alpha_v0001.py --corpus-root <path> [wikimaker.py args...]")
        sys.exit(1)

    if args[0].startswith("-"):
        wikimaker_args = args
    else:
        wikimaker_args = ["--corpus-root", args[0]]
        rest = args[1:]
        if rest and not rest[0].startswith("-"):
            wikimaker_args.extend(["--output-root", rest[0]])
            rest = rest[1:]
        wikimaker_args.extend(rest)

    if not RUNNER.exists():
        print(f"WikiMaker runner not found: {RUNNER}", file=sys.stderr)
        sys.exit(2)

    cmd = ["conda", "run", "-n", CONDA_ENV, "python", str(RUNNER), *wikimaker_args]
    raise SystemExit(subprocess.call(cmd))


if __name__ == '__main__':
    main()
