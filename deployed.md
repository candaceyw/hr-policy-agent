# Deployment

**Live:** https://web-production-1fa45.up.railway.app
(`/health` → `mcp.connected: true`, `transport: streamable_http`, `retrieval.active_method: vector`)

Two Railway services from this one repo, built from **the same `Dockerfile`**,
differing only in the start command:

| Service | Start command | Exposure |
| --- | --- | --- |
| `web` | *(Dockerfile default)* `uvicorn hr_agent.web.app:app --host 0.0.0.0 --port $PORT` | Public domain (the app URL) |
| `mcp` | `python -m hr_agent.mcp_server --http` | **Private network only** |

`web` serves the API (`/chat`, `/health`) and the built React SPA. It discovers
the 9 MCP tools from `mcp` at runtime over **Streamable HTTP** on Railway's
private network (`MCP_SERVER_URL`). The committed vector index
(`data/index/index.sqlite`) ships inside the image, so there is no build-time
embedding step and no cold-start rebuild.

## Why two services

The course rubric encourages a production-like split with a separate MCP
service. It also makes the degradation path a literal demo: stop `mcp` and
`/health` reports `mcp.connected: false` while answers fall back to RAG-only
(acceptance criterion: "removing the MCP server causes the agent to degrade").

## Railway setup (dashboard)

Config-as-code (`railway.json`) is deprecated for new services, so everything is
set in the dashboard.

### 1. Create the project and the `web` service

1. **New Project → Deploy from GitHub repo**, pick this repo, connect the branch.
2. Railway auto-creates one service. Open it → **Settings**:
   - **Service → Name**: `web`
   - **Build → Builder**: `Dockerfile` (Railway auto-detects the root `Dockerfile`;
     if it shows Railpack, switch it). No Dockerfile path needed — it's at the root.
   - **Deploy → Healthcheck Path**: `/health`
   - **Networking → Generate Domain** (port `8000` if asked). This is the app URL.
3. **Variables**:

   | Variable | Value |
   | --- | --- |
   | `MCP_SERVER_URL` | `http://mcp.railway.internal:8765/mcp` |
   | `LLM_PROVIDER` | `groq` |
   | `LLM_MODEL` | `qwen/qwen3.8-27b` |
   | `GROQ_API_KEY` | *(your key — text generation)* |
   | `GEMINI_API_KEY` | *(your key — embeddings for retrieval + `/health`)* |

### 2. Add the `mcp` service

1. Project canvas → **+ New → GitHub Repo** → same repo.
2. Open it → **Settings**:
   - **Service → Name**: `mcp`
   - **Source → Branch**: same branch as `web`
   - **Build → Builder**: `Dockerfile` (same root `Dockerfile`)
   - **Deploy → Custom Start Command**:
     `python -m hr_agent.mcp_server --http`
   - **Networking**: do **not** generate a domain.
3. **Variables**: `PORT` = `8765` (pin it so `MCP_SERVER_URL` above is stable).

`mcp` needs no LLM keys — its tools are retrieval and mock-data lookups.

### 3. Deploy

Deploy both. Railway Hobby services are always-on (no cold start). Private
networking is on by default for new projects.

## Verify

```
curl https://<web-domain>/health
# { "mcp": { "connected": true, "tools_discovered": 9, "transport": "streamable_http" }, ... }
```

Open the app URL, pick an employee, run the two demo prompts. To show the
degradation path: stop the `mcp` service in Railway, wait ~15 s (health is
probed on a short TTL), reload `/health` — `connected` flips to `false` and the
app answers from retrieval only with a caveat in the trace.

## Issues hit on the first deploy (and the fixes)

| Symptom | Cause | Fix |
| --- | --- | --- |
| `/` → "Application failed to respond" | `Dockerfile` `EXPOSE 8000`, but Railway injects `PORT=8080`; the domain was bound to 8000 | pin `PORT=8000` on `web` so uvicorn binds the port the domain targets |
| `mcp` deploy "healthcheck failed" | healthcheck path was `/health`; the MCP server only serves `/mcp` | clear the healthcheck path on `mcp` |
| `mcp`: `invalid int value: '$PORT'` | Railway's Custom Start Command isn't shell-expanded | drop `--port` from the command; `main()` reads `$PORT` from the env |
| `retrieval.active_method: keyword` despite the key being set | `pip install .` copied the package to `site-packages`, so `Path(__file__).parents[2]/"data"` resolved outside `/app` | `pip install -e .` in the image so the package stays at `/app/src/hr_agent` |
| `transport: stdio`, `embedding_key_configured: false` | the env vars were set on `mcp`, not `web` | `web` gets the LLM keys + `MCP_SERVER_URL`; `mcp` only needs `PORT` |

## Local mirror

`docker compose up --build` runs the same image twice on a local network
(`web` on :8000, `mcp` private). Needs `GROQ_API_KEY` / `GEMINI_API_KEY` in the
environment or a local `.env`.

Without Docker: run them as two processes —

```
# terminal 1 — MCP over HTTP
PYTHONPATH=src python -m hr_agent.mcp_server --http --port 8765

# terminal 2 — web pointed at it
MCP_SERVER_URL=http://127.0.0.1:8765/mcp \
PYTHONPATH=src python -m uvicorn hr_agent.web.app:app --port 8000
```
