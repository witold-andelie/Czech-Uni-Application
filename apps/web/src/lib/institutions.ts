import type { BaselineInstitution } from "./loadBaseline.ts";
import { cityFromBaseline } from "./mergeBrowseCatalog.ts";
import type { UiLocale } from "./types.ts";

export interface InstitutionQuery {
  search: string;
  city: string | "all";
  ownership: "all" | "public" | "private";
  cscse: "all" | "listed" | "not_found" | "operator_listed";
}

export function operatorListStatus(item: BaselineInstitution): "listed" | "absent" {
  const status = item.cscseReference?.operatorListStatus;
  if (status === "listed" || status === "absent") return status;
  return "absent";
}

export function defaultInstitutionQuery(): InstitutionQuery {
  return { search: "", city: "all", ownership: "all", cscse: "all" };
}

export function foldText(value: string): string {
  return value.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

/**
 * A71: reviewed institution aliases keyed by baseline ID. Only official
 * abbreviations and established names are listed; a query matches an alias by
 * whole-phrase equality after folding, never by arbitrary substring, so short
 * or ambiguous codes cannot leak into unrelated matches.
 */
export const INSTITUTION_ALIASES: Record<string, string[]> = {
  "msmt-vs_11000": ["CUNI", "UK", "Charles University", "Charles University in Prague", "Univerzita Karlova", "查理大学", "布拉格查理大学"],
  "msmt-vs_14000": ["MUNI", "MU", "Masaryk University", "Masarykova univerzita", "马萨里克大学", "布尔诺马萨里克大学"],
  "msmt-vs_21000": ["CTU", "ČVUT", "CVUT", "Czech Technical University in Prague", "České vysoké učení technické v Praze", "布拉格捷克理工大学"],
  "msmt-vs_22000": ["VŠCHT", "VSCHT", "UCT Prague", "University of Chemistry and Technology Prague", "布拉格化工大学"],
  "msmt-vs_26000": ["VUT", "BUT", "Brno University of Technology", "Vysoké učení technické v Brně", "布尔诺理工大学"],
  "msmt-vs_27000": ["VŠB-TUO", "VSB-TUO", "VŠB", "Technical University of Ostrava", "俄斯特拉发技术大学"],
  "msmt-vs_31000": ["VŠE", "VSE", "Prague University of Economics and Business", "Vysoká škola ekonomická v Praze", "布拉格经济大学"],
  "msmt-vs_12000": ["JCU", "University of South Bohemia", "Jihočeská univerzita v Českých Budějovicích", "南波希米亚大学"],
  "msmt-vs_15000": ["UPOL", "Palacký University Olomouc", "Univerzita Palackého v Olomouci", "帕拉茨基大学"],
  "msmt-vs_17000": ["OSU", "University of Ostrava", "Ostravská univerzita", "俄斯特拉发大学"],
  "msmt-vs_18000": ["UHK", "University of Hradec Králové", "Univerzita Hradec Králové", "赫拉德茨-克拉洛韦大学"],
  "msmt-vs_19000": ["SU", "Silesian University in Opava", "Slezská univerzita v Opavě", "奥帕瓦西里西亚大学"],
  "msmt-vs_23000": ["ZČU", "ZCU", "University of West Bohemia", "Západočeská univerzita v Plzni", "西波希米亚大学"],
  "msmt-vs_24000": ["TUL", "Technical University of Liberec", "Technická univerzita v Liberci", "利贝雷茨技术大学"],
  "msmt-vs_25000": ["UPCE", "University of Pardubice", "Univerzita Pardubice", "帕尔杜比采大学"],
  "msmt-vs_28000": ["UTB", "Tomas Bata University in Zlín", "Univerzita Tomáše Bati ve Zlíně", "托马斯·巴塔大学"],
  "msmt-vs_41000": ["CZU", "ČZU", "CULS", "Czech University of Life Sciences Prague", "Česká zemědělská univerzita v Praze", "捷克布拉格生命科学大学", "捷克生命科学大学"],
  "msmt-vs_43000": ["MENDELU", "Mendel University in Brno", "Mendelova univerzita v Brně", "孟德尔大学"],
  "msmt-vs_16000": ["VETUNI", "Veterinární univerzita Brno", "University of Veterinary Sciences Brno", "布尔诺兽医大学"],
};

export function institutionAliases(institutionId: string): string[] {
  return (INSTITUTION_ALIASES[institutionId] ?? []).map((alias) => foldText(alias));
}

export function institutionSearchBlob(item: BaselineInstitution): string {
  const rec = item.cscseReference;
  return [
    item.officialName,
    item.officialNameEn ?? "",
    item.msmtCode,
    item.region,
    item.seat ?? "",
    rec?.listedNameZh ?? "",
    rec?.listedNameEn ?? "",
    rec?.officialMatchedName ?? "",
  ].join(" ");
}

export function matchesInstitutionQuery(item: BaselineInstitution, query: InstitutionQuery): boolean {
  if (query.ownership !== "all" && item.ownership !== query.ownership) return false;
  if (query.cscse === "operator_listed" && operatorListStatus(item) !== "listed") return false;
  if ((query.cscse === "listed" || query.cscse === "not_found") && item.cscseLookupStatus !== query.cscse) return false;
  if (query.city && query.city !== "all" && cityFromBaseline(item).en !== query.city) return false;
  const needle = foldText(query.search.trim());
  if (!needle) return true;
  const haystack = foldText(institutionSearchBlob(item));
  return needle.split(/\s+/).every((token) => haystack.includes(token));
}

export function uniqueBaselineCities(items: BaselineInstitution[], locale: UiLocale): { value: string; label: string }[] {
  const seen = new Map<string, string>();
  for (const item of items) {
    const city = cityFromBaseline(item);
    if (!seen.has(city.en)) seen.set(city.en, city[locale]);
  }
  return [...seen.entries()].map(([value, label]) => ({ value, label })).sort((a, b) => a.label.localeCompare(b.label, locale));
}

export function institutionCityRank(item: BaselineInstitution): number {
  const seat = foldText(item.seat ?? "");
  const region = foldText(item.region ?? "");
  if (region === "praha" || seat.includes("praha")) return 0;
  if (seat.includes("brno")) return 1;
  if (seat.includes("olomouc")) return 2;
  if (seat.includes("ostrava")) return 3;
  return 4;
}

export function compareDirectoryInstitutions(a: BaselineInstitution, b: BaselineInstitution): number {
  const listed = Number(operatorListStatus(a) !== "listed") - Number(operatorListStatus(b) !== "listed");
  if (listed !== 0) return listed;
  const city = institutionCityRank(a) - institutionCityRank(b);
  if (city !== 0) return city;
  return foldText(a.officialName).localeCompare(foldText(b.officialName), "cs");
}

export function filterBaselineInstitutions(
  items: BaselineInstitution[],
  query: InstitutionQuery,
): BaselineInstitution[] {
  return items.filter((item) => matchesInstitutionQuery(item, query)).sort(compareDirectoryInstitutions);
}

export function institutionQueryFromSearch(search: string): InstitutionQuery {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const ownership = params.get("ownership");
  const cscse = params.get("cscse");
  const city = params.get("city");
  return {
    search: params.get("q") ?? "",
    city: city && city !== "all" ? city : "all",
    ownership: ownership === "public" || ownership === "private" ? ownership : "all",
    cscse: cscse === "listed" || cscse === "not_found" || cscse === "operator_listed" ? cscse : "all",
  };
}

export function searchFromInstitutionQuery(query: InstitutionQuery): string {
  const params = new URLSearchParams();
  if (query.search.trim()) params.set("q", query.search.trim());
  if (query.city && query.city !== "all") params.set("city", query.city);
  if (query.ownership !== "all") params.set("ownership", query.ownership);
  if (query.cscse !== "all") params.set("cscse", query.cscse);
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function institutionDisplayName(item: BaselineInstitution, locale: "zh-CN" | "en" | "cs"): string {
  const rec = item.cscseReference;
  if (locale === "zh-CN") return rec?.listedNameZh || item.officialName;
  if (locale === "en") return item.officialNameEn || rec?.listedNameEn || item.officialName;
  return item.officialName;
}
