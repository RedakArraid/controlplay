"""
Configuration pytest : base SQLite en mémoire partagée (StaticPool) pour toute la suite.

Doit être chargé avant `import main` afin que le seed startup et TestClient
utilisent la même base que les overrides éventuels.
"""
from __future__ import annotations

import os
import sys

_APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-for-pytest")
os.environ.setdefault("ADMIN_USERNAME", "admin@test.com")
os.environ.setdefault("ADMIN_PASSWORD", "testpass123")
os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("AUTO_CREATE_SCHEMA", "false")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import database as _database  # noqa: E402
import models  # noqa: F401, E402 — enregistre les tables sur Base.metadata

_test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_database.engine = _test_engine
_database.SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=_test_engine,
)
_database.Base.metadata.create_all(bind=_test_engine)

# Seed synchrone : le premier test ne doit pas dépendre du fait que le 1er HTTP soit /admin ou /health.
# (sinon un test qui commence par GET /login peut échouer avant que le lifespan n’ait peuplé la DB selon l’ordre d’exécution.)
import main as _main_module  # noqa: E402

_main_module.seed_default_data()
