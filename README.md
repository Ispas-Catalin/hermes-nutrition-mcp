# nutrition-mcp

A small local-first nutrition tracker exposed as an HTTP MCP server for Hermes.

The database is the source of truth. Hermes should call tools here to remember foods, aliases, recipes, and meal logs instead of storing nutrition facts in agent memory.

## Design

The server stores three useful concepts:

- **Foods**: atomic macro sources such as Babybel, Greek yogurt, tuna, dough, mozzarella, or homemade sauce.
- **Aliases**: stable names Hermes can resolve, such as `babybel`, `default tuna`, or `pizza dough`.
- **Recipes**: reusable templates composed from foods, such as `tuna pizza = 165g dough + 60g tuna + 40g cheese`.

Recipes can be logged with one-off adjustments. For example, after creating a `tuna pizza` recipe, Hermes can log it with:

```json
{
  "alias": "tuna pizza",
  "adjustments": [
    {"alias": "cheese", "delta_grams": 20}
  ]
}
```

The logged meal stores macro snapshots and a component snapshot, so historical logs do not change when you later edit a food or recipe.

## MCP Endpoint

- URL: `http://HOST:8765/mcp`
- Transport: Streamable HTTP via the official Python MCP SDK v1 `FastMCP`
- Health endpoints:
  - `GET /`
  - `GET /health`

If `MCP_TOKEN` is set, every HTTP request must include:

```text
Authorization: Bearer <token>
```

## Tools

Core tools:

- `add_food`
- `update_food`
- `add_alias`
- `search_foods`
- `log_food`
- `get_day`
- `delete_entry`
- `update_entry`
- `finalize_day`
- `list_aliases`
- `health`

Recipe tools:

- `add_recipe`
- `update_recipe`
- `get_recipe`
- `search_recipes`
- `log_recipe`

## Data Paths

Inside the container:

- SQLite DB: `/data/nutrition.db`
- Exports: `/data/exports`
- Daily Markdown: `/data/exports/daily/YYYY-MM-DD.md`
- CSV: `/data/exports/csv/YYYY-MM-DD.csv`
- JSON: `/data/exports/json/YYYY-MM-DD.json`

## Local Development

```powershell
py -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
.\.venv\Scripts\pytest
.\.venv\Scripts\python -m app.main
```

On Linux/macOS:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[test]"
pytest
python -m app.main
```

Test the health endpoint:

```bash
curl http://localhost:8765/health
```

With a token:

```bash
curl -H "Authorization: Bearer change-me" http://localhost:8765/health
```

## Demo Data

After the server is running, add demo foods through MCP:

```json
{
  "name": "Babybel",
  "serving_name": "1 piece",
  "kcal": 70,
  "protein_g": 5,
  "carbs_g": 0,
  "fat_g": 5,
  "aliases": ["babybel"]
}
```

```json
{
  "name": "Greek yogurt",
  "serving_name": "1 serving",
  "kcal": 180,
  "protein_g": 20,
  "carbs_g": 8,
  "fat_g": 4,
  "aliases": ["greek yogurt"]
}
```

Example recipe ingredients use grams when the food has `grams_per_serving`:

```json
{
  "name": "Tuna pizza",
  "aliases": ["tuna pizza"],
  "ingredients": [
    {"alias": "pizza dough", "grams": 165},
    {"alias": "default tuna", "grams": 60},
    {"alias": "cheese", "grams": 40}
  ]
}
```

## Docker

Build:

```bash
docker build -t nutrition-mcp:0.1.0 .
```

Run:

```bash
docker run -d \
  --name nutrition-mcp \
  -p 8765:8765 \
  -e TZ=Europe/Bucharest \
  -e MCP_TOKEN=change-me \
  -v /mnt/user/appdata/nutrition-mcp:/data \
  nutrition-mcp:0.1.0
```

For a published image:

```bash
docker run -d \
  --name nutrition-mcp \
  -p 8765:8765 \
  -e TZ=Europe/Bucharest \
  -e MCP_TOKEN=change-me \
  -v /mnt/user/appdata/nutrition-mcp:/data \
  ghcr.io/REPLACE_ME/nutrition-mcp:0.1.0
```

## Unraid Add Container

- Name: `nutrition-mcp`
- Repository: `ghcr.io/REPLACE_ME/nutrition-mcp:0.1.0`
- Network Type: `bridge`
- Port: host `8765` -> container `8765` TCP
- Path: `/mnt/user/appdata/nutrition-mcp` -> `/data`
- Env:
  - `TZ=Europe/Bucharest`
  - `MCP_TOKEN=<long random token>`
- WebUI: `http://[IP]:[PORT:8765]/`

## Hermes MCP Config

If Hermes connects over LAN:

```yaml
mcp_servers:
  nutrition:
    url: "http://192.168.1.142:8765/mcp"
    headers:
      Authorization: "Bearer change-me"
```

If Hermes and this server are on the same custom Docker network:

```yaml
mcp_servers:
  nutrition:
    url: "http://nutrition-mcp:8765/mcp"
    headers:
      Authorization: "Bearer change-me"
```

## Environment

```text
DATA_DIR=/data
TZ=Europe/Bucharest
MCP_TOKEN=
HOST=0.0.0.0
PORT=8765
```

## Notes

- SQLite is the only database.
- All persistent files live under `/data`.
- No arbitrary SQL tool is exposed.
- Deletes require an exact meal `entry_id`.
- Historical entries keep snapshots when foods or recipes are updated.

