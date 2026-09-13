"""Safely check or normalize the three tracked UI locale catalogues.

The JSON catalogues are authoritative.  ``MESSAGES`` remains a bootstrap seed
for older keys, but it must never overwrite newer reviewed wording or remove
keys added directly to all three catalogues.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "locales"

MESSAGES: dict[str, dict[str, str]] = {
    "brand.name": {
        "zh-CN": "捷克留学与科研平台",
        "en": "Czech Study and Research Platform",
        "cs": "Platforma pro studium a výzkum v Česku",
    },
    "brand.tagline": {
        "zh-CN": "按授课语言查找学位项目，并查找硕士可申请的带薪科研岗位",
        "en": "Find degree programmes by language of instruction, and paid research jobs open to master’s graduates",
        "cs": "Hledejte studijní programy podle vyučovacího jazyka a placené výzkumné pozice pro absolventy magistra",
    },
    "skip.nav": {
        "zh-CN": "跳到主要内容",
        "en": "Skip to main content",
        "cs": "Přejít k hlavnímu obsahu",
    },
    "nav.home": {"zh-CN": "首页", "en": "Home", "cs": "Domů"},
    "nav.programmes": {"zh-CN": "学位项目", "en": "Degree programmes", "cs": "Studijní programy"},
    "nav.research": {"zh-CN": "带薪科研", "en": "Paid research jobs", "cs": "Placené výzkumné pozice"},
    "nav.guides": {"zh-CN": "申请指南", "en": "Application guides", "cs": "Průvodce přihláškou"},
    "nav.saved": {"zh-CN": "我的清单", "en": "My shortlist", "cs": "Můj seznam"},
    "nav.compare": {"zh-CN": "比较", "en": "Compare", "cs": "Porovnání"},
    "nav.map": {"zh-CN": "地图", "en": "Map", "cs": "Mapa"},
    "locale.label": {"zh-CN": "界面语言", "en": "Interface language", "cs": "Jazyk rozhraní"},
    "locale.zh-CN": {"zh-CN": "简体中文", "en": "简体中文", "cs": "简体中文"},
    "locale.en": {"zh-CN": "English", "en": "English", "cs": "English"},
    "locale.cs": {"zh-CN": "Čeština", "en": "Čeština", "cs": "Čeština"},
    "teaching.label": {"zh-CN": "授课语言", "en": "Language of instruction", "cs": "Vyučovací jazyk"},
    "teaching.prompt": {
        "zh-CN": "你想用哪种语言学习？",
        "en": "Which language would you like to study in?",
        "cs": "V jakém jazyce chcete studovat?",
    },
    "teaching.en": {"zh-CN": "英语授课", "en": "Study in English", "cs": "Studium v angličtině"},
    "teaching.cs": {"zh-CN": "捷克语授课", "en": "Study in Czech", "cs": "Studium v češtině"},
    "teaching.en.help": {
        "zh-CN": "需核对各项目英语要求；部分项目可能另有实习、临床或活动的捷克语要求。",
        "en": "Check each programme’s English requirements. Some programmes may also require Czech for placements, clinical work, or activities.",
        "cs": "Ověřte anglické požadavky každého programu. Některé programy mohou navíc vyžadovat češtinu pro praxi, klinickou výuku nebo aktivity.",
    },
    "teaching.cs.help": {
        "zh-CN": "需核对各项目捷克语要求；不预设所有项目同一语言等级。",
        "en": "Check each programme’s Czech requirements. Do not assume one language level for every programme.",
        "cs": "Ověřte české požadavky každého programu. Nepředpokládejte stejnou jazykovou úroveň u všech programů.",
    },
    "teaching.all": {
        "zh-CN": "查看全部授课语言",
        "en": "View all teaching languages",
        "cs": "Zobrazit všechny vyučovací jazyky",
    },
    "teaching.joint": {
        "zh-CN": "包含必需双语项目",
        "en": "Include programmes requiring both languages",
        "cs": "Zahrnout programy vyžadující oba jazyky",
    },
    "teaching.additional": {
        "zh-CN": "其他语言要求",
        "en": "Additional language requirements",
        "cs": "Další jazykové požadavky",
    },
    "teaching.change": {
        "zh-CN": "更改授课语言",
        "en": "Change language of instruction",
        "cs": "Změnit vyučovací jazyk",
    },
    "teaching.unset.notice": {
        "zh-CN": "请先选择授课语言。未选择时不会按语言限定检索。",
        "en": "Choose a language of instruction first. No language-limited search runs while this is unset.",
        "cs": "Nejprve zvolte vyučovací jazyk. Dokud není zvolen, neprobíhá vyhledávání omezené jazykem.",
    },
    "teaching.selected.en": {"zh-CN": "当前：英语授课", "en": "Current: English instruction", "cs": "Aktuálně: výuka v angličtině"},
    "teaching.selected.cs": {"zh-CN": "当前：捷克语授课", "en": "Current: Czech instruction", "cs": "Aktuálně: výuka v češtině"},
    "teaching.selected.all": {"zh-CN": "当前：全部授课语言", "en": "Current: all teaching languages", "cs": "Aktuálně: všechny vyučovací jazyky"},
    "teaching.continue": {
        "zh-CN": "继续上次选择：{label}",
        "en": "Continue with last choice: {label}",
        "cs": "Pokračovat v poslední volbě: {label}",
    },
    "search.placeholder": {
        "zh-CN": "搜索专业、学校或城市",
        "en": "Search programmes, institutions or cities",
        "cs": "Hledat programy, školy nebo města",
    },
    "filter.apply": {"zh-CN": "应用筛选", "en": "Apply filters", "cs": "Použít filtry"},
    "filter.live": {
        "zh-CN": "更改条件会立即更新列表，不必再点应用。",
        "en": "Changes update the list immediately; you do not need to apply.",
        "cs": "Změny se v seznamu projeví hned; není třeba je potvrzovat.",
    },
    "filter.clear": {"zh-CN": "清空筛选", "en": "Clear filters", "cs": "Vymazat filtry"},
    "filter.degree": {"zh-CN": "学位", "en": "Degree", "cs": "Stupeň studia"},
    "filter.field": {"zh-CN": "学科", "en": "Field", "cs": "Obor"},
    "filter.city": {"zh-CN": "城市", "en": "City", "cs": "Město"},
    "filter.institution": {"zh-CN": "学校", "en": "Institution", "cs": "Škola"},
    "filter.ownership": {"zh-CN": "学校性质", "en": "Institution ownership", "cs": "Typ zřizovatele školy"},
    "filter.recognition": {"zh-CN": "中留服认证参考", "en": "CSCSE recognition reference", "cs": "Informace k uznávání vzdělání CSCSE"},
    "filter.recognition.listedOnly": {
        "zh-CN": "仅看中留服查询可查",
        "en": "Only CSCSE lookup listed",
        "cs": "Pouze uvedené ve vyhledávání CSCSE",
    },
    "filter.status": {"zh-CN": "申请状态", "en": "Application status", "cs": "Stav přihlášek"},
    "filter.orientation": {"zh-CN": "培养导向", "en": "Orientation", "cs": "Zaměření"},
    "filter.view.cards": {"zh-CN": "卡片", "en": "Cards", "cs": "Karty"},
    "filter.view.list": {"zh-CN": "列表", "en": "List", "cs": "Seznam"},
    "filter.count": {"zh-CN": "{n} 个结果", "en": "{n} results", "cs": "{n} výsledků"},
    "filter.drawer": {"zh-CN": "筛选", "en": "Filters", "cs": "Filtry"},
    "filter.viewResults": {"zh-CN": "查看结果（{n}）", "en": "View results ({n})", "cs": "Zobrazit výsledky ({n})"},
    "filter.close": {"zh-CN": "关闭筛选", "en": "Close filters", "cs": "Zavřít filtry"},
    "filter.all": {"zh-CN": "全部", "en": "All", "cs": "Vše"},
    "filter.unknown": {"zh-CN": "未知", "en": "Unknown", "cs": "Neznámé"},
    "degree.bachelor": {"zh-CN": "学士", "en": "Bachelor", "cs": "Bakalář"},
    "degree.master": {"zh-CN": "硕士", "en": "Master", "cs": "Magistr"},
    "degree.doctorate": {"zh-CN": "博士", "en": "Doctorate", "cs": "Doktorát"},
    "orientation.applied": {"zh-CN": "应用／实践导向", "en": "Applied / practice-oriented", "cs": "Aplikované / praktické zaměření"},
    "orientation.research": {"zh-CN": "研究导向", "en": "Research-oriented", "cs": "Výzkumné zaměření"},
    "action.save": {"zh-CN": "收藏", "en": "Save", "cs": "Uložit"},
    "action.saved": {"zh-CN": "已收藏", "en": "Saved", "cs": "Uloženo"},
    "action.unsave": {"zh-CN": "取消收藏", "en": "Remove from shortlist", "cs": "Odebrat ze seznamu"},
    "action.compare": {"zh-CN": "比较", "en": "Compare", "cs": "Porovnat"},
    "action.compared": {"zh-CN": "已加入比较", "en": "In comparison", "cs": "V porovnání"},
    "action.official": {"zh-CN": "去官网申请", "en": "Apply on the official website", "cs": "Podat přihlášku na oficiálním webu"},
    "action.officialLink": {"zh-CN": "官方链接", "en": "Official link", "cs": "Oficiální odkaz"},
    "action.applyNow": {"zh-CN": "立即申请", "en": "Apply now", "cs": "Přihlásit se nyní"},
    "action.officialInstructions": {
        "zh-CN": "查看官方申请说明",
        "en": "View official application instructions",
        "cs": "Zobrazit oficiální pokyny k přihlášce",
    },
    "action.siteInterpretation": {
        "zh-CN": "查看本站解读",
        "en": "View this site’s notes",
        "cs": "Zobrazit vysvětlení na tomto webu",
    },
    "action.remove": {"zh-CN": "移除", "en": "Remove", "cs": "Odebrat"},
    "action.retry": {"zh-CN": "重试", "en": "Retry", "cs": "Zkusit znovu"},
    "action.external": {"zh-CN": "外部网站", "en": "External website", "cs": "Externí web"},
    "action.back": {"zh-CN": "返回列表", "en": "Back to results", "cs": "Zpět na výsledky"},
    "status.unknown": {"zh-CN": "未公布", "en": "Not published", "cs": "Nezveřejněno"},
    "status.review": {"zh-CN": "待核验", "en": "Awaiting verification", "cs": "Čeká na ověření"},
    "status.closed": {"zh-CN": "已截止", "en": "Closed", "cs": "Uzavřeno"},
    "status.open": {"zh-CN": "申请开放", "en": "Applications open", "cs": "Přihlášky otevřeny"},
    "status.upcoming": {"zh-CN": "尚未开始", "en": "Not yet open", "cs": "Ještě nezačalo"},
    "status.conditional": {"zh-CN": "有名额才开放", "en": "Open only if vacancies remain", "cs": "Otevřeno jen při volných místech"},
    "source.label": {"zh-CN": "官方来源", "en": "Official source", "cs": "Oficiální zdroj"},
    "source.verified": {"zh-CN": "最后核验", "en": "Last verified", "cs": "Naposledy ověřeno"},
    "empty.title": {"zh-CN": "没有符合条件的结果", "en": "No matching results", "cs": "Žádné odpovídající výsledky"},
    "empty.help": {"zh-CN": "试试移除部分筛选条件。不会改用其他授课语言来填满列表。", "en": "Try removing some filters. Results are not silently filled with other teaching languages.", "cs": "Zkuste odebrat některé filtry. Seznam se tiše nedoplňuje jinými vyučovacími jazyky."},
    "error.retry": {"zh-CN": "加载失败，请重试", "en": "Could not load. Please try again.", "cs": "Načtení se nezdařilo. Zkuste to znovu."},
    "fixture.banner": {
        "zh-CN": "中留服查询可查的 24 所高校学习项目来自教育部登记册，不是已发布招生目录。学费未公布不是免费。缺开始日期不视为开放。科研岗位来自学校官方招聘页；博士后不进入默认硕士可申请列表。中留服标签是查询参考，不是个人认证保证。",
        "en": "Study programmes for the 24 CSCSE-listed HEIs come from the official register, not a published admissions catalogue. Unpublished tuition is not free. A missing start date is not treated as open. Research jobs come from official career pages; postdocs are excluded from the default master’s list. CSCSE labels are a lookup reference, not a personal recognition guarantee.",
        "cs": "Studijní programy 24 vysokých škol uvedených v seznamu CSCSE pocházejí z oficiálního registru, nikoli ze zveřejněného katalogu přijímaček. Nezveřejněné školné není zdarma. Chybějící datum zahájení se nepovažuje za otevřené. Výzkumné pozice pocházejí z oficiálních kariérních stránek; postdoktorandi nejsou ve výchozím seznamu pro magistry. Štítky CSCSE jsou orientační, nikoli záruka uznání.",
    },
    "fixture.card": {"zh-CN": "界面样例", "en": "UI fixture", "cs": "Ukázka rozhraní"},
    "tracer.card": {
        "zh-CN": "录取页示踪（范围有限）",
        "en": "Admissions tracer (limited scope)",
        "cs": "Ověření přijímaček (omezený rozsah)",
    },
    "programmes.browse.disclaimer": {
        "zh-CN": "中留服查询可查的 24 所高校学习项目来自教育部登记册，不是可申请招生目录：没有编造学费或申请窗口。查理大学、马萨里克大学另有已核验录取页示踪。缺开始日期不视为开放；主按钮只在窗口开放时指向已核验的官方申请页。博士项目是登记册中的科研学习项目。",
        "en": "Study programmes for the 24 CSCSE-listed HEIs come from the official register. This is not an applyable admissions catalogue: tuition and windows are not invented. Charles University and Masaryk University also have verified admissions tracers. A missing start date is not treated as open; the primary apply button appears only while a window is open. Doctoral programmes are the register’s research-study records.",
        "cs": "Studijní programy 24 vysokých škol uvedených v seznamu CSCSE pocházejí z oficiálního registru. Nejde o podávací katalog: školné ani okna se nevymýšlejí. Univerzita Karlova a Masarykova univerzita mají i ověřené sledování přijímaček. Chybějící datum zahájení se nepovažuje za otevřené; hlavní tlačítko je jen u otevřeného okna. Doktorské programy jsou výzkumné studijní záznamy registru.",
    },
    "inventory.card": {
        "zh-CN": "登记册清单（非招生目录）",
        "en": "Register inventory (not admissions)",
        "cs": "Inventář registru (ne přijímačky)",
    },
    "inventory.loading": {
        "zh-CN": "正在载入中留服查询可查高校的登记册项目…",
        "en": "Loading register programmes for CSCSE-listed universities…",
        "cs": "Načítají se programy z registru pro vysoké školy uvedené v CSCSE…",
    },
    "inventory.year": {
        "zh-CN": "登记册在录（不是某一招生年度）",
        "en": "On the register (not an intake year)",
        "cs": "V registru (nejde o ročník přijímaček)",
    },
    "inventory.faculty": {"zh-CN": "学院", "en": "Faculty", "cs": "Fakulta"},
    "inventory.portalHelp": {
        "zh-CN": "下列官方申请系统已核验可打开，能打开不等于当前正在开放申请。",
        "en": "The official application system below was verified as reachable. A working portal is not an open window.",
        "cs": "Níže uvedený oficiální systém přihlášky byl ověřen jako dostupný. Funkční portál není otevřené okno.",
    },
    "jobs.card": {
        "zh-CN": "官方招聘页采集",
        "en": "Official career-page harvest",
        "cs": "Sběr z oficiální kariérní stránky",
    },
    "jobs.track": {"zh-CN": "岗位类型", "en": "Job track", "cs": "Typ pozice"},
    "jobs.track.assistant": {"zh-CN": "助理研究员", "en": "Research assistant", "cs": "Výzkumný asistent"},
    "jobs.track.post_master": {"zh-CN": "硕士后", "en": "Post-master researcher", "cs": "Výzkumník po magistru"},
    "jobs.track.postdoc": {"zh-CN": "博士后", "en": "Postdoctoral", "cs": "Postdoktorská"},
    "jobs.track.all": {"zh-CN": "全部公开岗位", "en": "All public jobs", "cs": "Všechny veřejné pozice"},
    "lang.de": {"zh-CN": "德语", "en": "German", "cs": "Němčina"},
    "lang.fr": {"zh-CN": "法语", "en": "French", "cs": "Francouzština"},
    "lang.ru": {"zh-CN": "俄语", "en": "Russian", "cs": "Ruština"},
    "lang.it": {"zh-CN": "意大利语", "en": "Italian", "cs": "Italština"},
    "lang.pl": {"zh-CN": "波兰语", "en": "Polish", "cs": "Polština"},
    "lang.und": {"zh-CN": "公告未说明", "en": "Not specified in the vacancy", "cs": "V nabídce neuvedeno"},
    "jobs.master": {"zh-CN": "硕士可申请", "en": "Open to master’s graduates", "cs": "Pro absolventy magisterského studia"},
    "jobs.phd": {"zh-CN": "博士注册要求", "en": "Doctoral enrollment requirement", "cs": "Požadavek na zápis do doktorského studia"},
    "jobs.phd.required": {"zh-CN": "必须注册博士", "en": "Doctoral enrollment required", "cs": "Zápis do doktorského studia je povinný"},
    "jobs.phd.optional": {"zh-CN": "读博可选", "en": "Doctoral enrollment optional", "cs": "Zápis do doktorského studia je volitelný"},
    "jobs.phd.no": {"zh-CN": "不要求注册博士", "en": "Doctoral enrollment not required", "cs": "Zápis do doktorského studia není vyžadován"},
    "jobs.phd.unknown": {"zh-CN": "公告未说明", "en": "Not specified in the vacancy", "cs": "V nabídce neuvedeno"},
    "jobs.language": {"zh-CN": "工作语言", "en": "Working languages", "cs": "Pracovní jazyky"},
    "jobs.gross": {"zh-CN": "税前工资", "en": "Gross salary", "cs": "Hrubá mzda"},
    "jobs.salaryUnknown": {"zh-CN": "报酬已确认，数额未公布", "en": "Pay confirmed; amount not published", "cs": "Odměna potvrzena, částka nezveřejněna"},
    "jobs.paidConfirmed": {"zh-CN": "已确认带薪", "en": "Paid status confirmed", "cs": "Placená pozice potvrzena"},
    "jobs.postdocExcluded": {"zh-CN": "博士后不进入默认硕士可申请结果", "en": "Postdoctoral posts are excluded from default master’s results", "cs": "Postdoktorské pozice nejsou ve výchozích výsledcích pro magistry"},
    "jobs.closedNotice": {"zh-CN": "该岗位已关闭，申请入口已停用。", "en": "This vacancy is closed. The apply action is disabled.", "cs": "Tato pozice je uzavřena. Akce přihlášení je vypnuta."},
    "jobs.host": {"zh-CN": "官方申请域名", "en": "Official application host", "cs": "Oficiální doména přihlášky"},
    "jobs.prompt": {
        "zh-CN": "查找中留服查询可查高校官方招聘页上的科研岗位。默认只显示硕士可申请的带薪岗位；可一键切换助理研究员、硕士后和博士后。不使用授课语言作为第一筛选。缺开始日期不视为开放。",
        "en": "Find research jobs from official career pages of CSCSE-listed universities. The default list is paid posts open to master’s graduates; switch to research assistant, post-master, or postdoc. Language of instruction is not the first filter. A missing start date is not treated as open.",
        "cs": "Hledejte výzkumné pozice z oficiálních kariérních stránek vysokých škol uvedených v CSCSE. Výchozí seznam jsou placené pozice pro magistry; lze přepnout na výzkumného asistenta, výzkumníka po magistru nebo postdoktoranda. Vyučovací jazyk není prvním filtrem. Chybějící datum zahájení se nepovažuje za otevřené.",
    },
    "institution.ownership": {"zh-CN": "学校性质", "en": "Institution ownership", "cs": "Typ zřizovatele školy"},
    "institution.public": {"zh-CN": "公立", "en": "Public", "cs": "Veřejná"},
    "institution.private": {"zh-CN": "私立", "en": "Private", "cs": "Soukromá"},
    "institution.state": {"zh-CN": "国立", "en": "State", "cs": "Státní"},
    "institution.unknown": {"zh-CN": "待核验", "en": "Not yet verified", "cs": "Dosud neověřeno"},
    "institution.researchOrg": {"zh-CN": "科研机构", "en": "Research institute", "cs": "Výzkumná instituce"},
    "recognition.label": {"zh-CN": "中留服认证参考", "en": "CSCSE recognition reference", "cs": "Informace k uznávání vzdělání CSCSE"},
    "recognition.listed": {"zh-CN": "中留服查询可查", "en": "Listed in the CSCSE institution lookup", "cs": "Uvedeno ve vyhledávání institucí CSCSE"},
    "recognition.notFound": {"zh-CN": "中留服暂未收录（捷克官方认可）", "en": "Czech accredited (not listed in CSCSE)", "cs": "Akreditováno v ČR (mimo seznam CSCSE)"},
    "recognition.unverified": {"zh-CN": "待核验", "en": "Not yet verified", "cs": "Dosud neověřeno"},
    "recognition.disclaimer": {
        "zh-CN": "此标签为官方查询参考，个人学历学位认证以中留服审核结果为准。",
        "en": "This label is an official lookup reference. Individual credential recognition is decided by CSCSE after review.",
        "cs": "Tento štítek je pouze orientační údaj z oficiálního vyhledávání. O uznání konkrétního vzdělání rozhoduje CSCSE po posouzení žádosti.",
    },
    "recognition.lookupDate": {"zh-CN": "查询日期", "en": "Lookup date", "cs": "Datum ověření ve vyhledávání"},
    "recognition.matchedName": {"zh-CN": "匹配颁证学校", "en": "Matched awarding institution", "cs": "Odpovídající udělující instituce"},
    "recognition.notice": {"zh-CN": "官方特别公告", "en": "Official notice", "cs": "Oficiální oznámení"},
    "recognition.notFound.help": {
        "zh-CN": "未查到不等于不被认可。该校受捷克教育部官方认可，仅中留服查询名单暂未收录。",
        "en": "Not listed does not mean unrecognised; the institution is officially accredited in the Czech Republic.",
        "cs": "Neuvedení v seznamu neznamená, že vzdělání nelze uznat; instituce je v ČR oficiálně akreditována.",
    },
    "application.opens": {"zh-CN": "申请开始", "en": "Applications open", "cs": "Začátek podávání přihlášek"},
    "application.closes": {"zh-CN": "申请截止", "en": "Application deadline", "cs": "Termín podání přihlášky"},
    "application.round": {"zh-CN": "申请轮次", "en": "Application round", "cs": "Kolo přijímacího řízení"},
    "application.roundUnknown": {"zh-CN": "未公布轮次", "en": "Round not published", "cs": "Kolo nebylo zveřejněno"},
    "application.rolling": {"zh-CN": "滚动申请", "en": "Rolling applications", "cs": "Průběžné podávání přihlášek"},
    "application.supplementary": {"zh-CN": "补录", "en": "Supplementary round", "cs": "Dodatečné kolo"},
    "application.opensUnknown": {"zh-CN": "开始日期未公布", "en": "Opening date not published", "cs": "Datum zahájení nebylo zveřejněno"},
    "application.currentRound": {"zh-CN": "当前适用轮次", "en": "Current applicable round", "cs": "Aktuálně platné kolo"},
    "application.nextRound": {"zh-CN": "下一轮尚未开始", "en": "Next round has not started", "cs": "Další kolo ještě nezačalo"},
    "application.timeline": {"zh-CN": "申请时间线", "en": "Application timeline", "cs": "Časová osa přihlášek"},
    "application.vacanciesConditional": {
        "zh-CN": "补录取决于是否仍有空余名额，未确认时不提前标为开放。",
        "en": "A supplementary round opens only if vacancies remain. It is not marked open before that is confirmed.",
        "cs": "Dodatečné kolo se otevře jen při volných místech. Před potvrzením se jako otevřené neoznačuje.",
    },
    "application.scope": {"zh-CN": "适用人群", "en": "Applicant group", "cs": "Skupina uchazečů"},
    "application.roundN": {"zh-CN": "第 {n} 轮", "en": "Round {n}", "cs": "Kolo {n}"},
    "detail.summary": {"zh-CN": "摘要", "en": "Summary", "cs": "Shrnutí"},
    "detail.requirements": {"zh-CN": "申请要求", "en": "Requirements", "cs": "Požadavky"},
    "detail.timeline": {"zh-CN": "时间线", "en": "Timeline", "cs": "Časová osa"},
    "detail.documents": {"zh-CN": "材料", "en": "Documents", "cs": "Dokumenty"},
    "detail.curriculum": {"zh-CN": "课程与实习", "en": "Curriculum and placements", "cs": "Studium a praxe"},
    "detail.institution": {"zh-CN": "学校", "en": "Institution", "cs": "Škola"},
    "detail.sources": {"zh-CN": "来源", "en": "Sources", "cs": "Zdroje"},
    "detail.teachingLanguage": {"zh-CN": "授课语言", "en": "Language of instruction", "cs": "Vyučovací jazyk"},
    "detail.admissionLanguage": {"zh-CN": "入学语言证明", "en": "Admission language evidence", "cs": "Jazykový doklad k přijetí"},
    "detail.additionalLanguage": {"zh-CN": "其他必需语言", "en": "Additional required languages", "cs": "Další povinné jazyky"},
    "detail.tuition": {"zh-CN": "学费", "en": "Tuition", "cs": "Školné"},
    "detail.duration": {"zh-CN": "学制", "en": "Duration", "cs": "Délka studia"},
    "detail.degree": {"zh-CN": "学位", "en": "Degree", "cs": "Titul"},
    "detail.notSubmitted": {
        "zh-CN": "跳转官方网站不代表已在本站提交申请。",
        "en": "Opening the official site does not mean an application was submitted here.",
        "cs": "Otevření oficiálního webu neznamená, že byla přihláška podána na tomto webu.",
    },
    "detail.city": {"zh-CN": "城市", "en": "City", "cs": "Město"},
    "detail.year": {"zh-CN": "入学年度", "en": "Intake year", "cs": "Akademický rok"},
    "detail.semesters": {"zh-CN": "{n} 学期", "en": "{n} semesters", "cs": "{n} semestrů"},
    "compare.title": {"zh-CN": "比较清单", "en": "Comparison", "cs": "Porovnání"},
    "compare.limit": {"zh-CN": "最多比较 4 项。", "en": "You can compare up to 4 items.", "cs": "Lze porovnat nejvýše 4 položky."},
    "compare.empty": {"zh-CN": "还没有加入比较的项目。", "en": "Nothing has been added to comparison yet.", "cs": "Do porovnání zatím nic nebylo přidáno."},
    "compare.remove": {"zh-CN": "移除此项", "en": "Remove", "cs": "Odebrat"},
    "compare.clear": {"zh-CN": "清空对比", "en": "Clear comparison", "cs": "Vymazat porovnání"},
    "saved.title": {"zh-CN": "我的清单", "en": "My shortlist", "cs": "Můj seznam"},
    "saved.empty": {"zh-CN": "清单是空的。收藏保存在本机，不会自动同步到其他设备。", "en": "Your shortlist is empty. Saved items stay on this device and are not synced automatically.", "cs": "Seznam je prázdný. Uložené položky zůstanou na tomto zařízení a nesynchronizují se automaticky."},
    "saved.localOnly": {
        "zh-CN": "收藏仅保存在本机浏览器，不会自动跨设备同步。",
        "en": "The shortlist is stored in this browser only and is not synced across devices.",
        "cs": "Seznam je uložen jen v tomto prohlížeči a nesynchronizuje se mezi zařízeními.",
    },
    "guides.title": {"zh-CN": "申请指南", "en": "Application guides", "cs": "Průvodce přihláškou"},
    "guides.intro": {
        "zh-CN": "本站帮助你形成候选清单。申请须通过学校或雇主的官方入口自行提交。",
        "en": "This site helps you build a shortlist. Applications must be submitted by you through the official institutional or employer channel.",
        "cs": "Tento web pomáhá sestavit užší výběr. Přihlášku podáváte sami přes oficiální kanál školy nebo zaměstnavatele.",
    },
    "guides.body": {
        "zh-CN": "先选择授课语言，再核对学生语言证明、实习或临床等额外语言、学费口径和当前申请轮次。中留服查询结果只是参考，不是个人认证保证。科研岗位看工作语言和博士注册要求，不套用授课语言筛选。",
        "en": "Choose the language of instruction first, then check admission language evidence, extra language needs for placements or clinics, tuition terms, and the current application round. A CSCSE lookup is a reference, not a personal recognition guarantee. Research jobs use working language and doctoral enrollment filters, not teaching-language filters.",
        "cs": "Nejprve zvolte vyučovací jazyk, poté ověřte jazykový doklad k přijetí, další jazykové požadavky pro praxi nebo kliniku, podmínky školného a aktuální kolo přihlášek. Vyhledávání CSCSE je orientační, nikoli záruka osobního uznání. U výzkumných pozic se používá pracovní jazyk a požadavek na zápis do doktorského studia, nikoli filtr vyučovacího jazyka.",
    },
    "home.researchCta": {"zh-CN": "查找带薪科研岗位", "en": "Find paid research jobs", "cs": "Hledat placené výzkumné pozice"},
    "home.researchHelp": {
        "zh-CN": "科研入口不要求先选择授课语言。",
        "en": "The research-jobs entry does not require a teaching-language choice first.",
        "cs": "Vstup k výzkumným pozicím nevyžaduje nejprve volbu vyučovacího jazyka.",
    },
    "footer.disclaimer": {
        "zh-CN": "不编造录取概率或用户评价。费用未知不表示免费。关闭岗位会从公开列表下架。",
        "en": "This site does not invent admission odds or user reviews. Unknown tuition is not free. Closed vacancies are removed from public lists.",
        "cs": "Tento web nevymýšlí pravděpodobnost přijetí ani uživatelské recenze. Neznámé školné neznamená, že je studium zdarma. Uzavřené pozice se z veřejných seznamů odebírají.",
    },
    "sort.default": {"zh-CN": "开放优先", "en": "Open first", "cs": "Nejprve otevřené"},
    "sort.deadline": {"zh-CN": "截止日期", "en": "Deadline", "cs": "Termín"},
    "pagination.prev": {"zh-CN": "上一页", "en": "Previous", "cs": "Předchozí"},
    "pagination.next": {"zh-CN": "下一页", "en": "Next", "cs": "Další"},
    "pagination.page": {"zh-CN": "第 {n} 页", "en": "Page {n}", "cs": "Strana {n}"},
    "pagination.pageOf": {
        "zh-CN": "第 {n} 页，共 {total} 页",
        "en": "Page {n} of {total}",
        "cs": "Strana {n} z {total}",
    },
    "meta.description": {
        "zh-CN": "面向中文、英文、捷克文用户的捷克学位项目与带薪科研岗位检索。授课语言与界面语言分开保存。",
        "en": "Search Czech degree programmes and paid research jobs in Chinese, English, and Czech. Interface language is stored separately from language of instruction.",
        "cs": "Vyhledávání českých studijních programů a placených výzkumných pozic v čínštině, angličtině a češtině. Jazyk rozhraní se ukládá odděleně od vyučovacího jazyka.",
    },
    "lang.en": {"zh-CN": "英语", "en": "English", "cs": "angličtina"},
    "lang.cs": {"zh-CN": "捷克语", "en": "Czech", "cs": "čeština"},
    "lang.joint": {"zh-CN": "英语与捷克语均必修", "en": "Both English and Czech required", "cs": "Povinná angličtina i čeština"},
    "clinical.cs.required": {
        "zh-CN": "临床／实习要求捷克语",
        "en": "Czech required for clinical work or placement",
        "cs": "Čeština povinná pro klinickou výuku nebo praxi",
    },
    "degree.unknown": {"zh-CN": "学位未公布", "en": "Degree not published", "cs": "Stupeň neuveden"},
    "degree.other": {"zh-CN": "其他学位", "en": "Other degree", "cs": "Jiný stupeň"},
    "tuition.cycle.year": {"zh-CN": "年", "en": "year", "cs": "rok"},
    "tuition.cycle.semester": {"zh-CN": "学期", "en": "semester", "cs": "semestr"},
    "tuition.cycle.programme": {"zh-CN": "全程", "en": "programme", "cs": "program"},
    "nav.main": {"zh-CN": "主导航", "en": "Main navigation", "cs": "Hlavní navigace"},
    "nav.openMenu": {"zh-CN": "打开菜单", "en": "Open menu", "cs": "Otevřít nabídku"},
    "nav.closeMenu": {"zh-CN": "关闭菜单", "en": "Close menu", "cs": "Zavřít nabídku"},
    "jobs.fte": {"zh-CN": "薪资折算基准（FTE）", "en": "Salary basis (FTE)", "cs": "Mzdový základ (FTE)"},
    "jobs.workloadFte": {"zh-CN": "岗位工时（FTE）", "en": "Position workload (FTE)", "cs": "Úvazek pozice (FTE)"},
    "jobs.employmentStart": {"zh-CN": "可到岗日期", "en": "Possible start from", "cs": "Možný nástup od"},
    "jobs.notMaster": {"zh-CN": "不在默认硕士可申请结果中", "en": "Not in the default master’s results", "cs": "Není ve výchozích výsledcích pro magistry"},
    "context.admission": {"zh-CN": "入学", "en": "Admission", "cs": "Přijetí"},
    "context.clinical": {"zh-CN": "临床", "en": "Clinical", "cs": "Klinická výuka"},
    "context.placement": {"zh-CN": "实习／实践", "en": "Placement", "cs": "Praxe"},
    "context.other": {"zh-CN": "其他", "en": "Other", "cs": "Jiné"},
    "requirement.required": {"zh-CN": "必需", "en": "Required", "cs": "Povinné"},
    "requirement.optional": {"zh-CN": "可选", "en": "Optional", "cs": "Volitelné"},
    "requirement.unknown": {"zh-CN": "未公布", "en": "Not published", "cs": "Nezveřejněno"},
    "application.roundClosed": {"zh-CN": "本轮已截止", "en": "This round is closed", "cs": "Toto kolo je uzavřeno"},
    "application.roundNotOpen": {"zh-CN": "本轮尚未开放申请", "en": "This round is not open for applications", "cs": "Toto kolo není otevřeno pro přihlášky"},
    "noscript.lists": {
        "zh-CN": "筛选后的项目列表需要启用 JavaScript。上方授课语言入口在关闭脚本时仍可打开。",
        "en": "JavaScript is required to view the filtered programme list. Teaching-language links above still work with scripts off.",
        "cs": "Pro zobrazení filtrovaného seznamu programů je nutný JavaScript. Odkazy na vyučovací jazyk výše fungují i bez skriptů.",
    },
    "noscript.jobs": {
        "zh-CN": "岗位筛选需要启用 JavaScript。无脚本时仍显示默认公开列表。",
        "en": "JavaScript is required to filter jobs. The default public list still renders with scripts off.",
        "cs": "Pro filtrování pozic je nutný JavaScript. Výchozí veřejný seznam se vykreslí i bez skriptů.",
    },
    "noscript.map": {
        "zh-CN": "地图针点和筛选需要启用 JavaScript。无脚本时仍可使用本页下方的学校列表；坐标未收录的学校没有点位。",
        "en": "JavaScript is required for map pins and filters. The school list below still works with scripts off; schools without coordinates have no pin.",
        "cs": "Pro špendlíky a filtry na mapě je nutný JavaScript. Seznam škol níže funguje i bez skriptů; školy bez souřadnic nemají špendlík.",
    },
    "error.notFound": {"zh-CN": "没有这个页面", "en": "This page does not exist", "cs": "Tato stránka neexistuje"},
    "error.home": {"zh-CN": "回到首页", "en": "Back to home", "cs": "Zpět na úvod"},
    "error.loadFailed": {
        "zh-CN": "目录未能载入",
        "en": "The catalogue could not be loaded",
        "cs": "Katalog se nepodařilo načíst",
    },
    "error.partialCatalog": {
        "zh-CN": "这不是空结果：登记项目列表这次没有载入成功。请重试，不要用清除筛选代替。",
        "en": "This is not an empty result: the register inventory failed to load. Retry; do not clear filters instead.",
        "cs": "Toto není prázdný výsledek: inventář z registru se nenačetl. Zkuste to znovu; nepoužívejte vymazání filtrů.",
    },
    "action.viewOfficialNotice": {
        "zh-CN": "查看官方公告（不是当前申请入口）",
        "en": "View the official notice (not a current apply link)",
        "cs": "Zobrazit oficiální oznámení (není aktuální podání)",
    },
    "application.opportunityClosed": {
        "zh-CN": "该机会已整体关闭，各轮次都不再接受申请。",
        "en": "This opportunity is closed as a whole; no round is accepting applications.",
        "cs": "Tato příležitost je jako celek uzavřena; žádné kolo nepřijímá přihlášky.",
    },
    "error.notFound.help": {
        "zh-CN": "这个地址没有对应页面。可以用下面的入口回到检索。",
        "en": "This address does not match a page. Use the links below to return to search.",
        "cs": "Tato adresa neodpovídá žádné stránce. Níže se můžete vrátit k vyhledávání.",
    },
    "nav.institutions": {"zh-CN": "高校名录", "en": "Institutions", "cs": "Vysoké školy"},
    "institutions.title": {"zh-CN": "捷克高校名录（官方登记）", "en": "Czech higher education institutions (official register)", "cs": "České vysoké školy (oficiální registr)"},
    "institutions.search": {"zh-CN": "搜索高校", "en": "Search institutions", "cs": "Hledat školy"},
    "institutions.search.placeholder": {
        "zh-CN": "查理大学、Charles University、Univerzita Karlova…",
        "en": "Charles University, Univerzita Karlova, 查理大学…",
        "cs": "Univerzita Karlova, Charles University, 查理大学…",
    },
    "institutions.open": {"zh-CN": "查看学校", "en": "View institution", "cs": "Otevřít školu"},
    "institutions.openMap": {"zh-CN": "在地图上查看", "en": "View on the map", "cs": "Zobrazit na mapě"},
    "institutions.website": {"zh-CN": "官网", "en": "Official website", "cs": "Oficiální web"},
    "institutions.intro": {
        "zh-CN": "以下名称、学校性质和大学／非大学类型来自教育部《高校及实施中的学习项目登记册》。中留服“查询可查”来自运营方 2026-09-06 提供的名单，已与现行登记册校名核对，不是现场打开中留服网站的抓取。本页不是已核验的招生目录，也没有编造专业或截止日期。",
        "en": "Names, ownership and university / non-university type come from the Ministry register. CSCSE “listed” rows come from an operator-supplied list dated 2026-09-06, matched to current register names; this is not a live scrape of the CSCSE portal. This is not a verified admissions catalogue; programmes and deadlines are not invented.",
        "cs": "Názvy, typ zřizovatele a univerzitní / neuniverzitní charakter vycházejí z ministerského registru. Položky CSCSE „uvedeno“ pocházejí ze seznamu provozovatele k 2026-09-06, spárovaného s aktuálním registrem; nejde o živé stažení portálu CSCSE. Toto není ověřený přijímací katalog; programy a termíny se nedomýšlejí.",
    },
    "institutions.source": {"zh-CN": "官方来源：MŠMT 登记册", "en": "Official source: MŠMT register", "cs": "Oficiální zdroj: registr MŠMT"},
    "institutions.noWebsite": {"zh-CN": "本页未收录官网地址", "en": "No official website recorded on this page", "cs": "Oficiální web na této stránce není uveden"},
    "institutions.count": {"zh-CN": "共 {n} 所登记高校", "en": "{n} registered institutions", "cs": "{n} evidovaných institucí"},
    "institutions.websiteArchive": {
        "zh-CN": "官网主机名来自教育部登记册当天的 CSV（VŠ）导出；无协议时补了 https://，未再逐校打开核对是否仍为当前首页。",
        "en": "Website hostnames come from the ministry register CSV (VŠ) export of the harvest day. https:// was prefixed when the export had no scheme; live homepages were not re-checked.",
        "cs": "Názvy hostitelů webů pocházejí z CSV exportu (VŠ) ministerského registru v den sklizně. Pokud export neměl schéma, bylo doplněno https://; aktuální homepage nebyly znovu ověřeny.",
    },
    "institutions.region": {"zh-CN": "州／地区", "en": "Region", "cs": "Kraj"},
    "institutions.ico": {"zh-CN": "公司识别号 IČO", "en": "Company ID (IČO)", "cs": "IČO"},
    "institutions.seat": {"zh-CN": "注册地址", "en": "Registered seat", "cs": "Sídlo"},
    "institutions.englishName": {"zh-CN": "官方英文名", "en": "Official English name", "cs": "Oficiální anglický název"},
    "institutions.noProgrammes": {
        "zh-CN": "本页只展示教育部登记的学校身份。尚未从官方登记册导入已核验的招生专业、学费或截止日期，因此这里不编造项目列表。",
        "en": "This page shows the institution identity from the ministry register. Verified programmes, tuition and deadlines have not been imported, so no programme list is invented here.",
        "cs": "Tato stránka ukazuje identitu školy z ministerského registru. Ověřené programy, školné a termíny ještě nebyly importovány, proto se zde seznam programů nedomýšlí.",
    },
    "institutions.websiteOnly": {
        "zh-CN": "本页没有已核验的项目库存或官方招生入口，请以学校官网为准。",
        "en": "This page has no verified programme inventory or official admissions portal; use the official website.",
        "cs": "Na této stránce není ověřený inventář programů ani oficiální přijímací vstup; řiďte se oficiálním webem školy.",
    },
    "institutions.registerOnly": {
        "zh-CN": "官方登记身份，尚未发布招生目录",
        "en": "Official register identity; not a published admissions catalogue",
        "cs": "Identita z oficiálního registru; nejde o zveřejněný přijímací katalog",
    },
    "legalType.university": {"zh-CN": "大学型高校", "en": "University-type institution", "cs": "Univerzitní vysoká škola"},
    "legalType.nonUniversity": {"zh-CN": "非大学型高校", "en": "Non-university-type institution", "cs": "Neuniverzitní vysoká škola"},
    "institutions.inventory": {
        "zh-CN": "登记册中有 {n} 条认证／实施中的学习项目记录。这不是招生目录：没有申请窗口、学费或申请链接，因此不在此列出可申请项目。",
        "en": "The register lists {n} accredited / delivered programme records. This is not an admissions catalogue: no application windows, tuition or apply links, so no applyable offerings are listed here.",
        "cs": "Registr eviduje {n} záznamů akreditovaných / uskutečňovaných programů. Toto není přijímací katalog: chybí termíny, školné i odkazy k přihlášce, proto se zde nenabízejí podatelné nabídky.",
    },
    "institutions.cscseListedGroup": {"zh-CN": "中留服查询可查（已与登记册核对）", "en": "Listed in the CSCSE lookup (matched to the register)", "cs": "Uvedeno ve vyhledávání CSCSE (spárováno s registrem)"},
    "institutions.cscseNotFoundGroup": {"zh-CN": "现行登记册中有、但不在本次中留服名单", "en": "On the current register, not on this CSCSE list", "cs": "V aktuálním registru, mimo tento seznam CSCSE"},
    "institutions.cscseUnmatchedGroup": {"zh-CN": "名单中有、但不在现行教育部登记册", "en": "On the supplied CSCSE list, not on the current ministry register", "cs": "Na dodaném seznamu CSCSE, mimo aktuální ministerský registr"},
    "institutions.cscseCountListed": {"zh-CN": "可查 {n} 所", "en": "{n} listed", "cs": "{n} uvedeno"},
    "institutions.cscseCountNotFound": {"zh-CN": "名单未列入 {n} 所", "en": "{n} not on this list", "cs": "{n} mimo tento seznam"},
    "institutions.cscseOperatorNote": {
        "zh-CN": "中留服名单由运营方提供并与教育部校名核对。标签是查询参考，个人认证以中留服审核为准。未查到不等于不被认可。",
        "en": "The CSCSE names were supplied by the operator and matched to ministry names. The label is a lookup reference; individual recognition is decided by CSCSE. Not found does not mean a credential cannot be recognised.",
        "cs": "Názvy CSCSE dodal provozovatel a byly spárovány s ministerskými názvy. Štítek je orientační; o uznání konkrétního vzdělání rozhoduje CSCSE. Nenalezení neznamená, že vzdělání nelze uznat.",
    },
    "map.title": {"zh-CN": "高校地图", "en": "Institution map", "cs": "Mapa vysokých škol"},
    "map.intro": {
        "zh-CN": "地图是辅助视图，列表才是数据。底图是捷克 14 个州的开源行政区划，城市名为 Wikidata／Nominatim 标注。可滚轮或按钮放大缩小、拖动平移。不使用 Google 地图或境外瓦片。",
        "en": "The map is an auxiliary view; the list is the data. The base map is the 14 open Czech administrative regions, with city names from Wikidata / Nominatim. Zoom with the wheel or buttons, and pan by dragging. It does not use Google Maps or foreign map tiles.",
        "cs": "Mapa je pomocný pohled; seznam je zdrojem dat. Podklad tvoří 14 otevřených českých krajů, názvy měst pocházejí z Wikidat / Nominatim. Přibližujte kolečkem nebo tlačítky a posouvejte tažením. Nepoužívá Google Maps ani zahraniční mapové dlaždice.",
    },
    "map.coverage": {
        "zh-CN": "教育部登记 {n} 所高校，其中 {mapped} 所有坐标，{missing} 所未收录坐标。",
        "en": "{n} register HEIs, {mapped} with coordinates, {missing} without.",
        "cs": "{n} škol v registru, {mapped} se souřadnicemi, {missing} bez souřadnic.",
    },
    "map.harvestedAt": {"zh-CN": "坐标采集日期 {date}", "en": "Coordinates harvested {date}", "cs": "Souřadnice sklizeny {date}"},
    "map.disclaimer": {
        "zh-CN": "身份以教育部登记册为准。坐标优先用 Wikidata P625，且须 IČO、官网主机或官方捷克名唯一匹配；否则用登记地址做 Nominatim 地理编码。匹配不上的不编造。布拉格等重叠点位保持原坐标，请用列表区分。中留服名单中的“政治与社会科学学院”不在现行登记册，故不画点。",
        "en": "Identity stays on the ministry register. Coordinates prefer Wikidata P625 when IČO, website host, or the official Czech name matches uniquely; otherwise the register seat is geocoded with Nominatim. Missing points are not invented. Overlapping Prague pins keep their exact coordinates — use the list to tell them apart. The CSCSE name “College of Political and Social Sciences” is not on the current register, so it is not plotted.",
        "cs": "Identita zůstává na ministerském registru. Souřadnice preferují Wikidata P625 při jedinečné shodě IČO, hostitele webu nebo oficiálního českého názvu; jinak se sídlo z registru geokóduje přes Nominatim. Chybějící body se nedomýšlejí. Překrývající se špendlíky v Praze si ponechávají přesné souřadnice — rozlišíte je seznamem. Název CSCSE „College of Political and Social Sciences“ v aktuálním registru není, proto se nekreslí.",
    },
    "map.legend": {"zh-CN": "图例", "en": "Legend", "cs": "Legenda"},
    "map.legend.listed": {"zh-CN": "圆点：中留服查询可查", "en": "Circle: listed in the CSCSE lookup", "cs": "Kruh: uvedeno ve vyhledávání CSCSE"},
    "map.legend.notFound": {"zh-CN": "方点：登记册有、但不在本次中留服名单", "en": "Square: on the register, not on this CSCSE list", "cs": "Čtverec: v registru, mimo tento seznam CSCSE"},
    "map.legend.unmapped": {"zh-CN": "无点位：坐标未收录，只出现在列表", "en": "No pin: coordinates not recorded; list only", "cs": "Bez špendlíku: souřadnice chybí; pouze seznam"},
    "map.legend.cities": {"zh-CN": "文字：城市名", "en": "Text: city name", "cs": "Text: název města"},
    "map.zoom": {"zh-CN": "地图缩放", "en": "Map zoom", "cs": "Přiblížení mapy"},
    "map.zoomIn": {"zh-CN": "放大", "en": "Zoom in", "cs": "Přiblížit"},
    "map.zoomOut": {"zh-CN": "缩小", "en": "Zoom out", "cs": "Oddálit"},
    "map.zoomReset": {"zh-CN": "复位", "en": "Reset", "cs": "Obnovit"},
    "map.basemap.source": {
        "zh-CN": "州界：jlacko/powerbi-cesko（ČSÚ NUTS-3）。河流／湖泊／邻国：Natural Earth（nvkelso/natural-earth-vector）。城市名：Wikidata／Nominatim。",
        "en": "Regions: jlacko/powerbi-cesko (ČSÚ NUTS-3). Rivers, lakes and neighbours: Natural Earth (nvkelso/natural-earth-vector). Cities: Wikidata / Nominatim.",
        "cs": "Kraje: jlacko/powerbi-cesko (NUTS-3 ČSÚ). Řeky, jezera a sousedé: Natural Earth (nvkelso/natural-earth-vector). Města: Wikidata / Nominatim.",
    },
    "map.filter.mapped": {"zh-CN": "有坐标", "en": "With coordinates", "cs": "Se souřadnicemi"},
    "map.filter.missing": {"zh-CN": "坐标未收录", "en": "Coordinates missing", "cs": "Bez souřadnic"},
    "map.noCoordinates": {"zh-CN": "坐标未收录", "en": "Coordinates not recorded", "cs": "Souřadnice neuvedeny"},
    "map.select": {"zh-CN": "在地图上查看", "en": "Show on map", "cs": "Ukázat na mapě"},
    "map.source.wikidata": {"zh-CN": "Wikidata 坐标", "en": "Wikidata coordinates", "cs": "Souřadnice Wikidata"},
    "map.source.nominatim": {"zh-CN": "登记地址地理编码", "en": "Geocoded register seat", "cs": "Geokódované sídlo z registru"},
    "map.unmapped": {
        "zh-CN": "当前列表中有学校尚未收录核验坐标，因此地图上没有对应点位。",
        "en": "Some schools in the current list have no verified coordinates, so they have no pin.",
        "cs": "U některých škol v aktuálním seznamu chybí ověřené souřadnice, proto nemají špendlík.",
    },
    "map.list": {"zh-CN": "学校列表", "en": "Institution list", "cs": "Seznam škol"},
    "map.canvas": {"zh-CN": "捷克高校位置图", "en": "Map of Czech higher education institutions", "cs": "Mapa českých vysokých škol"},
    "map.pins": {"zh-CN": "地图上 {n} 个点位", "en": "{n} pins on the map", "cs": "{n} špendlíků na mapě"},
    "institutions.tracer": {
        "zh-CN": "录取页示踪（范围有限）",
        "en": "Admissions-page trace (limited scope)",
        "cs": "Ověření přijímací stránky (omezený rozsah)",
    },
    "institutions.tracer.disclaimer": {
        "zh-CN": "这是该校官方录取页的核验样本，不是完整招生目录。登记册清单不能当作可申请项目。缺开始日期不视为开放；未公布学费不是 0 或免费。冲突的申请费不会压成一个数字。主按钮仅在窗口开放时指向官方申请页。",
        "en": "This is a verified sample from this institution's official admissions pages, not a full catalogue. The register inventory is not an applyable offering. A missing start date is not treated as open; unpublished tuition is not 0 or free. Conflicting application fees are not collapsed to one amount. The primary apply button appears only while a window is open.",
        "cs": "Jde o ověřený vzorek z oficiálních přijímacích stránek této školy, nikoli o úplný katalog. Inventář z registru není nabídkou, do níž lze právě podat přihlášku. Chybějící datum zahájení se nepovažuje za otevřené; nezveřejněné školné není 0 ani zdarma. Rozdílné údaje o poplatku za přihlášku se neslučují do jediné částky. Hlavní tlačítko k přihlášce se zobrazí jen u otevřeného okna.",
    },
    "institutions.tracer.faculty": {"zh-CN": "学院", "en": "Faculty", "cs": "Fakulta"},
    "institutions.tracer.sourcePage": {"zh-CN": "官方录取页", "en": "Official admissions page", "cs": "Oficiální přijímací stránka"},
    "tuition.unpublishedNotFree": {
        "zh-CN": "学费未公布（不是免费，也不是 0）",
        "en": "Tuition not published (not free, not 0)",
        "cs": "Školné nebylo zveřejněno (není zdarma ani 0)",
    },
    "application.feeNotTuition": {
        "zh-CN": "申请手续费，不是学费",
        "en": "Application fee, not tuition",
        "cs": "Poplatek za přihlášku, nikoli školné",
    },
    "application.opensMonthOnly": {
        "zh-CN": "院系页只写到月的开放说明，不作为申请开始日，因此不自动视为开放：{note}",
        "en": "The faculty page only states a month for the application server opening; that is not stored as the start date and does not auto-open the window: {note}",
        "cs": "Fakultní stránka uvádí otevření podatelny jen na úrovni měsíce; to se neukládá jako datum zahájení a okno se proto samo neotevře: {note}",
    },
    "institutions.applyPortal": {
        "zh-CN": "官方申请入口（已核验可打开）",
        "en": "Official application portal (verified reachable)",
        "cs": "Oficiální podatelna (ověřeně dostupná)",
    },
    "institutions.applyPortal.help": {
        "zh-CN": "下列链接在采集当天返回正常页面，不是 404。能打开申请系统不等于当前正在开放申请；缺开始日期不视为开放。",
        "en": "These links returned a live page on the harvest day, not a 404. A reachable application system is not an open window; a missing start date is not treated as open.",
        "cs": "Tyto odkazy v den sběru vracely živou stránku, nikoli 404. Dostupný podací systém neznamená otevřené okno; chybějící datum zahájení se nepovažuje za otevřené.",
    },
    "institutions.applyPortal.form": {
        "zh-CN": "官方电子申请系统",
        "en": "Official e-application",
        "cs": "Oficiální e-přihláška",
    },
    "institutions.applyPortal.info": {
        "zh-CN": "官方招生说明",
        "en": "Official admissions information",
        "cs": "Oficiální informace o přijímacím řízení",
    },
    "institutions.applyPortal.missing": {
        "zh-CN": "当天未能核验到可打开的官方申请页，因此这里不放置会 404 的申请按钮。",
        "en": "No reachable official application page was verified on the harvest day, so no apply button that would 404 is shown here.",
        "cs": "V den sběru se nepodařilo ověřit dostupnou oficiální stránku přihlášky, proto se zde nezobrazuje tlačítko, které by vedlo na 404.",
    },
    "institutions.applyPortal.en": {"zh-CN": "英文入口", "en": "English portal", "cs": "Anglický vstup"},
    "institutions.applyPortal.cs": {"zh-CN": "捷克文入口", "en": "Czech portal", "cs": "Český vstup"},
}


LOCALES = ("zh-CN", "en", "cs")
PLACEHOLDER = re.compile(r"\{[A-Za-z][A-Za-z0-9_]*\}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--write",
        action="store_true",
        help="normalize JSON formatting after all parity checks pass",
    )
    args = parser.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    catalogues: dict[str, dict[str, str]] = {}
    for locale in LOCALES:
        path = OUT / f"{locale}.json"
        if not path.exists():
            catalogues[locale] = {}
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise SystemExit(f"{path}: root must be an object")
        catalogues[locale] = payload

    # Fill only absent bootstrap keys. Existing reviewed values always win.
    for key, values in MESSAGES.items():
        for locale in LOCALES:
            catalogues[locale].setdefault(key, values[locale])

    all_keys = set().union(*(set(payload) for payload in catalogues.values()))
    errors: list[str] = []
    for locale, payload in catalogues.items():
        missing = sorted(all_keys - set(payload))
        if missing:
            errors.append(f"{locale}: missing keys {missing}")
        invalid = sorted(
            key for key, value in payload.items()
            if not isinstance(value, str) or not value.strip()
        )
        if invalid:
            errors.append(f"{locale}: empty or non-string values {invalid}")

    for key in sorted(all_keys):
        if any(key not in catalogues[locale] for locale in LOCALES):
            continue
        placeholders = {
            locale: sorted(PLACEHOLDER.findall(catalogues[locale][key]))
            for locale in LOCALES
        }
        if len({tuple(value) for value in placeholders.values()}) != 1:
            errors.append(f"{key}: placeholder mismatch {placeholders}")

    if errors:
        raise SystemExit("\n".join(errors))

    if args.write:
        for locale, payload in catalogues.items():
            (OUT / f"{locale}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    verb = "Normalized" if args.write else "Checked"
    print(
        f"{verb} {len(all_keys)} identical non-empty keys in zh-CN, en, cs; "
        f"bootstrap seed covers {len(MESSAGES)} keys"
    )


if __name__ == "__main__":
    main()
