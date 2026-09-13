# apps/api

Go online API. Domain rules live in `services/catalog` and are imported here. This process must not crawl, translate, or scan the whole database at startup.

```powershell
cd services/catalog
go test
cd ..\..\apps\api
go run ./cmd/server
```

Endpoints:

- `GET /healthz`
- `GET /readyz`
- `GET /api/programmes?teachingLanguage=en`
- `GET /api/jobs?masterEligible=1`

Production startup reads `data/published/current.json`, verifies snapshot checksums, and refuses `dataClass=ui_fixture` unless `CATALOG_ALLOW_FIXTURE=1`.

Environment:

- `CATALOG_PUBLICATION_DIR` — directory that contains `current.json` (default: repo `data/published`)
- `CATALOG_ALLOW_FIXTURE=1` — local/demo only; loads `CATALOG_SNAPSHOT` or `data/fixtures/catalog.json`
- `CATALOG_SAFETY_STATUS` — optional overlay JSON; default is the published safety pointer
- `API_ADDR` — default `127.0.0.1:8080`

`GET /readyz` returns `publicationVersion`, `counts`, `fixture` and `safetyGeneration`. Corrupted publication files fail startup instead of serving fixtures. Hosted deployment is not verified.
