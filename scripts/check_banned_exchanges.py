#!/usr/bin/env python3
"""
VALR/OVEX Ban Check - CI Script
================================
Ensures VALR and OVEX exchanges are not reintroduced into the codebase.
Only acceptable mentions are in:
- Test files checking for their absence
- Documentation/archives
- This script itself

Exit codes:
    0 - No violations found
    1 - VALR/OVEX found in active code

Usage:
    python scripts/check_banned_exchanges.py
"""

import sys
import re
from pathlib import Path

# Root directory
repo_root = Path(__file__).parent.parent

# Patterns to search for
BANNED_PATTERNS = [
    r'\bvalr\b',
    r'\bVALR\b', 
    r'\bovex\b',
    r'\bOVEX\b'
]

# Allowed locations (where these terms can appear for checking/documentation)
ALLOWED_PATHS = [
    '_archive',
    'docs/archive',
    'test_',  # Test files
    'check_banned_exchanges.py',  # This script
    'audit_repo.py',  # Audit script
    'remove_valr_ovex.sh',  # Removal script
    'verify_go_live.sh',  # Verification script
]

# Files to check
EXTENSIONS = ['.py', '.js', '.jsx', '.ts', '.tsx', '.json', '.yaml', '.yml', '.md']

def is_allowed_path(file_path: Path) -> bool:
    """Check if file is in an allowed location"""
    path_str = str(file_path)
    return any(allowed in path_str for allowed in ALLOWED_PATHS)

def check_file(file_path: Path) -> list:
    """Check a file for banned exchange references"""
    violations = []
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f, 1):
                for pattern in BANNED_PATTERNS:
                    if re.search(pattern, line):
                        violations.append({
                            'file': str(file_path.relative_to(repo_root)),
                            'line': line_num,
                            'text': line.strip()[:100]  # Truncate long lines
                        })
    except Exception as e:
        print(f"Warning: Could not read {file_path}: {e}")
    
    return violations

def main():
    """Run the ban check"""
    print("=" * 70)
    print("🚫 VALR/OVEX Ban Check")
    print("=" * 70)
    print("\nSearching for banned exchanges in active code...")
    
    all_violations = []
    
    # Scan backend and frontend directories
    for directory in ['backend', 'frontend']:
        dir_path = repo_root / directory
        if not dir_path.exists():
            continue
            
        for ext in EXTENSIONS:
            for file_path in dir_path.rglob(f"*{ext}"):
                # Skip allowed paths
                if is_allowed_path(file_path):
                    continue
                
                # Skip node_modules, __pycache__, etc.
                if any(skip in str(file_path) for skip in ['node_modules', '__pycache__', '.venv', 'venv', 'build', 'dist']):
                    continue
                
                violations = check_file(file_path)
                all_violations.extend(violations)
    
    # Report results
    if not all_violations:
        print("\n✅ No VALR/OVEX references found in active code!")
        print("\nSupported exchanges (7 total):")
        print("  - luno")
        print("  - binance")
        print("  - kucoin")
        print("  - bybit")
        print("  - kraken")
        print("  - bitget")
        print("  - gate")
        return 0
    else:
        print(f"\n❌ Found {len(all_violations)} VALR/OVEX references in active code:")
        print()
        
        # Group by file
        by_file = {}
        for v in all_violations:
            file = v['file']
            if file not in by_file:
                by_file[file] = []
            by_file[file].append(v)
        
        for file, violations in sorted(by_file.items()):
            print(f"📄 {file}")
            for v in violations[:5]:  # Show first 5 per file
                print(f"   Line {v['line']}: {v['text']}")
            if len(violations) > 5:
                print(f"   ... and {len(violations) - 5} more")
            print()
        
        print("⚠️  These exchanges must be removed from active code!")
        print("   VALR and OVEX are not supported.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
