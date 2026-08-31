# Deployment

The system deploys as **two Railway services from this one repo**, matching the
architecture in `hr-policy-agent-vibespec.md`:

| Service | Image | Command | Exposure |
| --- | --- | --- | --- |
| `web` | `Dockerfile.web` | `uvicorn hr_agent.web.app:app --host 0.0.0.0 --port $PORT` | Public domain (the app URL) |
| `mcp` | `Dockerfile.mcp` | `python -m hr_agent.mcp_server --http --port $PORT` | **Private network only** |

`web` serves the API (`/chat`, `/health`) and the built React SPA. It discovers
the 9 MCP tools from `mcp` at runtime over **Streamable HTTP** on Railway's
private network (`MCP_SERVER_URL`). The committed vector index
(`data/index/index.sqlite`) ships inside the `web` image, so there is no build-time
embedding step and no cold-start rebuild.

## Why two services

The course rubric encourages a production-like split with a separate MCP service.
It also makes the degradation path a literal demo: stop `mcp` and `/health`
reports `mcp.connected: false` while answers fall back to RAG-only with a caveat
(acceptance criterion: "removing the MCP server causes the agent to degrade").

## Railway setup

1. **New Project → Deploy from GitHub repo**, pick this repo.
2. The first service picks up `railway.json` → builds `Dockerfile.web`. Rename it
   **`web`**. Generate a public domain for it (Settings → Networking).
3. **Add a second service** from the same repo. In its Settings:
   - Build → **Dockerfile Path** = `Dockerfile.mcp`
   - Name it **`mcp`**. Do **not** generate a public domain.
   - Variables → set `PORT=8765` (pin it so the URL below is stable).
4. **Enable private networking** on the project (on by default for new projects).
5. On **`web`**, set variables:

   | Variable | Value |
   | --- | --- |
   | `MCP_SERVER_URL` | `http://${{mcp.RAILWAY_PRIVATE_DOMAIN}}:8765/mcp` |
   | `LLM_PROVIDER` | `groq` |
   | `LLM_MODEL` | `qwen/qwen3.8-27b` |
   | `GROQ_API_KEY` | *(your key — text generation)* |
   | `GEMINI_API_KEY` | *(your key — embeddings for retrieval + `/health`)* |

   `mcp` needs no LLM keys — its tools are retrieval and mock-data lookups.
6. Deploy both. Railway Hobby services are always-on (no cold start).

### CLI alternative

```
railway login
railway link                       # select the project
railway up --service web
railway up --service mcp
```

## Verify

```
curl https://<web-domain>/health
# { "mcp": { "connected": true, "tools_discovered": 9, "transport": "streamable_http" }, ... }
```

Open the app URL, select an employee, run the two demo prompts. Then, to show the
degradation path: stop the `mcp` service in Railway and reload `/health` —
`connected` flips to `false` and the app answers from retrieval only with a
caveat in the trace.

## Local mirror

`docker compose up --build` runs the same two images on a local network
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
