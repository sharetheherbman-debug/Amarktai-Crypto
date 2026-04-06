"""
Test router mounting to ensure all routers can be imported and mounted successfully.
This test will fail CI if any router fails to mount, preventing deployment of broken code.
"""

import pytest
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


def test_all_routers_can_import():
    """Test that all routers in the routes directory can be imported successfully.
    
    Note: This list should be kept in sync with routers_to_mount in server.py.
    Any router added to server.py should also be added here to ensure CI catches
    import failures before deployment.
    """
    
    # List of all router modules that should be importable
    # This matches the routers_to_mount list in server.py
    routers_to_test = [
        "routes.keys",
        "routes.system_mode",
        "routes.platforms",
        "routes.build_info",
        "routes.system",
        "routes.trades",
        "routes.health",
        "routes.system_status",
        "routes.phase5_endpoints",
        "routes.phase6_endpoints",
        "routes.phase8_endpoints",
        "routes.capital_tracking_endpoints",
        "routes.emergency_stop_endpoints",
        "routes.wallet_endpoints",
        "routes.wallet_hub",
        "routes.admin_endpoints",
        "routes.admin_enhanced",
        "routes.admin_start_fresh",
        "routes.risk_management",
        "routes.dashboard_overview",
        "routes.bot_lifecycle",
        "routes.autopilot_control",
        "routes.training",
        "routes.training_quarantine",
        "routes.system_limits",
        "routes.live_trading_gate",
        "routes.analytics_api",
        "routes.diagnostics",
        "routes.ai_chat",
        "routes.chat_enhanced",
        "routes.two_factor_auth",
        "routes.genetic_algorithm",
        "routes.dashboard_endpoints",
        "routes.daily_report",
        "routes.ledger_endpoints",
        "routes.order_endpoints",
        "routes.alerts",
        "routes.limits_management",
        "routes.advanced_trading_endpoints",
        "routes.payment_agent_endpoints",
        "routes.dashboard_aliases",
        "routes.quarantine",
        "routes.decision_trace",
        "routes.compatibility_endpoints",
        "routes.chat_endpoints",
        "routes.wallet_transfers_enhanced",
        "routes.wallet_addresses",
        "routes.admin_whitelist",
        "routes.user_whitelist",
        "routes.user_countdowns",
        "routes.execution_quality",
        "routes.treasury",
        "routes.notifications",
        "routes.realtime",
        "routes.auth",
    ]
    
    failed_imports = []
    successful_imports = []
    
    for module_path in routers_to_test:
        try:
            # Import the module
            module = __import__(module_path, fromlist=['router'])
            
            # Check that it has a 'router' attribute
            if not hasattr(module, 'router'):
                failed_imports.append((module_path, "Module has no 'router' attribute"))
                continue
            
            # Verify router is a FastAPI APIRouter
            router = getattr(module, 'router')
            from fastapi import APIRouter
            if not isinstance(router, APIRouter):
                failed_imports.append((module_path, f"'router' is not an APIRouter instance: {type(router)}"))
                continue
            
            successful_imports.append(module_path)
            
        except ImportError as e:
            failed_imports.append((module_path, f"ImportError: {str(e)}"))
        except Exception as e:
            failed_imports.append((module_path, f"Unexpected error: {str(e)}"))
    
    # Print summary
    print(f"\n✅ Successfully imported {len(successful_imports)} routers")
    print(f"❌ Failed to import {len(failed_imports)} routers\n")
    
    if failed_imports:
        print("Failed router imports:")
        for module_path, error in failed_imports:
            print(f"  - {module_path}: {error}")
        print("")
    
    # Fail the test if any routers failed to import
    assert len(failed_imports) == 0, f"{len(failed_imports)} router(s) failed to import. See output above for details."


def test_critical_routers_mount():
    """Test that CRITICAL routers can be imported and mounted."""
    
    # These are the critical routers from server.py that MUST work
    critical_routers = [
        "routes.auth",
        "routes.keys",
        "routes.trades",
        "routes.bot_lifecycle",
        "routes.realtime",
        "routes.system_mode",
        "routes.ledger_endpoints",
        "routes.analytics_api",
        "routes.training",
        "routes.quarantine"
    ]
    
    failed_critical = []
    
    for module_path in critical_routers:
        try:
            module = __import__(module_path, fromlist=['router'])
            
            if not hasattr(module, 'router'):
                failed_critical.append((module_path, "No 'router' attribute"))
                continue
            
            from fastapi import APIRouter
            router = getattr(module, 'router')
            if not isinstance(router, APIRouter):
                failed_critical.append((module_path, "Not an APIRouter"))
                continue
                
        except Exception as e:
            failed_critical.append((module_path, str(e)))
    
    if failed_critical:
        print("\n❌ CRITICAL FAILURE: The following critical routers failed to import:")
        for module_path, error in failed_critical:
            print(f"  - {module_path}: {error}")
        print("")
    
    assert len(failed_critical) == 0, f"CRITICAL: {len(failed_critical)} critical router(s) failed to import!"


def test_server_app_imports():
    """Test that server:app can be imported successfully."""
    
    try:
        import server
        assert hasattr(server, 'app'), "server module has no 'app' attribute"
        
        from fastapi import FastAPI
        assert isinstance(server.app, FastAPI), f"server.app is not a FastAPI instance: {type(server.app)}"
        
        print("✅ server:app imported successfully")
        
    except Exception as e:
        pytest.fail(f"Failed to import server:app: {e}")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
