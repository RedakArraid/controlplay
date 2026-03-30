"""
Lance l'app FastAPI pour les tests navigateur (même SQLite en mémoire que conftest).

Usage : depuis le dossier ``app/`` ::
    python tests/e2e_server.py

Port : variable d'environnement ``E2E_PORT`` (défaut 9876).
"""
from __future__ import annotations

import os
import sys

_APP = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _APP)

os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-for-pytest")
# Ce script est réservé aux E2E : identifiants fixes (l'environnement hôte peut
# avoir ADMIN_USERNAME/ADMIN_PASSWORD pour Docker, ce qui casserait le login).
os.environ["ADMIN_USERNAME"] = "admin@test.com"
os.environ["ADMIN_PASSWORD"] = "testpass123"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("AUTO_CREATE_SCHEMA", "false")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

import database as _database  # noqa: E402
import models  # noqa: F401, E402

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

import uvicorn  # noqa: E402
import main as main_module  # noqa: E402

if __name__ == "__main__":
    # Garantit les données avant le premier client (au cas où le worker uvicorn
    # ne déclencherait pas le lifespan comme attendu).
    main_module.seed_default_data()
    port = int(os.environ.get("E2E_PORT", "9876"))
    uvicorn.run(
        main_module.app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
