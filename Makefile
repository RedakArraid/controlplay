APP_PORT ?= 8000
DB_PORT ?= 5432
REDIS_PORT ?= 6379

.PHONY: frontend-build
# Construit la SPA (Vite → app/static/spa). Requis en dev Docker : le volume ./app:/app écrase l’image.
frontend-build:
	cd frontend && npm ci && npm run build

.PHONY: frontend-dev
# Hot reload (Vite) : ouvrir http://localhost:5173 — l’API est proxifiée vers 127.0.0.1:8000 (lancer FastAPI à part).
frontend-dev:
	cd frontend && npm run dev

.PHONY: test
test:
	cd app && python -m pytest tests/ -q -m "not browser"

# Pytest complet : unitaires/intégration + navigateur (installe Playwright si besoin).
.PHONY: test-all
test-all: test
	cd app && python -m pip install -q -r requirements-e2e.txt && python -m playwright install chromium && python -m pytest tests/test_e2e_browser.py -q --tb=short

# Tests navigateur (Playwright + Chromium). Une fois : pip install -r app/requirements-e2e.txt && playwright install chromium
.PHONY: test-browser
test-browser:
	cd app && python -m pip install -q -r requirements-e2e.txt && python -m playwright install chromium && python -m pytest tests/test_e2e_browser.py -v --tb=short

.PHONY: help
help:
	@echo "Cibles disponibles :"
	@echo "  init-env   - Crée .env à partir de .env.example s'il n'existe pas"
	@echo "  up         - Lance l'environnement Docker (build + up)"
	@echo "  migrate    - Applique les migrations Alembic (conteneur app doit tourner)"
	@echo "  revision   - Crée une nouvelle migration Alembic (message=...)"
	@echo "  bootstrap  - Démarre les services puis applique les migrations"
	@echo "  reset-admin - Réinitialise le mot de passe admin (ADMIN_* dans .env)"
	@echo "  admin-salle-only - ADMIN_USERNAME devient salle_admin (toutes les salles), sans super_admin"
	@echo "  ensure-super-admin - Crée/met à jour superadmin@controlplay.com (SUPER_ADMIN_* dans .env)"
	@echo "  ensure-dev-admin - Crée/met à jour admin@test.com (mot de passe testpass123 par défaut)"
	@echo "  down       - Arrête les conteneurs"
	@echo "  frontend-build - Build React → app/static/spa (Docker + volume ./app)"
	@echo "  frontend-dev   - Vite + hot reload sur :5173 (FastAPI :8000 séparé pour /api)"
	@echo "  test       - Lance pytest (auth web + paiements) hors Docker"
	@echo "  test-all   - test + test-browser (suite complète locale)"
	@echo "  test-browser - Playwright : tests login/admin/super-admin dans Chromium"

.PHONY: init-env
init-env:
	@if [ ! -f .env ]; then cp .env.example .env; echo ".env créé depuis .env.example"; else echo ".env existe déjà"; fi

.PHONY: up
up:
	APP_PORT=$(APP_PORT) DB_PORT=$(DB_PORT) REDIS_PORT=$(REDIS_PORT) docker compose up --build

.PHONY: migrate
migrate:
	docker compose exec app sh -lc "cd /app && alembic -c alembic.ini upgrade head"

.PHONY: revision
revision:
	@if [ -z "$(message)" ]; then echo "Usage: make revision message='description'"; exit 1; fi
	docker compose exec app sh -lc "cd /app && alembic -c alembic.ini revision --autogenerate -m \"$(message)\""

.PHONY: bootstrap
bootstrap:
	APP_PORT=$(APP_PORT) DB_PORT=$(DB_PORT) REDIS_PORT=$(REDIS_PORT) docker compose up -d --build
	docker compose exec app sh -lc "cd /app && alembic -c alembic.ini upgrade head"

.PHONY: down
down:
	docker compose down

# Réinitialise le hash bcrypt du user identifié par ADMIN_USERNAME (email ou phone)
# avec ADMIN_PASSWORD (voir .env). Utile si la connexion /login échoue après un changement manuel en DB.
.PHONY: reset-admin
reset-admin:
	docker compose exec app sh -lc "cd /app && python reset_admin_password.py"

.PHONY: admin-salle-only
admin-salle-only:
	docker compose exec app sh -lc "cd /app && python demote_env_admin_to_salle_admin.py"

# Compte propriétaire global (super_admin). Variables optionnelles dans .env :
# SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD, SUPER_ADMIN_NAME
.PHONY: ensure-super-admin
ensure-super-admin:
	docker compose exec app sh -lc "cd /app && python ensure_super_admin.py"

# Compte dev documenté (admin@test.com / testpass123) — utile si la base a été seed avec un autre ADMIN_*
.PHONY: ensure-dev-admin
ensure-dev-admin:
	docker compose exec app sh -lc "cd /app && python ensure_dev_admin.py"

