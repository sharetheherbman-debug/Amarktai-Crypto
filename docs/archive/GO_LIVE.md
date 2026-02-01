# GO LIVE - Production Deployment Guide

## Overview
This document provides exact VPS commands for deploying the Amarktai Network trading system to production.

## Prerequisites
- VPS with Ubuntu 20.04+ or Debian 11+
- Root or sudo access
- Domain pointing to VPS IP
- Minimum 2GB RAM, 2 CPU cores, 20GB storage

## Quick Deployment

### 1. Clone Repository on VPS
```bash
cd /opt
sudo git clone https://github.com/sharetheherbman-debug/Amarktai-Network---Deployment.git
cd Amarktai-Network---Deployment
```

### 2. Set Environment Variables
```bash
# Copy example env file
cd backend
cp .env.example .env

# Edit with your credentials
sudo nano .env
```

Required environment variables:
```bash
# Database
DATABASE_URL=postgresql://user:password@localhost/amarktai_db

# OpenAI (Required for AI features)
OPENAI_API_KEY=your_openai_key_here

# Admin Password (for admin panel unlock)
ADMIN_PASSWORD=Ashmor12@

# JWT Secret (generate a strong random string)
JWT_SECRET=your_jwt_secret_here
JWT_ALGORITHM=HS256

# Optional Exchange API Keys
LUNO_API_KEY=your_luno_key
LUNO_API_SECRET=your_luno_secret

BINANCE_API_KEY=your_binance_key
BINANCE_API_SECRET=your_binance_secret

KUCOIN_API_KEY=your_kucoin_key
KUCOIN_API_SECRET=your_kucoin_secret
KUCOIN_PASSPHRASE=your_kucoin_passphrase

OVEX_API_KEY=your_ovex_key
OVEX_API_SECRET=your_ovex_secret

VALR_API_KEY=your_valr_key
VALR_API_SECRET=your_valr_secret
```

### 3. Install System Dependencies
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.10+
sudo apt install python3 python3-pip python3-venv -y

# Install Node.js 18+ (for frontend)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install nodejs -y

# Install PostgreSQL
sudo apt install postgresql postgresql-contrib -y

# Install Nginx
sudo apt install nginx -y

# Install PM2 (for process management)
sudo npm install -g pm2
```

### 4. Setup Database
```bash
# Switch to postgres user
sudo -u postgres psql

# In psql shell:
CREATE DATABASE amarktai_db;
CREATE USER amarktai_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE amarktai_db TO amarktai_user;
\q

# Run migrations
cd /opt/Amarktai-Network---Deployment/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
```

### 5. Deploy Backend
```bash
cd /opt/Amarktai-Network---Deployment/backend

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start with PM2
pm2 start server.py --name amarktai-backend --interpreter python3
pm2 save
pm2 startup

# Check logs
pm2 logs amarktai-backend
```

### 6. Deploy Frontend
```bash
cd /opt/Amarktai-Network---Deployment

# Run deployment script
bash scripts/deploy.sh

# Or manually:
cd frontend
rm -rf node_modules build
npm ci
npm run build

