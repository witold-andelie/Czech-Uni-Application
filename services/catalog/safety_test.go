package catalog

import (
	"testing"
	"time"
)

func TestApplySafetyClosesJobAndKeepsTombstone(t *testing.T) {
	s := load(t)
	var target *ResearchJob
	for i := range s.Jobs {
		if s.Jobs[i].ID == "job-master-paid" {
			target = &s.Jobs[i]
			break
		}
	}
	if target == nil {
		t.Fatal("missing fixture job")
	}
	closed := "closed"
	overlay := &SafetyOverlay{
		GenerationID: "s2026-09-12.1",
		Entities: []SafetyEntity{{
			EntityType: "research_job",
			EntityID:   target.ID,
			Status:     closed,
			Scope:      "whole_opportunity",
		}},
	}
	next := s.ApplySafety(overlay)
	found := false
	for _, job := range next.Jobs {
		if job.ID != target.ID {
			continue
		}
		found = true
		if !job.WholeOpportunityClosed {
			t.Fatal("overlay must close the opportunity")
		}
		summary := SummarizeWindows(next.windows("research_job", job.ID), time.Date(2026, 9, 6, 12, 0, 0, 0, time.UTC), JobOpportunityClosed(job))
		if IsPublicJob(job, summary) {
			t.Fatal("closed job must leave the public list")
		}
	}
	if !found {
		t.Fatal("tombstone missing")
	}
}
