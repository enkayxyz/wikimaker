from __future__ import annotations

from contextlib import redirect_stderr
from pathlib import Path
import io
import os
import runpy
import sys
import warnings

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
CODE_ROOT = PROJECT_ROOT / "code"

load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(Path.home() / ".hermes" / ".env", override=False)

# Keep the console readable during large corpus runs.
# The ADK + authlib stack is still somewhat noisy in this environment.
os.environ.setdefault("PYTHONWARNINGS", "ignore")
warnings.filterwarnings("ignore")

# Avoid duplicate Gemini alias noise while leaving the OpenAI-compatible key
# available to WikiMaker's Osaurus/OpenAI-compatible config path.
os.environ.pop("GEMINI_API_KEY", None)

if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))


def main(argv: list[str] | None = None) -> int:
    stderr_buffer = io.StringIO()
    try:
        with redirect_stderr(stderr_buffer):
            runpy.run_path(str(CODE_ROOT / "wikimaker.py"), run_name="__main__")
        return 0
    except KeyboardInterrupt:
        print("WikiMaker interrupted by user.", file=sys.stderr)
        return 130
    except Exception:
        captured = stderr_buffer.getvalue()
        if captured:
            print(captured, file=sys.stderr, end="")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
