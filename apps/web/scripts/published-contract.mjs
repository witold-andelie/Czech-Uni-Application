import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
export const ROOT = path.resolve(SCRIPT_DIR, "../../..");
export const WEB_ROOT = path.resolve(ROOT, "apps/web");
export const PUBLISHED_ROOT = path.resolve(ROOT, "data/published");
const POLICY = JSON.parse(fs.readFileSync(path.resolve(ROOT, "config/publication-policy.json"), "utf8"));

export const REQUIRED_FILES = Object.freeze([...POLICY.requiredFiles]);
export const BROWSER_ASSETS = Object.freeze([...POLICY.browserAssets]);
const LOCALES = Object.freeze([...POLICY.locales]);
const VERSION_RE = /^v\d{4}-\d{2}-\d{2}\.\d+$/;
const SHA_RE = /^sha256:[0-9a-f]{64}$/;
const LANGUAGE_RE = /^[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$/;
const SAFE_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]*$/;

function sha256(filePath) {
  return "sha256:" + crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function safeRelative(value) {
  if (typeof value !== "string" || !value || value.includes("\\") || path.posix.isAbsolute(value)) return false;
  return value.split("/").every((part) => part && part !== "." && part !== "..");
}

function contained(root, relative) {
  if (!safeRelative(relative)) throw new Error(`Unsafe snapshot path: ${JSON.stringify(relative)}`);
  const target = path.resolve(root, ...relative.split("/"));
  const prefix = root.endsWith(path.sep) ? root : root + path.sep;
  if (target !== root && !target.startsWith(prefix)) throw new Error(`Snapshot path escapes root: ${relative}`);
  return target;
}

function loadObject(root, relative, errors) {
  let target;
  try {
    target = contained(root, relative);
  } catch (error) {
    errors.push(error.message);
    return null;
  }
  if (!fs.existsSync(target) || !fs.statSync(target).isFile()) {
    errors.push(`Missing required file: ${relative}`);
    return null;
  }
  if (fs.statSync(target).size === 0) {
    errors.push(`Required file is empty: ${relative}`);
    return null;
  }
  try {
    const value = JSON.parse(fs.readFileSync(target, "utf8"));
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      errors.push(`Top-level JSON must be an object: ${relative}`);
      return null;
    }
    return value;
  } catch (error) {
    errors.push(`Invalid JSON in ${relative}: ${error.message}`);
    return null;
  }
}

function webUrl(value, httpsOnly = false) {
  if (typeof value !== "string" || !value.trim()) return false;
  try {
    const parsed = new URL(value);
    const allowed = httpsOnly ? parsed.protocol === "https:" : parsed.protocol === "http:" || parsed.protocol === "https:";
    return allowed && Boolean(parsed.hostname) && !parsed.username && !parsed.password;
  } catch {
    return false;
  }
}

function isoDateTime(value) {
  return typeof value === "string" && value.length > 0 && !Number.isNaN(Date.parse(value));
}

function uniqueIds(items, label, errors, key = "id") {
  const result = new Set();
  if (!Array.isArray(items)) {
    errors.push(`${label} must be an array`);
    return result;
  }
  items.forEach((item, index) => {
    const id = item && typeof item === "object" ? item[key] : null;
    if (typeof id !== "string" || !SAFE_ID_RE.test(id)) errors.push(`${label}[${index}].${key} is missing or unsafe`);
    else if (result.has(id)) errors.push(`Duplicate ${label} ${key}: ${id}`);
    else result.add(id);
  });
  return result;
}

function localized(value, label, errors) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    errors.push(`${label} must contain zh-CN, en and cs`);
    return;
  }
  for (const locale of LOCALES) {
    if (typeof value[locale] !== "string" || !value[locale].trim()) errors.push(`${label}.${locale} must be non-empty`);
  }
}

function urls(item, fields, label, errors, httpsOnly = false) {
  for (const field of fields) {
    if (item[field] != null && !webUrl(item[field], httpsOnly)) errors.push(`URL_INVALID: ${label}.${field} is not an allowed web URL`);
  }
}

function requireUrl(item, field, label, errors, code, httpsOnly = false) {
  const value = item[field];
  if (value == null || value === "") errors.push(`${code}: ${label}.${field} is required`);
  else if (!webUrl(value, httpsOnly)) errors.push(`URL_INVALID: ${label}.${field} is not an allowed web URL`);
}

const FACT_NORMALIZATION_VERSION = "fact-v1";
const SALARY_CURRENCIES = new Set(["CZK", "EUR", "USD", "GBP", "CHF", "PLN", "SEK", "NOK", "DKK", "CNY", "HUF"]);
const SALARY_CYCLES = new Set(["month", "year", "hour", "day", "week", "semester", "programme", "unspecified"]);
const SALARY_TAX = new Set(["gross", "net", "unknown", "unspecified"]);
const WINDOW_STATUSES = new Set(["open", "closed", "upcoming", "conditional", "unknown"]);
const DATE_PRECISIONS = new Set(["date", "datetime", "month", "unknown"]);
const ROUND_TYPES = new Set(["regular", "supplementary", "rolling", "unspecified"]);
const UNAPPROVED_PUBLICATION = new Set(["review_pending", "draft", "rejected"]);
const UNAPPROVED_TRANSLATION = new Set(["unreviewed", "stale", "missing"]);
const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
const MONTH_RE = /^(\d{4})-(\d{2})$/;
const DATETIME_RE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|[+-]\d{2}:\d{2})$/;

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]));
  }
  if (typeof value === "number" && Number.isFinite(value) && Number.isInteger(value)) return value;
  return value;
}

function canonicalJson(value) {
  return JSON.stringify(canonicalize(value));
}

