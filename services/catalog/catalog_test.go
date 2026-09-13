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
	_, page := s.FilterJobs(JobFilterQuery{MasterEligible: Bool(true), DoctoralEnrollment: "all", WorkingLanguage: "all", Page: 1, PageSize: 20}, now(), "en")
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

func str(v string) *string { return &v }

func TestCityAndOrientationFilters(t *testing.T) {
	s := load(t)
	cs := "cs"
	_, total, page := s.FilterOfferings(FilterQuery{TeachingLanguage: &cs, City: "Prague", Page: 1, PageSize: 20}, now(), "en")
	if total != 2 {
		t.Fatalf("Prague Czech offerings want 2 got %d", total)
	}
	for _, view := range page {
		if view.Institution.City.En != "Prague" {
			t.Fatalf("%s city %s", view.Offering.ID, view.Institution.City.En)
		}
	}
	_, applied, _ := s.FilterOfferings(FilterQuery{TeachingLanguage: &cs, Orientation: "applied", Page: 1, PageSize: 20}, now(), "en")
	if applied != 1 {
		t.Fatalf("applied Czech offerings want 1 got %d", applied)
	}
}

func TestMissingStartNeverOpens(t *testing.T) {
	tz := "Europe/Prague"
	close := "2026-12-15"
	window := ApplicationWindow{ClosesAt: &close, Timezone: &tz, DatePrecision: "date", Status: "open"}
	if got := EvaluateWindow(window, now()); got != "unknown" {
		t.Fatalf("got %s", got)
	}
}

func TestConditionalOpportunityIsNotOpen(t *testing.T) {
	s := load(t)
	summary := SummarizeWindows(windows(s, "offering", "off-biz-en-supp"), now(), false)
	if summary.OpportunityStatus != "conditional" {
		t.Fatalf("got %s", summary.OpportunityStatus)
	}
}

func TestDatetimeCloseUsesClock(t *testing.T) {
	tz := "Europe/Prague"
	opens := "2026-09-01T00:00:00+02:00"
	closes := "2026-09-06T10:00:00+02:00"
	window := ApplicationWindow{OpensAt: &opens, ClosesAt: &closes, Timezone: &tz, DatePrecision: "datetime", Status: "open"}
	if got := EvaluateWindow(window, now()); got != "closed" {
		t.Fatalf("got %s", got)
	}
}

func TestExplicitClosedWinsWithoutStart(t *testing.T) {
	tz := "Europe/Prague"
	closes := "2026-09-30"
	window := ApplicationWindow{ClosesAt: &closes, Timezone: &tz, DatePrecision: "date", Status: "closed"}
	if got := EvaluateWindow(window, now()); got != "closed" {
		t.Fatalf("got %s", got)
	}
}

func TestInstitutionFilterExcludesUnknown(t *testing.T) {
	s := load(t)
	cs := "cs"
	_, total, page := s.FilterOfferings(FilterQuery{TeachingLanguage: &cs, InstitutionID: "does-not-exist", Page: 1, PageSize: 20}, now(), "en")
	if total != 0 || len(page) != 0 {
		t.Fatalf("unknown institution should yield zero, got %d", total)
	}
}

func TestJobTrackPostdoc(t *testing.T) {
	s := load(t)
	_, page := s.FilterJobs(JobFilterQuery{Track: "postdoc", Page: 1, PageSize: 20}, now(), "en")
	if len(page) == 0 {
		t.Fatal("expected public postdocs")
	}
	for _, view := range page {
		if !view.Job.IsPostdoc && JobTrackOf(view.Job) != "postdoc" {
			t.Fatalf("non-postdoc %s", view.Job.ID)
		}
	}
}

func TestZeroValueJobFilterExcludesPostdocs(t *testing.T) {
	s := load(t)
	_, page := s.FilterJobs(JobFilterQuery{Page: 1, PageSize: 20}, now(), "en")
	for _, view := range page {
		if view.Job.ID == "job-postdoc" {
			t.Fatal("nil MasterEligible must keep the product default")
		}
	}
}

func TestMasterEligibleFalseKeepsPublicPostdoc(t *testing.T) {
	s := load(t)
	_, page := s.FilterJobs(JobFilterQuery{MasterEligible: Bool(false), Page: 1, PageSize: 20}, now(), "en")
	found := false
	for _, view := range page {
		if view.Job.ID == "job-postdoc" {
			found = true
		}
	}
	if !found {
		t.Fatal("masterEligible=false must not hide public postdocs")
	}
}
