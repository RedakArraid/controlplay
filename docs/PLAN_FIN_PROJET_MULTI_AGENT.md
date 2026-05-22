# Plan De Fin De Projet Multi-Agent

Dernière mise à jour : 10 avril 2026.

## Objectif

Terminer ControlPlay sans casser les flux déjà fonctionnels, en séparant le travail en chantiers indépendants et en limitant les régressions sur :

- le tunnel station QR -> checkout -> activation session
- l'administration SPA (`/admin`)
- la zone plateforme (`/super-admin`)
- la location matériel
- la mise en service Docker / worker / Broadlink / PSP

## État observé

Le projet est déjà bien avancé et exploitable en local :

- backend FastAPI + Celery + SQLAlchemy en place
- SPA React/Vite riche côté marketing, admin et super admin
- migrations Alembic présentes
- tests backend solides sur les flux critiques
- documentation produit et architecture déjà fournie

Vérifications locales réalisées :

- `python -m pytest tests/ -q -m "not browser"` : 35 tests passés, 8 tests navigateur exclus
- `npm run typecheck` : exécuté sans erreur visible
- `npm run lint` : lancement OK, terminaison non observée dans cette session

## Risques Principaux

### 1. Dette de structure backend

Les modules API sont difficiles à maintenir car plusieurs fichiers répliquent les mêmes imports, schémas Pydantic et helpers de base. Le cas le plus visible est la duplication du préambule dans `auth.py`, `public.py`, `admin_stations.py` et `leftovers.py`.

Impact :

- coût élevé pour faire évoluer les contrats JSON
- risque d'incohérence entre endpoints
- onboarding plus lent

Point d'attention critique :

- les helpers de paiement et certains garde-fous RBAC n'ont pas encore une source de vérité unique
- les routes web legacy portent encore une partie du métier critique

### 2. Duplication de logique frontend

Les layouts admin et super admin refont la logique d'authentification / bootstrap alors qu'un `AuthContext` existe déjà. Cela augmente le risque de divergences de comportement.

Impact :

- logique d'accès dispersée
- maintenance plus coûteuse
- comportements différents selon les routes

Point d'attention critique :

- la page `Sessions` ne couvre pas encore clairement pause / reprise / ajustement du temps
- le checkout station ne matérialise pas encore toutes les promesses UX documentées

### 3. Couverture QA incomplète côté SPA

La base de tests backend est bonne, mais les tests navigateur couvrent surtout le login. Les parcours SPA métier restent peu protégés.

Impact :

- régressions possibles sur checkout station, feedback, CRUD admin et zone super admin
- difficulté à finir vite avec confiance

### 4. Friction dev / build / déploiement

Le frontend doit être buildé séparément dans `app/static/spa/`, ce qui est documenté mais reste une source d'oubli. Le projet est fonctionnel, mais la boucle de livraison n'est pas encore la plus fluide.

Impact :

- faux positifs en local
- confusion entre build statique et mode Vite
- mise en service plus fragile

Point d'attention critique :

- le premier bootstrap peut être fragile si le seed applicatif précède un schéma réellement migré
- le compose mélange aujourd'hui usage dev et usage plus proche prod

## Sous-Agents Créés

Sous-agents d'analyse lancés dans cette session :

- `Euler` : backend / RBAC / paiements / worker
- `Anscombe` : frontend SPA / UX / layouts / pages
- `Laplace` : qualité / tests / CI
- `Dewey` : Docker / docs / exploitation

Leur rôle est de produire un diagnostic parallèle sans bloquer le pilotage principal.

## Organisation Recommandée Des Sous-Agents D'Exécution

### Agent 1 — Backend Structure

Mission :

- extraire les schémas Pydantic et helpers partagés hors des fichiers de routes
- rationaliser `app/routes/api/*`
- renommer ou redistribuer les endpoints rangés dans des fichiers peu explicites comme `leftovers.py`

Zone prioritaire :

- `app/routes/api/auth.py`
- `app/routes/api/public.py`
- `app/routes/api/admin_*.py`
- `app/routes/api/leftovers.py`
- `app/routes/api/common_models.py`

Définition de terminé :

- plus de duplication évidente des modèles d'entrée/sortie
- découpage lisible par domaine
- aucun changement de comportement API non voulu

### Agent 2 — Frontend Auth Et Shell

Mission :

- centraliser `auth/me` + `admin/bootstrap`
- faire reposer `AdminLayout` et `SuperAdminLayout` sur une même source de vérité
- éliminer la duplication entre layouts

Zone prioritaire :

- `frontend/src/contexts/AuthContext.tsx`
- `frontend/src/layouts/AdminLayout.tsx`
- `frontend/src/layouts/SuperAdminLayout.tsx`
- `frontend/src/App.tsx`

Définition de terminé :

- une stratégie unique de chargement auth/bootstrap
- comportements cohérents de redirection et erreurs
- layouts simplifiés

