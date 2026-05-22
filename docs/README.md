## Vue d'ensemble du projet ControlPlay

ControlPlay permet de contrôler des TV de stations de jeu via des requêtes HTTP et des paiements en ligne.
Un client scanne un QR code affiché sur la TV, choisit une offre (durée + prix),
et le système lance le paiement automatiquement avec **Paystack en priorité** et **CinetPay en backup** (sans choix du provider côté utilisateur).
Le système bascule ensuite la TV sur l'entrée HDMI de la console pendant la durée achetée, puis revient à l'écran d'accueil.

### Stack technique

- **Backend / Web**: FastAPI (Python)
- **Interface admin / publique (SPA)**: React + TypeScript + Vite + Tailwind (`frontend/`), build dans `app/static/spa/`, API JSON sous `/api`
- **Workers**: Celery (tâches asynchrones)
- **Base de données**: PostgreSQL
- **Queue / timers**: Redis
- **Migrations DB**: Alembic
- **Contrôle TV**: Broadlink RM Mini 3 (IR) via librairie `broadlink` (mode dry-run possible)
- **Conteneurisation**: Docker Compose

### Services Docker

- `app`: API FastAPI + **SPA React** (build dans `app/static/spa`) + **pages HTML client** (`/salle/…`, checkout legacy) ; **`GET /s/{code}`** sert la SPA (checkout via POST `/checkout` / `/extend/checkout`) sur le port **8000**
- `worker`: worker Celery pour activer/désactiver les sessions de jeu
- `db`: PostgreSQL (stockage des stations, offres, sessions, logs)
- `redis`: broker / backend Celery

### Flux fonctionnel simplifié

1. La TV affiche la page d'accueil de la station avec un QR unique.
2. Le client scanne le QR, arrive sur `/s/{station_code}` (page **SPA** : route React `/s/:stationCode`, données `GET /api/public/stations/{code}`) et choisit une offre (durée + prix).
   Les offres sont des templates rattachés via l'admin :
   - directement à la station (`station_offers`)
   - ou via la salle de la station (`salle_offers`)
   Les salles peuvent aussi être annotées côté admin via des utilisateurs (rôle `manager` / `responsable`) et des coordonnées GPS.
   Les admins sont gérés en RBAC : `super_admin` (plateforme), `salle_admin` / `manager` / `responsable` (par salle, table `salle_users`) — voir section **Administrateurs de salle** ci-dessous.
   Le formulaire de paiement :
   - `connexion` optionnelle : si cochée, `phone` est obligatoire et `email` reste optionnel
   - si non cochée (mode invité), `email` et `phone` peuvent être vides (associé à `default_user`)
3. Le backend crée une session de jeu et redirige vers le paiement :
   - Les clés PSP se configurent dans **`.env`** ; le détail des variables et URLs webhooks est dans **`docs/PSP_PAYSTACK_CINETPAY.md`**.
   - Le super-admin peut activer ou désactiver chaque PSP (sans retirer les clés) via **`/super-admin/providers`** (formulaire posté vers `/admin/providers`).
   - Pour supervision, un récapitulatif est disponible via `/admin/dashboard`.
   - **MVP/dev**: simulation (si les clés PSP ne sont pas configurées)
   - **production**: initialisation Paystack, fallback CinetPay si nécessaire
4. À la confirmation de paiement (webhook PSP / retour PSP ou simulation) :
   - une tâche worker active la session
   - envoie la commande IR pour passer la TV sur HDMI 2 (console)
   - programme la désactivation à la fin du temps (retour HDMI 1)
   - l’utilisateur est redirigé vers la page de la station `/s/{station_code}` pour pouvoir ajouter du temps

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

#### 3) Construire l’interface web (SPA)

Avec **Docker Compose**, le répertoire local `./app` est monté dans le conteneur (`./app:/app`) : le build Vite présent **dans l’image** est remplacé par ton arborescence hôte. Il faut donc générer **`app/static/spa/`** sur ta machine (Node.js 20+ / npm) **avant** ou **après** le premier `make up` :

```bash
make frontend-build
```

Sans ce dossier, les routes `/`, `/login`, `/admin`, `/super-admin` renvoient **503** (« Interface web non construite »). Voir aussi `frontend/README.md`.

#### 3 bis) Développement front avec rechargement à chaud (optionnel)

Pour modifier l’interface **sans** relancer `npm run build` à chaque fois :

1. Lancer l’API sur le port **8000** (Docker ou `uvicorn` local).
2. Dans un second terminal : **`make frontend-dev`** (ou `cd frontend && npm run dev`).
3. Ouvrir **`http://localhost:5173`** (Vite). Les appels **`/api`** sont proxifiés vers **`127.0.0.1:8000`**.

