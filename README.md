# AI Real Estate Chatbot

RAG chatbot over a **limited public subset** of [DarGlobal](https://darglobal.co.uk/projects) developments and [Wasalt](https://wasalt.sa/en) listings.

User question → Chroma Cloud hybrid search (Qwen dense + Splade sparse, RRF) → OpenRouter free model → grounded answer with source cards.

**Live demo:** [https://real-estate-chatbot-sable.vercel.app](https://real-estate-chatbot-sable.vercel.app/)  
**API:** [https://real-estate-chatbot-pwjs.onrender.com](https://real-estate-chatbot-pwjs.onrender.com/)

## Architecture

```text
                    ┌─ Vercel (static Vite / React UI)
Browser ───────────┤
                    └─ HTTPS POST /api/chat
                              │
                              ▼
                    Render  FastAPI  (Docker)
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
           SQLite       Chroma Cloud     OpenRouter
         (metadata)   Qwen + Splade    Inkling (free)
              ▲               ▲
              └────── seed JSON + optional live scrape
                      (DarGlobal / Wasalt public pages)
```

This is retrieval-augmented generation. The LLM never receives the full dataset. It only sees the top retrieved properties.

Production splits the stack because the API needs Python and optional Playwright. That does not fit Vercel serverless. The UI is a static Vite build, so Vercel hosts it and calls the Render origin. Vectors live on Chroma Cloud.

## Design notes

- **Packaged seed, not a live MLS.** Wasalt sits behind Cloudflare and both sites are JavaScript-rendered. A full scrape is unreliable, so `backend/data/seed/properties.json` (~83 public listings) ships in git. On boot, `ensure_ready()` loads that seed into SQLite and Chroma if the stores are empty.
- **Chroma Cloud search.** Listings are chunked (16 KiB limit) and indexed with **Chroma Cloud Qwen** dense embeddings plus **Chroma Cloud Splade** sparse embeddings. Queries use Reciprocal Rank Fusion. Chunks from the same listing are collapsed with GroupBy on `property_id`.
- **No local embedding model.** Render does not load PyTorch or MiniLM. `CHROMA_API_KEY` is required for search.
- **Hybrid filters.** Cloud ranking first, then light filters for city, source, bedrooms, budget, type, and amenities from the user question.
- **Scrape-on-miss is best-effort.** If retrieval looks thin, the API may fetch a small set of public pages, upsert new rows, and answer. Failures (Cloudflare, empty HTML) are swallowed. The model is told not to mention scraping or databases in the reply.
- **LLM fallback.** If OpenRouter is missing or errors, the API still returns a template answer from retrieved listings so the UI is never empty of sources.
- **Two Dockerfiles.** Repo-root `Dockerfile` is for Compose (builds the UI into the API image). `backend/Dockerfile` is API-only for Render. `VITE_API_URL` points the Vercel build at that API. CORS allows localhost plus `https://*.vercel.app`.

The credentials required to deploy are `OPENROUTER_API_KEY` and `CHROMA_API_KEY`. SQLite is a file, not a server.

## Technology stack

| Layer | Technology |
| --- | --- |
| Frontend | React, Vite, Axios, CSS |
| Backend | Python, FastAPI, Pydantic |
| Scraping | Playwright, BeautifulSoup |
| Embeddings | Chroma Cloud Qwen (dense) + Splade (sparse) |
| Vector DB | Chroma Cloud |
| Metadata | SQLite |
| LLM | OpenRouter `thinkingmachines/inkling:free` |
| Packaging | Docker |
| Deployment | Render (API) + Vercel (UI) |

## Scraping approach

The scrapers collect a **small public sample** (about 20–50 records per site), not a full-site crawl.

- DarGlobal: `https://darglobal.co.uk/projects` and linked project pages. `robots.txt` allows `/projects/`.
- Wasalt: public category pages such as `/en/villas-for-sale-in-saudi-arabia`. `robots.txt` **disallows `/search`**, so the scraper never uses that path.
- Both sites are JavaScript-heavy. Wasalt is also behind Cloudflare, so Playwright is used when HTTP fetch is blocked.
- httpx is tried first; Playwright runs only for pages that look blocked or empty.
- Do not run the scraper against private, authenticated, or disallowed URLs.

## RAG pipeline

1. Each property is stored in SQLite.
2. A text document is built from title, location, type, bedrooms, price, amenities, and description, then split if it exceeds 16 KiB.
3. Chroma Cloud Qwen creates dense embeddings; Splade creates sparse embeddings.
4. Chroma Cloud stores both indexes in the `listings` collection (`real-estate` database).
5. A user question is searched with RRF hybrid ranking, then GroupBy `property_id`.
6. Local filters apply city, source, bedrooms, budget, type, and amenities.
7. The top properties are sent to OpenRouter with a grounding system prompt (answer only from context; never invent prices or availability; listing cards carry the URLs).

## LLM integration

Set `OPENROUTER_API_KEY` and keep `OPENROUTER_MODEL=thinkingmachines/inkling:free`.

This pins one free OpenRouter model instead of the free-model router, so identity and grounding answers stay consistent. Free endpoints are still rate-limited.

## API

Swagger UI: `/docs`

### `POST /api/chat`

```json
{ "message": "Find 3 bedroom properties in Dubai under AED 2 million" }
```

```json
{
  "answer": "I found matching properties...",
  "sources": [
    {
      "title": "DG1",
      "source": "DarGlobal",
      "url": "https://darglobal.co.uk/dg1"
    }
  ]
}
```

Chat requests use a 120s client timeout. A cold Render instance plus retrieval (and an optional scrape) can take that long.

### `GET /api/health`

```json
{ "status": "UP", "properties": 83, "vector_store": "ready" }
```

### `POST /api/admin/scrape`

Disabled unless `ADMIN_TOKEN` is set. Send header `X-Admin-Token`.

## Local development

```bash
cp .env.example .env
# add OPENROUTER_API_KEY

python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt

cd backend
python scripts/ingest.py
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` to `http://127.0.0.1:8000`, so leave `VITE_API_URL` empty locally. API docs: `http://127.0.0.1:8000/docs`.

Optional live scrape (Playwright):

```bash
pip install -r backend/requirements-scrape.txt
python -m playwright install chromium
cd backend
python scripts/scrape.py --source all
```

## Docker

Compose runs the API only. Vectors are on Chroma Cloud, SQLite stays on a volume:

```text
chatbot          SQLite volume sqlite_data  →  /data/properties.db
                 Chroma Cloud               →  api.trychroma.com / real-estate
```

```bash
docker compose up --build
```

- App: http://127.0.0.1:8000
- Chroma viewer: http://127.0.0.1:8000/chroma

Put `CHROMA_API_KEY` in `.env` first. Copy it from the [Chroma Cloud SDK page](https://www.trychroma.com/siddhantprajapatiaum/aws-us-east-1/real-estate/sdk?tab=env). Then index listings:

```bash
cd backend
python scripts/migrate_chroma_cloud.py
```

Use `--reset` to rebuild the Cloud collection.

## Deployment

Push this repository to GitHub first. Deploy the **API on Render**, then the **UI on Vercel**.

### 1. Backend on Render

1. New **Web Service** from the GitHub repo.
2. Runtime: **Docker**.
3. Dockerfile path: `backend/Dockerfile`.
4. Docker build context: `backend`.
5. Health check: `/api/live`.
6. Environment:
   - `OPENROUTER_API_KEY` — your OpenRouter key (required).
   - `CHROMA_API_KEY` — Chroma Cloud key (required). Copy from the database SDK tab.
   - `CHROMA_TENANT` — `7ff33401-8f97-45e9-92ca-060ca2fdb321`
   - `CHROMA_DATABASE` — `real-estate`
   - `CHROMA_HOST` — `api.trychroma.com`
   - `CORS_ORIGINS` — the Vercel origin, `https://real-estate-chatbot-sable.vercel.app` (plus localhost for local UI).
   - `CORS_ORIGIN_REGEX` — already defaults to `https://.*\.vercel\.app` so preview URLs work.

`render.yaml` encodes the same settings if you apply a Render Blueprint.

The first request after a cold start still needs Chroma Cloud to be reachable. Free Render services sleep after idle traffic and can take about a minute to wake. SQLite is rebuilt from seed on each deploy; vectors stay in Chroma Cloud.

Working API URL: `https://real-estate-chatbot-pwjs.onrender.com`  
Health: `https://real-estate-chatbot-pwjs.onrender.com/api/health`  
Docs: `https://real-estate-chatbot-pwjs.onrender.com/docs`

### 2. Frontend on Vercel

1. New Vercel project from the same GitHub repo.
2. **Root Directory**: `frontend` (or leave the repo root; `vercel.json` builds `frontend/`).
3. Framework: Vite.
4. Build command: `npm run build`. Output: `dist`.
5. Environment (must be set **before** the production build):
   - `VITE_API_URL` = `https://real-estate-chatbot-pwjs.onrender.com` (no trailing slash). The production UI also hardcodes this in `frontend/src/api.js`.

Vite inlines `VITE_*` at build time. If you change the Render URL later, update `VITE_API_URL` and redeploy Vercel.

Live UI: `https://real-estate-chatbot-sable.vercel.app`

Then set `CORS_ORIGINS` on Render to that Vercel origin and restart the API if needed.

## Example questions

- Show me properties in Dubai.
- Find 3 bedroom properties.
- What properties are under AED 2 million?
- Which properties are from DarGlobal?
- Show me villas in Dubai.
- Compare Urban Oasis by Missoni and DG1.
- Tell me about Trump Cliff Villas.
- Which properties have swimming pools?
- Give me the source links.

## Limitations

- This is a demo dataset, not a live MLS feed. Prices and availability change.
- DarGlobal often publishes **price on request**; the bot will not invent a number.
- Wasalt listing cards sometimes omit price, bathrooms, or a stable detail URL.
- Free OpenRouter models have lower rate limits and can be temporarily unavailable.
- Render’s API is on a free instance. After 15 minutes of inactivity it goes to sleep; the next request can take a minute or more (or return 502) while it wakes.
- Render’s Docker web service keeps SQLite in the container. Vector search is on Chroma Cloud and survives deploys.
- Local Compose still persists SQLite in the `sqlite_data` volume.
- Scrapers must stay limited, public, and robots.txt-aware. Site HTML can change and break selectors.

## Project layout

```text
backend/app/api           FastAPI routes
backend/app/scraper       DarGlobal + Wasalt scrapers
backend/app/rag           Chroma Cloud hybrid search
backend/app/llm           OpenRouter client
backend/app/services      chatbot + ingest + scrape-on-miss
backend/scripts/migrate_chroma_cloud.py  seed → Chroma Cloud
backend/data/seed         portable listing catalog (tracked)
frontend/                 React + Vite chat UI (Vercel)
Dockerfile                local Compose image (API + UI)
backend/Dockerfile        Render API image
docker-compose.yml        chatbot + SQLite volume
render.yaml               Render Blueprint
vercel.json               Vercel build from repo root
frontend/vercel.json      Vercel SPA rewrites when root is frontend/
.env.example              backend env template
frontend/.env.example     VITE_API_URL template
```
