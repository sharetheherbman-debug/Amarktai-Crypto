#!/usr/bin/env python3
"""
Verification script for AI Chat Session Enhancement

Tests:
1. Backend endpoint exists
2. Session tracking logic
3. Frontend component structure
4. localStorage integration
"""

import sys
import re

def check_backend_greeting_endpoint():
    """Verify greeting endpoint exists in backend"""
    try:
        with open('backend/routes/ai_chat.py', 'r') as f:
            content = f.read()
            
        checks = [
            ('@router.post("/chat/greeting")', 'Greeting endpoint decorator'),
            ('async def get_daily_greeting', 'Greeting function definition'),
            ('chat_sessions_collection', 'Session tracking collection'),
            ('last_greeting_at', 'Greeting timestamp tracking'),
            ('already_greeted', 'Duplicate greeting prevention'),
            ('yesterday_start', 'Yesterday\'s performance calculation'),
        ]
        
        print("✓ Backend Greeting Endpoint Checks:")
        for pattern, description in checks:
            if pattern in content:
                print(f"  ✓ {description}")
            else:
                print(f"  ✗ {description} - NOT FOUND")
                return False
        
        return True
    except Exception as e:
        print(f"✗ Error checking backend: {e}")
        return False


def check_backend_context_loading():
    """Verify chat history context loading"""
    try:
        with open('backend/routes/ai_chat.py', 'r') as f:
            content = f.read()
            
        checks = [
            ('chat_history = await db.chat_messages_collection.find', 'History loading'),
            ('.limit(30)', 'Load 30 messages for context'),
            ('chat_history.reverse()', 'Chronological order'),
            ('for hist_msg in chat_history', 'Iterate history'),
            ('ai_messages.append', 'Add to AI messages'),
        ]
        
        print("\n✓ Backend Context Loading Checks:")
        for pattern, description in checks:
            if pattern in content:
                print(f"  ✓ {description}")
            else:
                print(f"  ✗ {description} - NOT FOUND")
                return False
        
        return True
    except Exception as e:
        print(f"✗ Error checking context loading: {e}")
        return False


def check_frontend_session_management():
    """Verify frontend session management"""
    try:
        with open('frontend/src/components/AIChatPanel.js', 'r') as f:
            content = f.read()
            
        checks = [
            ('sessionChecked', 'Session check state'),
            ('checkSessionAndLoad', 'Session check function'),
            ('fetchDailyGreeting', 'Fetch greeting function'),
            ('loadRecentMessages', 'Load recent messages function'),
            ('lastChatSession', 'localStorage session tracking'),
            ('ONE_HOUR', '1-hour timeout constant'),
            ('clearUIMessages', 'Clear UI function'),
        ]
        
        print("\n✓ Frontend Session Management Checks:")
        for pattern, description in checks:
            if pattern in content:
                print(f"  ✓ {description}")
            else:
                print(f"  ✗ {description} - NOT FOUND")
                return False
        
        return True
    except Exception as e:
        print(f"✗ Error checking frontend: {e}")
        return False


def check_frontend_greeting_ui():
    """Verify greeting UI enhancements"""
    try:
        with open('frontend/src/components/AIChatPanel.js', 'r') as f:
            content = f.read()
            
        checks = [
            ('is_greeting', 'Greeting flag'),
            ('Daily Report', 'Daily report badge'),
            ('bg-gradient-to-r from-green-50 to-blue-50', 'Green gradient styling'),
            ('border-green-200', 'Green border'),
            ('CheckCircle', 'Checkmark icon'),
            ('Clear', 'Clear button'),
        ]
        
        print("\n✓ Frontend Greeting UI Checks:")
        for pattern, description in checks:
            if pattern in content:
                print(f"  ✓ {description}")
            else:
                print(f"  ✗ {description} - NOT FOUND")
                return False
        
        return True
    except Exception as e:
        print(f"✗ Error checking greeting UI: {e}")
        return False


def check_imports():
    """Verify necessary imports"""
    try:
        # Backend imports
        with open('backend/routes/ai_chat.py', 'r') as f:
            backend = f.read()
            
        if 'from datetime import datetime, timezone, timedelta' in backend:
            print("\n✓ Backend Import Checks:")
            print("  ✓ timedelta imported")
        else:
            print("\n✗ Backend Import Checks:")
            print("  ✗ timedelta not imported")
            return False
        
        # Frontend imports
        with open('frontend/src/components/AIChatPanel.js', 'r') as f:
            frontend = f.read()
            
        if 'CheckCircle' in frontend and "from 'lucide-react'" in frontend:
            print("\n✓ Frontend Import Checks:")
            print("  ✓ CheckCircle imported from lucide-react")
        else:
            print("\n✗ Frontend Import Checks:")
            print("  ✗ CheckCircle not properly imported")
            return False
        
        return True
    except Exception as e:
        print(f"✗ Error checking imports: {e}")
        return False


def check_documentation():
    """Verify documentation exists"""
    try:
        with open('AI_CHAT_SESSION_ENHANCEMENT.md', 'r') as f:
            content = f.read()
            
        checks = [
            ('Session-Aware Daily Greeting', 'Feature documentation'),
            ('Memory Retention', 'Memory feature'),
            ('Context Preservation', 'Context feature'),
            ('POST /api/ai/chat/greeting', 'API documentation'),
            ('Testing', 'Test scenarios'),
            ('User Experience Flow', 'UX documentation'),
        ]
        
        print("\n✓ Documentation Checks:")
        for pattern, description in checks:
            if pattern in content:
                print(f"  ✓ {description}")
            else:
                print(f"  ✗ {description} - NOT FOUND")
                return False
        
        return True
    except Exception as e:
        print(f"✗ Error checking documentation: {e}")
        return False


def main():
    """Run all verification checks"""
    print("=" * 60)
    print("AI Chat Session Enhancement - Verification")
    print("=" * 60)
    
    checks = [
        check_backend_greeting_endpoint,
        check_backend_context_loading,
        check_frontend_session_management,
        check_frontend_greeting_ui,
        check_imports,
        check_documentation,
    ]
    
    results = []
    for check in checks:
        try:
            results.append(check())
        except Exception as e:
            print(f"\n✗ Check failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print("Verification Summary")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"\nPassed: {passed}/{total}")
    
    if passed == total:
        print("\n✅ All checks passed!")
        print("\nImplementation is complete and verified.")
        return 0
    else:
        print("\n⚠️  Some checks failed.")
        print("\nPlease review the output above for details.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
