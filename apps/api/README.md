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

`CATALOG_SNAPSHOT` defaults to `data/fixtures/catalog.json`.
