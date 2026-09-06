package catalog

import (
	"encoding/json"
	"os"
	"sort"
	"strings"
	"time"
)

type LocalizedText struct {
	ZhCN string `json:"zh-CN"`
	En   string `json:"en"`
	Cs   string `json:"cs"`
}

func (t LocalizedText) Get(locale string) string {
	switch locale {
	case "en":
		return t.En
	case "cs":
		return t.Cs
	default:
		return t.ZhCN
	}
}

type CscseNotice struct {
	ID            string        `json:"id"`
	Text          LocalizedText `json:"text"`
	Scope         *string       `json:"scope"`
	EffectiveFrom *string       `json:"effectiveFrom"`
	EffectiveTo   *string       `json:"effectiveTo"`
	Active        bool          `json:"active"`
}

type CscseReference struct {
	LookupStatus                 string        `json:"lookupStatus"`
	OfficialMatchedName          *string       `json:"officialMatchedName"`
	MatchedAwardingInstitutionID *string       `json:"matchedAwardingInstitutionId"`
	LookupURL                    string        `json:"lookupUrl"`
	CheckedAt                    *string       `json:"checkedAt"`
	SourceVersion                *string       `json:"sourceVersion"`
	EvidenceID                   *string       `json:"evidenceId"`
	Reviewer                     *string       `json:"reviewer"`
	MatchConfidence              *string       `json:"matchConfidence"`
	Notices                      []CscseNotice `json:"notices"`
}

type Institution struct {
	ID                  string         `json:"id"`
	OfficialName        string         `json:"officialName"`
	DisplayName         LocalizedText  `json:"displayName"`
	Country             string         `json:"country"`
	City                LocalizedText  `json:"city"`
	Ownership           string         `json:"ownership"`
	OwnershipEvidenceID *string        `json:"ownershipEvidenceId"`
	LegalType           string         `json:"legalType"`
	Orientation         string         `json:"orientation"`
	OfficialURL         string         `json:"officialUrl"`
	CscseReference      CscseReference `json:"cscseReference"`
	DataClass           string         `json:"dataClass"`
}

type ApplicationWindow struct {
	ID                      string         `json:"id"`
	OwnerType               string         `json:"ownerType"`
	OwnerID                 string         `json:"ownerId"`
	AcademicYear            *string        `json:"academicYear"`
	RoundNumber             *int           `json:"roundNumber"`
	RoundLabelOriginal      *string        `json:"roundLabelOriginal"`
	RoundType               string         `json:"roundType"`
	ApplicantScope          *LocalizedText `json:"applicantScope"`
	OpensAt                 *string        `json:"opensAt"`
	ClosesAt                *string        `json:"closesAt"`
	Timezone                *string        `json:"timezone"`
	DatePrecision           string         `json:"datePrecision"`
	Status                  string         `json:"status"`
	ConditionalOnVacancies  bool           `json:"conditionalOnVacancies"`
	ApplicationURL          *string        `json:"applicationUrl"`
	SourceEvidenceID        string         `json:"sourceEvidenceId"`
}

type AdditionalLanguageRequirement struct {
	Language    string         `json:"language"`
	Context     string         `json:"context"`
	Requirement string         `json:"requirement"`
	EvidenceURL string         `json:"evidenceUrl"`
	Note        *LocalizedText `json:"note"`
}

type Tuition struct {
	Amount      *float64 `json:"amount"`
	Currency    *string  `json:"currency"`
	Cycle       *string  `json:"cycle"`
	Published   bool     `json:"published"`
	EvidenceURL *string  `json:"evidenceUrl"`
}

type Programme struct {
	ID            string        `json:"id"`
	InstitutionID string        `json:"institutionId"`
	OfficialCode  *string       `json:"officialCode"`
	Degree        string        `json:"degree"`
	Field         LocalizedText `json:"field"`
	Orientation   string        `json:"orientation"`
}

type Offering struct {
	ID                              string                           `json:"id"`
	ProgrammeID                     string                           `json:"programmeId"`
	InstitutionID                   string                           `json:"institutionId"`
	AcademicYear                    string                           `json:"academicYear"`
	TeachingLanguages               []string                         `json:"teachingLanguages"`
	LanguageMode                    string                           `json:"languageMode"`
	LanguageEvidenceURL             string                           `json:"languageEvidenceUrl"`
	AdditionalLanguageRequirements  []AdditionalLanguageRequirement  `json:"additionalLanguageRequirements"`
	Title                           LocalizedText                    `json:"title"`
	Degree                          string                           `json:"degree"`
	DurationSemesters               *int                             `json:"durationSemesters"`
	Field                           LocalizedText                    `json:"field"`
	Tuition                         Tuition                          `json:"tuition"`
	ApplicationURL                  *string                          `json:"applicationUrl"`
	VerifiedAt                      *string                          `json:"verifiedAt"`
	DataClass                       string                           `json:"dataClass"`
	LifecycleOverride               *string                          `json:"lifecycleOverride"`
}

