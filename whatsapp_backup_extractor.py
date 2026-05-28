from __future__ import annotations

from contextlib import redirect_stderr
from pathlib import Path
import io
import os
import runpy
import sys
import warnings

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional convenience dependency
    def load_dotenv(*args, **kwargs):
        return False

PROJECT_ROOT = Path(__file__).resolve().parent
CODE_ROOT = PROJECT_ROOT / "code"

load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(Path.home() / ".wikimaker" / ".env", override=False)

os.environ.setdefault("PYTHONWARNINGS", "ignore")
warnings.filterwarnings("ignore")

if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))


def main(argv: list[str] | None = None) -> int:
    stderr_buffer = io.StringIO()
    try:
        with redirect_stderr(stderr_buffer):
            runpy.run_path(str(CODE_ROOT / "whatsapp_backup_extractor.py"), run_name="__main__")
        return 0
    except KeyboardInterrupt:
        print("WhatsApp extractor interrupted by user.", file=sys.stderr)
        return 130
    except Exception:
        captured = stderr_buffer.getvalue()
        if captured:
            print(captured, file=sys.stderr, end="")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
