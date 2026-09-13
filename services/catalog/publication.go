package catalog

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

const FixtureDataClass = "ui_fixture"

type PublicationPointer struct {
	SchemaVersion  int    `json:"schemaVersion"`
	ActiveVersion  string `json:"activeVersion"`
	SnapshotDir    string `json:"snapshotDir"`
	PublishedAt    string `json:"publishedAt"`
	ActivatedAt    string `json:"activatedAt"`
}

type PublicationManifest struct {
	SchemaVersion int               `json:"schemaVersion"`
	PolicyVersion string            `json:"policyVersion"`
	Version       string            `json:"version"`
	PublishedAt   string            `json:"publishedAt"`
	Status        string            `json:"status"`
	Counts        map[string]int    `json:"counts"`
	Checksums     map[string]string `json:"checksums"`
	Validation    struct {
		Passed bool     `json:"passed"`
		Errors []string `json:"errors"`
	} `json:"validation"`
	CandidateGeneration *CandidateGeneration `json:"candidateGeneration"`
}

type CandidateGeneration struct {
	ID        string            `json:"id"`
	PinnedAt  string            `json:"pinnedAt"`
	Checksums map[string]string `json:"checksums"`
	LockOrder []string          `json:"lockOrder"`
}

type Publication struct {
	Version     string
	PublishedAt string
	DataClass   string
	Fixture     bool
	Counts      map[string]int
	Checksums   map[string]string
	Snapshot    *Snapshot
	Manifest    PublicationManifest
	Pointer     PublicationPointer
}

type OpenOptions struct {
	PublicationDir string
	SnapshotPath   string
	AllowFixture   bool
	SafetyPath     string
}

func sha256File(path string) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer file.Close()
	digest := sha256.New()
	if _, err := io.Copy(digest, file); err != nil {
		return "", err
	}
	return "sha256:" + hex.EncodeToString(digest.Sum(nil)), nil
}

func readJSON(path string, dest any) error {
	raw, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(raw, dest)
}

func OpenCatalog(opts OpenOptions) (*Publication, error) {
	if opts.SnapshotPath != "" {
		snapshot, err := LoadSnapshot(opts.SnapshotPath)
		if err != nil {
			return nil, fmt.Errorf("catalog snapshot: %w", err)
		}
		if snapshot.DataClass == FixtureDataClass && !opts.AllowFixture {
			return nil, fmt.Errorf("refusing fixture catalogue %q unless CATALOG_ALLOW_FIXTURE=1", opts.SnapshotPath)
		}
		if snapshot.DataClass == FixtureDataClass && opts.AllowFixture {
			return &Publication{
				Version:     "fixture",
				PublishedAt: snapshot.GeneratedAt,
				DataClass:   snapshot.DataClass,
				Fixture:     true,
				Counts: map[string]int{
					"institutions": len(snapshot.Institutions),
					"offerings":    len(snapshot.Offerings),
					"jobs":         len(snapshot.Jobs),
				},
				Snapshot: snapshot,
			}, nil
		}
		return &Publication{
			Version:     filepath.Base(filepath.Dir(opts.SnapshotPath)),
			PublishedAt: snapshot.GeneratedAt,
			DataClass:   snapshot.DataClass,
			Fixture:     false,
			Counts: map[string]int{
				"institutions": len(snapshot.Institutions),
				"offerings":    len(snapshot.Offerings),
				"jobs":         len(snapshot.Jobs),
			},
			Snapshot: snapshot,
		}, nil
	}
	if opts.PublicationDir == "" {
		return nil, fmt.Errorf("production catalogue requires CATALOG_PUBLICATION_DIR or data/published")
	}
	return LoadPublication(opts.PublicationDir)
}

