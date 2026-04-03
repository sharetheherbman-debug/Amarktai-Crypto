#!/usr/bin/env python3
"""
TODO Finder - Analyze incomplete features in Amarktai Network

This script scans the new feature files and reports all TODOs,
categorized by feature and priority.
"""

import re
import os
from pathlib import Path
from collections import defaultdict

# ANSI colors
GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
BOLD = '\033[1m'
RESET = '\033[0m'

def find_todos(file_path):
    """Extract all TODO comments from a file"""
    todos = []
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
            for i, line in enumerate(lines, 1):
                if 'TODO:' in line or 'TODO -' in line:
                    # Extract the TODO text
                    todo_text = line.strip()
                    # Remove comment markers
                    todo_text = re.sub(r'^\s*#\s*', '', todo_text)
                    todos.append((i, todo_text))
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    return todos

def categorize_priority(todo_text):
    """Categorize TODO by priority based on keywords"""
    high_priority = ['security', 'validation', 'authorization', 'critical']
    medium_priority = ['implement', 'integration', 'calculate']
    
    text_lower = todo_text.lower()
    
    if any(word in text_lower for word in high_priority):
        return 'HIGH'
    elif any(word in text_lower for word in medium_priority):
        return 'MEDIUM'
    else:
        return 'LOW'

def analyze_feature_files():
    """Analyze all new feature files"""
    
    base_path = Path('/home/runner/work/Amarktai-Crypto/Amarktai-Crypto/backend')
    
    features = {
        'External Signals': base_path / 'routes' / 'signals.py',
        'DeFi/DEX Trading': base_path / 'routes' / 'defi_trading.py',
        'Strategy Marketplace': base_path / 'routes' / 'marketplace.py',
        'Advanced Backtesting': base_path / 'routes' / 'backtesting.py',
        'Wallet Transfers': base_path / 'services' / 'wallet_transfers_service.py',
    }
    
    results = {}
    total_todos = 0
    priority_counts = defaultdict(int)
    
    for feature_name, file_path in features.items():
        if file_path.exists():
            todos = find_todos(file_path)
            results[feature_name] = todos
            total_todos += len(todos)
            
            for _, todo_text in todos:
                priority = categorize_priority(todo_text)
                priority_counts[priority] += 1
    
    return results, total_todos, priority_counts

def print_report(results, total_todos, priority_counts):
    """Print formatted report"""
    
    print(f"\n{BOLD}{'='*80}{RESET}")
    print(f"{BOLD}{BLUE}AMARKTAI NETWORK - TODO ANALYSIS{RESET}")
    print(f"{BOLD}{'='*80}{RESET}\n")
    
    print(f"{BOLD}Summary:{RESET}")
    print(f"  Total TODOs found: {YELLOW}{total_todos}{RESET}")
    print(f"  High Priority: {RED}{priority_counts['HIGH']}{RESET}")
    print(f"  Medium Priority: {YELLOW}{priority_counts['MEDIUM']}{RESET}")
    print(f"  Low Priority: {GREEN}{priority_counts['LOW']}{RESET}\n")
    
    print(f"{BOLD}{'='*80}{RESET}\n")
    
    for feature_name, todos in results.items():
        if todos:
            print(f"{BOLD}{BLUE}📋 {feature_name}{RESET}")
            print(f"{BOLD}{'─'*80}{RESET}")
            print(f"TODOs found: {len(todos)}\n")
            
            for line_num, todo_text in todos:
                priority = categorize_priority(todo_text)
                
                if priority == 'HIGH':
                    priority_color = RED
                elif priority == 'MEDIUM':
                    priority_color = YELLOW
                else:
                    priority_color = GREEN
                
                print(f"  Line {line_num:4d}: [{priority_color}{priority}{RESET}] {todo_text}")
            
            print()
    
    print(f"{BOLD}{'='*80}{RESET}")
    print(f"\n{BOLD}Next Steps:{RESET}")
    print(f"  1. Review high-priority TODOs first")
    print(f"  2. Group related TODOs by feature")
    print(f"  3. Estimate effort for each TODO")
    print(f"  4. Assign to developers")
    print(f"  5. Track completion\n")
    
    print(f"{BOLD}Documentation:{RESET}")
    print(f"  • docs/INCOMPLETE_FEATURES_ANALYSIS.md (detailed)")
    print(f"  • docs/FEATURE_COMPLETION_QUICK_REF.md (quick ref)\n")

def main():
    results, total_todos, priority_counts = analyze_feature_files()
    print_report(results, total_todos, priority_counts)

if __name__ == '__main__':
    main()
