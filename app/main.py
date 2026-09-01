from contextlib import asynccontextmanager
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect

from .db import engine, Base, get_db
from . import models
from .router import router
from .support_system.router import router as support_router

from app.xlsx_import.router import router as xlsx_import_router
from app.xlsx_import.control import init_control_tables
from app.init_roles import init_builtin_roles


# ---------------------------------------------------------
# Logging
# ---------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s"
)


def ensure_admin_profile_columns():
    """Backfill missing admin profile columns for legacy databases created before the fields existed."""
    try:
        inspector = inspect(engine)
        columns = [col["name"] for col in inspector.get_columns("admin_users")]
        missing_columns = []

        for column_name, column_type in {
            "profile_image": "VARCHAR(1000)",
            "phone_number": "VARCHAR(50)",
            "bio": "TEXT",
        }.items():
            if column_name not in columns:
                missing_columns.append((column_name, column_type))

        if missing_columns:
            with engine.begin() as conn:
                for column_name, column_type in missing_columns:
                    conn.execute(f"ALTER TABLE admin_users ADD COLUMN IF NOT EXISTS {column_name} {column_type}")
            logging.getLogger(__name__).info("Added missing admin_users columns: %s", [name for name, _ in missing_columns])
    except Exception as exc:
        logging.getLogger(__name__).warning("Could not ensure admin_users profile columns: %s", exc)


# ---------------------------------------------------------
# Lifespan
# ---------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown events.
    """

    # Create database tables
    Base.metadata.create_all(bind=engine)

    # Backfill legacy database schemas that predate the profile-related columns.
    ensure_admin_profile_columns()

    # Initialize built-in roles
    db = next(get_db())
    try:
        init_builtin_roles(db)
    finally:
        db.close()

    # Initialize XLSX import control tables
    init_control_tables()

    yield

    # Shutdown logic can be added here if required


# ---------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------

app = FastAPI(
    title="CMS Backend API",
    lifespan=lifespan
)


# ---------------------------------------------------------
# CORS
# ---------------------------------------------------------

allow_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000"
).split(",")

allow_origins = [origin.strip() for origin in allow_origins]


app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------
# Routers
# ---------------------------------------------------------

app.include_router(router)

app.include_router(
    support_router,
    prefix="/api"
)

app.include_router(
    xlsx_import_router,
    prefix="/api"
)


# ---------------------------------------------------------
# Root Endpoint
# ---------------------------------------------------------

@app.get("/")
def read_root():
    return {
        "status": "Backend is running"
    }