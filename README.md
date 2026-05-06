## Iran FX Watch (Official vs Market)

> **If you “published” this repo and only see documentation:** GitHub Pages (and similar) show the repo’s web root. This project’s **interactive dashboard** is the **FastAPI** app served by the **`api`** container (for example `http://localhost:8000` when you run Docker Compose). A static landing page lives at **`index.html`** in the repo root so your published site is not just a raw README dump.

A small system that tracks the Iranian rial (**IRR**) against major currencies in near real time, comparing **official** (CBI) vs **market** (Bonbast) and alerting on unusual moves and spread changes.

### What runs locally

- TimescaleDB (Postgres)
- Adminer DB UI
- Ingest service (polls sources, normalizes, writes to DB, emits alerts)
- API + dashboard (FastAPI + simple UI)

### Quickstart

1. Start everything:

```bash
docker compose up -d --build
```

2. Open:

- Dashboard/API: `http://localhost:8000`
- Adminer: `http://localhost:8080` (server: `db`, user/pass/db: `iranx`)

3. Run ingestion once (no loop):

```bash
docker compose run --rm -e ENABLE_LOOP=false ingest
```

### Push to GitHub

1. Create an empty repo on GitHub (no README/license if you want a clean first push).

2. From this folder:

```bash
git init
git add -A
git commit -m "Initial Iran FX Watch stack"
git branch -M main
git remote add origin https://github.com/<YOUR_USER>/<YOUR_REPO>.git
git push -u origin main
```

### Publish the webpage (hosted API + dashboard)

This app is easiest to ship as **Docker Compose** (DB + ingest + API). Good fits:

- **Railway** or **Render**: connect the GitHub repo and deploy using the root `docker-compose.yml` (you will need persistent volume for Postgres data and to set **non-default** `POSTGRES_PASSWORD` / secrets in the host UI).

- **Fly.io**: deploy `api` + `db` + `ingest` as separate apps or one compose stack; use Fly volumes for the database.

Before any public URL: change default credentials in `docker-compose.yml` (or override via environment variables in the host) and avoid exposing Adminer publicly unless you lock it down.

