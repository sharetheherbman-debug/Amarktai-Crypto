#!/usr/bin/env python3
"""
Route Uniqueness Verification Script

Imports the FastAPI app and checks for duplicate (method, path) combinations.
Exits with non-zero code if duplicates are found.
"""

import sys
from collections import defaultdict

def main():
    # Import the FastAPI app
    try:
        sys.path.insert(0, '/home/runner/work/Amarktai-Network---Deployment/Amarktai-Network---Deployment/backend')
        from server import app
    except Exception as e:
        print(f"❌ Error importing app: {e}")
        return 1
    
    # Collect all routes
    routes_map = defaultdict(list)
    
    for route in app.routes:
        if hasattr(route, 'methods') and hasattr(route, 'path'):
            methods = route.methods or []
            for method in methods:
                if method != 'HEAD':  # Skip HEAD as it's auto-generated
                    key = (method, route.path)
                    routes_map[key].append(route.name or 'unnamed')
    
    # Check for duplicates
    duplicates = []
    for (method, path), names in routes_map.items():
        if len(names) > 1:
            duplicates.append({
                'method': method,
                'path': path,
                'count': len(names),
                'handlers': names
            })
    
    # Report results
    print(f"Total unique (method, path) combinations: {len(routes_map)}")
    
    if duplicates:
        print(f"\n❌ Found {len(duplicates)} duplicate route(s):\n")
        for dup in duplicates:
            print(f"  {dup['method']} {dup['path']}")
            print(f"    Handlers ({dup['count']}): {', '.join(dup['handlers'])}")
            print()
        return 1
    else:
        print("✅ No duplicate routes found!")
        return 0

if __name__ == '__main__':
    sys.exit(main())