type Salary struct {
	Amount   *float64 `json:"amount"`
	Currency *string  `json:"currency"`
	Cycle    *string  `json:"cycle"`
	Tax      string   `json:"tax"`
	BasisFte *float64 `json:"basisFte"`
}

type ResearchJob struct {
	ID                       string        `json:"id"`
	EmployerID               string        `json:"employerId"`
	Title                    LocalizedText `json:"title"`
	Laboratory               *LocalizedText `json:"laboratory"`
	MinimumDegree            string        `json:"minimumDegree"`
	DoctorateRequired        *bool         `json:"doctorateRequired"`
	DoctoralEnrollment       string        `json:"doctoralEnrollment"`
	PaidStatus               string        `json:"paidStatus"`
	Salary                   Salary        `json:"salary"`
	WorkingLanguages         []string      `json:"workingLanguages"`
	SourceURL                string        `json:"sourceUrl"`
	ApplicationURL           *string       `json:"applicationUrl"`
	ApplicationMethod        string        `json:"applicationMethod"`
	ApplicationHostVerified  bool          `json:"applicationHostVerified"`
	LifecycleStatus          string        `json:"lifecycleStatus"`
	Visibility               string        `json:"visibility"`
	IsPostdoc                bool          `json:"isPostdoc"`
	City                     LocalizedText `json:"city"`
	VerifiedAt               *string       `json:"verifiedAt"`
	DataClass                string        `json:"dataClass"`
	WholeOpportunityClosed   bool          `json:"wholeOpportunityClosed"`
}

type Snapshot struct {
	GeneratedAt  string               `json:"generatedAt"`
	DataClass    string               `json:"dataClass"`
	CatalogKind  string               `json:"catalogKind"`
	Institutions []Institution        `json:"institutions"`
	Programmes   []Programme          `json:"programmes"`
	Offerings    []Offering           `json:"offerings"`
	Windows      []ApplicationWindow  `json:"windows"`
	Jobs         []ResearchJob        `json:"jobs"`
}

type WindowSummary struct {
	OpportunityStatus string
	Current           []ApplicationWindow
	Upcoming          []ApplicationWindow
	Closed            []ApplicationWindow
	All               []ApplicationWindow
}

type OfferingView struct {
	Offering    Offering
	Programme   Programme
	Institution Institution
	Windows     []ApplicationWindow
	Summary     WindowSummary
}

type JobView struct {
	Job      ResearchJob
	Employer Institution
	Windows  []ApplicationWindow
	Summary  WindowSummary
}

type FilterQuery struct {
	TeachingLanguage     *string
	IncludeJointRequired bool
	Search               string
	Degree               string
	City                 string
	Ownership            string
	ListedOnly           bool
	Status               string
	Orientation          string
	Sort                 string
	Page                 int
	PageSize             int
}

type JobFilterQuery struct {
	MasterEligible       bool
	DoctoralEnrollment   string
	WorkingLanguage      string
	Search               string
	Page                 int
	PageSize             int
}

func LoadSnapshot(path string) (*Snapshot, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var snapshot Snapshot
	if err := json.Unmarshal(raw, &snapshot); err != nil {
		return nil, err
	}
	return &snapshot, nil
}

func datePart(value string) string {
	if len(value) >= 10 {
		return value[:10]
	}
	return value
}

func EvaluateWindow(window ApplicationWindow, now time.Time) string {
	if window.ConditionalOnVacancies && window.Status == "conditional" {
		return "conditional"
	}
	loc, err := time.LoadLocation("Europe/Prague")
	if err != nil {
		loc = time.UTC
	}
	if window.Timezone != nil && *window.Timezone != "" {
		if loaded, loadErr := time.LoadLocation(*window.Timezone); loadErr == nil {
			loc = loaded
		}
	}
	today := now.In(loc).Format("2006-01-02")
	if window.DatePrecision == "month" || window.DatePrecision == "unknown" {
		return window.Status
	}
	if window.ClosesAt != nil && today > datePart(*window.ClosesAt) {
		return "closed"
	}
	if window.OpensAt != nil && today < datePart(*window.OpensAt) {
		return "upcoming"
	}
	if window.OpensAt != nil && (window.ClosesAt == nil || today <= datePart(*window.ClosesAt)) {
		return "open"
	}
	if window.OpensAt == nil && window.ClosesAt != nil {
		if today > datePart(*window.ClosesAt) {
			return "closed"
		}
		if window.Status == "open" || window.Status == "conditional" {
			return window.Status
		}
		return "unknown"
	}
	return window.Status
}

