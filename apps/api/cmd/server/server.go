package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/czech-uni-apply/catalog"
)

type apiRuntime struct {
	mu          sync.RWMutex
	publication *catalog.Publication
	overlay     *catalog.SafetyOverlay
	overlayPath string
	clock       func() time.Time
}

func getenv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func envTruthy(key string) bool {
	switch strings.ToLower(strings.TrimSpace(os.Getenv(key))) {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}

func findPath(candidates ...string) string {
	for _, candidate := range candidates {
		if candidate == "" {
			continue
		}
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
	}
	if len(candidates) == 0 {
		return ""
	}
	return candidates[len(candidates)-1]
}

func defaultPublicationDir() string {
	if value := os.Getenv("CATALOG_PUBLICATION_DIR"); value != "" {
		return value
	}
	wd, _ := os.Getwd()
	return findPath(
		filepath.Join(wd, "data", "published"),
		filepath.Join(wd, "..", "..", "data", "published"),
		filepath.Join(wd, "..", "..", "..", "data", "published"),
	)
}

func defaultFixturePath() string {
	if value := os.Getenv("CATALOG_SNAPSHOT"); value != "" {
		return value
	}
	wd, _ := os.Getwd()
	return findPath(
		filepath.Join(wd, "data", "fixtures", "catalog.json"),
		filepath.Join(wd, "..", "..", "data", "fixtures", "catalog.json"),
	)
}

func openFromEnv() (*catalog.Publication, error) {
	allowFixture := envTruthy("CATALOG_ALLOW_FIXTURE")
	if snapshot := os.Getenv("CATALOG_SNAPSHOT"); snapshot != "" {
		return catalog.OpenCatalog(catalog.OpenOptions{SnapshotPath: snapshot, AllowFixture: allowFixture})
	}
	if allowFixture {
		return catalog.OpenCatalog(catalog.OpenOptions{SnapshotPath: defaultFixturePath(), AllowFixture: true})
	}
	dir := defaultPublicationDir()
	if dir == "" {
		return nil, errors.New("production API requires a validated publication at data/published; set CATALOG_PUBLICATION_DIR or CATALOG_ALLOW_FIXTURE=1")
	}
	return catalog.OpenCatalog(catalog.OpenOptions{PublicationDir: dir})
}

func newRuntime(publication *catalog.Publication, overlayPath string, clock func() time.Time) *apiRuntime {
	if clock == nil {
		clock = time.Now
	}
	rt := &apiRuntime{publication: publication, overlayPath: overlayPath, clock: clock, overlay: catalog.EmptySafetyOverlay()}
	rt.reloadOverlay()
	return rt
}

func (rt *apiRuntime) reloadOverlay() {
	if rt.overlayPath == "" {
		return
	}
	overlay, err := catalog.LoadSafetyOverlay(rt.overlayPath)
	if err != nil {
		if errors.Is(err, fs.ErrNotExist) {
			return
		}
		return
	}
	rt.overlay = overlay
}

func (rt *apiRuntime) snapshot() (*catalog.Publication, *catalog.Snapshot, *catalog.SafetyOverlay) {
	rt.mu.RLock()
	defer rt.mu.RUnlock()
	live := rt.publication.Snapshot.ApplySafety(rt.overlay)
	return rt.publication, live, rt.overlay
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeError(w http.ResponseWriter, status int, code, message string) {
	writeJSON(w, status, map[string]string{"error": code, "message": message})
}

func requestLocale(r *http.Request) (string, error) {
	locale := r.URL.Query().Get("locale")
	if locale == "" {
		return "zh-CN", nil
	}
	if !catalog.IsKnownLocale(locale) {
		return "", fmt.Errorf("unsupported locale")
	}
	return locale, nil
}

func (rt *apiRuntime) handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
			return
		}
		rt.mu.Lock()
		rt.reloadOverlay()
		rt.mu.Unlock()
		pub, _, overlay := rt.snapshot()
		writeJSON(w, http.StatusOK, map[string]any{
			"status":              "ready",
			"publicationVersion":  pub.Version,
			"publishedAt":         pub.PublishedAt,
			"generatedAt":         pub.Snapshot.GeneratedAt,
			"dataClass":           pub.DataClass,
			"fixture":             pub.Fixture,
			"counts":              pub.Counts,
			"safetyGeneration":    overlay.GenerationID,
			"safetyPublishedAt":   overlay.StatusPublishedAt,
			"sourceCheckedAt":     overlay.SourceCheckedAt,
		})
	})
	mux.HandleFunc("/api/safety-status", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
			return
		}
		rt.mu.Lock()
		rt.reloadOverlay()
		overlay := rt.overlay
		rt.mu.Unlock()
		maxAge := overlay.CacheMaxAgeSeconds
		if maxAge <= 0 {
			maxAge = 60
		}
		w.Header().Set("Cache-Control", fmt.Sprintf("max-age=%d, must-revalidate", maxAge))
		writeJSON(w, http.StatusOK, overlay)
	})
	mux.HandleFunc("/api/programmes", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
			return
		}
		locale, err := requestLocale(r)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid_locale", "locale must be zh-CN, en or cs")
			return
		}
		query := r.URL.Query()
		var teaching *string
		if value := query.Get("teachingLanguage"); value != "" {
			teaching = &value
		}
		filter := catalog.FilterQuery{
			TeachingLanguage:     teaching,
			IncludeJointRequired: query.Get("includeJoint") == "1",
			Search:               query.Get("q"),
			Degree:               query.Get("degree"),
			City:                 query.Get("city"),
			InstitutionID:        query.Get("institution"),
			Ownership:            query.Get("ownership"),
			ListedOnly:           query.Get("listedOnly") == "1",
			Status:               query.Get("status"),
			Orientation:          query.Get("orientation"),
			Sort:                 query.Get("sort"),
			Page:                 atoi(query.Get("page"), 1),
			PageSize:             atoi(query.Get("pageSize"), 20),
		}
		pub, snapshot, overlay := rt.snapshot()
		needs, total, page := snapshot.FilterOfferings(filter, rt.clock(), locale)
		if page == nil {
			page = []catalog.OfferingView{}
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"needsChoice":        needs,
			"total":              total,
			"page":               page,
			"generatedAt":        pub.Snapshot.GeneratedAt,
			"publicationVersion": pub.Version,
			"safetyGeneration":   overlay.GenerationID,
		})
	})
	mux.HandleFunc("/api/jobs", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "method not allowed")
			return
		}
		locale, err := requestLocale(r)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid_locale", "locale must be zh-CN, en or cs")
			return
		}
		query := r.URL.Query()
		filter := catalog.JobFilterQuery{
			MasterEligible:     parseMasterEligible(query.Get("masterEligible")),
			Track:              query.Get("track"),
			DoctoralEnrollment: query.Get("phd"),
			WorkingLanguage:    query.Get("lang"),
			Search:             query.Get("q"),
			Page:               atoi(query.Get("page"), 1),
			PageSize:           atoi(query.Get("pageSize"), 20),
		}
		pub, snapshot, overlay := rt.snapshot()
		total, page := snapshot.FilterJobs(filter, rt.clock(), locale)
		if page == nil {
			page = []catalog.JobView{}
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"total":              total,
			"page":               page,
			"generatedAt":        pub.Snapshot.GeneratedAt,
			"publicationVersion": pub.Version,
			"safetyGeneration":   overlay.GenerationID,
		})
	})
	return withJSON(mux)
}

func withJSON(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		next.ServeHTTP(w, r)
	})
}

func atoi(value string, fallback int) int {
	if value == "" {
		return fallback
	}
	n, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}
	return n
}

func parseMasterEligible(value string) *bool {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "":
		return nil
	case "0", "false", "all":
		return catalog.Bool(false)
	default:
		return catalog.Bool(true)
	}
}

func newHTTPServer(addr string, handler http.Handler) *http.Server {
	return &http.Server{
		Addr:              addr,
		Handler:           handler,
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      15 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
}
