#!/usr/bin/env python3
"""
System Health Monitor
=====================
Lightweight monitoring service that checks system health and sends alerts.

Features:
- Pings /api/health/ping endpoint
- Checks log files for errors
- Sends daily health report
- Sends alerts on failures

Usage:
    # Run health check
    python scripts/health_monitor.py check
    
    # Start monitoring daemon (runs every 5 minutes)
    python scripts/health_monitor.py daemon
    
    # Send daily report
    python scripts/health_monitor.py report

Systemd service example in deployment/systemd/amarktai-monitor.service
"""

import sys
import os
import time
import json
import asyncio
import smtplib
from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Add backend to path for imports
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

# Configuration from environment
API_URL = os.getenv('API_URL', 'http://127.0.0.1:8000')
HEALTH_ENDPOINT = f"{API_URL}/api/health/ping"
LOG_FILE = os.getenv('LOG_FILE', '/var/log/amarktai/backend.log')
ALERT_EMAIL = os.getenv('ALERT_EMAIL', 'amarktainetwork@gmail.com')
CHECK_INTERVAL = int(os.getenv('HEALTH_CHECK_INTERVAL', '300'))  # 5 minutes

# SMTP Configuration
SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
FROM_EMAIL = os.getenv('FROM_EMAIL', SMTP_USER)

# State file to track consecutive failures
STATE_FILE = '/tmp/amarktai-monitor-state.json'


def load_state():
    """Load monitor state from disk"""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        'consecutive_failures': 0,
        'last_alert_time': None,
        'last_success_time': None
    }


def save_state(state):
    """Save monitor state to disk"""
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Warning: Could not save state: {e}")


def send_email(subject, body):
    """Send email alert"""
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"Email disabled: {subject}")
        return False
    
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = f"Amarktai Monitor <{FROM_EMAIL}>"
        msg['To'] = ALERT_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
        
        print(f"✅ Email sent: {subject}")
        return True
    except Exception as e:
        print(f"❌ Email failed: {e}")
        return False


