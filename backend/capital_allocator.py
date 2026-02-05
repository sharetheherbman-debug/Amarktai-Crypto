"""
DEPRECATED - DO NOT USE - USE engines/capital_allocator.py INSTEAD

This file exists for backwards compatibility only.
All functionality has been moved to /backend/engines/capital_allocator.py

The new system:
- Enforces bot caps per exchange (Luno: 5, others: 10) 
- Implements profit-gated auto-growth (>= R1000 per exchange)
- Handles reinvestment when at cap
- Uses backend/rules/bot_rules.py for all business rules
"""

# Import the new allocator
from engines.capital_allocator import capital_allocator

# Re-export for compatibility
__all__ = ['capital_allocator']
