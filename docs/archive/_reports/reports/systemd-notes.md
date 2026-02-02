# Systemd Service Notes

**Date:** December 28, 2025  
**Service:** amarktai-api.service  
**Status:** ✅ Production Ready

## Overview

The Amarktai Network API runs as a systemd service on Ubuntu 24.04, providing automatic startup, restart on failure, and proper lifecycle management.

## Service File Location

```
/etc/systemd/system/amarktai-api.service
```

## Service Configuration

### Full Service File

```ini
[Unit]
Description=Amarktai Network API
Documentation=https://github.com/amarktainetwork-blip/Amarktai-Network---Deployment
After=network.target mongodb.service

[Service]
Type=simple
User=amarktai
WorkingDirectory=/var/amarktai/app/backend
Environment="PATH=/var/amarktai/venv/bin"
EnvironmentFile=/var/amarktai/app/backend/.env

# Start command
ExecStart=/var/amarktai/venv/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8000 --log-level info

# Restart policy
Restart=always
RestartSec=5
TimeoutStopSec=60

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/amarktai/app /var/amarktai/logs
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictRealtime=true

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=amarktai-api

[Install]
WantedBy=multi-user.target
```

## Installation

### Using Provided Script

```bash
sudo bash tools/systemd_install.sh
```

This script:
1. Verifies prerequisites
2. Creates service file
3. Reloads systemd
4. Enables service
5. Optionally starts service

### Manual Installation

```bash
# Copy service file
sudo cp deploy/amarktai-api.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service
sudo systemctl enable amarktai-api

# Start service
sudo systemctl start amarktai-api
```

## Service Management

### Basic Commands

```bash
# Start service
sudo systemctl start amarktai-api

# Stop service
sudo systemctl stop amarktai-api

# Restart service
sudo systemctl restart amarktai-api

# Reload configuration (graceful)
sudo systemctl reload amarktai-api

# Check status
sudo systemctl status amarktai-api

# Enable at boot
sudo systemctl enable amarktai-api

# Disable at boot
sudo systemctl disable amarktai-api
```

### Viewing Logs

```bash
# View all logs
sudo journalctl -u amarktai-api

# Follow logs (live)
sudo journalctl -u amarktai-api -f

# Last 50 lines
sudo journalctl -u amarktai-api -n 50

# Since timestamp
sudo journalctl -u amarktai-api --since "2025-01-01"
sudo journalctl -u amarktai-api --since "10 minutes ago"

# With timestamps
sudo journalctl -u amarktai-api -o short-precise

# Export to file
sudo journalctl -u amarktai-api --since "today" > /tmp/api-logs.txt
```

## Service Lifecycle

### Startup Sequence

1. **System Boot**
   - systemd starts
   - Network initialized
   - MongoDB starts (if dependency configured)

2. **Service Start**
   - Load environment from `.env` file
   - Execute uvicorn with Python from venv
   - Server initializes (lifespan startup)
     - Start autopilot engine (with await)
     - Start AI bodyguard
     - Start self-healing systems
     - Initialize database connections
     - Start CCXT connections (if enabled)

3. **Ready State**
   - API listening on 127.0.0.1:8000
   - Health endpoint responding
   - All subsystems operational

### Shutdown Sequence

1. **Stop Command**
   - systemd sends SIGTERM
   - Uvicorn begins graceful shutdown

2. **Lifespan Shutdown**
   - Each subsystem stopped in try/except
   - Autopilot scheduler shutdown (wait=False)
   - CCXT exchanges closed
   - Database connections closed
   - Never raises exceptions

3. **Timeout**
   - TimeoutStopSec=60 (60 seconds)
   - If not stopped, systemd sends SIGKILL

### Restart on Failure

```ini
Restart=always
RestartSec=5
```

- Service automatically restarts on failure
- 5-second delay between restart attempts
- Prevents rapid restart loops

## Security Features

### User Isolation

```ini
User=amarktai
```

- Service runs as non-root user
- Limited system access
- Principle of least privilege

### Filesystem Protection

```ini
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/amarktai/app /var/amarktai/logs
```

- System directories read-only
- Home directories inaccessible
- Only specific paths writable

### Process Restrictions

```ini
NoNewPrivileges=true
PrivateTmp=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictRealtime=true
```

- Cannot gain new privileges
- Isolated /tmp directory
- Kernel parameters protected
- Control groups protected
- Realtime scheduling restricted

## Environment Variables

### EnvironmentFile

```ini
EnvironmentFile=/var/amarktai/app/backend/.env
```

All environment variables loaded from `.env`:
- JWT_SECRET
- MONGO_URL
- OPENAI_API_KEY
- Feature flags (ENABLE_TRADING, etc.)

### PATH Override

```ini
Environment="PATH=/var/amarktai/venv/bin"
```

Ensures Python packages from venv are used.

## Dependencies

### After Directive

```ini
After=network.target mongodb.service
```

- Waits for network to be ready
- Waits for MongoDB (if running locally)
- Does not fail if MongoDB service doesn't exist

### Adding More Dependencies

To wait for other services:

