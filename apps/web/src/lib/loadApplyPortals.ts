import portalsJson from "@published/admissions/apply-portals.json";

export interface ApplyPortal {
  institutionId: string;
  msmtCode: string;
  officialName: string;
  officialUrl: string | null;
  applyUrl: string | null;
  applyUrlEn: string | null;
  admissionsUrl: string | null;
  admissionsUrlEn: string | null;
  kind: "e_application" | "admissions_info" | "missing";
  checkedAt: string;
}

export interface ApplyPortalSnapshot {
  generatedAt: string;
  catalogKind: "tracer_not_published";
  institutions: ApplyPortal[];
}

const snapshot = portalsJson as ApplyPortalSnapshot;

export function loadApplyPortals(): ApplyPortalSnapshot {
  return snapshot;
}

export function findApplyPortal(institutionId: string): ApplyPortal | null {
  return snapshot.institutions.find((item) => item.institutionId === institutionId) ?? null;
}

export function portalHasReachableLink(portal: ApplyPortal | null): boolean {
  if (!portal) return false;
  return Boolean(portal.applyUrl || portal.applyUrlEn || portal.admissionsUrl || portal.admissionsUrlEn);
}