func SummarizeWindows(windows []ApplicationWindow, now time.Time, wholeClosed bool) WindowSummary {
	sorted := append([]ApplicationWindow(nil), windows...)
	sort.Slice(sorted, func(i, j int) bool {
		ai, aj := "", ""
		if sorted[i].OpensAt != nil {
			ai = *sorted[i].OpensAt
		} else if sorted[i].ClosesAt != nil {
			ai = *sorted[i].ClosesAt
		}
		if sorted[j].OpensAt != nil {
			aj = *sorted[j].OpensAt
		} else if sorted[j].ClosesAt != nil {
			aj = *sorted[j].ClosesAt
		}
		return ai < aj
	})
	if wholeClosed {
		return WindowSummary{OpportunityStatus: "closed", Closed: sorted, All: sorted}
	}
	var current, upcoming, closed []ApplicationWindow
	for _, window := range sorted {
		switch EvaluateWindow(window, now) {
		case "open", "conditional":
			current = append(current, window)
		case "upcoming":
			upcoming = append(upcoming, window)
		case "closed":
			closed = append(closed, window)
		}
	}
	if len(current) > 0 {
		return WindowSummary{OpportunityStatus: "open", Current: current, Upcoming: upcoming, Closed: closed, All: sorted}
	}
	if len(upcoming) > 0 {
		return WindowSummary{OpportunityStatus: "upcoming", Current: upcoming, Upcoming: upcoming, Closed: closed, All: sorted}
	}
	unknown := make([]ApplicationWindow, 0)
	for _, window := range sorted {
		if EvaluateWindow(window, now) == "unknown" {
			unknown = append(unknown, window)
		}
	}
	if len(unknown) > 0 {
		return WindowSummary{OpportunityStatus: "unknown", Current: unknown, Upcoming: upcoming, Closed: closed, All: sorted}
	}
	if len(sorted) > 0 {
		return WindowSummary{OpportunityStatus: "closed", Upcoming: upcoming, Closed: closed, All: sorted}
	}
	return WindowSummary{OpportunityStatus: "unknown", All: sorted}
}

func MatchesTeachingLanguage(offering Offering, choice string, includeJoint bool) bool {
	if choice == "" {
		return false
	}
	if choice == "all" {
		return true
	}
	if offering.LanguageMode == "joint_required" {
		hasEn, hasCs := false, false
		for _, code := range offering.TeachingLanguages {
			if code == "en" {
				hasEn = true
			}
			if code == "cs" {
				hasCs = true
			}
		}
		return includeJoint && hasEn && hasCs
	}
	return offering.LanguageMode == "single" && len(offering.TeachingLanguages) == 1 && offering.TeachingLanguages[0] == choice
}

func IsMasterEligible(job ResearchJob) bool {
	if job.IsPostdoc || job.MinimumDegree == "doctorate" {
		return false
	}
	if job.DoctorateRequired == nil || *job.DoctorateRequired {
		return false
	}
	if job.PaidStatus != "confirmed" {
		return false
	}
	return job.MinimumDegree == "bachelor" || job.MinimumDegree == "master"
}

func IsPublicJob(job ResearchJob, summary WindowSummary) bool {
	if job.WholeOpportunityClosed || job.Visibility != "public" {
		return false
	}
	if job.LifecycleStatus == "closed" || job.LifecycleStatus == "expired" {
		return false
	}
	return summary.OpportunityStatus != "closed"
}

func (s *Snapshot) institution(id string) (Institution, bool) {
	for _, item := range s.Institutions {
		if item.ID == id {
			return item, true
		}
	}
	return Institution{}, false
}

func (s *Snapshot) programme(id string) (Programme, bool) {
	for _, item := range s.Programmes {
		if item.ID == id {
			return item, true
		}
	}
	return Programme{}, false
}

func (s *Snapshot) windows(ownerType, ownerID string) []ApplicationWindow {
	out := make([]ApplicationWindow, 0)
	for _, window := range s.Windows {
		if window.OwnerType == ownerType && window.OwnerID == ownerID {
			out = append(out, window)
		}
	}
	return out
}

func (s *Snapshot) OfferingViews(now time.Time) []OfferingView {
	out := make([]OfferingView, 0, len(s.Offerings))
	for _, offering := range s.Offerings {
		programme, okP := s.programme(offering.ProgrammeID)
		institution, okI := s.institution(offering.InstitutionID)
		if !okP || !okI {
			continue
		}
		windows := s.windows("offering", offering.ID)
		closed := offering.LifecycleOverride != nil && *offering.LifecycleOverride == "closed"
		out = append(out, OfferingView{
			Offering:    offering,
			Programme:   programme,
			Institution: institution,
			Windows:     windows,
			Summary:     SummarizeWindows(windows, now, closed),
		})
	}
	return out
}