func LoadPublication(publishedDir string) (*Publication, error) {
	pointerPath := filepath.Join(publishedDir, "current.json")
	var pointer PublicationPointer
	if err := readJSON(pointerPath, &pointer); err != nil {
		return nil, fmt.Errorf("publication pointer: %w", err)
	}
	if pointer.ActiveVersion == "" || pointer.SnapshotDir != "snapshots/"+pointer.ActiveVersion {
		return nil, fmt.Errorf("current.json does not select one immutable snapshot")
	}
	snapshotDir := filepath.Join(publishedDir, filepath.FromSlash(pointer.SnapshotDir))
	var manifest PublicationManifest
	if err := readJSON(filepath.Join(snapshotDir, "manifest.json"), &manifest); err != nil {
		return nil, fmt.Errorf("publication manifest: %w", err)
	}
	if manifest.Version != pointer.ActiveVersion {
		return nil, fmt.Errorf("manifest version %s does not match pointer %s", manifest.Version, pointer.ActiveVersion)
	}
	if manifest.Status != "published" || !manifest.Validation.Passed {
		return nil, fmt.Errorf("active snapshot %s is not a passed published manifest", manifest.Version)
	}
	if len(manifest.Checksums) == 0 {
		return nil, fmt.Errorf("manifest checksums missing")
	}
	for relative, expected := range manifest.Checksums {
		if strings.Contains(relative, "..") || strings.Contains(relative, `\`) {
			return nil, fmt.Errorf("unsafe checksum path %q", relative)
		}
		actual, err := sha256File(filepath.Join(snapshotDir, filepath.FromSlash(relative)))
		if err != nil {
			return nil, fmt.Errorf("checksum %s: %w", relative, err)
		}
		if actual != expected {
			return nil, fmt.Errorf("checksum mismatch for %s", relative)
		}
	}
	snapshot, err := snapshotFromPublication(snapshotDir, manifest)
	if err != nil {
		return nil, err
	}
	if snapshot.DataClass == FixtureDataClass {
		return nil, fmt.Errorf("published snapshot unexpectedly has fixture dataClass")
	}
	return &Publication{
		Version:     pointer.ActiveVersion,
		PublishedAt: pointer.PublishedAt,
		DataClass:   snapshot.DataClass,
		Fixture:     false,
		Counts:      manifest.Counts,
		Checksums:   manifest.Checksums,
		Snapshot:    snapshot,
		Manifest:    manifest,
		Pointer:     pointer,
	}, nil
}

type baselineFile struct {
	GeneratedAt  string `json:"generatedAt"`
	DataClass    string `json:"dataClass"`
	Institutions []struct {
		ID            string `json:"id"`
		OfficialName  string `json:"officialName"`
		Ownership     string `json:"ownership"`
		LegalType     string `json:"legalType"`
		Region        string `json:"region"`
		OfficialURL   string `json:"officialUrl"`
		CscseReference CscseReference `json:"cscseReference"`
	} `json:"institutions"`
}

type reviewedFile struct {
	GeneratedAt string          `json:"generatedAt"`
	DataClass   string          `json:"dataClass"`
	Offerings   []Offering      `json:"offerings"`
	Windows     []ApplicationWindow `json:"windows"`
}

type jobsFile struct {
	GeneratedAt string              `json:"generatedAt"`
	DataClass   string              `json:"dataClass"`
	Jobs        []ResearchJob       `json:"jobs"`
	Windows     []ApplicationWindow `json:"windows"`
}

func snapshotFromPublication(snapshotDir string, manifest PublicationManifest) (*Snapshot, error) {
	var baseline baselineFile
	if err := readJSON(filepath.Join(snapshotDir, "msmt-hei-baseline.json"), &baseline); err != nil {
		return nil, fmt.Errorf("baseline: %w", err)
	}
	var reviewed reviewedFile
	if err := readJSON(filepath.Join(snapshotDir, "admissions", "reviewed-offerings.json"), &reviewed); err != nil {
		return nil, fmt.Errorf("reviewed offerings: %w", err)
	}
	var jobs jobsFile
	if err := readJSON(filepath.Join(snapshotDir, "browse", "nine-hei-jobs.json"), &jobs); err != nil {
		return nil, fmt.Errorf("jobs: %w", err)
	}
	institutions := make([]Institution, 0, len(baseline.Institutions))
	for _, item := range baseline.Institutions {
		name := LocalizedText{ZhCN: item.OfficialName, En: item.OfficialName, Cs: item.OfficialName}
		if item.CscseReference.OfficialMatchedName != nil && *item.CscseReference.OfficialMatchedName != "" {
			name.Cs = *item.CscseReference.OfficialMatchedName
		}
		city := LocalizedText{ZhCN: item.Region, En: item.Region, Cs: item.Region}
		institutions = append(institutions, Institution{
			ID:             item.ID,
			OfficialName:   item.OfficialName,
			DisplayName:    name,
			Country:        "CZ",
			City:           city,
			Ownership:      item.Ownership,
			LegalType:      item.LegalType,
			Orientation:    "unknown",
			OfficialURL:    item.OfficialURL,
			CscseReference: item.CscseReference,
			DataClass:      baseline.DataClass,
		})
	}
	programmes := make([]Programme, 0, len(reviewed.Offerings))
	seenProg := map[string]bool{}
	for _, offering := range reviewed.Offerings {
		if seenProg[offering.ProgrammeID] {
			continue
		}
		seenProg[offering.ProgrammeID] = true
		programmes = append(programmes, Programme{
			ID:            offering.ProgrammeID,
			InstitutionID: offering.InstitutionID,
			Degree:        offering.Degree,
			Field:         offering.Field,
			Orientation:   "unknown",
		})
	}
	windows := append([]ApplicationWindow{}, reviewed.Windows...)
	windows = append(windows, jobs.Windows...)
	return &Snapshot{
		GeneratedAt:  manifest.PublishedAt,
		DataClass:    "published_release",
		CatalogKind:  "published_admissions_and_jobs",
		Institutions: institutions,
		Programmes:   programmes,
		Offerings:    reviewed.Offerings,
		Windows:      windows,
		Jobs:         jobs.Jobs,
	}, nil
}

func ResolveSafetyPath(publishedDir, explicit string) string {
	if explicit != "" {
		return explicit
	}
	publicCopy := filepath.Join(publishedDir, "safety-status.json")
	if _, err := os.Stat(publicCopy); err == nil {
		return publicCopy
	}
	pointerPath := filepath.Join(publishedDir, "safety", "current.json")
	var pointer struct {
		GenerationDir string `json:"generationDir"`
	}
	if err := readJSON(pointerPath, &pointer); err != nil {
		return publicCopy
	}
	if pointer.GenerationDir == "" {
		return publicCopy
	}
	return filepath.Join(publishedDir, "safety", filepath.FromSlash(pointer.GenerationDir))
}
