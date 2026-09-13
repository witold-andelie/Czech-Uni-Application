package catalog

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func repoRoot(t *testing.T) string {
	t.Helper()
	_, file, _, _ := runtime.Caller(0)
	return filepath.Join(filepath.Dir(file), "..", "..")
}

func TestOpenCatalogRefusesFixtureWithoutFlag(t *testing.T) {
	path := filepath.Join(repoRoot(t), "data", "fixtures", "catalog.json")
	_, err := OpenCatalog(OpenOptions{SnapshotPath: path, AllowFixture: false})
	if err == nil {
		t.Fatal("production must refuse fixture catalogue")
	}
}

func TestOpenCatalogAllowsFixtureWithFlag(t *testing.T) {
	path := filepath.Join(repoRoot(t), "data", "fixtures", "catalog.json")
	pub, err := OpenCatalog(OpenOptions{SnapshotPath: path, AllowFixture: true})
	if err != nil {
		t.Fatal(err)
	}
	if !pub.Fixture || pub.DataClass != FixtureDataClass {
		t.Fatalf("expected fixture publication, got %+v", pub)
	}
}

func TestLoadPublicationMatchesActivePointer(t *testing.T) {
	published := filepath.Join(repoRoot(t), "data", "published")
	pub, err := LoadPublication(published)
	if err != nil {
		t.Fatal(err)
	}
	if pub.Fixture {
		t.Fatal("published catalogue must not be a fixture")
	}
	if pub.Version == "" || pub.Counts["jobs"] == 0 {
		t.Fatalf("missing version or jobs: %+v", pub.Counts)
	}
	if len(pub.Snapshot.Jobs) != pub.Counts["jobs"] {
		t.Fatalf("API jobs %d != manifest jobs %d", len(pub.Snapshot.Jobs), pub.Counts["jobs"])
	}
	if pub.Snapshot.DataClass == FixtureDataClass {
		t.Fatal("published snapshot dataClass")
	}
	if len(pub.Snapshot.Offerings) != pub.Counts["reviewedOfferings"] && pub.Counts["reviewedOfferings"] > 0 {
		t.Fatalf("reviewed offerings %d != %d", len(pub.Snapshot.Offerings), pub.Counts["reviewedOfferings"])
	}
}

func TestLoadPublicationRejectsCorruptChecksum(t *testing.T) {
	root := t.TempDir()
	src := filepath.Join(repoRoot(t), "data", "published")
	// Copy only the pointer to a missing snapshot.
	if err := os.MkdirAll(filepath.Join(root, "snapshots", "v2099-01-01.1"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "current.json"), []byte(`{"schemaVersion":1,"activeVersion":"v2099-01-01.1","snapshotDir":"snapshots/v2099-01-01.1"}`), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(root, "snapshots", "v2099-01-01.1", "manifest.json"), []byte(`{"version":"v2099-01-01.1","status":"published","validation":{"passed":true,"errors":[]},"checksums":{"missing.json":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}`), 0o644); err != nil {
		t.Fatal(err)
	}
	_, err := LoadPublication(root)
	if err == nil {
		t.Fatal("corrupt publication must not become ready")
	}
	_ = src
}
