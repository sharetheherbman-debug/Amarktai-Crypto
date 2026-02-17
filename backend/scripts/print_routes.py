#!/usr/bin/env python3
"""
Backend Route Inventory Script
Extracts route definitions from backend code using grep/regex.
Usage: python backend/scripts/print_routes.py
"""

import re
import os
import glob

def extract_routes_from_file(filepath):
    """Extract route definitions from a Python file"""
    routes = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Match @router.get/post/put/delete/patch("path")
        # Also match @api_router.get(...), @app.get(...)
        pattern = r'@(?:router|api_router|app)\.(get|post|put|delete|patch|options|head)\([\'"]([^\'"]+)[\'"]'
        
        for match in re.finditer(pattern, content):
            method = match.group(1).upper()
            path = match.group(2)
            routes.append({'method': method, 'path': path, 'file': os.path.basename(filepath)})
    except Exception as e:
        pass
    
    return routes

def main():
    print("=" * 80)
    print("BACKEND ROUTES INVENTORY (from code analysis)")
    print("=" * 80)
    
    backend_dir = os.path.join(os.path.dirname(__file__), '..')
    
    # Find all Python files in backend and routes
    python_files = []
    python_files.extend(glob.glob(os.path.join(backend_dir, '*.py')))
    python_files.extend(glob.glob(os.path.join(backend_dir, 'routes', '*.py')))
    
    all_routes = []
    for filepath in python_files:
        routes = extract_routes_from_file(filepath)
        all_routes.extend(routes)
    
    # Sort by path
    all_routes.sort(key=lambda x: x['path'])
    
    print(f"{'METHOD':<10} {'PATH':<50} {'FILE':<30}")
    print("-" * 80)
    
    for route in all_routes:
        print(f"{route['method']:<10} {route['path']:<50} {route['file']:<30}")
    
    print("-" * 80)
    print(f"Total routes found: {len(all_routes)}")
    print("=" * 80)

if __name__ == '__main__':
    main()

