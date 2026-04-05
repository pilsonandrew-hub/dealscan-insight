"""
Database configuration and session management
"""
import importlib
import logging

from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from config.settings import settings

logger = logging.getLogger(__name__)

supabase_client = None
try:
    import os

    _supabase_url = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL", "")
    _supabase_key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("VITE_SUPABASE_ANON_KEY", "")
    )
    if _supabase_url and _supabase_key:
        from supabase import create_client

        supabase_client = create_client(_supabase_url, _supabase_key)
except Exception as exc:
    logger.warning("Supabase client init failed in webapp.database (non-fatal): %s", exc)

# Create engine with proper pooling
engine = None  # type: ignore[assignment]
if settings.database_url.startswith("sqlite"):
    # SQLite for testing only
    engine = create_engine(
        settings.database_url,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
        echo=settings.debug
    )
elif settings.database_url:
    # PostgreSQL for production
    engine = create_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_timeout=settings.database_pool_timeout,
        pool_recycle=3600,  # Recycle connections every hour
        echo=settings.debug
    )
else:
    logger.warning(
        "DATABASE_URL not set — SQLAlchemy engine not created. "
        "Routes that depend on SessionLocal will fail at request time, not import time."
    )

# Session factory — only bind to engine if one was successfully created
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) if engine is not None else None  # type: ignore[arg-type]

# Base class for models
Base = declarative_base()

async def init_db():
    """Initialize database and create tables"""
    try:
        # Import all models to ensure they're registered
        from webapp.models import user, vehicle, audit_log

        try:
            importlib.import_module("webapp.models.opportunity")
        except ImportError:
            logger.warning(
                "Optional model module webapp.models.opportunity is unavailable; "
                "continuing with registered models."
            )
        
        # Create tables
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized successfully")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

def get_db() -> Session:
    """Database dependency for FastAPI"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def check_db_health() -> bool:
    """Check database connectivity"""
    try:
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False

# Database event listeners for monitoring (only if engine was created)
if engine is not None:
    @event.listens_for(engine, "connect")
    def receive_connect(dbapi_connection, connection_record):
        """Log database connections"""
        logger.debug("Database connection established")

    @event.listens_for(engine, "disconnect")
    def receive_disconnect(dbapi_connection, connection_record):
        """Log database disconnections"""
        logger.debug("Database connection closed")
