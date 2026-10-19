# SPARQL Endpoint — Apache Jena Fuseki

A SPARQL 1.1 endpoint for querying RDF files using **Apache Jena Fuseki** (`stain/jena-fuseki:5.1.0`), served via **Docker**. RDF files are downloaded automatically from remote URLs at startup.

## Quickstart

### 1 — Start Fuseki

```bash
docker compose up -d
```

This will:
1. Download all configured RDF files into `./data/` (via the `download` service)
2. Start Fuseki once all downloads are complete

Watch progress with:
```bash
docker compose logs -f
```

### 2 — Load your RDF files into TDB2

Run the loader once after Fuseki is up:

```bash
./load.sh
```

This stops Fuseki, bulk-loads all files from `./data/` into the TDB2 `ds` dataset, then restarts Fuseki.

### 3 — Query

Open the web UI directly in your browser:
```
ui/index.html
```

Or use Fuseki's built-in UI:
```
http://localhost:3030    (login: admin / admin)
```

---

## Adding or changing RDF sources

RDF files are downloaded from URLs configured in `docker-compose.yml` under the `download` service. To add or remove files, edit the `command` block:

```yaml
download "$$BASE/my-new-file.ttl"
```

Then do a clean reload:
```bash
docker compose down -v     # wipe TDB2 database and downloaded files
docker compose up -d       # re-download and restart
./load.sh                  # reload into TDB2
```

To skip re-downloading files that already exist in `./data/`, omit `-v`:
```bash
docker compose down
docker compose up -d
./load.sh
```

---

## Project Structure

```
.
├── data/                  ← Populated automatically by docker compose up
├── ui/
│   └── index.html         ← Standalone web UI (open directly in browser)
├── load.sh                ← Bulk-loads ./data/ into Fuseki TDB2
├── docker-compose.yml     ← Downloads RDF files + starts Fuseki
└── README.md
```

---

## SPARQL Endpoints

| Endpoint    | URL                               |
|-------------|-----------------------------------|
| Query       | `http://localhost:3030/ds/sparql` |
| Update      | `http://localhost:3030/ds/update` |
| Graph Store | `http://localhost:3030/ds/data`   |
| Fuseki UI   | `http://localhost:3030`           |
| Ping        | `http://localhost:3030/$/ping`    |

### Example curl

```bash
curl -X POST http://localhost:3030/ds/sparql \
  --data-urlencode "query=SELECT ?s ?p ?o WHERE { ?s ?p ?o } LIMIT 5" \
  -H "Accept: application/sparql-results+json"
```

---

## Configuration

| Variable           | Default  | Description                            |
|--------------------|----------|----------------------------------------|
| `ADMIN_PASSWORD`   | `admin`  | Fuseki admin UI password               |
| `FUSEKI_DATASET_1` | `ds`     | Dataset name                           |
| `TDB`              | `2`      | TDB version (2 = TDB2, recommended)    |
| `JVM_ARGS`         | `-Xmx4g` | JVM heap — increase for large datasets |

---

## Notes

- The `download` service uses `curlimages/curl` (native ARM64) — no Rosetta emulation on Apple Silicon
- The `fuseki` service uses `stain/jena-fuseki:5.1.0` (linux/amd64) — runs via Rosetta 2 on Apple M1/M2/M3
- The TDB2 database is persisted in a Docker named volume (`fuseki-db`) — Fuseki restarts are fast after the initial load
- Files already present in `./data/` are never re-downloaded