func (s *Snapshot) FilterOfferings(q FilterQuery, now time.Time, locale string) (needsChoice bool, total int, page []OfferingView) {
	if q.TeachingLanguage == nil {
		return true, 0, nil
	}
	if q.Page < 1 {
		q.Page = 1
	}
	if q.PageSize < 1 || q.PageSize > 100 {
		q.PageSize = 20
	}
	views := make([]OfferingView, 0)
	for _, view := range s.OfferingViews(now) {
		if !MatchesTeachingLanguage(view.Offering, *q.TeachingLanguage, q.IncludeJointRequired) {
			continue
		}
		if q.Search != "" {
			blob := strings.ToLower(strings.Join([]string{
				view.Offering.Title.Get(locale), view.Offering.Title.En, view.Institution.DisplayName.Get(locale), view.Institution.OfficialName, view.Institution.City.Get(locale),
			}, " "))
			if !strings.Contains(blob, strings.ToLower(q.Search)) {
				continue
			}
		}
		if q.Degree != "" && q.Degree != "all" && view.Offering.Degree != q.Degree {
			continue
		}
		if q.Ownership != "" && q.Ownership != "all" && view.Institution.Ownership != q.Ownership {
			continue
		}
		if q.ListedOnly && view.Institution.CscseReference.LookupStatus != "listed" {
			continue
		}
		if q.Status != "" && q.Status != "all" && view.Summary.OpportunityStatus != q.Status {
			continue
		}
		views = append(views, view)
	}
	sort.SliceStable(views, func(i, j int) bool {
		rank := map[string]int{"open": 0, "upcoming": 1, "unknown": 2, "closed": 3}
		if q.Sort == "deadline" {
			ai, aj := "9999-99-99", "9999-99-99"
			if len(views[i].Summary.Current) > 0 && views[i].Summary.Current[0].ClosesAt != nil {
				ai = *views[i].Summary.Current[0].ClosesAt
			}
			if len(views[j].Summary.Current) > 0 && views[j].Summary.Current[0].ClosesAt != nil {
				aj = *views[j].Summary.Current[0].ClosesAt
			}
			return ai < aj
		}
		if rank[views[i].Summary.OpportunityStatus] != rank[views[j].Summary.OpportunityStatus] {
			return rank[views[i].Summary.OpportunityStatus] < rank[views[j].Summary.OpportunityStatus]
		}
		return views[i].Offering.Title.Get(locale) < views[j].Offering.Title.Get(locale)
	})
	total = len(views)
	start := (q.Page - 1) * q.PageSize
	if start >= total {
		return false, total, []OfferingView{}
	}
	end := start + q.PageSize
	if end > total {
		end = total
	}
	return false, total, views[start:end]
}

func (s *Snapshot) FilterJobs(q JobFilterQuery, now time.Time, locale string) (int, []JobView) {
	if q.Page < 1 {
		q.Page = 1
	}
	if q.PageSize < 1 || q.PageSize > 100 {
		q.PageSize = 20
	}
	out := make([]JobView, 0)
	for _, job := range s.Jobs {
		employer, ok := s.institution(job.EmployerID)
		if !ok {
			continue
		}
		windows := s.windows("research_job", job.ID)
		summary := SummarizeWindows(windows, now, job.WholeOpportunityClosed)
		if !IsPublicJob(job, summary) {
			continue
		}
		if q.MasterEligible && !IsMasterEligible(job) {
			continue
		}
		if q.DoctoralEnrollment != "" && q.DoctoralEnrollment != "all" && job.DoctoralEnrollment != q.DoctoralEnrollment {
			continue
		}
		if q.WorkingLanguage != "" && q.WorkingLanguage != "all" {
			found := false
			for _, lang := range job.WorkingLanguages {
				if lang == q.WorkingLanguage {
					found = true
					break
				}
			}
			if !found {
				continue
			}
		}
		if q.Search != "" {
			blob := strings.ToLower(job.Title.Get(locale) + " " + job.Title.En + " " + employer.OfficialName)
			if !strings.Contains(blob, strings.ToLower(q.Search)) {
				continue
			}
		}
		out = append(out, JobView{Job: job, Employer: employer, Windows: windows, Summary: summary})
	}
	total := len(out)
	start := (q.Page - 1) * q.PageSize
	if start >= total {
		return total, []JobView{}
	}
	end := start + q.PageSize
	if end > total {
		end = total
	}
	return total, out[start:end]
}
