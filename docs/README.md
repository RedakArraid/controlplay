## Vue d'ensemble du projet ControlPlay

ControlPlay permet de contrôler des TV de stations de jeu via des requêtes HTTP et des paiements en ligne.
Un client scanne un QR code affiché sur la TV, choisit une offre (durée + prix), paie (Paystack ou CinetPay),
et le système bascule la TV sur l'entrée HDMI de la console pendant la durée achetée, puis revient à l'écran d'accueil.

### Stack technique

- **Backend / Web**: FastAPI (Python)
- **Workers**: Celery (tâches asynchrones)
- **Base de données**: PostgreSQL
- **Queue / timers**: Redis
- **Migrations DB**: Alembic
- **Contrôle TV**: Broadlink RM Mini 3 (IR) via librairie `broadlink` (mode dry-run possible)
- **Conteneurisation**: Docker Compose

### Services Docker

- `app`: API + pages HTML (client + admin) sur le port 8000
- `worker`: worker Celery pour activer/désactiver les sessions de jeu
- `db`: PostgreSQL (stockage des stations, offres, sessions, logs)
- `redis`: broker / backend Celery

### Flux fonctionnel simplifié

1. La TV affiche la page d'accueil de la station avec un QR unique.
2. Le client scanne le QR, arrive sur `/s/{station_code}` et choisit une offre (durée + prix).
3. Le backend crée une session de jeu et redirige vers le paiement (MVP: simulation, ensuite Paystack/CinetPay).
4. À la confirmation de paiement (webhook PSP ou simulation), une tâche worker active la session :
   - envoie la commande IR pour passer la TV sur HDMI 2 (console)
   - programme la désactivation à la fin du temps (retour HDMI 1).

### Démarrage rapide (dev)

#### 1) Prérequis

- Docker Desktop installé et démarré
- `make` disponible dans le terminal

#### 2) Initialiser la configuration

Depuis la racine du projet :

```bash
make init-env
```

Cette commande crée `.env` à partir de `.env.example` si le fichier n'existe pas.

#### 3) Lancer l'environnement

```bash
make up
```

Services démarrés :

- `app` sur `http://localhost:${APP_PORT}` (par défaut `8000`)
- `db` exposé sur `${DB_PORT}` (par défaut `5432`)
- `redis` exposé sur `${REDIS_PORT}` (par défaut `6379`)

Tu peux changer les ports à la volée :

```bash
make up APP_PORT=8001 DB_PORT=5433 REDIS_PORT=6380
```

#### 4) Appliquer les migrations (Alembic)

Après démarrage des services :

```bash
make migrate
```

Alternative en une seule commande (démarrage + migration) :

```bash
make bootstrap
```

Notes importantes :

- La configuration Alembic est dans `/app` (`app/alembic.ini` et `app/alembic/`).
- Les commandes `make migrate` et `make revision` exécutent Alembic depuis le conteneur `app`.
- En cas de problème local Buildx/permissions Docker, tu peux utiliser :

```bash
DOCKER_BUILDKIT=0 COMPOSE_DOCKER_CLI_BUILD=0 make bootstrap
```

#### 5) Arrêter les services

```bash
make down
```

