# apps/web

TypeScript + Astro static pages, Svelte islands for filters, shortlist and locale switching.

```powershell
cd apps/web
npm install
npm test
npm run dev
```

Open http://127.0.0.1:4321/zh-CN/

The first version reads `data/fixtures/catalog.json`. Those records are UI fixtures, not a verified published catalogue. Production pages must later read `data/published/` snapshots or the Go API.

Do not add Google Fonts, Google Translate, or other third-party translation widgets.
