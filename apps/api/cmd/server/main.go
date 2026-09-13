package main

import (
	"log"
	"os"
	"path/filepath"

	"github.com/czech-uni-apply/catalog"
)

func main() {
	addr := getenv("API_ADDR", "127.0.0.1:8080")
	publication, err := openFromEnv()
	if err != nil {
		log.Fatalf("catalog: %v", err)
	}
	publishedDir := os.Getenv("CATALOG_PUBLICATION_DIR")
	if publishedDir == "" && !publication.Fixture {
		publishedDir = defaultPublicationDir()
	}
	overlayPath := os.Getenv("CATALOG_SAFETY_STATUS")
	if overlayPath == "" && publishedDir != "" {
		overlayPath = catalog.ResolveSafetyPath(publishedDir, "")
	}
	rt := newRuntime(publication, overlayPath, nil)
	server := newHTTPServer(addr, rt.handler())
	log.Printf(
		"api listening on %s version=%s fixture=%t snapshot=%s",
		addr,
		publication.Version,
		publication.Fixture,
		filepath.ToSlash(publishedDir),
	)
	log.Fatal(server.ListenAndServe())
}
