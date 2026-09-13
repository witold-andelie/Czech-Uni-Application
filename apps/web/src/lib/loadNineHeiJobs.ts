import jobsJson from "@published/browse/nine-hei-jobs.json";
import type { HarvestedJobsSnapshot } from "./buildBrowseCatalog.ts";

export function loadNineHeiJobs(): HarvestedJobsSnapshot {
  const payload = jobsJson as HarvestedJobsSnapshot;
  return {
    generatedAt: payload.generatedAt,
    dataClass: "official_career_extract",
    jobs: payload.jobs ?? [],
    windows: payload.windows ?? [],
    evidence: payload.evidence ?? [],
  };
}