### Agent 3 — Frontend Parcours Métier

Mission :

- fiabiliser les pages à fort impact business
- traiter les états vides, erreurs, chargement et cohérence UX
- vérifier les écrans admin les plus utilisés

Zone prioritaire :

- `frontend/src/pages/marketing/StationCheckoutPage.tsx`
- `frontend/src/pages/admin/*`
- `frontend/src/pages/super/*`

Définition de terminé :

- parcours station clair même en erreur ou session active
- admin exploitable sans zone ambiguë
- zone super admin cohérente

### Agent 4 — QA Et CI

Mission :

- étendre Playwright au-delà du login
- protéger les parcours station, feedback, CRUD admin et rôles
- intégrer `npm run typecheck` dans la routine CI

Zone prioritaire :

- `app/tests/test_e2e_browser.py`
- nouveaux tests Playwright ou équivalents
- `Makefile`
- future CI si ajoutée dans le dépôt

Définition de terminé :

- tests navigateur couvrant au moins un parcours station et un parcours admin
- garde-fous automatiques pour le front
- guide simple pour lancer la suite

### Agent 5 — Ops Et Mise En Service

Mission :

- fluidifier la boucle locale et la préparation pilote
- consolider les checklists Broadlink et PSP
- clarifier ce qui relève du build statique et du mode dev

Zone prioritaire :

- `docker-compose.yml`
- `Makefile`
- `.env.example`
- `docs/README.md`
- `docs/ROADMAP.md`
- `docs/ARCHITECTURE.md`

Définition de terminé :

- démarrage local sans ambiguïté
- checklist pilote matériel / paiement prête
- docs cohérentes avec le code réel

## Ordre D'Exécution Recommandé

## P0 Concret

Ce sont les trois sujets à traiter avant d'ouvrir trop de chantiers en parallèle :

1. Unifier la logique paiement / provider flags / webhooks pour éviter qu'un provider désactivé côté UI reste utilisable côté backend.
2. Finir le noyau admin opérationnel côté SPA, surtout les actions de session annoncées au métier.
3. Rendre le bootstrap local et pilote déterministe : ordre migrations, compose, healthcheck, build SPA.

### Phase 1 — Stabiliser L'architecture

1. Agent 1 : réduire la duplication backend
2. Agent 2 : unifier auth/bootstrap côté frontend
3. Valider que la suite backend passe toujours

### Phase 2 — Fermer Les Parcours Produit

1. Agent 3 : checkout station + feedback + pages admin sensibles
2. Agent 4 : automatiser les scénarios critiques
3. Relecture manuelle sur les rôles RBAC les plus sensibles

### Phase 3 — Préparer La Mise En Service

1. Agent 5 : docs et exécution locale
2. recette Paystack / CinetPay
3. recette Broadlink réelle avec `BROADLINK_DRY_RUN=false` sur environnement pilote

## Quick Wins Immédiats

- déplacer les schémas Pydantic communs hors des fichiers de routes
- unifier les helpers PSP et les toggles provider entre UI, routes web et API JSON
- fusionner la logique de chargement auth dans le frontend
- ajouter au moins un test navigateur sur le parcours station
- ajouter un release gate minimal : `pytest` backend + `typecheck` + smoke browser
- rendre le lint frontend déterministe dans la routine locale
- documenter une checklist unique de livraison

## Tâches Ciblées Par Agent

### Backend Structure

- extraire modèles Pydantic partagés et helpers communs
- isoler les services `payments`, `sessions`, `rbac`, `rentals`
- réduire la dépendance à `app/main.py`
- préparer le retrait progressif des formulaires legacy encore critiques

### Frontend Auth Et Shell

- brancher réellement `AuthContext`
- supprimer les doubles fetch auth/bootstrap dans les layouts
- homogénéiser les états de chargement, erreur et redirection

### Frontend Parcours Métier

- compléter `Sessions` pour pause / reprise / ajustement
- consolider `StationCheckoutPage`
- corriger les promesses UX trompeuses sur carte et états de chargement

### QA Et CI

- couvrir extension, webhooks, toggles PSP, station publique
- étendre Playwright au flux station et à un flux admin
- intégrer `npm run typecheck` à la routine de validation

### Ops Et Mise En Service

- sécuriser l'ordre `init-env -> migrate -> up`
- séparer compose dev et compose local plus proche prod
- aligner docs, healthcheck et ports par défaut

## Critères De Fin De Projet

Le projet peut être considéré comme prêt à livrer quand les points suivants sont vrais :

- les flux station, admin, super admin et location sont testés au moins sur un scénario nominal
- la structure API et frontend n'impose plus de duplication majeure pour chaque évolution
- la documentation reflète exactement la procédure locale et pilote
- la recette paiement et la recette matériel ont été rejouées
- l'équipe peut répartir le travail par agents sans conflits de responsabilité
