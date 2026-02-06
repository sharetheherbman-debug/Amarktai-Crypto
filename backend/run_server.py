#!/usr/bin/env python3
"""
Boot-Safe Server Entrypoint
Safely imports and runs the FastAPI server with error handling
Can be used by systemd instead of directly importing server:app
"""

import sys
import os
import logging

# Configure basic logging before anything else
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = logging.getLogger(__name__)

def main():
    """Main entry point with safe import handling"""
    try:
        logger.info("="*80)
        logger.info("🚀 Amarktai Network - Boot-Safe Server Entrypoint")
        logger.info("="*80)
        
        # Validate Python version
        if sys.version_info < (3, 8):
            logger.error("❌ Python 3.8+ required")
            sys.exit(1)
        
        logger.info(f"✅ Python {sys.version.split()[0]}")
        
        # Validate required environment variables (non-critical)
        required_env = ['MONGO_URL', 'JWT_SECRET']
        missing_env = []
        for env_var in required_env:
            if not os.getenv(env_var):
                missing_env.append(env_var)
        
        if missing_env:
            logger.warning(f"⚠️  Missing environment variables: {', '.join(missing_env)}")
            logger.warning("⚠️  Server may fail to start - check /etc/amarktai/amarktai.env")
        
        # Import uvicorn
        try:
            import uvicorn
        except ImportError:
            logger.error("❌ uvicorn not installed - run: pip install uvicorn")
            sys.exit(1)
        
        # Import server module (this triggers all imports)
        try:
            logger.info("📦 Importing server module...")
            import server
            logger.info("✅ Server module imported successfully")
        except Exception as import_error:
            logger.error(f"❌ Failed to import server module: {import_error}", exc_info=True)
            sys.stderr.write(f"\nFATAL: Server import failed: {import_error}\n")
            sys.exit(1)
        
        # Get configuration
        host = os.getenv("HOST", "127.0.0.1")
        port = int(os.getenv("PORT", "8000"))
        log_level = os.getenv("LOG_LEVEL", "info").lower()
        
        logger.info(f"📡 Starting server on {host}:{port}")
        logger.info(f"📝 Log level: {log_level}")
        logger.info("="*80)
        
        # Run uvicorn
        uvicorn.run(
            "server:app",
            host=host,
            port=port,
            log_level=log_level,
            access_log=True
        )
        
    except KeyboardInterrupt:
        logger.info("\n👋 Server stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.stderr.write(f"\nFATAL ERROR: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
