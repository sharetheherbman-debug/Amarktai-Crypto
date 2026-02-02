# Reports Directory

This directory contains all audit reports, deployment guides, and documentation for the Amarktai Network project.

## 📋 Index

### Dependency Audits
- **[dependency-audit.md](dependency-audit.md)** - Comprehensive dependency reorganization audit
- **[backend-deps-audit.md](backend-deps-audit.md)** - Backend Python dependencies analysis
- **[frontend-deps-audit.md](frontend-deps-audit.md)** - Frontend Node.js dependencies analysis

### Deployment Guides
- **[deployment-notes.md](deployment-notes.md)** - Complete production deployment guide
- **[systemd-notes.md](systemd-notes.md)** - Systemd service management guide

## 🎯 Quick Links

### For Deployment
1. Start with [deployment-notes.md](deployment-notes.md) for full deployment process
2. Review [dependency-audit.md](dependency-audit.md) to understand modular requirements
3. Check [systemd-notes.md](systemd-notes.md) for service management

### For Development
1. Review [backend-deps-audit.md](backend-deps-audit.md) for Python dependency details
2. Check [frontend-deps-audit.md](frontend-deps-audit.md) for Node.js setup
3. Understand [dependency-audit.md](dependency-audit.md) for optional feature modules

## 📦 Modular Requirements Structure

The backend dependencies are organized into separate files:

- **`backend/requirements/base.txt`** - Core FastAPI, database, auth (always required)
- **`backend/requirements/trading.txt`** - CCXT and trading features (optional)
- **`backend/requirements/ai.txt`** - ML, transformers, LangChain (optional)
- **`backend/requirements/agents.txt`** - Fetch.ai uAgents (optional, may conflict)
- **`backend/requirements/dev.txt`** - Testing, linting, type checking (development only)
- **`backend/requirements/constraints.txt`** - Version constraints to prevent conflicts

## 🚀 Installation Examples

### Minimal (API only)
```bash
pip install -r backend/requirements/base.txt
```

### With Trading
```bash
pip install -r backend/requirements/base.txt -r backend/requirements/trading.txt
```

### With AI Features
```bash
pip install -r backend/requirements/base.txt -r backend/requirements/ai.txt
```

### Full Stack (Trading + AI)
```bash
pip install -r backend/requirements/base.txt \
            -r backend/requirements/trading.txt \
            -r backend/requirements/ai.txt
```

### Development Environment
```bash
pip install -r backend/requirements/base.txt \
            -r backend/requirements/trading.txt \
            -r backend/requirements/ai.txt \
            -r backend/requirements/dev.txt
```

## ⚠️ Important Notes

### Agents Module Conflicts
The `agents.txt` file contains Fetch.ai dependencies that have protobuf version conflicts with Google AI packages. Only install if you specifically need Fetch.ai agent features.

### Feature Flags
Use environment variables to control which features are enabled:
- `ENABLE_TRADING=true/false` - Trading features (requires trading.txt)
- `ENABLE_AI=true/false` - AI features (requires ai.txt)
- `ENABLE_AGENTS=true/false` - Fetch.ai agents (requires agents.txt)
- `ENABLE_AUTOPILOT=true/false` - Autonomous trading
- `ENABLE_CCXT=true/false` - Exchange connections

## 📖 Documentation Updates

All reports are kept up-to-date with the latest changes. When making changes to dependencies or deployment procedures, update the relevant report file.

## 🔍 Finding Information

- **Dependency issues?** → Check dependency-audit.md
- **Installation failing?** → Check deployment-notes.md troubleshooting section
- **Service not starting?** → Check systemd-notes.md
- **Frontend build errors?** → Check frontend-deps-audit.md
- **Backend import errors?** → Check backend-deps-audit.md and dependency-audit.md

## 📝 Contributing

When adding new features or dependencies:
1. Update the appropriate requirements file in `backend/requirements/`
2. Document the change in `dependency-audit.md`
3. Test installation in a clean Python 3.12 environment
4. Update this README.md index if adding new reports