function sha256Canonical(value) {
  return "sha256:" + crypto.createHash("sha256").update(canonicalJson(value), "utf8").digest("hex");
}

function translationContentHash(text) {
  const normalized = typeof text === "string" ? text.normalize("NFC") : "";
  return "sha256:" + crypto.createHash("sha256").update(normalized, "utf8").digest("hex");
}

function validCalendarDate(value) {
  if (typeof value !== "string") return false;
  const match = DATE_RE.exec(value);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const dt = new Date(Date.UTC(year, month - 1, day));
  return dt.getUTCFullYear() === year && dt.getUTCMonth() === month - 1 && dt.getUTCDate() === day;
}

function validMonth(value) {
  if (typeof value !== "string") return false;
  const match = MONTH_RE.exec(value);
  if (!match) return false;
  const month = Number(match[2]);
  return month >= 1 && month <= 12;
}

function validDatetimeWithOffset(value) {
  if (typeof value !== "string") return false;
  const match = DATETIME_RE.exec(value);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  const dt = new Date(Date.UTC(year, month - 1, day, hour, minute, second));
  return dt.getUTCFullYear() === year && dt.getUTCMonth() === month - 1 && dt.getUTCDate() === day && dt.getUTCHours() === hour && dt.getUTCMinutes() === minute && dt.getUTCSeconds() === second;
}

function validIanaTimezone(value) {
  if (typeof value !== "string" || !value.trim()) return false;
  try {
    Intl.DateTimeFormat("en-US", { timeZone: value.trim() });
    return true;
  } catch {
    return false;
  }
}

function validWindowTimestamp(value, precision) {
  if (value == null) return true;
  if (precision === "month") return validMonth(value) || validCalendarDate(value);
  if (precision === "datetime") return validDatetimeWithOffset(value);
  return validCalendarDate(value) || validDatetimeWithOffset(value);
}

function comparableDate(value) {
  if (typeof value !== "string" || !value) return null;
  if (DATE_RE.test(value)) return value;
  if (MONTH_RE.test(value)) return `${value}-01`;
  if (DATETIME_RE.test(value)) return value.slice(0, 10);
  return null;
}

function windowSignature(item) {
  return canonicalJson({
    id: item.id,
    ownerType: item.ownerType,
    ownerId: item.ownerId,
    opensAt: item.opensAt,
    closesAt: item.closesAt,
    timezone: item.timezone,
    datePrecision: item.datePrecision,
    status: item.status,
    sourceEvidenceId: item.sourceEvidenceId,
    roundType: item.roundType,
    roundNumber: item.roundNumber,
    conditionalOnVacancies: item.conditionalOnVacancies,
    applicationUrl: item.applicationUrl,
  });
}

function renderedOfferingWindows(item) {
  if (Array.isArray(item.windows) && item.windows.length) return item.windows.filter((row) => row && typeof row === "object");
  if (item.window && typeof item.window === "object") return [item.window];
  return [];
}

function canonicalJobFacts(job, windows = []) {
  const salary = job.salary && typeof job.salary === "object" ? job.salary : {};
  const owned = (windows || [])
    .filter((item) => item && item.ownerId === job.id)
    .map((item) => ({
      id: item.id,
      opensAt: item.opensAt,
      closesAt: item.closesAt,
      timezone: item.timezone,
      datePrecision: item.datePrecision,
      status: item.status,
      roundType: item.roundType,
      conditionalOnVacancies: item.conditionalOnVacancies,
    }))
    .sort((a, b) => String(a.id || "").localeCompare(String(b.id || "")));
  const languages = Array.isArray(job.workingLanguages) ? [...job.workingLanguages].sort() : job.workingLanguages;
  return {
    normalizationVersion: FACT_NORMALIZATION_VERSION,
    id: job.id,
    minimumDegree: job.minimumDegree,
    doctorateRequired: job.doctorateRequired,
    doctoralEnrollment: job.doctoralEnrollment,
    paidStatus: job.paidStatus,
    salary: {
      amount: salary.amount ?? null,
      currency: salary.currency ?? null,
      cycle: salary.cycle ?? null,
      tax: salary.tax ?? null,
      basisFte: salary.basisFte ?? null,
    },
    employmentFte: job.employmentFte ?? null,
    employmentStartsAt: job.employmentStartsAt ?? null,
    workingLanguages: languages,
    applicationMethod: job.applicationMethod ?? null,
    applicationUrl: job.applicationUrl ?? null,
    sourceUrl: job.sourceUrl ?? null,
    originalText: job.originalText ?? null,
    isPostdoc: job.isPostdoc ?? null,
    track: job.track ?? null,
    windows: owned,
  };
}

function jobFactHash(job, windows = []) {
  return sha256Canonical(canonicalJobFacts(job, windows));
}

