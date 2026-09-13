import type { LocalizedText, Offering, UiLocale } from "./types";

/** UNESCO ISCED-F 2013 broad fields. Codes come from the MŠMT register, not invented groups. */
export const ISCED_BROAD_ORDER = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "00"] as const;

export const ISCED_BROAD_NAMES: Record<string, LocalizedText> = {
  "01": { "zh-CN": "教育", en: "Education", cs: "Vzdělávání a výchova" },
  "02": { "zh-CN": "艺术与人文", en: "Arts and humanities", cs: "Umění a humanitní vědy" },
  "03": { "zh-CN": "社会科学与新闻", en: "Social sciences and journalism", cs: "Sociální vědy, žurnalistika a informace" },
  "04": { "zh-CN": "商科、管理与法律", en: "Business, administration and law", cs: "Obchod, administrativa a právo" },
  "05": { "zh-CN": "自然科学与数学", en: "Natural sciences, mathematics and statistics", cs: "Přírodní vědy, matematika a statistika" },
  "06": { "zh-CN": "计算机与信息通信", en: "Information and communication technologies", cs: "Informační a komunikační technologie" },
  "07": { "zh-CN": "工程、制造与建筑", en: "Engineering, manufacturing and construction", cs: "Inženýrství, výroba a stavebnictví" },
  "08": { "zh-CN": "农学、林业与兽医", en: "Agriculture, forestry, fisheries and veterinary", cs: "Zemědělství, lesnictví, rybářství a veterinářství" },
  "09": { "zh-CN": "卫生与社会福利", en: "Health and welfare", cs: "Zdravotní a sociální péče" },
  "10": { "zh-CN": "服务", en: "Services", cs: "Služby" },
  "00": { "zh-CN": "通用课程", en: "Generic programmes", cs: "Obory obecné" },
  unknown: { "zh-CN": "登记未列学科", en: "Field not coded on the register", cs: "Obor v registru neuveden" },
};

export function iscedBroad(code: string | null | undefined): string {
  const digits = (code ?? "").replace(/\D/g, "");
  if (digits.length >= 2) return digits.slice(0, 2).padStart(2, "0");
  if (digits.length === 1) return digits.padStart(2, "0");
  return "unknown";
}

export function offeringFieldGroup(offering: Offering): string {
  return iscedBroad(offering.iscedF);
}

export function fieldGroupLabel(code: string, locale: UiLocale): string {
  return (ISCED_BROAD_NAMES[code] ?? ISCED_BROAD_NAMES.unknown)[locale];
}
