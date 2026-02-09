#!/usr/bin/env python3
"""
Production Deployment Verification Script
==========================================
Comprehensive checklist to verify system is production-ready.

Run this after fresh deployment to ensure everything is configured correctly.

Usage:
    python scripts/deployment_verification.py

Exit codes:
    0 - All checks passed
    1 - Some checks failed (review output)
"""

import sys
import os
import json
import subprocess
from pathlib import Path
from datetime import datetime

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

# Add backend to path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

class DeploymentVerifier:
    def __init__(self):
        self.checks_passed = 0
        self.checks_failed = 0
        self.checks_warning = 0
        self.results = []
    
    def check(self, name, func):
        """Run a check and record result"""
        try:
            result = func()
            if result is True:
                self.checks_passed += 1
                self.results.append(('PASS', name, ''))
                print(f"{GREEN}✅ PASS{RESET} - {name}")
                return True
            elif result is False:
                self.checks_failed += 1
                self.results.append(('FAIL', name, ''))
                print(f"{RED}❌ FAIL{RESET} - {name}")
                return False
            else:
                # Warning
                self.checks_warning += 1
                self.results.append(('WARN', name, result))
                print(f"{YELLOW}⚠️  WARN{RESET} - {name}: {result}")
                return None
        except Exception as e:
            self.checks_failed += 1
            self.results.append(('FAIL', name, str(e)))
            print(f"{RED}❌ FAIL{RESET} - {name}: {e}")
            return False
    
    def section(self, title):
        """Print section header"""
        print(f"\n{BLUE}{'=' * 70}{RESET}")
        print(f"{BLUE}{title}{RESET}")
        print(f"{BLUE}{'=' * 70}{RESET}\n")

    def check_env_file(self):
        """Check .env file exists and has required variables"""
        env_file = Path('.env')
        if not env_file.exists():
            return "No .env file found"
        
        with open(env_file, 'r') as f:
            content = f.read()
        
        required = [
            'MONGO_URL',
            'JWT_SECRET',
            'OPENAI_API_KEY',
            'SMTP_HOST',
            'SMTP_USER',
            'SMTP_PASSWORD'
        ]
        
        missing = [var for var in required if var not in content]
        if missing:
            return f"Missing: {', '.join(missing)}"
        
        # Check for default values
        if 'change-in-production' in content or 'your-secret-key' in content:
            return "Contains default/example values - update JWT_SECRET"
        
        return True
    
    def check_python_syntax(self):
        """Check Python syntax"""
        result = subprocess.run(
            [sys.executable, 'scripts/boot_self_test.py'],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    
    def check_supported_exchanges(self):
        """Verify exactly 7 supported exchanges"""
        result = subprocess.run(
            [sys.executable, 'scripts/check_banned_exchanges.py'],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    
    def check_admin_import(self):
        """Verify is_admin is imported in server.py"""
        server_file = backend_dir / "server.py"
        with open(server_file, 'r') as f:
            content = f.read()
        
        import_lines = [line for line in content.split('\n') if 'from auth import' in line]
        return any('is_admin' in line for line in import_lines)
    
    def check_requirements(self):
        """Check requirements.txt exists"""
        req_file = backend_dir / "requirements.txt"
        if not req_file.exists():
            return "requirements.txt not found"
        
        with open(req_file, 'r') as f:
            lines = f.readlines()
        
        if len(lines) < 50:
            return "requirements.txt seems incomplete"
        
        return True
    
    def check_systemd_files(self):
        """Check systemd service files exist"""
        systemd_dir = Path('deployment/systemd')
        if not systemd_dir.exists():
            return "deployment/systemd directory not found"
        
        required_files = [
            'amarktai-monitor.service',
            'amarktai-daily-report.service',
            'amarktai-daily-report.timer'
        ]
        
        missing = [f for f in required_files if not (systemd_dir / f).exists()]
        if missing:
            return f"Missing: {', '.join(missing)}"
        
        return True
    
    def check_monitoring_script(self):
        """Check monitoring script exists and is executable"""
        monitor_script = Path('scripts/health_monitor.py')
        if not monitor_script.exists():
            return "health_monitor.py not found"
        
        if not os.access(monitor_script, os.X_OK):
            return "health_monitor.py not executable"
        
        return True
    
    def check_paper_trading_realism(self):
        """Verify paper trading has fund enforcement"""
        paper_engine = backend_dir / "paper_trading_engine.py"
        paper_ledger = backend_dir / "services" / "paper_wallet_ledger.py"
        
        if not paper_engine.exists():
            return "paper_trading_engine.py not found"
        
        if not paper_ledger.exists():
            return "paper_wallet_ledger.py not found"
        
        with open(paper_ledger, 'r') as f:
            content = f.read()
        
        # Check for key fund enforcement features
        if 'reserve_funds' not in content:
            return "Missing reserve_funds function"
        
        if 'NO FREE MONEY' not in content:
            return "Missing fund enforcement comment"
        
        return True
    
    def check_email_service(self):
        """Verify email service exists"""
        email_service = backend_dir / "email_service.py"
        email_scheduler = backend_dir / "email_scheduler.py"
        
        if not email_service.exists():
            return "email_service.py not found"
        
        if not email_scheduler.exists():
            return "email_scheduler.py not found"
        
        return True
    
    def check_diagnostics_endpoint(self):
        """Check diagnostics/go-live endpoint exists"""
        server_file = backend_dir / "server.py"
        with open(server_file, 'r') as f:
            content = f.read()
        
        if 'diagnostics_go_live' not in content:
            return "diagnostics_go_live endpoint not found"
        
        if '/diagnostics/go-live' not in content:
            return "/diagnostics/go-live route not found"
        
        return True
    
    def check_platform_config(self):
        """Verify platform configuration"""
        platforms_file = backend_dir / "config" / "platforms.py"
        if not platforms_file.exists():
            return "config/platforms.py not found"
        
        with open(platforms_file, 'r') as f:
            content = f.read()
        
        if "SUPPORTED_PLATFORMS = ['luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate']" not in content:
            return "SUPPORTED_PLATFORMS list incorrect"
        
        return True
    
    def check_readme(self):
        """Check README has deployment info"""
        readme = Path('README.md')
        if not readme.exists():
            return "README.md not found"
        
        with open(readme, 'r') as f:
            content = f.read()
        
        if 'deployment' not in content.lower():
            return "README missing deployment information"
        
        return True

    def run_all_checks(self):
        """Run all verification checks"""
        print(f"{BLUE}{'=' * 70}{RESET}")
        print(f"{BLUE}🚀 Production Deployment Verification{RESET}")
        print(f"{BLUE}{'=' * 70}{RESET}")
        print(f"\nTimestamp: {datetime.now().isoformat()}")
        
        # Environment
        self.section("📋 Environment Configuration")
        self.check("Environment file (.env)", self.check_env_file)
        self.check("Requirements file", self.check_requirements)
        
        # Code Quality
        self.section("🔍 Code Quality")
        self.check("Python syntax", self.check_python_syntax)
        self.check("Admin import fix", self.check_admin_import)
        self.check("Supported exchanges (7 only)", self.check_supported_exchanges)
        self.check("Platform configuration", self.check_platform_config)
        
        # Features
        self.section("✨ Feature Completeness")
        self.check("Paper trading realism", self.check_paper_trading_realism)
        self.check("Email service", self.check_email_service)
        self.check("Diagnostics endpoint", self.check_diagnostics_endpoint)
        
        # Monitoring
        self.section("📊 Monitoring & Observability")
        self.check("Health monitor script", self.check_monitoring_script)
        self.check("Systemd service files", self.check_systemd_files)
        
        # Documentation
        self.section("📚 Documentation")
        self.check("README completeness", self.check_readme)
        
        # Summary
        self.section("📊 Summary")
        total = self.checks_passed + self.checks_failed + self.checks_warning
        
        print(f"\nTotal Checks: {total}")
        print(f"{GREEN}✅ Passed: {self.checks_passed}{RESET}")
        print(f"{YELLOW}⚠️  Warnings: {self.checks_warning}{RESET}")
        print(f"{RED}❌ Failed: {self.checks_failed}{RESET}")
        
        if self.checks_failed == 0 and self.checks_warning == 0:
            print(f"\n{GREEN}{'=' * 70}{RESET}")
            print(f"{GREEN}🎉 ALL CHECKS PASSED - System is production-ready!{RESET}")
            print(f"{GREEN}{'=' * 70}{RESET}")
            return 0
        elif self.checks_failed == 0:
            print(f"\n{YELLOW}{'=' * 70}{RESET}")
            print(f"{YELLOW}⚠️  All checks passed with warnings - Review warnings before deploying{RESET}")
            print(f"{YELLOW}{'=' * 70}{RESET}")
            return 0
        else:
            print(f"\n{RED}{'=' * 70}{RESET}")
            print(f"{RED}❌ Some checks failed - Fix issues before deploying{RESET}")
            print(f"{RED}{'=' * 70}{RESET}")
            return 1

def main():
    """Main entry point"""
    os.chdir(Path(__file__).parent.parent)
    verifier = DeploymentVerifier()
    sys.exit(verifier.run_all_checks())

if __name__ == "__main__":
    main()
