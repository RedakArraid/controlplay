## Architecture technique

### Composants principaux

- **FastAPI (`app`)**
  - Démarrage : données par défaut (salles, offres, rôles, compte `ADMIN_*`) via **lifespan ASGI** (`seed_default_data`), plus `on_event("startup")` retiré (compatibilité TestClient / Starlette récents).
  - **UI (SPA)** : build **Vite + React + TypeScript** dans `frontend/` → sortie `app/static/spa/` (`npm run build`). Les routes `/`, `/login`, `/admin/*`, `/super-admin/*`, et **`GET /s/{station_code}`** (par défaut) servent `index.html` via `app/spa.py` (placeholder `__CP_NEXT__` pour le paramètre `?next=` du login). Les chunks JS/CSS sont sous `/static/spa/assets/…` (build Vite avec `base: '/static/spa/'`) ; un montage optionnel `/assets/…` pointe sur le même dossier pour compatibilité. API JSON session cookie : préfixe **`/api`** (`app/api_json.py`) — login JSON `POST /api/auth/login`, bootstrap `GET /api/admin/bootstrap`, etc. Les **POST** formulaires historiques (`/login`, `/admin/...`, `/super-admin/...`, **`/checkout`**, **`/extend/checkout`**) restent pour compatibilité et actions critiques.
  - **Thème legacy (HTML serveur)** : feuille `GET /static/controlplay.css` ; pages client **`theme-public`** (sombre, proche SPA) pour `/salle/...`, paiements simulés / retours ; si **`PUBLIC_STATION_SPA=0`**, `GET /s/{station_code}` reste en HTML serveur. Polices Google chargées pour ce thème dans `html_shell` (`ui_theme.py`).
  - Expose :
    - vitrine **SPA** (React) : `/`, `/location`, `/boutique`, `/carte`, `/jeux`, `/s/:stationCode` (même `index.html` que `/login` et `/admin`)
    - pages publiques **HTML** : `/salle/{salle_code}`, `/qr/{station_code}.png` ; **`GET /s/{station_code}`** → SPA par défaut (voir `PUBLIC_STATION_SPA`)
    - auth navigateur : `GET/POST /login`, `GET /logout` (session cookie ; `/admin` et `/super-admin` redirigent vers `/login` si non connecté)
    - API JSON **`/api`** : `GET /api/public/salles`, `GET /api/public/stations/{code}` (tunnel station / offres dédupliquées), auth, bootstrap admin, listes, options session manuelle, et CRUD SPA des salles (`POST /api/admin/salles`, `PUT /api/admin/salles/{id}`, etc.) (voir `app/api_json.py`)
    - admin : `/admin`, `/admin/salles`, `/admin/offers`, `/admin/stations`, `/admin/sessions`, `/admin/dashboard`, `/admin/manual-session`
      - **`/admin/mes-utilisateurs`** : comptes créés par un admin de salle (`created_by_user_id`) — hors super admin global
      - toggles : `/admin/providers` (super admin uniquement)
      - utilitaires : reset sessions station / salle
    - super admin : `/super-admin`, `/super-admin/users` (création user avec rôles globaux / option salle+rôle ; édition rôles : accorder + **retrait** globaux via `…/roles/global-remove`, rôles par salle), `/super-admin/providers`
    - paiements: `/checkout`, `/simulate/pay/{reference}`
    - retours paiements:
      - `/payments/return/paystack/{reference}`
      - `/payments/return/cinetpay`
    - Après confirmation, l'utilisateur est redirigé vers la page de station `/s/{station_code}` pour pouvoir ajouter du temps (session active via worker / webhook).
    - webhooks: `/webhooks/paystack`, `/webhooks/cinetpay`
    - santé: `/health`
  - Gère:
    - la création des sessions de jeu
    - la génération de QR codes
    - l’interface d’administration (offres + stations)

- **Celery / `worker`**
  - Tâches:
    - `tasks.activate_session(session_id)`
      - marque la session comme active
      - envoie la commande IR HDMI2 à la station
      - planifie la fin de session (`deactivate_session`)
    - `tasks.deactivate_session(session_id)`
      - renvoie la TV sur HDMI1
      - clôt la session