function canonicalOfferingFacts(offering, windows = []) {
  const tuition = offering.tuition && typeof offering.tuition === "object" ? offering.tuition : {};
  const variants = (tuition.variants || [])
    .filter((item) => item && typeof item === "object")
    .map((item) => ({
      amount: item.amount ?? null,
      currency: item.currency ?? null,
      cycle: item.cycle ?? null,
      applicantScopeOriginal: item.applicantScopeOriginal ?? null,
    }))
    .sort((a, b) => String(a.currency || "").localeCompare(String(b.currency || "")) || (Number(a.amount) || 0) - (Number(b.amount) || 0) || String(a.applicantScopeOriginal || "").localeCompare(String(b.applicantScopeOriginal || "")));
  const ownedById = new Map();
  for (const item of windows || []) {
    if (!item || (item.ownerId != null && item.ownerId !== offering.id) || typeof item.id !== "string") continue;
    ownedById.set(item.id, {
      id: item.id,
      opensAt: item.opensAt,
      closesAt: item.closesAt,
      timezone: item.timezone,
      datePrecision: item.datePrecision,
      status: item.status,
      roundType: item.roundType,
      conditionalOnVacancies: item.conditionalOnVacancies,
    });
  }
  const owned = [...ownedById.values()].sort((a, b) => String(a.id || "").localeCompare(String(b.id || "")));
  const languages = Array.isArray(offering.teachingLanguages) ? [...offering.teachingLanguages].sort() : offering.teachingLanguages;
  return {
    normalizationVersion: FACT_NORMALIZATION_VERSION,
    id: offering.id,
    degree: offering.degree,
    teachingLanguages: languages,
    languageMode: offering.languageMode,
    titleOriginal: offering.titleOriginal ?? null,
    sourceLanguage: offering.sourceLanguage ?? null,
    academicYear: offering.academicYear ?? null,
    applicationTargetKind: offering.applicationTargetKind ?? null,
    applicationUrl: offering.applicationUrl ?? null,
    generalApplyPortalUrl: offering.generalApplyPortalUrl ?? null,
    officialProgrammeUrl: offering.officialProgrammeUrl || offering.languageEvidenceUrl || null,
    tuition: {
      published: tuition.published ?? null,
      amount: tuition.amount ?? null,
      currency: tuition.currency ?? null,
      cycle: tuition.cycle ?? null,
      variants,
    },
    windows: owned,
  };
}

function offeringFactHash(offering, windows = []) {
  return sha256Canonical(canonicalOfferingFacts(offering, windows));
}

function validateOfferingReview(offering, label, errors, windows, titles) {
  if (typeof offering.sourceHash !== "string" || !SHA_RE.test(offering.sourceHash)) {
    errors.push(`${label}.sourceHash must be a SHA256 value`);
    return;
  }
  const review = offering.translationReview;
  if (!review || review.sourceHash !== offering.sourceHash) {
    errors.push(`${label}.translationReview must match sourceHash`);
    return;
  }
  if (review.normalizationVersion !== FACT_NORMALIZATION_VERSION) errors.push(`REVIEW_NORMALIZATION_INVALID: ${label} review normalizationVersion is missing or stale`);
  if (!reviewerRole(review.reviewer)) errors.push(`REVIEW_REVIEWER_MISSING: ${label} review is missing reviewer identity or role`);
  if (review.factHash !== offeringFactHash(offering, windows)) errors.push(`REVIEW_FACT_HASH_MISMATCH: ${label} reviewed facts do not match the published record`);
  if (review.evidenceHash !== offering.sourceHash) errors.push(`REVIEW_EVIDENCE_HASH_MISMATCH: ${label} review evidenceHash does not match sourceHash`);
  if (!review.locales) {
    errors.push(`${label}.translationReview.locales is missing`);
    return;
  }
  for (const locale of LOCALES) {
    const item = review.locales[locale];
    if (!item || item.status !== "reviewed") errors.push(`${label} ${locale} translation is not reviewed`);
    else {
      if (item.translatedFromHash !== offering.sourceHash) errors.push(`${label} ${locale} review is stale`);
      if (!isoDateTime(item.reviewedAt)) errors.push(`${label} ${locale} reviewedAt is invalid`);
      if (item.contentHash !== translationContentHash(titles?.[locale])) errors.push(`REVIEW_TRANSLATION_HASH_MISMATCH: ${label} ${locale} translated content does not match the review`);
    }
  }
}

function reviewerRole(value) {
  if (value && typeof value === "object" && typeof value.role === "string" && value.role.trim()) return value.role.trim();
  if (typeof value === "string" && value.trim()) return value.trim();
  return null;
}

function validateWindow(item, label, errors, ownerIds, evidenceIds, expectedOwnerType) {
  const prefix = `${label} ${item.id || ""}`.trim();
  if (item.ownerType !== expectedOwnerType || !ownerIds.has(item.ownerId)) errors.push(`WINDOW_OWNER_INVALID: ${prefix} has invalid owner`);
  if (!evidenceIds.has(item.sourceEvidenceId)) errors.push(`WINDOW_EVIDENCE_MISSING: ${prefix} references missing evidence`);
  if (!WINDOW_STATUSES.has(item.status)) errors.push(`WINDOW_STATUS_INVALID: ${prefix} has invalid status`);
  const precision = DATE_PRECISIONS.has(item.datePrecision) ? item.datePrecision : "unknown";
  if (!DATE_PRECISIONS.has(item.datePrecision)) errors.push(`WINDOW_PRECISION_INVALID: ${prefix} has invalid datePrecision`);
  if (!ROUND_TYPES.has(item.roundType)) errors.push(`WINDOW_ROUND_INVALID: ${prefix} has invalid roundType`);
  if (!validIanaTimezone(item.timezone)) errors.push(`WINDOW_TIMEZONE_INVALID: ${item.timezone ? `${prefix} timezone is not a valid IANA zone` : `${prefix} has no timezone`}`);
  if (!validWindowTimestamp(item.opensAt, precision)) errors.push(`WINDOW_DATE_INVALID: ${prefix}.opensAt is not a valid calendar value`);
  if (!validWindowTimestamp(item.closesAt, precision)) errors.push(`WINDOW_DATE_INVALID: ${prefix}.closesAt is not a valid calendar value`);
  if (precision === "datetime") {
    for (const field of ["opensAt", "closesAt"]) {
      if (item[field] != null && !validDatetimeWithOffset(item[field])) errors.push(`WINDOW_DATETIME_OFFSET_REQUIRED: ${prefix}.${field} must include an explicit UTC offset`);
    }
  }
  const start = comparableDate(item.opensAt);
  const end = comparableDate(item.closesAt);
  if (start && end && start > end) errors.push(`WINDOW_DATE_ORDER: ${prefix} opens after it closes`);
}

