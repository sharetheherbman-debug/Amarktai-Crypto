#!/usr/bin/env python3
"""
Run nightly learning loop (manual or systemd).
"""

import argparse
import asyncio
import logging
import sys

import database
from services.learning_loop import learning_loop


async def main() -> int:
    parser = argparse.ArgumentParser(description="Run nightly learning loop")
    parser.add_argument("--dry-run", action="store_true", help="Run without applying changes")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    try:
        await database.connect()
        await learning_loop.run_nightly_learning(dry_run=args.dry_run)
        return 0
    except Exception as exc:
        logging.error("Learning loop failed: %s", exc)
        return 1
    finally:
        try:
            if database.client:
                database.client.close()
        except Exception:
            pass


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
