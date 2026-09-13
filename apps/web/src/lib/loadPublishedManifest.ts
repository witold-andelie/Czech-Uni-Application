import manifest from "@published/manifest.json";

export interface PublishedManifest {
  schemaVersion: number;
  policyVersion: string;
  version: string;
  publishedAt: string;
  status: string;
  counts: Record<string, number>;
  checksums: Record<string, string>;
  validation: {
    passed: boolean;
    errors: string[];
  };
}

export function loadPublishedManifest(): PublishedManifest {
  return manifest as unknown as PublishedManifest;
}
