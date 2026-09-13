package main

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"

	"github.com/czech-uni-apply/catalog"
)

func repoRoot(t *testing.T) string {
	t.Helper()
	_, file, _, _ := runtime.Caller(0)
	return filepath.Join(filepath.Dir(file), "..", "..", "..", "..")
}

func fixturePath(t *testing.T) string {
	t.Helper()
	return filepath.Join(repoRoot(t), "data", "fixtures", "catalog.json")
}

func decodeJSON(t *testing.T, rec *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var payload map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &payload); err != nil {
		t.Fatalf("json: %v body=%s", err, rec.Body.String())
	}
	return payload
}

func TestProductionStartupRefusesFixture(t *testing.T) {
	t.Setenv("CATALOG_ALLOW_FIXTURE", "")
	t.Setenv("CATALOG_SNAPSHOT", fixturePath(t))
	t.Setenv("CATALOG_PUBLICATION_DIR", "")
	if _, err := openFromEnv(); err == nil {
		t.Fatal("expected fixture refusal")
	}
}

func TestFixtureStartupRequiresExplicitFlag(t *testing.T) {
	t.Setenv("CATALOG_ALLOW_FIXTURE", "1")
	t.Setenv("CATALOG_SNAPSHOT", fixturePath(t))
	pub, err := openFromEnv()
	if err != nil {
		t.Fatal(err)
	}
	if !pub.Fixture {
		t.Fatal("flag must load the fixture as a demo catalogue")
	}
}

func TestPublicationReadyzAndJobFilters(t *testing.T) {
	published := filepath.Join(repoRoot(t), "data", "published")
	pub, err := catalog.LoadPublication(published)
	if err != nil {
		t.Fatal(err)
	}
	clock := func() time.Time { return time.Date(2026, 9, 12, 12, 0, 0, 0, time.UTC) }
	rt := newRuntime(pub, catalog.ResolveSafetyPath(published, ""), clock)
	handler := rt.handler()

	ready := httptest.NewRecorder()
	handler.ServeHTTP(ready, httptest.NewRequest(http.MethodGet, "/readyz", nil))
	if ready.Code != http.StatusOK {
		t.Fatalf("readyz %d", ready.Code)
	}
	body := decodeJSON(t, ready)
	if body["fixture"] != false {
		t.Fatalf("readyz fixture: %v", body["fixture"])
	}
	if body["publicationVersion"] != pub.Version {
		t.Fatalf("version %v", body["publicationVersion"])
	}

	needs := httptest.NewRecorder()
	handler.ServeHTTP(needs, httptest.NewRequest(http.MethodGet, "/api/programmes", nil))
	if needs.Code != http.StatusOK {
		t.Fatalf("programmes %d", needs.Code)
	}
	if decodeJSON(t, needs)["needsChoice"] != true {
		t.Fatal("unset teaching language must not query")
	}

	listed := httptest.NewRecorder()
	handler.ServeHTTP(listed, httptest.NewRequest(http.MethodGet, "/api/programmes?teachingLanguage=en&locale=en", nil))
	if listed.Code != http.StatusOK {
		t.Fatalf("en programmes %d", listed.Code)
	}

	empty := httptest.NewRecorder()
	handler.ServeHTTP(empty, httptest.NewRequest(http.MethodGet, "/api/jobs?page=99&masterEligible=0&track=all", nil))
	if empty.Code != http.StatusOK {
		t.Fatalf("empty page %d", empty.Code)
	}
	emptyBody := decodeJSON(t, empty)
	if emptyBody["total"].(float64) <= 0 {
		t.Fatal("expected published jobs")
	}
	page, _ := emptyBody["page"].([]any)
	if len(page) != 0 {
		t.Fatalf("page 99 must be empty, got %d", len(page))
	}

	badLocale := httptest.NewRecorder()
	handler.ServeHTTP(badLocale, httptest.NewRequest(http.MethodGet, "/api/jobs?locale=de", nil))
	if badLocale.Code != http.StatusBadRequest {
		t.Fatalf("locale %d", badLocale.Code)
	}

	method := httptest.NewRecorder()
	handler.ServeHTTP(method, httptest.NewRequest(http.MethodPost, "/api/jobs", nil))
	if method.Code != http.StatusMethodNotAllowed {
		t.Fatalf("method %d", method.Code)
	}
}

func TestJobsEndpointAppliesSafetyOverlay(t *testing.T) {
	pub, err := catalog.OpenCatalog(catalog.OpenOptions{SnapshotPath: fixturePath(t), AllowFixture: true})
	if err != nil {
		t.Fatal(err)
	}
	dir := t.TempDir()
	overlayPath := filepath.Join(dir, "safety-status.json")
	if err := os.WriteFile(overlayPath, []byte(`{
  "schemaVersion": 1,
  "generationId": "s2026-09-12.9",
  "publishedAt": "2026-09-12T15:00:00Z",
  "sourceCheckedAt": "2026-09-12T15:00:00Z",
  "statusPublishedAt": "2026-09-12T15:00:00Z",
  "cacheMaxAgeSeconds": 60,
  "entities": [{"entityType":"research_job","entityId":"job-master-paid","status":"closed","scope":"whole_opportunity"}]
}`), 0o644); err != nil {
		t.Fatal(err)
	}
	clock := func() time.Time { return time.Date(2026, 9, 6, 12, 0, 0, 0, time.UTC) }
	rt := newRuntime(pub, overlayPath, clock)
	rec := httptest.NewRecorder()
	rt.handler().ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/api/jobs?masterEligible=1", nil))
	if rec.Code != http.StatusOK {
		t.Fatalf("jobs %d", rec.Code)
	}
	body := decodeJSON(t, rec)
	page, _ := body["page"].([]any)
	for _, item := range page {
		row, _ := item.(map[string]any)
		job, _ := row["job"].(map[string]any)
		if job["id"] == "job-master-paid" {
			t.Fatal("closed job remained in public results")
		}
	}
}

func TestInvalidPublicationLeavesCallerWithoutReadyHandler(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "current.json"), []byte(`{"activeVersion":"nope","snapshotDir":"snapshots/nope"}`), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := catalog.LoadPublication(dir); err == nil {
		t.Fatal("invalid publication must fail")
	}
}
