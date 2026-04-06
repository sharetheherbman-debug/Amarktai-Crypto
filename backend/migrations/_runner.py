"""
Migration auto-runner.
Discovers and runs all migration scripts in this directory in alphabetical order.
Each script must expose: async def run_migration(db) -> dict  OR  async def run_startup_migrations(db)
All migrations must be idempotent.
"""
import os
import importlib
import logging
from datetime import datetime, timezone
from typing import List, Dict

logger = logging.getLogger(__name__)

# Ordered list of migration module names (alphabetical order)
MIGRATION_MODULES = [
    "migrations.fix_user_id_field",
    "migrations.add_lifecycle_fields",
    "migrations.add_capital_tracking",
    "migrations.migrate_api_keys_user_id",
    "migrations.migrate_production_update",
    "migrations.quarantine_invalid_platforms",
    "migrations.repair_baseline_fields",
]

_run_results: List[Dict] = []
_ran_on_startup: bool = False
_last_run_ts: str | None = None


async def run_all_migrations(db) -> List[Dict]:
    """Run all migrations in order. Idempotent."""
    global _run_results, _ran_on_startup, _last_run_ts

    if os.getenv("RUN_MIGRATIONS_ON_STARTUP", "true").lower() != "true":
        logger.info("RUN_MIGRATIONS_ON_STARTUP=false — skipping migration runner")
        return []

    results = []
    _ran_on_startup = True
    _last_run_ts = datetime.now(timezone.utc).isoformat()

    for module_name in MIGRATION_MODULES:
        result = {"module": module_name, "status": "skipped", "error": None}
        try:
            mod = importlib.import_module(module_name)
            # Prefer run_migration(db) if it exists, fall back to run_startup_migrations(db)
            func = getattr(mod, "run_migration", None) or getattr(mod, "run_startup_migrations", None)
            if func is None:
                result["status"] = "no_entry_point"
                logger.debug(f"Migration {module_name}: no run_migration() found, skipping")
            else:
                await func(db)
                result["status"] = "ok"
                logger.info(f"✅ Migration {module_name}: applied")
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            logger.warning(f"⚠️ Migration {module_name} failed (non-fatal): {e}")
        results.append(result)

    _run_results = results
    ok = sum(1 for r in results if r["status"] == "ok")
    err = sum(1 for r in results if r["status"] == "error")
    logger.info(f"Migration runner complete: {ok} ok, {err} errors, {len(results)-ok-err} skipped")
    return results


def get_migration_status() -> Dict:
    return {
        "ran_on_startup": _ran_on_startup,
        "last_run_ts": _last_run_ts,
        "applied": [r["module"] for r in _run_results if r["status"] == "ok"],
        "errors": [{"module": r["module"], "error": r["error"]} for r in _run_results if r["status"] == "error"],
    }
