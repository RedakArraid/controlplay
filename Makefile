APP_PORT ?= 8000
DB_PORT ?= 5432
REDIS_PORT ?= 6379

.PHONY: help
help:
	@echo "Cibles disponibles :"
	@echo "  init-env   - Crée .env à partir de .env.example s'il n'existe pas"
	@echo "  up         - Lance l'environnement Docker (build + up)"
	@echo "  migrate    - Applique les migrations Alembic (upgrade head)"
	@echo "  revision   - Crée une nouvelle migration Alembic (message=...)"
	@echo "  bootstrap  - Démarre les services puis applique les migrations"
	@echo "  down       - Arrête les conteneurs"

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