def check_health():
    """Check system health by pinging health endpoint"""
    try:
        import requests
        response = requests.get(HEALTH_ENDPOINT, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return {
                'status': 'healthy',
                'response_time': response.elapsed.total_seconds(),
                'data': data
            }
        else:
            return {
                'status': 'unhealthy',
                'error': f"HTTP {response.status_code}",
                'response': response.text[:200]
            }
    except Exception as e:
        return {
            'status': 'unhealthy',
            'error': str(e)
        }


def check_logs():
    """Check log file for recent errors"""
    if not os.path.exists(LOG_FILE):
        return {'error_count': 0, 'warning': 'Log file not found'}
    
    try:
        # Read last 1000 lines
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()[-1000:]
        
        # Count errors in last hour
        errors = []
        for line in lines:
            if 'ERROR' in line or 'CRITICAL' in line:
                errors.append(line.strip())
        
        return {
            'error_count': len(errors),
            'recent_errors': errors[-10:]  # Last 10 errors
        }
    except Exception as e:
        return {'error_count': 0, 'warning': str(e)}


def run_check():
    """Run health check and send alerts if needed"""
    print("=" * 60)
    print(f"🔍 Health Check - {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)
    
    state = load_state()
    
    # Check health
    health = check_health()
    print(f"\n📊 API Health: {health['status'].upper()}")
    
    if health['status'] == 'healthy':
        print(f"   Response time: {health.get('response_time', 0):.3f}s")
        state['consecutive_failures'] = 0
        state['last_success_time'] = datetime.now(timezone.utc).isoformat()
        save_state(state)
        
    else:
        print(f"   Error: {health.get('error', 'Unknown')}")
        state['consecutive_failures'] += 1
        
        # Send alert after 3 consecutive failures
        if state['consecutive_failures'] >= 3:
            last_alert = state.get('last_alert_time')
            now = datetime.now(timezone.utc)
            
            # Only send alert if no alert in last hour
            should_alert = True
            if last_alert:
                try:
                    last_alert_dt = datetime.fromisoformat(last_alert)
                    if (now - last_alert_dt) < timedelta(hours=1):
                        should_alert = False
                except (ValueError, TypeError) as e:
                    print(f"Warning: Invalid timestamp format in state: {e}")
                    # Continue with alert if timestamp is invalid
            
            if should_alert:
                subject = "🚨 Amarktai System Health Alert"
                body = f"""
Amarktai system health check failed.

Status: {health['status']}
Error: {health.get('error', 'Unknown')}
Consecutive failures: {state['consecutive_failures']}
Time: {now.isoformat()}

Please check the system logs and ensure the backend service is running.

Log file: {LOG_FILE}
Health endpoint: {HEALTH_ENDPOINT}

---
Amarktai Health Monitor
                """
                send_email(subject, body)
                state['last_alert_time'] = now.isoformat()
        
        save_state(state)
    
    # Check logs
    logs = check_logs()
    print(f"\n📄 Log Analysis:")
    print(f"   Recent errors: {logs.get('error_count', 0)}")
    
    if logs.get('error_count', 0) > 50:
        print(f"   ⚠️  High error count detected!")
    
    print("\n" + "=" * 60)
    return health['status'] == 'healthy'


def send_daily_report():
    """Send daily health report"""
    print("📧 Generating daily health report...")
    
    state = load_state()
    health = check_health()
    logs = check_logs()
    
    # Calculate uptime
    uptime = "N/A"
    if state.get('last_success_time'):
        last_success = datetime.fromisoformat(state['last_success_time'])
        uptime = f"{(datetime.now(timezone.utc) - last_success).total_seconds() / 3600:.1f} hours ago"
    
    subject = f"Amarktai Daily Health Report - {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    body = f"""
Amarktai Daily Health Report
{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}

SYSTEM STATUS
-------------
Current Status: {health['status'].upper()}
Last Success: {uptime}
Consecutive Failures: {state.get('consecutive_failures', 0)}

LOG ANALYSIS
------------
Recent Errors (last 1000 lines): {logs.get('error_count', 0)}

API HEALTH
----------
Endpoint: {HEALTH_ENDPOINT}
Status: {health.get('status', 'unknown')}
{f"Error: {health.get('error', 'N/A')}" if health.get('error') else ''}

RECOMMENDATIONS
---------------
{f"⚠️  System appears to be down - investigate immediately" if health['status'] == 'unhealthy' else "✅ System is healthy"}
{f"⚠️  High error count - review logs" if logs.get('error_count', 0) > 50 else "✅ Error count is normal"}

---
Amarktai Health Monitor
    """
    
    send_email(subject, body)
    print("✅ Daily report sent")


def daemon_mode():
    """Run as daemon, checking every CHECK_INTERVAL seconds"""
    print(f"🚀 Starting health monitor daemon")
    print(f"   Check interval: {CHECK_INTERVAL} seconds ({CHECK_INTERVAL // 60} minutes)")
    print(f"   Health endpoint: {HEALTH_ENDPOINT}")
    print(f"   Alert email: {ALERT_EMAIL}")
    print()
    
    while True:
        try:
            run_check()
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            print("\n⛔ Stopping monitor...")
            break
        except Exception as e:
            print(f"❌ Monitor error: {e}")
            time.sleep(60)  # Wait 1 minute on error


def main():
    """Main entry point"""
    if len(sys.argv) < 2:
        print("Usage: python health_monitor.py [check|daemon|report]")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == 'check':
        success = run_check()
        sys.exit(0 if success else 1)
    elif command == 'daemon':
        daemon_mode()
    elif command == 'report':
        send_daily_report()
    else:
        print(f"Unknown command: {command}")
        print("Usage: python health_monitor.py [check|daemon|report]")
        sys.exit(1)


if __name__ == "__main__":
    main()