- **Alembic (migrations)**
  - Config dans `app/alembic.ini`.
  - Scripts dans `app/alembic/versions`.
  - Exécution via `make migrate` ou `make bootstrap` (dans le conteneur `app`).

- **Broadlink RM Mini 3**
  - Piloté via `broadlink_service.send_ir_command(ip, ir_code)`.
  - Mode dry-run contrôlé par `BROADLINK_DRY_RUN` :
    - `true`: log uniquement (développement / sans matériel)
    - `false`: envoie réel des codes IR.

### Modèle de données (résumé)

- `salles`
  - `code` (optionnel mais pratique pour admin)
  - `name`
  - `latitude`, `longitude`
  - regroupe des `stations`
  - rôles admin scopés via `salle_users` : `salle_admin` (CRUD complet sur ses salles), `responsable` (gérants, offres, etc. liés à ses salles), `manager` (gérant : sessions seulement — démarrage manuel, pause/reprise, durée)

- `users` / RBAC
  - `users` (email/phone + `password_hash`, `is_active`)
  - `roles` (`super_admin`, `salle_admin`, `manager`, `responsable`, `joueur`, ...)
  - `user_roles` (rôles globaux : **`super_admin`**, et **`salle_admin` global** — accès `/admin` sans salle assignée au préalable, pour créer la première salle)
  - `salle_users` (rôles par salle : `salle_admin` / `manager` / `responsable`)
  - endpoints : `GET/POST /admin/salles/{id}/users`, `GET/POST /admin/mes-utilisateurs`, etc.
- **Scoping admin** :
  - `super_admin` : accès global, **`/super-admin/*`**, **`/admin/users`** (utilisateurs globaux).
  - **`salle_admin` global** (`user_roles`) : `get_scoped_salle_ids` reste **vide** tant qu’aucune ligne `salle_users` n’existe ; l’UI affiche des messages orientés **« créer une salle »** (dashboard, offres, stations, sessions). Dès qu’une salle est créée (ou un rôle scopé ajouté), le périmètre se remplit normalement.
  - **Admin de salle « effectif »** sur une salle donnée (`effective_salle_admin_salle_ids` / `is_effective_salle_admin_for_salle` dans `app/main.py`) : soit **`salle_admin`** dans `salle_users` pour cette salle, soit **`salle_admin` global** + **n’importe quel** rôle scopé sur cette salle (`responsable`, `manager`, etc.). Cela évite un trou de droits (ex. uniquement `responsable` + global) pour éditer la fiche salle, nommer des responsables ou supprimer la salle.
  - **`responsable`** sans `salle_admin` (ni global ni sur la salle) : accès opérationnel aux salles scopées mais **pas** les pouvoirs « fiche salle » ci-dessus sur ces salles.
  - **`manager` (gérant)** : une seule salle ; **`require_admin`** pour `/admin`, **`require_config_admin`** refuse la configuration (offres, stations, salles…) ; reste **sessions**, **`/admin/manual-session`**, pause/reprise, durée.
  - **`salle_admin` global** est exclu du profil « gérant seul » (`is_session_gerant_only`).
  - Seul **`super_admin`** ouvre **`/super-admin/*`**. L’ancien rôle global `admin` est **déprécié** (migration **`0015`**).
  - **`users.created_by_user_id`** : filtrage des comptes assignables comme gérant/responsable par un admin de salle ; comptes créés via **`/admin/mes-utilisateurs`**. Assignation par le super admin depuis **`/super-admin/users/.../roles`** peut remettre `created_by_user_id` à **NULL** pour les rendre visibles côté admins de salle (voir `docs/README.md`).
  - Bootstrap `ADMIN_*` : pas de promotion en **`super_admin`** si le compte a déjà **`salle_admin`** en **`salle_users`** **ou** en **`user_roles`** (global).
  - En **développement** (`APP_ENV=development` par défaut), le seed appelle aussi `ensure_dev_admin` (`admin@test.com` / `testpass123`, surcharge `DEV_ADMIN_*`) — désactivation : `AUTO_ENSURE_DEV_ADMIN=false` ou `APP_ENV=production`.
  - Connexion web : `POST /login` renvoie **200** avec message d’erreur HTML si identifiants incorrects (évite une page navigateur « HTTP 401 » vide).
  - Compte super admin dédié : `make ensure-super-admin` (défaut `superadmin@controlplay.com`, voir `SUPER_ADMIN_*` dans `.env.example`).