function validateSalary(salary, label, errors) {
  if (!salary || typeof salary !== "object" || Array.isArray(salary)) {
    errors.push(`SALARY_OBJECT_INVALID: ${label}.salary must be an object`);
    return;
  }
  if (salary.amount == null) return;
  if (typeof salary.amount !== "number" || !Number.isFinite(salary.amount) || salary.amount < 0) errors.push(`SALARY_AMOUNT_INVALID: ${label}.salary.amount must be a finite nonnegative number or null`);
  if (!SALARY_CURRENCIES.has(salary.currency)) errors.push(`SALARY_CURRENCY_INVALID: ${label}.salary.currency is not a controlled currency code`);
  if (!SALARY_CYCLES.has(salary.cycle)) errors.push(`SALARY_CYCLE_INVALID: ${label}.salary.cycle is not a controlled period code`);
  if (!SALARY_TAX.has(salary.tax)) errors.push(`SALARY_TAX_INVALID: ${label}.salary.tax is not a controlled tax code`);
}

function validateCscseReference(item, ident, errors) {
  const rec = item.cscseReference;
  if (!rec || typeof rec !== "object") {
    errors.push(`CSCSE_REFERENCE_INVALID: institution ${ident} has invalid CSCSE reference status`);
    return;
  }
  const lookup = rec.lookupStatus;
  const status = item.cscseLookupStatus;
  if (!["listed", "not_found", "unverified"].includes(lookup) || !["listed", "not_found", "unverified"].includes(status)) {
    errors.push(`CSCSE_REFERENCE_INVALID: institution ${ident} has invalid CSCSE reference status`);
    return;
  }
  if (lookup !== status) errors.push(`CSCSE_STATUS_MISMATCH: institution ${ident} CSCSE lookupStatus does not match cscseLookupStatus`);
  if (rec.evidenceKind === "operator_supplied_list") {
    if (lookup === "listed" || lookup === "not_found" || status === "listed" || status === "not_found") {
      errors.push(`CSCSE_OPERATOR_AS_OFFICIAL: institution ${ident} operator list cannot be published as an official CSCSE lookup`);
    }
    if (!["listed", "absent"].includes(rec.operatorListStatus)) errors.push(`CSCSE_OPERATOR_STATUS_INVALID: institution ${ident} has invalid operatorListStatus`);
    return;
  }
  if (lookup === "listed" || lookup === "not_found") {
    if (rec.evidenceKind !== "official_lookup" || !rec.evidenceId || !rec.checkedAt) {
      errors.push(`CSCSE_OFFICIAL_WITHOUT_EVIDENCE: institution ${ident} official CSCSE status has no retrievable lookup evidence`);
    }
  }
}

export { FACT_NORMALIZATION_VERSION, jobFactHash, translationContentHash, validCalendarDate };