Le hot reload **ne s’applique pas** si tu ouvres uniquement **`http://localhost:8000`** : ce sont les fichiers **déjà buildés**.

#### 4) Lancer l'environnement

```bash
make up
```

Services démarrés :

- `app` sur `http://localhost:${APP_PORT}` (par défaut `8000`) — aligner `BASE_URL` dans `.env` sur ce port (ex. `http://localhost:8001` si `APP_PORT=8001`).
- `db` exposé sur `${DB_PORT}` (par défaut `5432`)
- `redis` exposé sur `${REDIS_PORT}` (par défaut `6379`)

Tu peux changer les ports à la volée :

```bash
make up APP_PORT=8001 DB_PORT=5433 REDIS_PORT=6380
```

#### 5) Appliquer les migrations (Alembic)

Après démarrage des services :

```bash
make migrate
```

Alternative en une seule commande (démarrage + migration) :

```bash
make bootstrap
```

**Après un `git pull`** (nouvelles migrations, ex. RBAC / `created_by_user_id`) : relance **`make migrate`** puis, si besoin, **`make ensure-dev-admin`** pour resynchroniser le compte dev.

Notes importantes :

- La configuration Alembic est dans `/app` (`app/alembic.ini` et `app/alembic/`).
- Les commandes `make migrate` et `make revision` exécutent Alembic depuis le conteneur `app`.
- En cas de problème local Buildx/permissions Docker, tu peux utiliser :

```bash
DOCKER_BUILDKIT=0 COMPOSE_DOCKER_CLI_BUILD=0 make bootstrap
```

#### 6) Arrêter les services

```bash
make down
```

#### Tests automatisés (sans Docker)

Depuis la racine du dépôt, les tests **pytest** utilisent une SQLite en mémoire (sessions `/login`, `/admin`, `/super-admin`, idempotence paiements) :

```bash
make test
```

Pour inclure les tests **navigateur** (Playwright / Chromium) en local : `make test-all` ou `make test-browser` (voir `Makefile`).

Sur GitHub, le workflow **Tests** (`.github/workflows/tests.yml`) lance la même suite **`make test`** sur push / pull request.

#### Administration : connexion (`/login`)

Les pages **`/admin`** et **`/super-admin`** exigent une **session** (cookie signé, secret `APP_SECRET_KEY`). Sans session, le navigateur est redirigé vers **`/login?next=…`**.

L’interface affiche un seul libellé **Se connecter** ; seuls les comptes avec **droits admin** (RBAC) obtiennent une session utile pour ces espaces. L’achat de **temps de jeu** sur place se fait via le **QR** de la station (parcours **`/s/{code}`**), pas via cet écran.

- Identifiant : **email ou téléphone** du compte dans la table `users`.
- Mot de passe : hash bcrypt en base (aligné sur `ADMIN_USERNAME` / `ADMIN_PASSWORD` au bootstrap, ou comptes créés ensuite).
- En cas d’échec de connexion, la page affiche un message d’erreur (réponse **200** avec HTML, pas de page « HTTP ERROR 401 » du navigateur).

En **développement** (`APP_ENV=development`, défaut dans `.env.example`), le seed au démarrage appelle aussi **`ensure_dev_admin`** : le compte **`admin@test.com`** / **`testpass123`** est (re)synchronisé avec le rôle global **`super_admin`** uniquement. Pour désactiver : `AUTO_ENSURE_DEV_ADMIN=false` ou `APP_ENV=production`.

Déconnexion : **`/logout`**.

Si le mot de passe ne correspond plus à la base ou après un reset, depuis la racine du projet :

```bash
make reset-admin
```

Puis reconnecte-toi avec les valeurs de ton `.env` (par défaut dans `.env.example` : **`admin@test.com`** / **`testpass123`**).

Si la connexion avec ce couple échoue alors qu’une autre adresse avait été seed au départ (`admin@gmail.com`, etc.), crée ou mets à jour explicitement le compte dev :

```bash
make ensure-dev-admin
```

(Création / MAJ de `admin@test.com` avec mot de passe `testpass123` par défaut — variables optionnelles `DEV_ADMIN_EMAIL`, `DEV_ADMIN_PASSWORD`, `DEV_ADMIN_NAME`.)

#### Administrateurs de salle (pas super-admin)

Un **nom d’utilisateur seul** ne donne **aucun** droit : accès **`/admin`** via **`super_admin`**, **`salle_admin` global** (`user_roles`, sans salle au départ), ou rôles dans **`salle_users`**.

