# Claude Connector — Domain Portfolio MCP Server

A deployable **remote MCP (Model Context Protocol) server** that exposes a curated domain portfolio to AI clients. Three tools: keyword search, single-record lookup, and Claude-powered recommendations.

Built as a reusable template — swap the data file and field mapping in `config.yaml` for a different client catalog without changing server logic.

## What it does

| Tool | Purpose |
|------|---------|
| `search_domains` | Keyword + optional category search across the portfolio |
| `get_domain_details` | Full metadata for one domain (category, TLD, tags) |
| `recommend_domains` | Claude reasons over the portfolio and returns top 3 matches with justifications |

**Dataset:** 412 domains with fields `domain`, `category`, `tld`, and `tags`. There are no price or commission fields in this demo dataset.

**Transport:** Streamable HTTP at `/mcp` — not stdio. Designed for remote deployment the way a real client integration would connect.

**Cost:** `recommend_domains` uses **Claude Haiku 4.5** with **prompt caching** on the static 412-domain portfolio block (1h TTL by default). Repeat calls read from cache at ~80–90% lower input cost than uncached.

## Quick start (local)

**Requires Python 3.10+** (tested on 3.12).

```bash
cd claude-connector
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
# Edit .env and set ANTHROPIC_API_KEY (required for recommend_domains)

python server.py
```

Server starts at:

- MCP endpoint: `http://localhost:8000/mcp`
- Health check: `http://localhost:8000/health`

## How to connect this to Claude

### Claude Desktop (remote MCP)

Add to your Claude Desktop MCP config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "domain-portfolio": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

For a deployed server, replace the URL with your public host (e.g. `https://your-app.onrender.com/mcp`).

Restart Claude Desktop. The three tools should appear when you start a new conversation.

### MCP Inspector (testing)

```bash
npx @modelcontextprotocol/inspector
```

Connect to `http://localhost:8000/mcp`, list tools, and call them interactively.

### Optional API key

Set `MCP_API_KEY` in `.env` to require `Authorization: Bearer <key>` on requests. Leave unset for open local development.

## Swapping the data source

Core logic never reads `domains.json` directly. Everything goes through `config.yaml`:

```yaml
catalog:
  source_path: data/domains.json
  record_type: domain
  fields:
    id: domain
    category: category
    tags: tags
    include:
      - tld
```

**For a new client:**

1. Add their JSON export to `data/`
2. Copy `config.yaml` → `config.client.yaml`
3. Update `source_path` and `fields` to match their column names
4. Run with `DATA_CONFIG=config.client.yaml python server.py`

**Included demo:** `config.sample.yaml` + `data/sample_catalog.json` maps a product catalog with fields `sku`, `product_name`, `vertical`, `keywords`, and `price_usd`. Try it:

```bash
DATA_CONFIG=config.sample.yaml python server.py
```

Only the config file changes — `server.py` and tool handlers stay the same.

## Project structure

```
claude-connector/
├── server.py              # FastMCP HTTP server + three tools
├── config.yaml            # Default domain portfolio mapping
├── config.sample.yaml     # Alternate dataset demo
├── catalog/
│   ├── loader.py          # Config-driven JSON loader
│   ├── search.py          # search_domains + get_domain_details logic
│   └── recommender.py     # Claude recommendation logic
├── data/
│   ├── domains.json       # 412-domain portfolio
│   └── sample_catalog.json
├── scripts/
│   └── verify.py          # Benchmark verification script
├── render.yaml            # Render.com deployment
├── .env.example
└── requirements.txt
```

## Deploy to Render

1. Push this folder to a GitHub repo
2. Create a new **Web Service** on [Render](https://render.com)
3. Connect the repo — Render detects `render.yaml` automatically
4. Set environment variables in the Render dashboard:
   - `ANTHROPIC_API_KEY` (required)
   - `MCP_API_KEY` (recommended for production)
5. Deploy. Health check hits `/health`; MCP clients connect to `https://<your-service>.onrender.com/mcp`

Render sets `PORT` automatically; the server reads it from the environment.

## Error handling

| Situation | Response |
|-----------|----------|
| Empty search query | `{ "error": "invalid_query", ... }` |
| Domain not found | `{ "error": "not_found", "found": false, ... }` |
| Empty business idea | `{ "error": "invalid_input", ... }` |
| Missing API key (recommend) | `{ "error": "missing_api_key", ... }` |
| Claude API failure | `{ "error": "claude_api_error", ... }` |

No stack traces are returned to MCP clients.

## Verify locally

```bash
python scripts/verify.py
```

Runs search, lookup, not-found, and recommendation tests against a running server (or starts checks against catalog logic directly).

## License

MIT — use as a template for client MCP connectors.