function validateDataset(snapshotRoot) {
  const errors = [];
  const data = Object.fromEntries(REQUIRED_FILES.map((rel) => [rel, loadObject(snapshotRoot, rel, errors)]));
  if (Object.values(data).some((value) => value == null)) return { errors, counts: {} };

  const baseline = data["msmt-hei-baseline.json"];
  const institutions = baseline.institutions;
  const institutionIds = uniqueIds(institutions, "institutions", errors);
  if (institutionIds.size === 0) errors.push("Institution baseline must not be empty");
  for (const item of Array.isArray(institutions) ? institutions : []) {
    if (!institutionIds.has(item.id)) continue;
    if (typeof item.officialName !== "string" || !item.officialName.trim()) errors.push(`institution ${item.id} has no officialName`);
    if (!["public", "private", "state", "unknown"].includes(item.ownership)) errors.push(`institution ${item.id} has invalid ownership`);
    urls(item, ["officialUrl", "officialUrlSource"], `institution ${item.id}`, errors);
    if (!item.source || !webUrl(item.source.registryUrl)) errors.push(`institution ${item.id} has no official registry evidence URL`);
    validateCscseReference(item, item.id, errors);
  }

  const portals = data["admissions/apply-portals.json"].institutions;
  const portalIds = uniqueIds(portals, "apply portals", errors, "institutionId");
  for (const id of institutionIds) if (!portalIds.has(id)) errors.push(`Apply portals missing institution: ${id}`);
  for (const id of portalIds) if (!institutionIds.has(id)) errors.push(`Apply portals reference unknown institution: ${id}`);
  for (const row of Array.isArray(portals) ? portals : []) {
    if (!portalIds.has(row.institutionId)) continue;
    if (!["e_application", "admissions_info", "missing"].includes(row.kind)) errors.push(`apply portal ${row.institutionId} has invalid kind`);
    urls(row, ["officialUrl", "applyUrl", "applyUrlEn", "admissionsUrl", "admissionsUrlEn"], `apply portal ${row.institutionId}`, errors);
    if (row.kind === "e_application" && !webUrl(row.applyUrl)) errors.push(`apply portal ${row.institutionId} is e_application without an allowed applyUrl`);
  }

  const inventory = data["browse/nine-hei-inventory.json"];
  const schoolIds = uniqueIds(inventory.schools, "inventory schools", errors);
  const inventoryRowIds = new Set();
  let inventoryOfferings = 0;
  for (const school of Array.isArray(inventory.schools) ? inventory.schools : []) {
    if (!institutionIds.has(school.id)) errors.push(`Inventory references unknown institution: ${school.id}`);
    if (!Array.isArray(school.rows)) {
      errors.push(`inventory school ${school.id} rows must be an array`);
      continue;
    }
    school.rows.forEach((row, index) => {
      inventoryOfferings += 1;
      const label = `inventory ${school.id} row ${index}`;
      if (!Array.isArray(row) || row.length !== 7) {
        errors.push(`${label} must contain exactly 7 fields`);
        return;
      }
      if (typeof row[0] !== "string" || !SAFE_ID_RE.test(row[0])) errors.push(`${label} has an unsafe id`);
      else if (inventoryRowIds.has(row[0])) errors.push(`Duplicate inventory row id: ${row[0]}`);
      else inventoryRowIds.add(row[0]);
      if (typeof row[1] !== "string" || !row[1].trim()) errors.push(`${label} has an empty title`);
      if (!["b", "m", "d", "o", "u"].includes(row[2])) errors.push(`${label} has invalid degree code`);
      if (typeof row[5] !== "string" || !LANGUAGE_RE.test(row[5])) errors.push(`${label} has invalid teaching language`);
    });
  }
  if (!inventory.counts || inventory.counts.schools !== schoolIds.size || inventory.counts.programmes !== inventoryOfferings) errors.push("Inventory embedded counts do not match actual records");
  if (schoolIds.size === 0 || inventoryOfferings === 0) errors.push("Inventory must contain at least one school and one record");

  for (const [relative, name] of [["admissions/cuni-mff-cs-tracer.json", "CUNI tracer"], ["admissions/muni-fi-tracer.json", "MUNI tracer"]]) {
    const tracer = data[relative];
    if (!institutionIds.has(tracer.institutionId)) errors.push(`${name} references unknown institution ${JSON.stringify(tracer.institutionId)}`);
    const offeringIds = uniqueIds(tracer.offerings, `${name} offerings`, errors);
    const evidenceIds = uniqueIds(tracer.evidence, `${name} evidence`, errors);
    const windowIds = uniqueIds(tracer.windows, `${name} windows`, errors);
    if (offeringIds.size === 0) errors.push(`${name} must contain at least one offering`);
    for (const item of Array.isArray(tracer.offerings) ? tracer.offerings : []) {
      if (!offeringIds.has(item.id)) continue;
      if (item.institutionId !== tracer.institutionId) errors.push(`${name} offering ${item.id} has mismatched institutionId`);
      localized(item.title, `${name} offering ${item.id}.title`, errors);
      if (!Array.isArray(item.teachingLanguages) || item.teachingLanguages.length === 0 || item.teachingLanguages.some((lang) => typeof lang !== "string" || !LANGUAGE_RE.test(lang))) errors.push(`${name} offering ${item.id} has invalid teachingLanguages`);
      urls(item, ["applicationUrl", "languageEvidenceUrl"], `${name} offering ${item.id}`, errors);
      if (item.publicationStatus !== "approved" || item.translationStatus !== "verified" || UNAPPROVED_PUBLICATION.has(item.publicationStatus) || UNAPPROVED_TRANSLATION.has(item.translationStatus)) errors.push(`TRACER_NOT_APPROVED: ${name} offering ${item.id} is not approved for publication`);
    }
    for (const item of Array.isArray(tracer.evidence) ? tracer.evidence : []) if (evidenceIds.has(item.id)) requireUrl(item, "url", `${name} evidence ${item.id}`, errors, "URL_REQUIRED_EVIDENCE");
    const topLevelById = new Map();
    for (const item of Array.isArray(tracer.windows) ? tracer.windows : []) {
      if (!windowIds.has(item.id)) continue;
      topLevelById.set(item.id, item);
      validateWindow(item, `${name} window`, errors, offeringIds, evidenceIds, "offering");
      urls(item, ["applicationUrl"], `${name} window ${item.id}`, errors);
    }
    for (const item of Array.isArray(tracer.offerings) ? tracer.offerings : []) {
      if (!offeringIds.has(item.id)) continue;
      for (const nested of renderedOfferingWindows(item)) {
        validateWindow(nested, `${name} nested window`, errors, new Set([item.id]), evidenceIds, "offering");
        urls(nested, ["applicationUrl"], `${name} nested window ${nested.id}`, errors);
        if (nested.id && topLevelById.has(nested.id) && windowSignature(nested) !== windowSignature(topLevelById.get(nested.id))) {
          errors.push(`TRACER_WINDOW_MISMATCH: ${name} offering ${item.id} nested window ${nested.id} does not match the top-level window`);
        }
      }
      const owned = (Array.isArray(tracer.windows) ? tracer.windows : []).filter((row) => row && row.ownerId === item.id);
      validateOfferingReview(item, `${name} offering ${item.id}`, errors, [...owned, ...renderedOfferingWindows(item)], item.title);
    }
  }

  const reviewedData = data["admissions/reviewed-offerings.json"];
  const reviewedIds = uniqueIds(reviewedData.offerings, "reviewed offerings", errors);
  const reviewedEvidenceIds = uniqueIds(reviewedData.evidence, "reviewed offering evidence", errors);
  const reviewedWindowIds = uniqueIds(reviewedData.windows, "reviewed offering windows", errors);
  for (const item of Array.isArray(reviewedData.evidence) ? reviewedData.evidence : []) if (reviewedEvidenceIds.has(item.id)) requireUrl(item, "url", `reviewed offering evidence ${item.id}`, errors, "URL_REQUIRED_EVIDENCE");
  const reviewedWindowRows = Array.isArray(reviewedData.windows) ? reviewedData.windows.filter((item) => item && typeof item === "object") : [];
  for (const item of reviewedWindowRows) {
    if (!reviewedWindowIds.has(item.id)) continue;
    validateWindow(item, "reviewed offering window", errors, reviewedIds, reviewedEvidenceIds, "offering");
    urls(item, ["applicationUrl"], `reviewed offering window ${item.id}`, errors);
  }
  for (const offering of Array.isArray(reviewedData.offerings) ? reviewedData.offerings : []) {
    if (!reviewedIds.has(offering.id)) continue;
    const label = `reviewed offering ${offering.id}`;
    if (!institutionIds.has(offering.institutionId)) errors.push(`${label} references unknown institution`);
    if (offering.publicationStatus !== "approved" || offering.translationStatus !== "verified") errors.push(`TRACER_NOT_APPROVED: ${label} is not approved for publication`);
    localized(offering.title, `${label}.title`, errors);
    if (!Array.isArray(offering.teachingLanguages) || offering.teachingLanguages.length === 0 || offering.teachingLanguages.some((lang) => typeof lang !== "string" || !LANGUAGE_RE.test(lang))) errors.push(`${label} has invalid teachingLanguages`);
    if (!["programme_page", "general_portal", "unknown"].includes(offering.applicationTargetKind)) errors.push(`${label} has invalid applicationTargetKind`);
    if (offering.applicationTargetKind === "general_portal") {
      if (offering.applicationUrl) errors.push(`${label} general portal must not be stored as a programme-specific applicationUrl`);
      requireUrl(offering, "generalApplyPortalUrl", label, errors, "URL_REQUIRED_APPLICATION");
    }
    requireUrl(offering, "officialProgrammeUrl", label, errors, "URL_REQUIRED_SOURCE");
    validateOfferingReview(offering, label, errors, reviewedWindowRows, offering.title);
  }
  if (!reviewedData.counts || reviewedData.counts.offerings !== reviewedIds.size) errors.push("Reviewed-offering embedded counts do not match actual records");

  const jobsData = data["browse/nine-hei-jobs.json"];
  const jobIds = uniqueIds(jobsData.jobs, "research jobs", errors);
  const jobEvidenceIds = uniqueIds(jobsData.evidence, "research job evidence", errors);
  const jobWindowIds = uniqueIds(jobsData.windows, "research job windows", errors);
  const evidenceHashById = {};
  for (const item of Array.isArray(jobsData.evidence) ? jobsData.evidence : []) {
    if (!jobEvidenceIds.has(item.id)) continue;
    requireUrl(item, "url", `research job evidence ${item.id}`, errors, "URL_REQUIRED_EVIDENCE", true);
    localized(item.note, `research job evidence ${item.id}.note`, errors);
    if (typeof item.sourceHash === "string") evidenceHashById[item.id] = item.sourceHash;
  }
  const windowRows = Array.isArray(jobsData.windows) ? jobsData.windows.filter((item) => item && typeof item === "object") : [];
  for (const item of windowRows) {
    if (!jobWindowIds.has(item.id)) continue;
    validateWindow(item, "research job window", errors, jobIds, jobEvidenceIds, "research_job");
    urls(item, ["applicationUrl"], `research job window ${item.id}`, errors, true);
  }
  for (const job of Array.isArray(jobsData.jobs) ? jobsData.jobs : []) {
    if (!jobIds.has(job.id)) continue;
    const label = `research job ${job.id}`;
    if (!institutionIds.has(job.employerId)) errors.push(`${label} references unknown employer ${JSON.stringify(job.employerId)}`);
    localized(job.title, `${label}.title`, errors);
    if (job.laboratory != null) localized(job.laboratory, `${label}.laboratory`, errors);
    if (job.publicationStatus !== "approved") errors.push(`${label} is not approved for publication`);
    if (job.translationStatus !== "verified") errors.push(`${label} translations are not verified`);
    if (typeof job.sourceHash !== "string" || !SHA_RE.test(job.sourceHash)) errors.push(`${label}.sourceHash must be a SHA256 value`);
    const evidenceId = `ev-${job.id}`;
    if (!jobEvidenceIds.has(evidenceId)) errors.push(`${label} has no matching source evidence`);
    const review = job.translationReview;
    if (!review || review.sourceHash !== job.sourceHash || !review.locales) errors.push(`${label}.translationReview must match sourceHash`);
    else {
      if (review.normalizationVersion !== FACT_NORMALIZATION_VERSION) errors.push(`REVIEW_NORMALIZATION_INVALID: ${label} review normalizationVersion is missing or stale`);
      if (!reviewerRole(review.reviewer)) errors.push(`REVIEW_REVIEWER_MISSING: ${label} review is missing reviewer identity or role`);
      if (review.factHash !== jobFactHash(job, windowRows)) errors.push(`REVIEW_FACT_HASH_MISMATCH: ${label} reviewed facts do not match the published record`);
      if (typeof review.evidenceHash !== "string" || !SHA_RE.test(review.evidenceHash)) errors.push(`REVIEW_EVIDENCE_HASH_MISMATCH: ${label} review evidenceHash is missing`);
      else if (review.evidenceHash !== job.sourceHash) errors.push(`REVIEW_EVIDENCE_HASH_MISMATCH: ${label} review evidenceHash does not match sourceHash`);
      else if (evidenceHashById[evidenceId] && review.evidenceHash !== evidenceHashById[evidenceId]) errors.push(`REVIEW_EVIDENCE_HASH_MISMATCH: ${label} evidence sourceHash does not match the review`);
      for (const locale of LOCALES) {
        const item = review.locales[locale];
        if (!item || item.status !== "reviewed") errors.push(`${label} ${locale} translation is not reviewed`);
        else {
          if (item.translatedFromHash !== job.sourceHash) errors.push(`${label} ${locale} review is stale`);
          if (!isoDateTime(item.reviewedAt)) errors.push(`${label} ${locale} reviewedAt is invalid`);
          if (item.contentHash !== translationContentHash(job.title?.[locale])) errors.push(`REVIEW_TRANSLATION_HASH_MISMATCH: ${label} ${locale} translated content does not match the review`);
        }
      }
    }
    if (!["bachelor", "master", "doctorate", "other", "unknown"].includes(job.minimumDegree)) errors.push(`${label} has invalid minimumDegree`);
    if (typeof job.doctorateRequired !== "boolean") errors.push(`${label}.doctorateRequired must be a strict boolean`);
    if (!["required", "optional", "not_required", "unspecified"].includes(job.doctoralEnrollment)) errors.push(`${label} has invalid doctoralEnrollment`);
    if (job.paidStatus !== "confirmed") errors.push(`${label} lacks confirmed compensation evidence`);
    // A67/A68: fundingType is optional for snapshots predating the field but must use the controlled vocabulary once present.
    if (job.fundingType != null && !["employment", "stipend", "mixed", "unknown"].includes(job.fundingType)) errors.push(`${label} has invalid fundingType`);
    if (job.applicationHostVerified !== true) errors.push(`${label} application host is not verified`);
    if (!["open", "closed", "expired", "unavailable", "unknown"].includes(job.lifecycleStatus)) errors.push(`${label} has invalid lifecycleStatus`);
    if (!["public", "archived"].includes(job.visibility)) errors.push(`${label} has invalid published visibility`);
    if (job.visibility === "public" && (job.wholeOpportunityClosed === true || ["closed", "expired"].includes(job.lifecycleStatus))) errors.push(`${label} is closed or expired but still public`);
    if (!Array.isArray(job.workingLanguages) || job.workingLanguages.length === 0 || job.workingLanguages.some((lang) => typeof lang !== "string" || !LANGUAGE_RE.test(lang))) errors.push(`${label} has invalid workingLanguages`);
    requireUrl(job, "sourceUrl", label, errors, "URL_REQUIRED_SOURCE", true);
    if (job.applicationMethod === "official_instructions") urls(job, ["applicationUrl"], label, errors, true);
    else requireUrl(job, "applicationUrl", label, errors, "URL_REQUIRED_APPLICATION", true);
    validateSalary(job.salary, label, errors);
    if (job.salary && typeof job.salary === "object" && !Array.isArray(job.salary) && job.salary.basisFte != null && (typeof job.salary.basisFte !== "number" || !Number.isFinite(job.salary.basisFte) || job.salary.basisFte <= 0 || job.salary.basisFte > 1)) errors.push(`${label}.salary.basisFte must be null or a number in (0, 1]`);
    if (job.employmentFte != null && (typeof job.employmentFte !== "number" || !Number.isFinite(job.employmentFte) || job.employmentFte <= 0 || job.employmentFte > 1)) errors.push(`${label}.employmentFte must be null or a number in (0, 1]`);
    if (job.employmentStartsAt != null && !validCalendarDate(job.employmentStartsAt)) errors.push(`EMPLOYMENT_DATE_INVALID: ${label}.employmentStartsAt must be null or YYYY-MM-DD`);
  }
  const skippedCount = Array.isArray(jobsData.skipped) ? jobsData.skipped.length : 0;
  if (!jobsData.counts || jobsData.counts.jobs !== jobIds.size || jobsData.counts.skipped !== skippedCount) errors.push("Research-job embedded counts do not match actual records");

  const coordinates = data["browse/hei-coordinates.json"].institutions;
  const coordinateIds = uniqueIds(coordinates, "institution coordinates", errors, "institutionId");
  if (coordinateIds.size !== institutionIds.size || [...coordinateIds].some((id) => !institutionIds.has(id))) errors.push("Coordinate institution IDs must exactly match the official baseline");
  for (const item of Array.isArray(coordinates) ? coordinates : []) {
    if (typeof item.lat !== "number" || item.lat < -90 || item.lat > 90) errors.push(`coordinates ${item.institutionId} has invalid latitude`);
    if (typeof item.lon !== "number" || item.lon < -180 || item.lon > 180) errors.push(`coordinates ${item.institutionId} has invalid longitude`);
  }
  if (!data["browse/czechia-outline.json"].geojson || typeof data["browse/czechia-outline.json"].geojson !== "object") errors.push("Czechia outline has no GeoJSON object");
  for (const field of ["regions", "cities"]) if (!Array.isArray(data["browse/czechia-basemap.json"][field]) || data["browse/czechia-basemap.json"][field].length === 0) errors.push(`Czechia basemap ${field} must be a non-empty array`);

  return { errors, counts: { institutions: institutionIds.size, portals: portalIds.size, inventoryOfferings, inventorySchools: schoolIds.size, jobs: jobIds.size, coordinates: coordinateIds.size, reviewedOfferings: reviewedIds.size } };
}

