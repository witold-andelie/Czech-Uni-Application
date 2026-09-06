package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"time"

	"github.com/czech-uni-apply/catalog"
)

func main() {
	addr := getenv("API_ADDR", "127.0.0.1:8080")
	snapshotPath := getenv("CATALOG_SNAPSHOT", defaultSnapshot())
	snapshot, err := catalog.LoadSnapshot(snapshotPath)
	if err != nil {
		log.Fatalf("catalog snapshot: %v", err)
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	mux.HandleFunc("/readyz", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{"status": "ready", "generatedAt": snapshot.GeneratedAt, "dataClass": snapshot.DataClass})
	})
	mux.HandleFunc("/api/programmes", func(w http.ResponseWriter, r *http.Request) {
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
			Ownership:            query.Get("ownership"),
			ListedOnly:           query.Get("listedOnly") == "1",
			Status:               query.Get("status"),
			Sort:                 query.Get("sort"),
			Page:                 atoi(query.Get("page"), 1),
			PageSize:             atoi(query.Get("pageSize"), 20),
		}
		locale := query.Get("locale")
		if locale == "" {
			locale = "zh-CN"
		}
		needs, total, page := snapshot.FilterOfferings(filter, time.Now(), locale)
		writeJSON(w, http.StatusOK, map[string]any{"needsChoice": needs, "total": total, "page": page, "generatedAt": snapshot.GeneratedAt})
	})
	mux.HandleFunc("/api/jobs", func(w http.ResponseWriter, r *http.Request) {
		query := r.URL.Query()
		filter := catalog.JobFilterQuery{
			MasterEligible:     query.Get("masterEligible") != "0",
			DoctoralEnrollment: query.Get("phd"),
			WorkingLanguage:    query.Get("lang"),
			Search:             query.Get("q"),
			Page:               atoi(query.Get("page"), 1),
			PageSize:           atoi(query.Get("pageSize"), 20),
		}
		locale := query.Get("locale")
		if locale == "" {
			locale = "zh-CN"
		}
		total, page := snapshot.FilterJobs(filter, time.Now(), locale)
		writeJSON(w, http.StatusOK, map[string]any{"total": total, "page": page, "generatedAt": snapshot.GeneratedAt})
	})
	server := &http.Server{Addr: addr, Handler: withJSON(mux), ReadHeaderTimeout: 5 * time.Second}
	log.Printf("api listening on %s snapshot=%s", addr, snapshotPath)
	log.Fatal(server.ListenAndServe())
}

func withJSON(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		next.ServeHTTP(w, r)
	})
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
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

func getenv(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func defaultSnapshot() string {
	wd, _ := os.Getwd()
	candidates := []string{
		filepath.Join(wd, "data", "fixtures", "catalog.json"),
		filepath.Join(wd, "..", "..", "data", "fixtures", "catalog.json"),
	}
	for _, candidate := range candidates {
		if _, err := os.Stat(candidate); err == nil {
			return candidate
		}
	}
	return candidates[len(candidates)-1]
}
