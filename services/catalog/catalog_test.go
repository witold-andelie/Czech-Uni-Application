package catalog

import (
	"path/filepath"
	"runtime"
	"testing"
	"time"
)

func load(t *testing.T) *Snapshot {
	t.Helper()
	_, file, _, _ := runtime.Caller(0)
	path := filepath.Join(filepath.Dir(file), "..", "..", "data", "fixtures", "catalog.json")
	snapshot, err := LoadSnapshot(path)
	if err != nil {
		t.Fatal(err)
	}
	return snapshot
}

func now() time.Time {
	return time.Date(2026, 9, 6, 12, 0, 0, 0, time.UTC)
}

func offering(s *Snapshot, id string) Offering {
	for _, item := range s.Offerings {
		if item.ID == id {
			return item
		}
	}
	panic(id)
}

func windows(s *Snapshot, ownerType, ownerID string) []ApplicationWindow {
	return s.windows(ownerType, ownerID)
}

func TestEnglishFilterExcludesJoint(t *testing.T) {
	s := load(t)
	if !MatchesTeachingLanguage(offering(s, "off-cs-en-2026"), "en", false) {
		t.Fatal("english track should match")
	}
	if MatchesTeachingLanguage(offering(s, "off-joint-2026"), "en", false) {
		t.Fatal("joint required must stay out of the default English list")
	}
	if !MatchesTeachingLanguage(offering(s, "off-joint-2026"), "en", true) {
		t.Fatal("explicit joint checkbox should include the bilingual programme")
	}
}

func TestUnsetTeachingLanguageDoesNotQuery(t *testing.T) {
	s := load(t)
	needs, total, page := s.FilterOfferings(FilterQuery{Page: 1, PageSize: 20}, now(), "zh-CN")
	if !needs || total != 0 || len(page) != 0 {
		t.Fatalf("unset language must not run a limited query: %v %d %d", needs, total, len(page))
	}
}

func TestRoundTwoKeepsOpportunityOpen(t *testing.T) {
	s := load(t)
	summary := SummarizeWindows(windows(s, "offering", "off-cs-en-2026"), now(), false)
	if summary.OpportunityStatus != "open" {
		t.Fatalf("got %s", summary.OpportunityStatus)
	}
	if len(summary.Current) == 0 || summary.Current[0].ID != "win-cs-r2" {
		t.Fatalf("current round should be round 2: %+v", summary.Current)
	}
}

func TestMissingStartDoesNotAutoOpen(t *testing.T) {
	s := load(t)
	for _, window := range s.Windows {
		if window.ID == "win-nursing-rolling" {
			if got := EvaluateWindow(window, now()); got != "unknown" {
				t.Fatalf("guanfu-style auto-open is forbidden, got %s", got)
			}
			return
		}
	}
	t.Fatal("missing rolling window")
}

func TestWholeJobClosureBeatsFutureRound(t *testing.T) {
	s := load(t)
	for _, job := range s.Jobs {
		if job.ID == "job-filled" {
			summary := SummarizeWindows(windows(s, "research_job", job.ID), now(), job.WholeOpportunityClosed)
			if summary.OpportunityStatus != "closed" {
				t.Fatalf("got %s", summary.OpportunityStatus)
			}
			if IsPublicJob(job, summary) {
				t.Fatal("filled job must leave public lists")
			}
			return
		}
	}
	t.Fatal("missing filled job")
}

func TestDefaultJobsExcludePostdocAndClosed(t *testing.T) {
	s := load(t)
	_, page := s.FilterJobs(JobFilterQuery{MasterEligible: true, DoctoralEnrollment: "all", WorkingLanguage: "all", Page: 1, PageSize: 20}, now(), "en")
	for _, view := range page {
		if view.Job.ID == "job-postdoc" || view.Job.ID == "job-closed" || view.Job.ID == "job-filled" {
			t.Fatalf("unexpected %s", view.Job.ID)
		}
	}
}

func TestOwnershipDoesNotImplyCscseListed(t *testing.T) {
	s := load(t)
	inst, ok := s.institution("inst-public-prague")
	if !ok || inst.Ownership != "public" || inst.CscseReference.LookupStatus != "unverified" {
		t.Fatalf("%+v", inst)
	}
}

func TestUnpublishedTuitionIsNotZero(t *testing.T) {
	item := offering(load(t), "off-cs-en-2026")
	if item.Tuition.Published || item.Tuition.Amount != nil {
		t.Fatalf("%+v", item.Tuition)
	}
}
