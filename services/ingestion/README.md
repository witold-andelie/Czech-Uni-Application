# services/ingestion

Python + Scrapling offline worker. Not started by the public website.

```powershell
py -3 services/ingestion/src/worker.py
py -3 services/ingestion/tests/test_failure_policy.py
```

The worker currently only loads `data/sources/registry.json` and `config/refresh-policy.json`. It does not fetch official pages. HTTP 404/429/timeout must not be stored as a closed vacancy.