- **`super_admin`** (`user_roles`) : voit **toute** la plateforme, CRUD global, **`/super-admin`**, création de salles, rôles globaux et par salle.
- **`salle_admin` global** (`user_roles`) : accès **`/admin`** **sans choisir de salle** ; la personne crée sa première salle via le menu **Salles**. À accorder depuis **`/super-admin/users/{id}/roles`**, section **« Admin de salle (global) »** (bouton Accorder) ; **retrait** des rôles globaux (`super_admin`, `salle_admin`, ancien `admin`) via la liste **« Rôles globaux (UserRole) »** sur la même page (`POST …/roles/global-remove`). Lors de la **création** d’un utilisateur sur **`/super-admin/users`**, le formulaire permet aussi de cocher **`super_admin`** / **`salle_admin` global** et, en option, d’assigner **une salle + un rôle** (`salle_admin`, `responsable`, `gérant`) en une fois. Pour un admin **d’une salle déjà existante** sans passer par ce formulaire, utiliser **`/admin/salles/{id}/users`** (connecté en super admin, case « Salle admin »).
- **`salle_admin` sur une salle** (`salle_users`) : CRUD sur cette salle. **Gérants / responsables** : uniquement des comptes créés via **`/admin/mes-utilisateurs`** (champ `created_by_user_id`). Les comptes **assignés à la salle par le super admin** depuis l’espace super admin redeviennent visibles / modifiables (traçabilité `created_by` réinitialisée à l’assignation).
- **`responsable`** : une ou **plusieurs** salles ; CRUD sur **gérants**, **offres** et le reste du périmètre opérationnel **rattaché à ses salles**. Sans rôle **`salle_admin` explicite** sur la salle, il ne peut pas **nommer de responsables** ni éditer/supprimer la **fiche salle** ; en revanche, avec un **`salle_admin` global** (`user_roles`) en plus d’un rôle sur la salle, l’app considère un **admin de salle effectif** sur toutes les salles où il a un rôle (voir `docs/ARCHITECTURE.md`).
- **`manager` (gérant)** : **une seule** salle à la fois (refus en base si on tente d’en assigner une deuxième). Accès **sessions uniquement** dans `/admin` : démarrer une session pour un joueur (`/admin/manual-session`), **pause / reprise**, **augmenter ou diminuer** le temps d’une session (`/admin/sessions`) — pas les écrans de configuration (offres, stations, utilisateurs, etc.).

**Premier admin d’une nouvelle salle :** uniquement un **`super_admin`** peut créer la salle (ou un `salle_admin` déjà présent sur une autre salle peut en créer une nouvelle — il devient `salle_admin` sur la salle créée). Ensuite le super-admin peut promouvoir quelqu’un en **`salle_admin`** sur cette salle.

Si un compte n’a **ni** `super_admin` **ni** `salle_admin` global **ni** ligne dans `salle_users` avec un rôle admin, il ne peut pas utiliser `/admin`.

#### Compte `.env` en **salle_admin** uniquement (plus de super admin global)

Si `ADMIN_USERNAME` doit être un **admin de salle** seulement (accès admin filtré par salles, **sans** gestion globale utilisateurs / providers) :

```bash
make admin-salle-only
```

Ce script retire **`super_admin`**, l’ancien **`admin`** et un éventuel **`salle_admin` global** (`user_roles`), supprime les anciennes lignes **`salle_users`**, puis recrée un **`salle_admin` par salle** existante. Le démarrage de l’app ne re-promouvra plus ce compte en `super_admin` tant qu’il a déjà le rôle `salle_admin` en **`salle_users`** ou en **`user_roles`** (global).

#### Super administrateur global (`super_admin`)

Pour créer ou mettre à jour un compte propriétaire (accès **`/super-admin`** : utilisateurs globaux, providers PSP, etc.) :

```bash
make ensure-super-admin
```

Par défaut : `superadmin@controlplay.com` / `admin123` (modifiable via `SUPER_ADMIN_EMAIL`, `SUPER_ADMIN_PASSWORD`, `SUPER_ADMIN_NAME` dans `.env`).

---

## Autres documents

- **[ROADMAP.md](./ROADMAP.md)** — état d’avancement, phases 1–4, **plan priorisé (P0–P5)** pour la suite.
- **[FLOW_TEMPS_DE_JEU.md](./FLOW_TEMPS_DE_JEU.md)** — parcours QR station, API publique, POST `/checkout` / `/extend/checkout`.
- **[ARCHITECTURE.md](./ARCHITECTURE.md)** — stack, routes, RBAC, données.
- **`frontend/README.md`** — commandes Vite, hot reload, build SPA.

