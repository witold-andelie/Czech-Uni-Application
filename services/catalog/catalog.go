package catalog

import (
	"encoding/json"
	"os"
	"sort"
	"strings"
	"time"
	"unicode"

	"golang.org/x/text/collate"
	"golang.org/x/text/language"
	"golang.org/x/text/unicode/norm"
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
	ID                       string         `json:"id"`
	EmployerID               string         `json:"employerId"`
	Title                    LocalizedText  `json:"title"`
	Laboratory               *LocalizedText `json:"laboratory"`
	MinimumDegree            string         `json:"minimumDegree"`
	DoctorateRequired        *bool          `json:"doctorateRequired"`
	DoctoralEnrollment       string         `json:"doctoralEnrollment"`
	PaidStatus               string         `json:"paidStatus"`
	Salary                   Salary         `json:"salary"`
	EmploymentFte            *float64       `json:"employmentFte"`
	EmploymentStartsAt       *string        `json:"employmentStartsAt"`
	WorkingLanguages         []string       `json:"workingLanguages"`
	SourceURL                string         `json:"sourceUrl"`
	ApplicationURL           *string        `json:"applicationUrl"`
	ApplicationMethod        string         `json:"applicationMethod"`
	ApplicationHostVerified  bool           `json:"applicationHostVerified"`
	LifecycleStatus          string         `json:"lifecycleStatus"`
	Visibility               string         `json:"visibility"`
	IsPostdoc                bool           `json:"isPostdoc"`
	Track                    string         `json:"track,omitempty"`
	City                     LocalizedText  `json:"city"`
	SourceLanguage           *string        `json:"sourceLanguage"`
	RoleSummary              *LocalizedText `json:"roleSummary"`
	QualificationEvidence    *LocalizedText `json:"qualificationEvidence"`
	ApplicationMaterials     *LocalizedText `json:"applicationMaterials"`
	VerifiedAt               *string        `json:"verifiedAt"`
	FactsReviewedAt          *string        `json:"factsReviewedAt"`
	DataClass                string         `json:"dataClass"`
	WholeOpportunityClosed   bool           `json:"wholeOpportunityClosed"`
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
	OpportunityStatus string              `json:"opportunityStatus"`
	Current           []ApplicationWindow `json:"current"`
	Upcoming          []ApplicationWindow `json:"upcoming"`
	Closed            []ApplicationWindow `json:"closed"`
	All               []ApplicationWindow `json:"all"`
}

type OfferingView struct {
	Offering    Offering           `json:"offering"`
	Programme   Programme          `json:"programme"`
	Institution Institution        `json:"institution"`
	Windows     []ApplicationWindow `json:"windows"`
	Summary     WindowSummary      `json:"summary"`
}

type JobView struct {
	Job      ResearchJob        `json:"job"`
	Employer Institution        `json:"employer"`
	Windows  []ApplicationWindow `json:"windows"`
	Summary  WindowSummary      `json:"summary"`
}

type FilterQuery struct {
	TeachingLanguage     *string
	IncludeJointRequired bool
	Search               string
	Degree               string
	City                 string
	InstitutionID        string
	Ownership            string
	ListedOnly           bool
	Status               string
	Orientation          string
	Sort                 string
	Page                 int
	PageSize             int
}

type JobFilterQuery struct {
	MasterEligible     *bool
	Track              string
	DoctoralEnrollment string
	WorkingLanguage    string
	Search             string
	Page               int
	PageSize           int
}

func Bool(v bool) *bool {
	return &v
}