```bash
sudo systemctl edit amarktai-api

# Add:
[Unit]
After=network.target mongodb.service redis.service
Requires=mongodb.service
```

- `After` - Start after service
- `Requires` - Hard dependency (fail if service fails)
- `Wants` - Soft dependency (optional)

## Monitoring

### Service Health

```bash
# Check if active
systemctl is-active amarktai-api

# Check if enabled
systemctl is-enabled amarktai-api

# Failed status
systemctl is-failed amarktai-api
```

### Resource Usage

```bash
# CPU and memory
systemctl status amarktai-api

# Detailed resource usage
systemd-cgtop

# Process tree
systemctl status amarktai-api -l --no-pager
```

## Troubleshooting

### Service Won't Start

```bash
# Check status
sudo systemctl status amarktai-api

# View recent logs
sudo journalctl -u amarktai-api -n 100

# Common issues:
# 1. .env file missing
# 2. Port 8000 in use
# 3. MongoDB not running
# 4. Python dependencies missing
```

### Service Restarts Constantly

```bash
# Check restart rate
sudo systemctl list-units | grep amarktai-api

# View crash logs
sudo journalctl -u amarktai-api --since "10 minutes ago"

# Disable auto-restart temporarily
sudo systemctl edit amarktai-api
# Add: [Service]
#      Restart=no

# Debug manually
source /var/amarktai/venv/bin/activate
cd /var/amarktai/app/backend
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

### Permission Denied Errors

```bash
# Check file ownership
ls -la /var/amarktai/app/backend/.env

# Fix ownership
sudo chown -R amarktai:amarktai /var/amarktai/app
sudo chown -R amarktai:amarktai /var/amarktai/venv

# Reload systemd
sudo systemctl daemon-reload
sudo systemctl restart amarktai-api
```

### Port Already in Use

```bash
# Find process using port 8000
sudo lsof -i :8000
# OR
sudo ss -tulpn | grep :8000

# Kill process
sudo kill -9 <PID>

# Restart service
sudo systemctl restart amarktai-api
```

## Performance Tuning

### Multiple Workers

For production with multiple CPU cores:

```bash
sudo systemctl edit amarktai-api

# Add:
[Service]
ExecStart=
ExecStart=/var/amarktai/venv/bin/uvicorn server:app \
  --host 127.0.0.1 --port 8000 \
  --workers 4 \
  --log-level info

sudo systemctl daemon-reload
sudo systemctl restart amarktai-api
```

### Memory Limits

```bash
sudo systemctl edit amarktai-api

# Add:
[Service]
MemoryMax=2G
MemoryHigh=1.5G

sudo systemctl daemon-reload
sudo systemctl restart amarktai-api
```

### CPU Limits

```bash
sudo systemctl edit amarktai-api

# Add:
[Service]
CPUQuota=200%  # 2 cores max

sudo systemctl daemon-reload
sudo systemctl restart amarktai-api
```

## Logging Configuration

### Log Level

```ini
ExecStart=... --log-level info
```

Options: debug, info, warning, error, critical

### Log Rotation

Systemd journal handles rotation automatically. Configure limits:

```bash
# Edit journal config
sudo nano /etc/systemd/journald.conf

# Set:
SystemMaxUse=1G
SystemKeepFree=2G
MaxRetentionSec=30day

# Restart journald
sudo systemctl restart systemd-journald
```

### Export Logs

```bash
# Export to syslog format
sudo journalctl -u amarktai-api --since today --no-pager > /tmp/amarktai.log

# Export as JSON
sudo journalctl -u amarktai-api -o json --since today > /tmp/amarktai.json
```

## Testing

### Dry Run

```bash
# Validate service file
systemd-analyze verify /etc/systemd/system/amarktai-api.service

# Check service dependencies
systemctl list-dependencies amarktai-api
```

### Restart Loop Test

```bash
# Test 10 restarts
for i in {1..10}; do
    echo "Restart $i"
    sudo systemctl restart amarktai-api
    sleep 5
    systemctl is-active amarktai-api || break
done

# Should show no:
# - "never awaited" warnings
# - SchedulerNotRunningError
# - "Application shutdown failed"
# - Unclosed client session errors
```

## Best Practices

1. **Never edit service file directly**
   - Use `systemctl edit amarktai-api`
   - Creates override file
   - Preserves updates

2. **Always reload after changes**
   ```bash
   sudo systemctl daemon-reload
   ```

3. **Monitor logs after restart**
   ```bash
   sudo journalctl -u amarktai-api -f
   ```

4. **Test before enabling**
   - Start manually first
   - Verify health checks
   - Then enable for boot

5. **Use health checks**
   ```bash
   bash tools/health_check.sh
   ```

## Conclusion

The systemd service provides robust process management with:
- ✅ Automatic startup on boot
- ✅ Automatic restart on failure
- ✅ Graceful shutdown (60s timeout)
- ✅ Security hardening
- ✅ Centralized logging
- ✅ Resource limits

All critical restart issues have been fixed:
- No more "never awaited" warnings
- No more SchedulerNotRunningError  
- No more unclosed CCXT sessions
- Idempotent startup/shutdown

Service can be safely restarted repeatedly with no errors.