export function selectActiveSnapshot({ root = ROOT, version = process.env.CZECH_UNI_PUBLISHED_VERSION } = {}) {
  const publishedRoot = path.resolve(root, "data/published");
  let activeVersion = version;
  let pointer = null;
  if (!activeVersion) {
    const pointerPath = path.resolve(publishedRoot, "current.json");
    if (!fs.existsSync(pointerPath)) throw new Error("data/published/current.json is missing");
    pointer = JSON.parse(fs.readFileSync(pointerPath, "utf8"));
    activeVersion = pointer.activeVersion;
    if (pointer.snapshotDir !== `snapshots/${activeVersion}`) throw new Error("current.json snapshotDir does not match activeVersion");
  }
  if (typeof activeVersion !== "string" || !VERSION_RE.test(activeVersion)) throw new Error("Active publication version is invalid");
  const snapshotRoot = contained(publishedRoot, `snapshots/${activeVersion}`);
  if (!fs.existsSync(snapshotRoot) || !fs.statSync(snapshotRoot).isDirectory()) throw new Error(`Active immutable snapshot does not exist: snapshots/${activeVersion}`);
  return { root, publishedRoot, version: activeVersion, snapshotRoot, pointer };
}

export function validateSnapshot(selection) {
  const { snapshotRoot, version } = selection;
  const { errors, counts } = validateDataset(snapshotRoot);
  const manifest = loadObject(snapshotRoot, "manifest.json", errors);
  if (!manifest) return { errors, counts, manifest: null, passed: false };
  if (manifest.version !== version || path.basename(snapshotRoot) !== version || !VERSION_RE.test(String(manifest.version || ""))) errors.push("Manifest version does not match the selected immutable snapshot");
  if (manifest.schemaVersion !== POLICY.schemaVersion) errors.push("Manifest schemaVersion does not match publication policy");
  if (manifest.policyVersion !== POLICY.policyVersion) errors.push("Manifest policyVersion does not match publication policy");
  if (manifest.status !== "published") errors.push("Manifest status must be published");
  if (!isoDateTime(manifest.publishedAt)) errors.push("Manifest publishedAt is invalid");
  if (!manifest.validation || manifest.validation.passed !== true || !Array.isArray(manifest.validation.errors) || manifest.validation.errors.length !== 0) errors.push("Manifest validation must be the strict successful result");
  if (JSON.stringify(manifest.counts) !== JSON.stringify(counts)) errors.push(`Manifest counts do not match actual records: ${JSON.stringify(manifest.counts)} != ${JSON.stringify(counts)}`);
  const checksumKeys = manifest.checksums && typeof manifest.checksums === "object" ? Object.keys(manifest.checksums).sort() : [];
  if (JSON.stringify(checksumKeys) !== JSON.stringify([...REQUIRED_FILES].sort())) errors.push("Manifest checksums must contain exactly the required file set");
  else {
    for (const relative of REQUIRED_FILES) {
      const expected = manifest.checksums[relative];
      if (typeof expected !== "string" || !SHA_RE.test(expected)) errors.push(`Manifest checksum is invalid for ${relative}`);
      else {
        const actual = sha256(contained(snapshotRoot, relative));
        if (actual !== expected) errors.push(`Checksum mismatch for ${relative}: ${actual} != ${expected}`);
      }
    }
  }
  // §15: a release manifest carries the generation triple. When present it must
  // match the active pointer so reports and releases never come from different
  // generations. Legacy snapshots without the triple stay readable.
  if (manifest.candidateGenerationId != null || manifest.sourceRunSetDigest != null) {
    if (typeof manifest.candidateGenerationId !== "string" || !manifest.candidateGenerationId.startsWith("cg-")) errors.push("Release candidateGenerationId is invalid");
    if (typeof manifest.sourceRunSetDigest !== "string" || !SHA_RE.test(manifest.sourceRunSetDigest)) errors.push("Release sourceRunSetDigest must be a sha256 value");
    if (!isoDateTime(manifest.generatedAt)) errors.push("Release generatedAt must be an ISO date-time");
    const pointerGen = selection.pointer ? selection.pointer.candidateGenerationId : undefined;
    const pointerDigest = selection.pointer ? selection.pointer.sourceRunSetDigest : undefined;
    if (pointerGen !== undefined && pointerGen !== manifest.candidateGenerationId) errors.push("Pointer candidateGenerationId does not match the sealed release manifest");
    if (pointerDigest !== undefined && pointerDigest !== manifest.sourceRunSetDigest) errors.push("Pointer sourceRunSetDigest does not match the sealed release manifest");
  }
  return { errors, counts, manifest, passed: errors.length === 0 };
}

