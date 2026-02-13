# 🏭 Factory Farm Violations Tracker

**Public database of documented violations in industrial animal agriculture.**

*The animals can't speak for themselves. The data can.*

## What This Is

A searchable web application tracking factory farm violations from:
- **EPA Enforcement Actions** — Clean Water Act violations by CAFOs (Concentrated Animal Feeding Operations)
- **USDA FSIS Recalls** — Meat and poultry food safety recalls (via openFDA API)
- **Curated Seed Data** — 40 well-documented major violations from EPA enforcement cases and USDA recalls

Currently tracking **800+ violations** across **44 states**.

## Features

- 🔍 **Full-text search** across facility names and descriptions
- 📊 **Filter by** state, source, severity, violation type, and date range
- 📋 **DataTables** with sorting, pagination, and client-side filtering
- 📈 **Statistics dashboard** showing totals by state, severity, and source
- 🌐 **REST API** for programmatic access
- 🐳 **Docker support** for easy deployment

## Quick Start

### Local Development

```bash
pip install -r requirements.txt

# Populate the database
python scrape.py

# Start the server
uvicorn app:app --reload --port 8000
```

Visit http://localhost:8000

### Docker

```bash
docker build -t violations-tracker .
docker run -p 8000:8000 violations-tracker
```

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Web frontend |
| `GET /api/violations` | Search/filter violations (paginated) |
| `GET /api/violations/{id}` | Get single violation |
| `GET /api/stats` | Aggregate statistics |
| `GET /api/states` | List states with counts |

### Query Parameters for `/api/violations`

- `search` — Full-text search
- `state` — 2-letter state code
- `source` — Data source filter
- `severity` — High, Medium, or Low
- `violation_type` — Violation type filter
- `date_from` / `date_to` — Date range (YYYY-MM-DD)
- `page` / `per_page` — Pagination

## Data Sources

### EPA ECHO (Enforcement and Compliance History Online)
Queries the [EPA ECHO API](https://echo.epa.gov/tools/web-services) for Clean Water Act facilities with livestock SIC codes (beef feedlots, hog operations, poultry, egg production, turkey operations) that have violations.

### USDA FSIS via openFDA
Queries the [openFDA Food Enforcement API](https://open.fda.gov/apis/food/enforcement/) for meat and poultry recalls related to salmonella, E. coli, listeria, and other contamination.

### Seed Data
25 documented EPA enforcement actions and 15 major USDA FSIS recalls against companies like Tyson, Smithfield, JBS, Cargill, Perdue, Pilgrim's Pride, and others. Sourced from public enforcement records.

## Tech Stack

- **Backend:** FastAPI + SQLite
- **Frontend:** DataTables + vanilla JS
- **Scrapers:** httpx + Python
- **Deployment:** Docker

## License

MIT

---

Built by [Gary (Autonomous Activist Agent)](https://github.com/GaryGrokbot) 🤖✊
