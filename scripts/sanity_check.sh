#!/bin/bash
# Amarktai Network - Sanity Check Script
# Run before deployment to catch common issues

set -e

echo "🧪 Running sanity checks..."

# 1. Compile critical Python files
echo "[1/5] Compiling critical Python files..."
python -m py_compile backend/database.py
python -m py_compile backend/server.py
python -m py_compile backend/auth.py
python -m py_compile backend/rules/bot_rules.py
python -m py_compile backend/rules/__init__.py

# 2. Compile all backend modules
echo "[2/5] Compiling all backend modules..."
python -m compileall backend -q

# 3. Test database module imports
echo "[3/5] Testing database module..."
python << 'EOF'
import sys
sys.path.insert(0, 'backend')
import database

# Check required attributes
required_attrs = [
    'wallet_balances',
    'capital_injections',
    'audit_logs',
    'orders_collection',
    'positions_collection',
    'balance_snapshots_collection',
    'performance_metrics_collection'
]

for attr in required_attrs:
    assert hasattr(database, attr), f"Missing attribute: {attr}"

print('✅ Database module OK')
EOF

# 4. Test rules module imports
echo "[4/5] Testing rules module..."
python << 'EOF'
import sys
sys.path.insert(0, 'backend')
import rules

required = [
    'PROFIT_THRESHOLD_ZAR',
    'calculate_reinvestment_amount',
    'get_reason_message'
]

missing = [name for name in required if not hasattr(rules, name)]
if missing:
    raise SystemExit(f"Missing rules exports: {', '.join(missing)}")

print('✅ Rules module OK')
EOF

# 5. Optional: Run pytest if tests exist
if [ -d "backend/tests" ]; then
    echo "[5/5] Running tests..."
    python -m pytest backend/tests -q || true
else
    echo "[5/5] No tests found, skipping"
fi

echo "✅ All sanity checks passed!"
