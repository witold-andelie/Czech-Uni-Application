package catalog

import (
	"encoding/json"
	"os"
	"strings"
)

type SafetyEntity struct {
	EntityType         string  `json:"entityType"`
	EntityID           string  `json:"entityId"`
	Status             string  `json:"status"`
	Scope              string  `json:"scope"`
	WindowID           *string `json:"windowId"`
	ObservedSourceHash *string `json:"observedSourceHash"`
	ObservedAt         *string `json:"observedAt"`
	ClosedAt           *string `json:"closedAt"`
	DatePrecision      *string `json:"datePrecision"`
	Reason             *string `json:"reason"`
	EvidenceURL        *string `json:"evidenceUrl"`
	Generation         int     `json:"generation"`
	ReopenEvidenceID   *string `json:"reopenEvidenceId"`
}

type SafetyOverlay struct {
	SchemaVersion             int            `json:"schemaVersion"`
	GenerationID              string         `json:"generationId"`
	PublishedAt               string         `json:"publishedAt"`
	SourceCheckedAt           *string        `json:"sourceCheckedAt"`
	StatusPublishedAt         string         `json:"statusPublishedAt"`
	CacheMaxAgeSeconds        int            `json:"cacheMaxAgeSeconds"`
	PropagationTargetSeconds  int            `json:"propagationTargetSeconds"`
	Entities                  []SafetyEntity `json:"entities"`
}

func LoadSafetyOverlay(path string) (*SafetyOverlay, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var overlay SafetyOverlay
	if err := json.Unmarshal(raw, &overlay); err != nil {
		return nil, err
	}
	if overlay.Entities == nil {
		overlay.Entities = []SafetyEntity{}
	}
	return &overlay, nil
}

func EmptySafetyOverlay() *SafetyOverlay {
	return &SafetyOverlay{
		SchemaVersion:            1,
		GenerationID:             "s2026-09-12.0",
		PublishedAt:              "2026-09-12T00:00:00Z",
		StatusPublishedAt:        "2026-09-12T00:00:00Z",
		CacheMaxAgeSeconds:       60,
		PropagationTargetSeconds: 300,
		Entities:                 []SafetyEntity{},
	}
}

func overlayClosed(status string) bool {
	return status == "closed" || status == "expired"
}

func (s *Snapshot) ApplySafety(overlay *SafetyOverlay) *Snapshot {
	if overlay == nil || len(overlay.Entities) == 0 {
		return s
	}
	clone := *s
	jobs := append([]ResearchJob(nil), s.Jobs...)
	windows := append([]ApplicationWindow(nil), s.Windows...)
	for i, job := range jobs {
		for _, record := range overlay.Entities {
			if record.EntityID != job.ID {
				continue
			}
			if record.Scope == "whole_opportunity" && overlayClosed(record.Status) {
				jobs[i].WholeOpportunityClosed = true
				if record.Status == "expired" {
					jobs[i].LifecycleStatus = "expired"
				} else {
					jobs[i].LifecycleStatus = "closed"
				}
			}
			if record.Scope == "whole_opportunity" && record.Status == "unavailable" {
				jobs[i].LifecycleStatus = "unavailable"
			}
		}
	}
	for i, window := range windows {
		for _, record := range overlay.Entities {
			if record.EntityID != window.OwnerID {
				continue
			}
			if record.Scope == "whole_opportunity" && overlayClosed(record.Status) {
				windows[i].Status = "closed"
			}
			if record.Scope == "window" && record.WindowID != nil && *record.WindowID == window.ID && overlayClosed(record.Status) {
				windows[i].Status = "closed"
			}
		}
	}
	clone.Jobs = jobs
	clone.Windows = windows
	return &clone
}

func IsKnownLocale(locale string) bool {
	switch strings.TrimSpace(locale) {
	case "zh-CN", "en", "cs":
		return true
	default:
		return false
	}
}