func masterEligibleEnabled(q JobFilterQuery) bool {
	if q.MasterEligible == nil {
		return true
	}
	return *q.MasterEligible
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

func foldText(value string) string {
	decomposed := norm.NFD.String(strings.ToLower(strings.TrimSpace(value)))
	var b strings.Builder
	for _, r := range decomposed {
		if unicode.Is(unicode.Mn, r) {
			continue
		}
		b.WriteRune(r)
	}
	return b.String()
}

func datePart(value string) string {
	if len(value) >= 10 {
		return value[:10]
	}
	return value
}

func windowLocation(window ApplicationWindow) *time.Location {
	loc, err := time.LoadLocation("Europe/Prague")
	if err != nil {
		loc = time.UTC
	}
	if window.Timezone != nil && *window.Timezone != "" {
		if loaded, loadErr := time.LoadLocation(*window.Timezone); loadErr == nil {
			loc = loaded
		}
	}
	return loc
}

func parseInstant(value string, loc *time.Location) (time.Time, bool) {
	if t, err := time.Parse(time.RFC3339, value); err == nil {
		return t, true
	}
	if t, err := time.ParseInLocation("2006-01-02T15:04:05", value, loc); err == nil {
		return t, true
	}
	if t, err := time.ParseInLocation("2006-01-02", value, loc); err == nil {
		return t, true
	}
	return time.Time{}, false
}

func isPastClose(window ApplicationWindow, now time.Time, loc *time.Location, today string) bool {
	if window.ClosesAt == nil {
		return false
	}
	if window.DatePrecision == "datetime" {
		if t, ok := parseInstant(*window.ClosesAt, loc); ok {
			return now.After(t)
		}
	}
	if window.DatePrecision == "date" {
		return today > datePart(*window.ClosesAt)
	}
	return false
}

func isBeforeOpen(window ApplicationWindow, now time.Time, loc *time.Location, today string) bool {
	if window.OpensAt == nil {
		return false
	}
	if window.DatePrecision == "datetime" {
		if t, ok := parseInstant(*window.OpensAt, loc); ok {
			return now.Before(t)
		}
	}
	if window.DatePrecision == "date" {
		return today < datePart(*window.OpensAt)
	}
	return false
}

func EvaluateWindow(window ApplicationWindow, now time.Time) string {
	loc := windowLocation(window)
	today := now.In(loc).Format("2006-01-02")
	if window.Status == "closed" {
		return "closed"
	}
	if window.ConditionalOnVacancies && window.Status == "conditional" {
		if isPastClose(window, now, loc, today) {
			return "closed"
		}
		return "conditional"
	}
	if window.DatePrecision == "month" || window.DatePrecision == "unknown" {
		return window.Status
	}
	if isPastClose(window, now, loc, today) {
		return "closed"
	}
	if window.OpensAt == nil {
		if window.Status == "conditional" {
			return "conditional"
		}
		return "unknown"
	}
	if isBeforeOpen(window, now, loc, today) {
		return "upcoming"
	}
	if window.Status == "conditional" {
		return "conditional"
	}
	return "open"
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
	open := []ApplicationWindow{}
	conditional := []ApplicationWindow{}
	upcoming := []ApplicationWindow{}
	closed := []ApplicationWindow{}
	for _, window := range sorted {
		switch EvaluateWindow(window, now) {
		case "open":
			open = append(open, window)
		case "conditional":
			conditional = append(conditional, window)
		case "upcoming":
			upcoming = append(upcoming, window)
		case "closed":
			closed = append(closed, window)
		}
	}
	if len(open) > 0 {
		return WindowSummary{OpportunityStatus: "open", Current: open, Upcoming: upcoming, Closed: closed, All: sorted}
	}
	if len(conditional) > 0 {
		return WindowSummary{OpportunityStatus: "conditional", Current: conditional, Upcoming: upcoming, Closed: closed, All: sorted}
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

func JobOpportunityClosed(job ResearchJob) bool {
	return job.WholeOpportunityClosed || job.LifecycleStatus == "closed" || job.LifecycleStatus == "expired"
}

func JobTrackOf(job ResearchJob) string {
	if job.Track != "" {
		return job.Track
	}
	if job.IsPostdoc {
		return "postdoc"
	}
	if job.MinimumDegree == "bachelor" {
		return "assistant"
	}
	return "post_master"
}

func IsPublicJob(job ResearchJob, summary WindowSummary) bool {
	if JobOpportunityClosed(job) || job.Visibility != "public" {
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
	q.Page, q.PageSize = clampPaging(q.Page, q.PageSize)
	views := make([]OfferingView, 0)
	for _, view := range s.OfferingViews(now) {
		if !MatchesTeachingLanguage(view.Offering, *q.TeachingLanguage, q.IncludeJointRequired) {
			continue
		}
		if q.Search != "" {
			blob := foldText(strings.Join([]string{
				view.Offering.Title.Get(locale), view.Offering.Title.En, view.Offering.Field.Get(locale), view.Institution.DisplayName.Get(locale), view.Institution.OfficialName, view.Institution.City.Get(locale),
			}, " "))
			if !strings.Contains(blob, foldText(q.Search)) {
				continue
			}
		}
		if q.Degree != "" && q.Degree != "all" && view.Offering.Degree != q.Degree {
			continue
		}
		if q.City != "" && q.City != "all" && view.Institution.City.En != q.City {
			continue
		}
		if q.InstitutionID != "" && q.InstitutionID != "all" && view.Offering.InstitutionID != q.InstitutionID {
			continue
		}
		if q.Ownership != "" && q.Ownership != "all" && view.Institution.Ownership != q.Ownership {
			continue
		}
		if q.ListedOnly && view.Institution.CscseReference.LookupStatus != "listed" {
			continue
		}
		if q.Orientation != "" && q.Orientation != "all" && view.Programme.Orientation != q.Orientation {
			continue
		}
		if q.Status != "" && q.Status != "all" && view.Summary.OpportunityStatus != q.Status {
			continue
		}
		views = append(views, view)
	}
	collator := titleCollator(locale)
	sort.SliceStable(views, func(i, j int) bool {
		rank := map[string]int{"open": 0, "conditional": 1, "upcoming": 2, "unknown": 3, "closed": 4}
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
		return collator.CompareString(views[i].Offering.Title.Get(locale), views[j].Offering.Title.Get(locale)) < 0
	})
	total = len(views)
	start, end, empty := slicePage(q.Page, q.PageSize, total)
	if empty {
		return false, total, []OfferingView{}
	}
	return false, total, views[start:end]
}

func titleCollator(locale string) *collate.Collator {
	tag := language.English
	switch locale {
	case "zh-CN":
		tag = language.SimplifiedChinese
	case "cs":
		tag = language.Czech
	}
	return collate.New(tag)
}

func clampPaging(page, pageSize int) (int, int) {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 {
		pageSize = 20
	}
	if pageSize > 100 {
		pageSize = 100
	}
	return page, pageSize
}

func slicePage(page, pageSize, total int) (start, end int, empty bool) {
	if page > 1 && pageSize > 0 && page-1 > (1<<30)/pageSize {
		return 0, 0, true
	}
	start = (page - 1) * pageSize
	if start < 0 || start >= total {
		return 0, 0, true
	}
	end = start + pageSize
	if end > total {
		end = total
	}
	return start, end, false
}

func (s *Snapshot) FilterJobs(q JobFilterQuery, now time.Time, locale string) (int, []JobView) {
	q.Page, q.PageSize = clampPaging(q.Page, q.PageSize)
	out := make([]JobView, 0)
	for _, job := range s.Jobs {
		employer, ok := s.institution(job.EmployerID)
		if !ok {
			continue
		}
		windows := s.windows("research_job", job.ID)
		summary := SummarizeWindows(windows, now, JobOpportunityClosed(job))
		if !IsPublicJob(job, summary) {
			continue
		}
		track := q.Track
		if track == "" {
			if masterEligibleEnabled(q) {
				track = "master_eligible"
			} else {
				track = "all"
			}
		}
		if track == "master_eligible" && !IsMasterEligible(job) {
			continue
		}
		if track == "assistant" && JobTrackOf(job) != "assistant" {
			continue
		}
		if track == "post_master" && JobTrackOf(job) != "post_master" {
			continue
		}
		if track == "postdoc" && !job.IsPostdoc && JobTrackOf(job) != "postdoc" {
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
			blob := foldText(job.Title.Get(locale) + " " + job.Title.En + " " + employer.DisplayName.Get(locale) + " " + employer.OfficialName)
			if !strings.Contains(blob, foldText(q.Search)) {
				continue
			}
		}
		out = append(out, JobView{Job: job, Employer: employer, Windows: windows, Summary: summary})
	}
	total := len(out)
	start, end, empty := slicePage(q.Page, q.PageSize, total)
	if empty {
		return total, []JobView{}
	}
	return total, out[start:end]
}
