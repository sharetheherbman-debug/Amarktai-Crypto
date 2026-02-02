#!/usr/bin/env python3
"""
Comprehensive Repository Audit Script
Generates audit_report.json and docs/CURRENT_STATE.md
"""

import os
import re
import json
import ast
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict

class RepoAuditor:
    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root)
        self.backend_dir = self.repo_root / "backend"
        self.frontend_dir = self.repo_root / "frontend"
        self.docs_dir = self.repo_root / "docs"
        
        self.audit_data = {
            "exchanges": {},
            "routers": [],
            "endpoints": [],
            "frontend_api_calls": [],
            "todos": [],
            "blockers": [],
            "valr_ovex_references": [],
            "removed_features": [],
            "tos_violations": []
        }
    
    def audit_exchanges(self):
        """Audit supported exchanges"""
        print("🔍 Auditing exchanges...")
        
        # Check exchange_limits.py
        exchange_limits_file = self.backend_dir / "exchange_limits.py"
        if exchange_limits_file.exists():
            content = exchange_limits_file.read_text()
            
            # Extract BOT_ALLOCATION
            allocation_match = re.search(r'BOT_ALLOCATION\s*=\s*\{([^}]+)\}', content, re.DOTALL)
            if allocation_match:
                allocation_str = allocation_match.group(1)
                # Parse exchange allocations
                exchanges = re.findall(r'"([^"]+)":\s*(\d+)', allocation_str)
                for exchange, limit in exchanges:
                    self.audit_data["exchanges"][exchange] = {
                        "max_bots": int(limit),
                        "source": "exchange_limits.py"
                    }
        
        # Check platforms.py
        platforms_file = self.backend_dir / "platforms.py"
        if platforms_file.exists():
            content = platforms_file.read_text()
            # Look for supported platforms
            supported = re.findall(r'"([a-z]+)"', content)
            for platform in set(supported):
                if platform not in self.audit_data["exchanges"]:
                    self.audit_data["exchanges"][platform] = {
                        "max_bots": "unknown",
                        "source": "platforms.py"
                    }
        
        print(f"  Found {len(self.audit_data['exchanges'])} exchanges")
    
    def audit_routers(self):
        """Audit all routers and their mount points"""
        print("🔍 Auditing routers...")
        
        routes_dir = self.backend_dir / "routes"
        if routes_dir.exists():
            for route_file in routes_dir.glob("*.py"):
                if route_file.name == "__init__.py":
                    continue
                
                content = route_file.read_text()
                
                # Look for APIRouter definitions
                if "APIRouter" in content:
                    router_info = {
                        "file": str(route_file.relative_to(self.repo_root)),
                        "name": route_file.stem,
                        "prefix": None,
                        "tags": []
                    }
                    
                    # Extract prefix
                    prefix_match = re.search(r'APIRouter\([^)]*prefix=["\']([^"\']+)["\']', content)
                    if prefix_match:
                        router_info["prefix"] = prefix_match.group(1)
                    
                    # Extract tags
                    tags_match = re.search(r'tags=\[([^\]]+)\]', content)
                    if tags_match:
                        tags_str = tags_match.group(1)
                        router_info["tags"] = re.findall(r'["\']([^"\']+)["\']', tags_str)
                    
                    self.audit_data["routers"].append(router_info)
        
        print(f"  Found {len(self.audit_data['routers'])} routers")
    
    def audit_endpoints(self):
        """Audit all FastAPI endpoints"""
        print("🔍 Auditing endpoints...")
        
        routes_dir = self.backend_dir / "routes"
        if routes_dir.exists():
            for route_file in routes_dir.glob("*.py"):
                if route_file.name == "__init__.py":
                    continue
                
                content = route_file.read_text()
                lines = content.split('\n')
                
                # Look for route decorators
                for i, line in enumerate(lines):
                    # Match @router.get, @router.post, etc.
                    decorator_match = re.match(r'@[a-z_]+\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']', line)
                    if decorator_match:
                        method = decorator_match.group(1).upper()
                        path = decorator_match.group(2)
                        
                        # Try to find function name on next non-decorator line
                        func_name = None
                        for j in range(i+1, min(i+5, len(lines))):
                            func_match = re.match(r'(async\s+)?def\s+([a-z_]+)', lines[j])
                            if func_match:
                                func_name = func_match.group(2)
                                break
                        
                        endpoint_info = {
                            "method": method,
                            "path": path,
                            "function": func_name,
                            "file": str(route_file.relative_to(self.repo_root)),
                            "auth_required": "Depends(get_current_user)" in content
                        }
                        
                        self.audit_data["endpoints"].append(endpoint_info)
        
        print(f"  Found {len(self.audit_data['endpoints'])} endpoints")
    
    def audit_frontend_api_calls(self):
        """Audit frontend API calls"""
        print("🔍 Auditing frontend API calls...")
        
        src_dir = self.frontend_dir / "src"
        if not src_dir.exists():
            return
        
        # Look for API calls in JS/JSX files
        for file_path in src_dir.rglob("*.js"):
            if "node_modules" in str(file_path):
                continue
            
            content = file_path.read_text(errors='ignore')
            
            # Look for axios/fetch calls
            api_calls = re.findall(r'(?:axios\.|apiClient\.|fetch\()(?:get|post|put|delete|patch)\(["\']([^"\']+)["\']', content)
            for path in api_calls:
                self.audit_data["frontend_api_calls"].append({
                    "path": path,
                    "file": str(file_path.relative_to(self.repo_root))
                })
        
        for file_path in src_dir.rglob("*.jsx"):
            if "node_modules" in str(file_path):
                continue
            
            content = file_path.read_text(errors='ignore')
            
            # Look for axios/fetch calls
            api_calls = re.findall(r'(?:axios\.|apiClient\.|fetch\()(?:get|post|put|delete|patch)\(["\']([^"\']+)["\']', content)
            for path in api_calls:
                self.audit_data["frontend_api_calls"].append({
                    "path": path,
                    "file": str(file_path.relative_to(self.repo_root))
                })
        
        print(f"  Found {len(self.audit_data['frontend_api_calls'])} frontend API calls")
    
    def audit_todos(self):
        """Audit TODO/FIXME/XXX/HACK markers"""
        print("🔍 Auditing TODO markers...")
        
        patterns = ['TODO', 'FIXME', 'XXX', 'HACK', 'BUG']
        
        for pattern in patterns:
            # Search in backend
            for file_path in self.backend_dir.rglob("*.py"):
                if "_archive" in str(file_path) or "__pycache__" in str(file_path):
                    continue
                
                content = file_path.read_text(errors='ignore')
                lines = content.split('\n')
                
                for line_num, line in enumerate(lines, 1):
                    if pattern in line.upper():
                        self.audit_data["todos"].append({
                            "type": pattern,
                            "file": str(file_path.relative_to(self.repo_root)),
                            "line": line_num,
                            "text": line.strip()
                        })
            
            # Search in frontend
            if self.frontend_dir.exists():
                for ext in ["*.js", "*.jsx"]:
                    for file_path in (self.frontend_dir / "src").rglob(ext):
                        if "node_modules" in str(file_path):
                            continue
                        
                        content = file_path.read_text(errors='ignore')
                        lines = content.split('\n')
                        
                        for line_num, line in enumerate(lines, 1):
                            if pattern in line.upper():
                                self.audit_data["todos"].append({
                                    "type": pattern,
                                    "file": str(file_path.relative_to(self.repo_root)),
                                    "line": line_num,
                                    "text": line.strip()
                                })
        
        print(f"  Found {len(self.audit_data['todos'])} TODO markers")
    
    def audit_valr_ovex(self):
        """Check for VALR and OVEX references"""
        print("🔍 Auditing VALR/OVEX references...")
        
        patterns = [r'\bvalr\b', r'\bVALR\b', r'\bovex\b', r'\bOVEX\b']
        
        # Search in all relevant files
        for root_dir in [self.backend_dir, self.frontend_dir, self.docs_dir, self.repo_root / "scripts"]:
            if not root_dir.exists():
                continue
            
            for file_path in root_dir.rglob("*"):
                if file_path.is_file() and file_path.suffix in ['.py', '.js', '.jsx', '.md', '.sh', '.json', '.yaml', '.yml']:
                    if "_archive" in str(file_path) or "node_modules" in str(file_path):
                        continue
                    
                    content = file_path.read_text(errors='ignore')
                    lines = content.split('\n')
                    
                    for line_num, line in enumerate(lines, 1):
                        for pattern in patterns:
                            if re.search(pattern, line):
                                self.audit_data["valr_ovex_references"].append({
                                    "file": str(file_path.relative_to(self.repo_root)),
                                    "line": line_num,
                                    "text": line.strip()[:100]
                                })
                                break
        
        print(f"  Found {len(self.audit_data['valr_ovex_references'])} VALR/OVEX references")
    
    def audit_removed_features(self):
        """Check for removed features that shouldn't exist"""
        print("🔍 Auditing removed features...")
        
        removed_features = {
            "DeFi/DEX": [r'\bdefi\b', r'\bDeFi\b', r'\bdex\b', r'\bDEX\b', r'\buniswap\b', r'\bsushi\b'],
            "Strategy Marketplace": [r'\bmarketplace\b', r'\bstripe\b', r'\bpaid.*strateg', r'\bsell.*strateg'],
            "TradingView": [r'\btradingview\b', r'\bTradingView\b', r'\bTV.*signal'],
            "Telegram": [r'\btelegram\b', r'\bTelegram\b', r'\bbot.*telegram'],
            "Advanced Backtesting": [r'\bwalk.*forward\b', r'\bMonte.*Carlo\b', r'\bmonte.*carlo\b']
        }
        
        for feature_name, patterns in removed_features.items():
            for root_dir in [self.backend_dir / "routes", self.backend_dir / "services"]:
                if not root_dir.exists():
                    continue
                
                for file_path in root_dir.rglob("*.py"):
                    if "_archive" in str(file_path):
                        continue
                    
                    content = file_path.read_text(errors='ignore')
                    
                    for pattern in patterns:
                        if re.search(pattern, content, re.IGNORECASE):
                            self.audit_data["removed_features"].append({
                                "feature": feature_name,
                                "file": str(file_path.relative_to(self.repo_root)),
                                "pattern": pattern
                            })
                            break
        
        print(f"  Found {len(self.audit_data['removed_features'])} removed feature references")
    
    def audit_tos_violations(self):
        """Check for ToS-breaking features"""
        print("🔍 Auditing ToS violations...")
        
        tos_patterns = {
            "proxy_rotation": [r'\bproxy.*rotat', r'\brotat.*proxy', r'\bip.*mask'],
            "fingerprint": [r'\bfingerprint', r'\bbrowser.*fingerprint'],
            "wash_trading": [r'\bwash.*trad', r'\bnoise.*trade', r'\bfake.*order'],
            "evasion": [r'\bevad', r'\bbypass.*detect', r'\bhide.*from.*platform']
        }
        
        for violation_type, patterns in tos_patterns.items():
            for root_dir in [self.backend_dir]:
                if not root_dir.exists():
                    continue
                
                for file_path in root_dir.rglob("*.py"):
                    if "_archive" in str(file_path):
                        continue
                    
                    content = file_path.read_text(errors='ignore')
                    
                    for pattern in patterns:
                        matches = re.finditer(pattern, content, re.IGNORECASE)
                        for match in matches:
                            # Get line number
                            line_num = content[:match.start()].count('\n') + 1
                            lines = content.split('\n')
                            self.audit_data["tos_violations"].append({
                                "type": violation_type,
                                "file": str(file_path.relative_to(self.repo_root)),
                                "line": line_num,
                                "text": lines[line_num-1].strip()[:100] if line_num <= len(lines) else ""
                            })
        
        print(f"  Found {len(self.audit_data['tos_violations'])} potential ToS violations")
    
    def identify_blockers(self):
        """Identify production blockers"""
        print("🔍 Identifying blockers...")
        
        blockers = []
        
        # Check if exactly 7 exchanges
        if len(self.audit_data["exchanges"]) != 7:
            blockers.append({
                "type": "EXCHANGE_COUNT",
                "severity": "HIGH",
                "message": f"Expected exactly 7 exchanges, found {len(self.audit_data['exchanges'])}"
            })
        
        # Check for VALR/OVEX
        if self.audit_data["valr_ovex_references"]:
            blockers.append({
                "type": "VALR_OVEX_PRESENT",
                "severity": "HIGH",
                "message": f"Found {len(self.audit_data['valr_ovex_references'])} VALR/OVEX references"
            })
        
        # Check for removed features
        if self.audit_data["removed_features"]:
            blockers.append({
                "type": "REMOVED_FEATURES_PRESENT",
                "severity": "MEDIUM",
                "message": f"Found {len(self.audit_data['removed_features'])} references to removed features"
            })
        
        # Check for ToS violations
        if self.audit_data["tos_violations"]:
            blockers.append({
                "type": "TOS_VIOLATIONS",
                "severity": "HIGH",
                "message": f"Found {len(self.audit_data['tos_violations'])} potential ToS violations"
            })
        
        self.audit_data["blockers"] = blockers
        print(f"  Identified {len(blockers)} blockers")
    
    def generate_current_state_md(self):
        """Generate docs/CURRENT_STATE.md"""
        print("📝 Generating CURRENT_STATE.md...")
        
        md_content = f"""# Amarktai Network - Current State

**Generated:** {Path(__file__).name}
**Date:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Supported Exchanges

Total: {len(self.audit_data['exchanges'])} exchanges

| Exchange | Max Bots | Source |
|----------|----------|--------|
"""
        
        for exchange, info in sorted(self.audit_data['exchanges'].items()):
            md_content += f"| {exchange} | {info['max_bots']} | {info['source']} |\n"
        
        md_content += f"""
**Total Bot Capacity:** {sum(int(info['max_bots']) for info in self.audit_data['exchanges'].values() if isinstance(info['max_bots'], int))}

## Backend Routers

Total: {len(self.audit_data['routers'])} routers

| Router | Prefix | File |
|--------|--------|------|
"""
        
        for router in sorted(self.audit_data['routers'], key=lambda x: x['name']):
            prefix = router.get('prefix', 'N/A')
            md_content += f"| {router['name']} | {prefix} | {router['file']} |\n"
        
        md_content += f"""
## API Endpoints

Total: {len(self.audit_data['endpoints'])} endpoints

### By Method
"""
        
        methods = defaultdict(int)
        for endpoint in self.audit_data['endpoints']:
            methods[endpoint['method']] += 1
        
        for method, count in sorted(methods.items()):
            md_content += f"- **{method}:** {count} endpoints\n"
        
        md_content += f"""
## Frontend API Calls

Total: {len(self.audit_data['frontend_api_calls'])} API calls from frontend

## TODO Markers

Total: {len(self.audit_data['todos'])} TODO/FIXME/XXX/HACK markers

### By Type
"""
        
        todo_types = defaultdict(int)
        for todo in self.audit_data['todos']:
            todo_types[todo['type']] += 1
        
        for todo_type, count in sorted(todo_types.items()):
            md_content += f"- **{todo_type}:** {count}\n"
        
        md_content += f"""
## Production Blockers

Total: {len(self.audit_data['blockers'])} blockers identified

"""
        
        for blocker in self.audit_data['blockers']:
            md_content += f"### {blocker['type']} ({blocker['severity']})\n"
            md_content += f"{blocker['message']}\n\n"
        
        if self.audit_data['valr_ovex_references']:
            md_content += f"""
## VALR/OVEX References (Must Be Removed)

Found {len(self.audit_data['valr_ovex_references'])} references:

"""
            for ref in self.audit_data['valr_ovex_references'][:20]:  # Limit to first 20
                md_content += f"- `{ref['file']}:{ref['line']}` - {ref['text']}\n"
            
            if len(self.audit_data['valr_ovex_references']) > 20:
                md_content += f"\n... and {len(self.audit_data['valr_ovex_references']) - 20} more\n"
        
        if self.audit_data['removed_features']:
            md_content += f"""
## Removed Features (Must Be Deleted)

Found {len(self.audit_data['removed_features'])} references to removed features:

"""
            for ref in self.audit_data['removed_features'][:20]:
                md_content += f"- **{ref['feature']}** in `{ref['file']}`\n"
        
        if self.audit_data['tos_violations']:
            md_content += f"""
## Potential ToS Violations (Must Be Removed)

Found {len(self.audit_data['tos_violations'])} potential violations:

"""
            for ref in self.audit_data['tos_violations'][:20]:
                md_content += f"- **{ref['type']}** in `{ref['file']}:{ref['line']}`\n"
        
        # Write to file
        output_file = self.docs_dir / "CURRENT_STATE.md"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(md_content)
        print(f"  ✅ Generated {output_file}")
    
    def generate_api_contract_md(self):
        """Generate docs/API_CONTRACT.md"""
        print("📝 Generating API_CONTRACT.md...")
        
        md_content = f"""# Amarktai Network - API Contract

**Generated:** {Path(__file__).name}
**Date:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Backend Endpoints

Total: {len(self.audit_data['endpoints'])} endpoints

| Method | Path | Auth | Function | File |
|--------|------|------|----------|------|
"""
        
        for endpoint in sorted(self.audit_data['endpoints'], key=lambda x: (x['method'], x['path'])):
            auth = "✓" if endpoint['auth_required'] else ""
            func = endpoint.get('function', 'N/A')
            file = endpoint['file'].replace('backend/', '')
            md_content += f"| {endpoint['method']} | `{endpoint['path']}` | {auth} | `{func}` | {file} |\n"
        
        md_content += f"""
## Frontend API Calls

Total: {len(self.audit_data['frontend_api_calls'])} API calls

"""
        
        # Group by path
        calls_by_path = defaultdict(list)
        for call in self.audit_data['frontend_api_calls']:
            calls_by_path[call['path']].append(call['file'])
        
        md_content += "| Path | Files |\n"
        md_content += "|------|-------|\n"
        
        for path in sorted(calls_by_path.keys()):
            files = calls_by_path[path]
            files_str = "<br>".join([f.replace('frontend/src/', '') for f in files[:3]])
            if len(files) > 3:
                files_str += f"<br>... and {len(files) - 3} more"
            md_content += f"| `{path}` | {files_str} |\n"
        
        md_content += """
## Contract Validation

The following checks should be performed:

1. **No 404s:** Every frontend API call should have a matching backend endpoint
2. **Consistent paths:** API keys should use single canonical route set
3. **Auth consistency:** Protected endpoints should require authentication
4. **Response schemas:** Backend responses should match frontend expectations

"""
        
        # Write to file
        output_file = self.docs_dir / "API_CONTRACT.md"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(md_content)
        print(f"  ✅ Generated {output_file}")
    
    def save_audit_json(self):
        """Save audit data as JSON"""
        print("💾 Saving audit_report.json...")
        
        output_file = self.repo_root / "audit_report.json"
        with open(output_file, 'w') as f:
            json.dump(self.audit_data, f, indent=2)
        
        print(f"  ✅ Saved {output_file}")
    
    def run(self):
        """Run full audit"""
        print("=" * 70)
        print("🔍 AMARKTAI NETWORK - COMPREHENSIVE REPOSITORY AUDIT")
        print("=" * 70)
        print()
        
        self.audit_exchanges()
        self.audit_routers()
        self.audit_endpoints()
        self.audit_frontend_api_calls()
        self.audit_todos()
        self.audit_valr_ovex()
        self.audit_removed_features()
        self.audit_tos_violations()
        self.identify_blockers()
        
        print()
        print("=" * 70)
        print("📝 GENERATING DOCUMENTATION")
        print("=" * 70)
        print()
        
        self.generate_current_state_md()
        self.generate_api_contract_md()
        self.save_audit_json()
        
        print()
        print("=" * 70)
        print("✅ AUDIT COMPLETE")
        print("=" * 70)
        print()
        print(f"📊 Summary:")
        print(f"  - Exchanges: {len(self.audit_data['exchanges'])}")
        print(f"  - Routers: {len(self.audit_data['routers'])}")
        print(f"  - Endpoints: {len(self.audit_data['endpoints'])}")
        print(f"  - Frontend API Calls: {len(self.audit_data['frontend_api_calls'])}")
        print(f"  - TODO Markers: {len(self.audit_data['todos'])}")
        print(f"  - VALR/OVEX References: {len(self.audit_data['valr_ovex_references'])}")
        print(f"  - Removed Features: {len(self.audit_data['removed_features'])}")
        print(f"  - ToS Violations: {len(self.audit_data['tos_violations'])}")
        print(f"  - Blockers: {len(self.audit_data['blockers'])}")
        print()
        
        if self.audit_data['blockers']:
            print("⚠️  BLOCKERS FOUND - See docs/CURRENT_STATE.md for details")
            return 1
        else:
            print("✅ No blockers found")
            return 0

if __name__ == "__main__":
    import sys
    
    # Get repo root (parent of scripts directory)
    repo_root = Path(__file__).parent.parent
    
    auditor = RepoAuditor(str(repo_root))
    exit_code = auditor.run()
    
    sys.exit(exit_code)
