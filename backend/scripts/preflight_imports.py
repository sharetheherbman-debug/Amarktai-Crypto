import sys
import traceback
from pathlib import Path


def main() -> int:
    try:
        backend_root = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(backend_root))
        import server  # noqa: F401
        print("OK")
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
