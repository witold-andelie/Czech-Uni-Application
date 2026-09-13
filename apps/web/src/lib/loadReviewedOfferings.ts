import reviewedJson from "@published/admissions/reviewed-offerings.json";
import type { ReviewedAdmissionsSnapshot } from "./buildBrowseCatalog.ts";

export function loadReviewedOfferings(): ReviewedAdmissionsSnapshot {
  const payload = reviewedJson as ReviewedAdmissionsSnapshot;
  return {
    generatedAt: payload.generatedAt,
    offerings: payload.offerings ?? [],
    windows: payload.windows ?? [],
    evidence: payload.evidence ?? [],
  };
}