- `stations`
  - `code` (pour le QR)
  - `name`
  - `broadlink_ip`
  - `ir_code_hdmi1`, `ir_code_hdmi2`
  - `is_active`
  - `salle_id` (nullable)

- `offers`
  - `name`
  - `duration_minutes`
  - `price_xof`
  - `provider` (`paystack` ou `cinetpay`) : choisi **en interne** (priorité Paystack, fallback CinetPay)
  - `is_active`

- tables de liaisons (rattachement des templates aux scopes)
  - `station_offers` : relie `offers` <-> `stations` (une offre peut être attachée à plusieurs stations)
  - `salle_offers` : relie `offers` <-> `salles` (une offre peut être attachée à plusieurs salles)

- `game_sessions`
  - `station_id`, `offer_id`
  - `payment_provider`
  - `payment_reference`
  - `customer_email` (optionnel)
  - `customer_phone` (obligatoire côté UI, stocké pour le suivi PSP / audits)
  - `payment_status` (`pending`, `paid`, `failed`)
  - `status` (`pending`, `active`, `expired`, `failed`)
  - `started_at`, `end_at`

- `event_logs`
  - logs techniques (activation session, erreurs, etc.)

### Variables d'environnement clés

Voir `.env` à la racine :

- Application / infra:
  - `APP_ENV`, `APP_SECRET_KEY`, `BASE_URL`
  - `DATABASE_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
  - `AUTO_CREATE_SCHEMA` (`false` recommandé quand Alembic est utilisé)
- Admin (bootstrap + connexion web) :
  - `APP_SECRET_KEY` : signature du cookie de session (obligatoire en prod ; défaut code = valeur d’exemple `change-me-in-prod` si absent)
  - `ADMIN_USERNAME` / `ADMIN_PASSWORD` : bootstrap (création d’un compte **`super_admin`** si aucun `super_admin` n’existe encore) ; la connexion se fait via **`/login`**, pas via HTTP Basic
  - `DEV_ADMIN_*`, `AUTO_ENSURE_DEV_ADMIN` : voir `docs/README.md` (compte dev synchronisé au démarrage, rôle `super_admin` uniquement)

- Broadlink:
  - `BROADLINK_IP`
  - `BROADLINK_DRY_RUN`
  - `IR_CODE_HDMI1`, `IR_CODE_HDMI2`, `IR_CODE_POWER`

- Paystack:
  - `PAYSTACK_PUBLIC_KEY` (front / futur checkout embarqué)
  - `PAYSTACK_SECRET_KEY` (**obligatoire** pour init + vérification transaction)
  - `PAYSTACK_WEBHOOK_SECRET` (recommandé en prod pour signer les webhooks ; optionnel pour tester l’init seul)
  - `PAYSTACK_CURRENCY` (défaut `XOF`)
  - `PAYSTACK_AMOUNT_MULTIPLIER` (défaut **`100`** dans le code, aligné Paystack sous-unités XOF ; ex. `100` pour NGN en kobo)

- CinetPay:
  - `CINETPAY_API_KEY`
  - `CINETPAY_SITE_ID`
  - `CINETPAY_SECRET_KEY`
  - `CINETPAY_WEBHOOK_SECRET`

### État actuel (mars 2026)

- Environnement local validé avec Docker (`app`, `worker`, `db`, `redis`).
- Endpoints FastAPI opérationnels (incluant `/health`).
- Migrations Alembic initiales appliquées (`0001_initial_schema`).

