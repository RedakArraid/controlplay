# ControlPlay — frontend (SPA)

Interface **React + TypeScript + Vite + Tailwind CSS v4** (plugin `@tailwindcss/vite`).

**Roadmap & prochaines étapes produit** : voir [`../docs/ROADMAP.md`](../docs/ROADMAP.md).

## Développement (hot reload)

Racine du dépôt : **`make frontend-dev`** — ou :

```bash
cd frontend
npm install
npm run dev
```

Ouvrir **`http://localhost:5173`**. Le proxy Vite (`vite.config.ts`) envoie **`/api`** vers **`http://127.0.0.1:8000`** : lancer l’API FastAPI **en parallèle**.

Sans ce serveur (navigation uniquement sur **:8000**), vous voyez le **build statique** : **pas** de rechargement à chaud.

## Build production

Sortie : **`../app/static/spa/`** (servi par FastAPI).

```bash
npm run build
```

Avec Docker + volume `./app:/app`, régénérer le build sur l’hôte : **`make frontend-build`** (depuis la racine du dépôt).

## TypeScript

```bash
npm run typecheck
```

## Design

- Polices : **Syne** (titres) + **Outfit** (texte) — déclarées dans `index.html`.
- Thème sombre « gaming / VR », panneaux vitrés, accents magenta · cyan · ambre ; zones admin / super-admin via `data-zone` sur le layout.