export function prepareBrowserAssets(selection, { webRoot = WEB_ROOT } = {}) {
  const targetRoot = path.resolve(webRoot, ".generated/public", selection.version);
  for (const relative of BROWSER_ASSETS) {
    const source = contained(selection.snapshotRoot, relative);
    const target = contained(targetRoot, `data/published/${selection.version}/${relative}`);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    if (!fs.existsSync(target) || sha256(target) !== sha256(source)) {
      const temporary = `${target}.tmp.${process.pid}.${crypto.randomUUID()}`;
      fs.copyFileSync(source, temporary);
      fs.renameSync(temporary, target);
    }
  }
  const assetManifestPath = contained(targetRoot, `data/published/${selection.version}/asset-manifest.json`);
  fs.mkdirSync(path.dirname(assetManifestPath), { recursive: true });
  fs.writeFileSync(assetManifestPath, JSON.stringify({ version: selection.version, assets: BROWSER_ASSETS }, null, 2) + "\n");
  copySafetyOverlay(selection.publishedRoot, targetRoot);
  return targetRoot;
}

export function copySafetyOverlay(publishedRoot, targetRoot) {
  const publicCopy = path.resolve(publishedRoot, "safety-status.json");
  const pointerPath = path.resolve(publishedRoot, "safety", "current.json");
  let source = publicCopy;
  if (fs.existsSync(pointerPath)) {
    try {
      const pointer = JSON.parse(fs.readFileSync(pointerPath, "utf8"));
      if (pointer && typeof pointer.generationDir === "string") {
        const generationPath = contained(path.resolve(publishedRoot, "safety"), pointer.generationDir);
        if (fs.existsSync(generationPath)) source = generationPath;
      }
    } catch {
      /* keep public copy */
    }
  }
  const target = path.resolve(targetRoot, "data", "safety-status.json");
  fs.mkdirSync(path.dirname(target), { recursive: true });
  if (fs.existsSync(source)) {
    fs.copyFileSync(source, target);
  } else {
    fs.writeFileSync(
      target,
      JSON.stringify(
        {
          schemaVersion: 1,
          generationId: "s2026-09-12.0",
          publishedAt: "2026-09-12T00:00:00Z",
          sourceCheckedAt: null,
          statusPublishedAt: "2026-09-12T00:00:00Z",
          cacheMaxAgeSeconds: 60,
          propagationTargetSeconds: 300,
          entities: [],
        },
        null,
        2,
      ) + "\n",
    );
  }
}

export { POLICY };