# Sync to web root
sudo mkdir -p /var/www/html/amarktai
sudo rsync -av --delete build/ /var/www/html/amarktai/
sudo chown -R www-data:www-data /var/www/html/amarktai
sudo chmod -R 755 /var/www/html/amarktai
```

### 7. Configure Nginx
```bash
# Create nginx config
sudo nano /etc/nginx/sites-available/amarktai
```

Paste this configuration:
```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;
    
    # Frontend
    root /var/www/html/amarktai;
    index index.html;
    
    # Frontend routes (SPA)
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # Backend API proxy
    location /api/ {
        proxy_pass http://localhost:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts for long-running requests
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # WebSocket support
    location /ws/ {
        proxy_pass http://localhost:8000/ws/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket timeouts
        proxy_connect_timeout 7d;
        proxy_send_timeout 7d;
        proxy_read_timeout 7d;
    }
    
    # Static assets caching
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

Enable the site:
```bash
sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 8. Setup SSL (Optional but Recommended)
```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Get SSL certificate
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Auto-renewal is set up automatically
sudo certbot renew --dry-run
```

### 9. Verify Deployment
```bash
# Run verification script
cd /opt/Amarktai-Network---Deployment
bash scripts/verify_go_live.sh

# Check backend status
pm2 status
pm2 logs amarktai-backend --lines 50

# Check nginx status
sudo systemctl status nginx

# Check if site is accessible
curl http://localhost:8000/api/health
curl http://your-domain.com
```

## Post-Deployment Checklist

- [ ] Backend is running and accessible at `/api/health`
- [ ] Frontend loads at root URL
- [ ] Can register a new user account
- [ ] Can login successfully
- [ ] Dashboard loads without errors
- [ ] Can configure API keys in API Setup
- [ ] Can create a bot
- [ ] Live trades section shows data (after trades execute)
- [ ] Admin panel unlocks with password: `Ashmor12@`
- [ ] WebSocket connection established (check browser console)
- [ ] No console errors in browser
- [ ] SSL certificate valid (if configured)

## Maintenance Commands

### Update Application
```bash
cd /opt/Amarktai-Network---Deployment
git pull origin main

# Redeploy backend
cd backend
source venv/bin/activate
pip install -r requirements.txt
pm2 restart amarktai-backend

# Redeploy frontend
cd ..
bash scripts/deploy.sh
```

### View Logs
```bash
# Backend logs
pm2 logs amarktai-backend

# Nginx access logs
sudo tail -f /var/log/nginx/access.log

# Nginx error logs
sudo tail -f /var/log/nginx/error.log

# System logs
sudo journalctl -u nginx -f
```

### Backup Database
```bash
# Create backup
sudo -u postgres pg_dump amarktai_db > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore from backup
sudo -u postgres psql amarktai_db < backup_file.sql
```

### Monitor System Resources
```bash
# Check disk usage
df -h

# Check memory usage
free -h

# Check CPU usage
top

# Check running processes
pm2 monit
```

## Troubleshooting

### Backend Won't Start
```bash
# Check logs
pm2 logs amarktai-backend

# Common issues:
# - Missing environment variables: Check .env file
# - Database connection: Verify DATABASE_URL
# - Port 8000 in use: Change PORT in .env or kill existing process
```

### Frontend Shows Blank Page
```bash
# Check nginx config
sudo nginx -t

# Check if build directory has files
ls -la /var/www/html/amarktai/

# Check nginx error logs
sudo tail -f /var/log/nginx/error.log

# Rebuild frontend
cd /opt/Amarktai-Network---Deployment
bash scripts/deploy.sh
```

### 502 Bad Gateway
```bash
# Backend is not running or not accessible
pm2 status
pm2 restart amarktai-backend

# Check if port 8000 is listening
sudo netstat -tulpn | grep 8000
```

### WebSocket Connection Fails
```bash
# Check nginx WebSocket proxy settings
sudo nano /etc/nginx/sites-available/amarktai

# Ensure these headers are set:
# proxy_set_header Upgrade $http_upgrade;
# proxy_set_header Connection "upgrade";

# Reload nginx
sudo systemctl reload nginx
```

## Performance Optimization

### Enable Gzip Compression
```bash
sudo nano /etc/nginx/nginx.conf

# Add in http block:
gzip on;
gzip_vary on;
gzip_proxied any;
gzip_comp_level 6;
gzip_types text/plain text/css text/xml text/javascript application/json application/javascript application/xml+rss application/rss+xml font/truetype font/opentype application/vnd.ms-fontobject image/svg+xml;
```

### PM2 Process Monitoring
```bash
# Enable PM2 monitoring
pm2 install pm2-logrotate

# Set log rotation
pm2 set pm2-logrotate:max_size 10M
pm2 set pm2-logrotate:retain 10
```

## Security Hardening

### Firewall Configuration
```bash
# Install UFW
sudo apt install ufw -y

# Allow SSH, HTTP, HTTPS
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Block direct backend access
sudo ufw deny 8000/tcp

# Enable firewall
sudo ufw enable
sudo ufw status
```

### Fail2ban (Prevent Brute Force)
```bash
# Install fail2ban
sudo apt install fail2ban -y

# Configure
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

## Support

For issues or questions:
- Check logs: `pm2 logs amarktai-backend`
- Run verification: `bash scripts/verify_go_live.sh`
- Review error messages in browser console
- Contact: [support email or GitHub issues]

## Version History
- **v1.0.0** - Initial production release
  - 5 supported platforms: Luno, Binance, KuCoin, OVEX, VALR
  - Paper trading and live trading modes
  - AI-powered trading decisions
  - Admin panel with system monitoring
  - Real-time WebSocket updates
