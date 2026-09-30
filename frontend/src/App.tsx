import { CSSProperties, FormEvent, KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, Baby, BookOpen, Boxes, Check, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, CircleAlert, CircleHelp, Database, Ellipsis, ExternalLink, Eye, EyeOff, FileInput, Film, ImageIcon, LibraryBig, RefreshCw, Search, ShieldCheck, Sparkles, UserRound, X } from "lucide-react";
import { api, BrowserSessionStatus, CatalogCategory, CatalogEntity, CatalogTreeNode, Child, Creator, DatabaseTable, DatabaseTableDetail, EntityType, ReadingList, ResearchSubject, ReviewBatch, ReviewItem, ReviewSourceDocument, catalogAssetUrl } from "./api/client";
import { SourceDocumentReader } from "./components/review/SourceDocumentReader";
import { CatalogAdminEditor } from "./components/catalog/CatalogAdminEditor";

type Tab = "catalog" | "lists" | "review" | "children" | "database";
type SourceImage = { filePath: string; pageOrder?: number | null; fileName?: string | null; directlyLinked: boolean };
type ProductImage = { source_url: string; local_path?: string | null; role?: "cover" | "detail"; selected?: boolean; source_id?: number };
type ProductImageSelection = { cover: string; detailUrls: string[] };
type CatalogDraftFields = {
  displayTitle: string;
  titleEn: string;
  titleZh: string;
  aliases: string;
  author: string;
  illustrator: string;
  translator: string;
  fictionType: string;
  publisher: string;
  language: string;
  pageCount: string;
  description: string;
  officialAge: string;
  ar: string;
  lexile: string;
  lexileMin: string;
  lexileMax: string;
  cover: string;
};

const REVIEW_QUEUE_MIN = 210;
const REVIEW_MEDIA_MIN = 190;

function storedPaneWidth(key: string, fallback: number): number {
  try {
    const value = Number(window.localStorage.getItem(key));
    return Number.isFinite(value) && value > 0 ? value : fallback;
  } catch {
    return fallback;
  }
}

function storedRetailer(): "amazon" | "jd" {
  try { return window.sessionStorage.getItem("reading-map-review-retailer") === "jd" ? "jd" : "amazon"; }
  catch { return "amazon"; }
}

function inferBilingualTitle(value: string): { titleEn: string; titleZh: string; split: boolean } {
  const title = value.normalize("NFKC").replace(/\s+/g, " ").trim();
  if (!title) return { titleEn: "", titleZh: "", split: false };

  const firstHan = title.search(/[\p{Script=Han}]/u);
  if (firstHan > 0) {
    const titleEn = title.slice(0, firstHan).trim();
    const titleZh = title.slice(firstHan).trim();
    if (/[A-Za-z]/.test(titleEn) && titleZh) return { titleEn, titleZh, split: true };
  }

  const firstLatin = title.search(/[A-Za-z]/);
  if (firstLatin > 0 && /\s$/.test(title.slice(0, firstLatin))) {
    const titleZh = title.slice(0, firstLatin).trim();
    const titleEn = title.slice(firstLatin).trim();
    if (/[\p{Script=Han}]/u.test(titleZh) && titleEn) return { titleEn, titleZh, split: true };
  }

  return /[\p{Script=Han}]/u.test(title)
    ? { titleEn: "", titleZh: title, split: false }
    : { titleEn: title, titleZh: "", split: false };
}

function parentSeriesHintFromTitle(value: string): string {
  const title = value.normalize("NFKC").replace(/\s+/g, " ").trim();
  const match = title.match(/\(([^()]{2,80}?)\s*(?:系列|series)\)\s*$/i);
  return match?.[1]?.trim() || "";
}

const entityLabels: Record<EntityType, string> = {
  book: "单本",
  animation: "动画",
  reading_system: "阅读产品线",
  series: "系列",
  level: "级别",
  set: "组合",
  franchise: "IP"
};

const categoryTypeLabels: Record<CatalogCategory["category_type"], string> = {
  material_type: "Material Type · 阅读材料",
  genre: "Genre · 内容类型",
  theme: "Theme · 主题",
  topic: "Topic · 题材",
  reading_form: "Reading Form · 阅读形式",
};
const categoryTypes = Object.keys(categoryTypeLabels) as CatalogCategory["category_type"][];
const reviewEntityTypes: EntityType[] = ["book", "animation", "reading_system", "series", "level", "set", "franchise"];
const parentEntityTypes: EntityType[] = ["reading_system", "series", "level", "set", "franchise"];

type StructureNodeStatus = { key: "create" | "existing" | "suspected" | "conflict"; label: string; blocking: boolean };

function automaticResearchChoice(subject: ResearchSubject): string {
  if (subject.resolved_catalog_entity_id) return String(subject.resolved_catalog_entity_id);
  if (!subject.candidates.length) return "create";
  return "";
}

function structureNodeStatus(subject: ResearchSubject, explicitChoice?: string): StructureNodeStatus {
  if (subject.pending_conflict_count > 0) return { key: "conflict", label: "冲突", blocking: true };
  if (subject.resolved_catalog_entity_id) return { key: "existing", label: "已存在", blocking: false };
  const choice = explicitChoice || automaticResearchChoice(subject);
  if (choice === "create") return { key: "create", label: "待创建", blocking: false };
  if (choice) return { key: "existing", label: "已存在", blocking: false };
  const plausibleCount = subject.candidates.filter((candidate) => (candidate.match_score ?? 0) >= 0.82).length;
  return { key: "suspected", label: `疑似已有 ${Math.max(1, plausibleCount)}`, blocking: true };
}
type ClassificationSuggestion = { categoryType: CatalogCategory["category_type"]; code: string; confidence?: number | null; reason?: string | null; source?: string | null };

function factValue(facts: Record<string, unknown> | null | undefined, key: string): unknown {
  const entry = asRecord(facts?.[key]);
  return "value" in entry ? entry.value : facts?.[key];
}

function draftText(value: unknown): string {
  if (value == null) return "";
  return Array.isArray(value) ? value.join(", ") : String(value);
}

const languageOptions = [
  { value: "zh", label: "中文" },
  { value: "en", label: "英文" },
  { value: "zh-en", label: "中英双语" },
];

function normalizeLanguageCode(value: unknown): string {
  const normalized = draftText(value).normalize("NFKC").trim().toLowerCase();
  const compact = normalized.replace(/[\s_-]+/g, "");
  if (!normalized) return "";
  if (normalized.includes("中英") || normalized.includes("双语") || normalized.includes("bilingual") || compact === "zhen" || compact === "enzh") return "zh-en";
  if (["en", "eng", "english", "英文", "英语", "英語"].includes(normalized)) return "en";
  if (["zh", "zho", "chi", "chinese", "中文", "汉语", "漢語"].includes(normalized)) return "zh";
  return "";
}

function catalogDraftFromSubject(subject: ResearchSubject | null): CatalogDraftFields {
  if (!subject) return { displayTitle: "", titleEn: "", titleZh: "", aliases: "", author: "", illustrator: "", translator: "", fictionType: "unknown", publisher: "", language: "", pageCount: "", description: "", officialAge: "", ar: "", lexile: "", lexileMin: "", lexileMax: "", cover: "" };
  const inferred = inferBilingualTitle(subject.proposed_display_title || "");
  const facts = subject.facts_json;
  const titleEn = subject.proposed_title_en == null ? inferred.titleEn : subject.proposed_title_en.trim();
  const titleZh = subject.proposed_title_zh == null ? inferred.titleZh : subject.proposed_title_zh.trim();
  const capturedLanguage = normalizeLanguageCode(factValue(facts, "language"));
  return {
    displayTitle: subject.proposed_display_title || "",
    titleEn,
    titleZh,
    aliases: (subject.proposed_aliases || []).join("，"),
    author: draftText(factValue(facts, "author")),
    illustrator: draftText(factValue(facts, "illustrator")),
    translator: draftText(factValue(facts, "translator")),
    fictionType: draftText(factValue(facts, "fiction_type")) || "unknown",
    publisher: draftText(factValue(facts, "publisher")),
    language: capturedLanguage || (titleEn ? "en" : titleZh ? "zh" : ""),
    pageCount: draftText(factValue(facts, "page_count")),
    description: draftText(factValue(facts, "description")),
    officialAge: draftText(factValue(facts, "official_age")),
    ar: draftText(factValue(facts, "ar")),
    lexile: draftText(factValue(facts, "lexile")),
    lexileMin: draftText(factValue(facts, "lexile_min")),
    lexileMax: draftText(factValue(facts, "lexile_max")),
    cover: draftText(factValue(facts, "cover")),
  };
}

function productImageSelectionFromSubject(subject: ResearchSubject | null): ProductImageSelection {
  if (!subject) return { cover: "", detailUrls: [] };
  const facts = subject.facts_json || {};
  const entry = asRecord(facts.product_images);
  const images = (Array.isArray(entry.value) ? entry.value : []).map(asRecord).filter((image) => typeof image.source_url === "string") as ProductImage[];
  return {
    cover: draftText(factValue(facts, "cover")) || images.find((image) => image.role === "cover")?.source_url || images[0]?.source_url || "",
    detailUrls: images.filter((image) => image.selected !== false).map((image) => image.source_url),
  };
}

function productImageSelectionKey(value: ProductImageSelection): string {
  return JSON.stringify([value.cover, value.detailUrls]);
}

function changedDraftFacts(subject: ResearchSubject, draft: CatalogDraftFields): { factValues: Record<string, unknown>; clearFactKeys: string[] } {
  const initial = catalogDraftFromSubject(subject);
  const values: Array<[string, keyof CatalogDraftFields, string]> = [
    ["author", "author", draft.author],
    ["illustrator", "illustrator", draft.illustrator],
    ["translator", "translator", draft.translator],
    ["fiction_type", "fictionType", draft.fictionType],
    ["language", "language", draft.language],
    ["description", "description", draft.description],
    ["official_age", "officialAge", draft.officialAge],
    ["ar", "ar", draft.ar],
    ["lexile", "lexile", draft.lexile],
    ["lexile_min", "lexileMin", draft.lexileMin],
    ["lexile_max", "lexileMax", draft.lexileMax],
  ];
  const factValues: Record<string, unknown> = {};
  const clearFactKeys: string[] = [];
  values.forEach(([key, field, rawValue]) => {
    const value = rawValue.trim();
    if (value === String(initial[field] || "").trim()) return;
    if (!value) {
      clearFactKeys.push(key);
      return;
    }
    factValues[key] = ["lexile_min", "lexile_max"].includes(key) ? Number(value) : value;
  });
  return { factValues, clearFactKeys };
}

function draftIdentityPayload(draft: CatalogDraftFields, proposalType: EntityType | "") {
  return {
    proposed_display_title: draft.displayTitle.trim(),
    proposed_title_en: draft.titleEn.trim(),
    proposed_title_zh: draft.titleZh.trim(),
    proposed_aliases: draft.aliases.split(/[，,\n]/).map((value) => value.trim()).filter(Boolean),
    proposed_entity_type: proposalType || null,
  };
}

/* Kept centralized so the main item and both structure inspectors save with
   exactly the same conflict-safe semantics. */
function reviewDraftPayload(subject: ResearchSubject, draft: CatalogDraftFields, proposalType: EntityType | "", expectedVersion: number) {
  const { factValues, clearFactKeys } = changedDraftFacts(subject, draft);
  return {
    expected_version: expectedVersion,
    ...draftIdentityPayload(draft, proposalType),
    fact_values: factValues,
    clear_fact_keys: clearFactKeys,
  };
}

function classificationSuggestions(value: unknown): ClassificationSuggestion[] {
  const classification = asRecord(asRecord(value).classification);
  return categoryTypes.flatMap((categoryType) => {
    const proposals = classification[categoryType];
    if (!Array.isArray(proposals)) return [];
    return proposals.flatMap((proposal) => {
      const row = asRecord(proposal);
      return typeof row.code === "string" ? [{
        categoryType,
        code: row.code,
        confidence: typeof row.confidence === "number" ? row.confidence : null,
        reason: typeof row.reason === "string" ? row.reason : null,
        source: typeof row.source === "string" ? row.source : null,
      }] : [];
    });
  });
}

function withoutClassification(value: unknown): Record<string, unknown> {
  const result = { ...asRecord(value) };
  delete result.classification;
  return result;
}

function entityTypeInference(subject: ResearchSubject): { reason: string; confidence?: number } {
  const inference = asRecord(asRecord(subject.ai_inferences_json).entity_type);
  return {
    reason: typeof inference.reason === "string" && inference.reason.trim()
      ? inference.reason
      : "Research 建议仅供审核：移除年龄、难度和分级定位后仍自然成套的作品倾向“系列”；主要按阅读阶段组织的产品体系倾向“阅读产品线”。",
    confidence: typeof inference.confidence === "number" ? inference.confidence : undefined,
  };
}

function collectionBrief(subject: ResearchSubject) {
  const facts = subject.facts_json;
  return {
    description: draftText(factValue(facts, "description") || factValue(facts, "official_positioning")),
    publisher: draftText(factValue(facts, "publisher")),
    audience: draftText(factValue(facts, "official_age") || factValue(facts, "reading_age") || factValue(facts, "target_readers")),
  };
}

export function AdminApp() {
  const exploreMatch = window.location.pathname.match(/^\/admin\/collection-explore\/(\d+)\/?$/);
  return exploreMatch ? <CollectionExploreView subjectId={Number(exploreMatch[1])} /> : <AdminWorkspace />;
}

function AdminWorkspace() {
  const [tab, setTab] = useState<Tab>(() => window.location.pathname.startsWith("/admin/database") ? "database" : window.location.pathname.startsWith("/admin/catalog") ? "catalog" : "review");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [entities, setEntities] = useState<CatalogEntity[]>([]);
  const [creators, setCreators] = useState<Creator[]>([]);
  const [lists, setLists] = useState<ReadingList[]>([]);
  const [children, setChildren] = useState<Child[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    setBusy(true);
    setError("");
    try {
      const [nextEntities, nextCreators, nextLists, nextChildren] = await Promise.all([
        api.entities(), api.creators(), api.readingLists(), api.children()
      ]);
      setEntities(nextEntities);
      setCreators(nextCreators);
      setLists(nextLists);
      setChildren(nextChildren);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "加载失败");
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { void load(); }, []);

  const counts = useMemo(() => ({
    book: entities.filter((item) => item.entity_type === "book").length,
    animation: entities.filter((item) => item.entity_type === "animation").length,
    collection: entities.filter((item) => ["reading_system", "series", "level", "set"].includes(item.entity_type)).length
  }), [entities]);

  async function runSearch(event: FormEvent) {
    event.preventDefault();
    if (!query.trim()) return void load();
    setBusy(true);
    try { setEntities(await api.search(query)); setError(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "搜索失败"); }
    finally { setBusy(false); }
  }

  function selectTab(nextTab: Tab) {
    setTab(nextTab);
    setSidebarCollapsed(nextTab === "review" || nextTab === "database");
    if (nextTab === "database") window.history.replaceState(null, "", `/admin/database${window.location.search}`);
    else if (window.location.pathname.startsWith("/admin/database") || window.location.pathname.startsWith("/admin/catalog/")) {
      window.history.replaceState(null, "", `/admin${window.location.search}`);
      window.dispatchEvent(new PopStateEvent("popstate"));
    }
  }

  return (
    <main className={`admin-shell${sidebarCollapsed ? " sidebar-collapsed" : ""}`}>
      <aside aria-label="管理后台侧栏">
        <button className="sidebar-toggle" type="button" aria-label={sidebarCollapsed ? "展开侧栏" : "收起侧栏"} title={sidebarCollapsed ? "展开侧栏" : "收起侧栏"} onClick={() => setSidebarCollapsed((current) => !current)}>
          {sidebarCollapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
        <div className="brand"><span><LibraryBig size={22} /></span><div className="brand-copy"><strong>Reading Map</strong><small>Admin workspace</small></div></div>
        <nav aria-label="管理后台">
          <button title="内容目录" className={tab === "catalog" ? "active" : ""} onClick={() => selectTab("catalog")}><Boxes size={18} /><span>内容目录</span></button>
          <button title="达人书单" className={tab === "lists" ? "active" : ""} onClick={() => selectTab("lists")}><Sparkles size={18} /><span>达人书单</span></button>
          <button title="审核工作台" className={tab === "review" ? "active" : ""} onClick={() => selectTab("review")}><ShieldCheck size={18} /><span>审核工作台</span></button>
          <button title="儿童画像" className={tab === "children" ? "active" : ""} onClick={() => selectTab("children")}><Baby size={18} /><span>儿童画像</span></button>
          <button title="数据库浏览" className={tab === "database" ? "active" : ""} onClick={() => selectTab("database")}><Database size={18} /><span>数据库浏览</span></button>
        </nav>
        <a className="admin-product-link" href="/map" title="进入前台地图"><ExternalLink size={14} /><span>进入前台地图</span></a>
        <a className="admin-product-link" href="/django-admin/" title="Django 管理后台"><ExternalLink size={14} /><span>Django 管理后台</span></a>
        <a className="admin-product-link" href="/account" title="我的账号 / 退出"><UserRound size={14} /><span>我的账号 / 退出</span></a>
        <div className="schema-note">统一 ID · 可递归 Collection<br />年龄以月保存 · 未知值保持为空</div>
      </aside>

      <section className={`workspace${tab === "review" ? " review-mode" : ""}`}>
        <header>
          <div><p className="eyebrow">童书与学习资源</p><h1>{tab === "catalog" ? "Catalog" : tab === "lists" ? "达人推荐路径" : tab === "review" ? "Research 与审核" : tab === "database" ? "数据库浏览" : "儿童基础画像"}</h1></div>
          <span className="status">{busy ? "同步中…" : "Catalog v1 已连接"}</span>
        </header>
        {error ? <div className="error">{error}</div> : null}
        {tab === "catalog" ? <CatalogView entities={entities} counts={counts} query={query} setQuery={setQuery} onSearch={runSearch} onCreated={load} /> : null}
        {tab === "lists" ? <ListsView creators={creators} lists={lists} onCreated={load} /> : null}
        {tab === "review" ? <ReviewView lists={lists} onResolved={load} /> : null}
        {tab === "children" ? <ChildrenView children={children} onCreated={load} /> : null}
        {tab === "database" ? <DatabaseView /> : null}
      </section>
    </main>
  );
}

export const App = AdminApp;

function CollectionExploreView({ subjectId }: { subjectId: number }) {
  const [subject, setSubject] = useState<ResearchSubject | null>(null);
  const [related, setRelated] = useState<ResearchSubject[]>([]);
  const [entityType, setEntityType] = useState<EntityType | "">("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setSubject(null); setRelated([]); setError("");
    void api.researchSubject(subjectId).then(async (next) => {
      if (!active) return;
      setSubject(next);
      setEntityType(next.proposed_entity_type || "");
      const relatedIds = [...new Set(next.relations.flatMap((relation) => [relation.parent_subject_id, relation.member_subject_id]).filter((id) => id !== next.id))];
      const nextRelated = await Promise.all(relatedIds.map((id) => api.researchSubject(id)));
      if (active) setRelated(nextRelated);
    }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "系列探索加载失败"); });
    return () => { active = false; };
  }, [subjectId]);

  async function saveType() {
    if (!subject || !entityType || entityType === subject.proposed_entity_type) return;
    setSaving(true); setError("");
    try {
      const updated = await api.updateResearchSubject(subject.id, { proposed_entity_type: entityType });
      setSubject(updated);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "对象类型保存失败"); }
    finally { setSaving(false); }
  }

  if (error && !subject) return <main className="collection-explore-page"><div className="collection-explore-state"><CircleAlert size={30} /><h1>系列探索</h1><p>{error}</p><a href="/admin">返回审核工作台</a></div></main>;
  if (!subject) return <main className="collection-explore-page"><div className="collection-explore-state"><RefreshCw className="spin" size={26} /><p>正在打开系列探索…</p></div></main>;

  const brief = collectionBrief(subject);
  const inference = entityTypeInference(subject);
  const facts = subject.facts_json || {};
  const relations = subject.relations.filter((relation) => relation.relation_type === "contains" && relation.review_status !== "rejected");
  const parentIds = new Set(relations.filter((relation) => relation.member_subject_id === subject.id).map((relation) => relation.parent_subject_id));
  const memberIds = new Set(relations.filter((relation) => relation.parent_subject_id === subject.id).map((relation) => relation.member_subject_id));
  const parents = related.filter((row) => parentIds.has(row.id));
  const members = related.filter((row) => memberIds.has(row.id));
  const productImages = factValue(facts, "product_images");
  const detailImages = factValue(facts, "detail_images");
  const coverImage = factValue(facts, "cover");
  const visualAssets = [...new Map([
    ...(typeof coverImage === "string" ? [{ source_url: coverImage }] : []),
    ...(Array.isArray(productImages) ? productImages : []),
    ...(Array.isArray(detailImages) ? detailImages : []),
  ].flatMap((value) => {
    const row = asRecord(value);
    const sourceUrl = typeof row.source_url === "string" ? row.source_url : "";
    return sourceUrl ? [[sourceUrl, sourceUrl] as const] : [];
  })).values()];

  const renderDiscovery = (item: ResearchSubject, relationLabel: string) => <article key={item.id}>
    <span className={`explore-entity-icon ${item.proposed_entity_type || "series"}`}><LibraryBig size={17} /></span>
    <div><strong>{item.proposed_display_title}</strong><small>{relationLabel} · {item.proposed_entity_type ? entityLabels[item.proposed_entity_type] : "类型待确认"}</small></div>
    <a href={`/admin/collection-explore/${item.id}`} target="_blank" rel="noreferrer">系列探索 <ExternalLink size={12} /></a>
  </article>;

  return <main className="collection-explore-page">
    <header className="collection-explore-topbar"><a href="/admin"><ArrowLeft size={15} />审核工作台</a><span>Research workspace · 不直接写入正式 Catalog</span></header>
    <div className="collection-explore-layout">
      <section className="collection-explore-hero">
        <div className={`collection-explore-emblem ${subject.proposed_entity_type || "series"}`}><LibraryBig size={34} /></div>
        <div><p className="eyebrow">系列探索</p><h1>{subject.proposed_display_title}</h1><p>{brief.description || "这个对象的深入资料仍在积累中。系列探索会逐步整理定位、适用读者、上下级结构和官方资料。"}</p></div>
        <div className="collection-explore-type">
          <label><span>对象类型</span><select value={entityType} disabled={saving} onChange={(event) => setEntityType(event.target.value as EntityType)}>{reviewEntityTypes.map((value) => <option key={value} value={value}>{entityLabels[value]}</option>)}</select></label>
          <button type="button" disabled={saving || !entityType || entityType === subject.proposed_entity_type} onClick={() => void saveType()}>{saving ? "保存中…" : "保存类型"}</button>
          <details><summary>查看判断依据</summary><p>{inference.reason}</p></details>
        </div>
      </section>

      {error ? <div className="review-error"><CircleAlert size={16} />{error}</div> : null}
      <section className="explore-overview-grid">
        <article><small>PUBLISHER</small><strong>{brief.publisher || "待研究"}</strong><p>出版社与官方品牌归属</p></article>
        <article><small>POSITIONING</small><strong>{draftText(factValue(facts, "official_positioning")) || (subject.proposed_entity_type === "reading_system" ? "阅读阶段产品线" : "待研究")}</strong><p>为什么存在、官方如何定位</p></article>
        <article><small>FOR WHOM</small><strong>{brief.audience || "待研究"}</strong><p>目标年龄、年级或阅读阶段</p></article>
      </section>

      <section className="explore-panel explore-structure-panel">
        <header><div><small>STRUCTURE</small><h2>它属于谁？下面有什么？</h2></div><span>{parents.length} 个父级 · {members.length} 个直接成员</span></header>
        {parents.length || members.length ? <div className="explore-discoveries">
          {parents.map((item) => renderDiscovery(item, "直接父级"))}
          {members.map((item) => renderDiscovery(item, "直接成员"))}
        </div> : <p className="explore-empty">尚未发现可确认的直接结构。这里始终只展示直接 membership，不推导祖先关系。</p>}
      </section>

      <section className="explore-panel explore-sources-panel">
        <header><div><small>RESEARCH MATERIALS</small><h2>研究资料</h2></div><button type="button" disabled title="本版先预留统一入口">+ 补充研究资料</button></header>
        <p className="explore-panel-note">后续可在这里统一加入 URL、图片、PDF 或文字，并保留原始资料进入同一 Research Pipeline。</p>
        {subject.sources.length ? <div className="explore-source-list">{subject.sources.map((source) => <a key={source.id} href={source.source_url} target="_blank" rel="noreferrer"><FileInput size={15} /><span><strong>{source.source_title || source.source_url}</strong><small>{source.source_type || "Research source"}</small></span><ExternalLink size={13} /></a>)}</div> : <p className="explore-empty">尚未关联研究来源。</p>}
      </section>

      <section className="explore-panel explore-visual-panel">
        <header><div><small>VISUAL MATERIALS</small><h2>视觉资料</h2></div><span>原图会与提取结果一起保留</span></header>
        {visualAssets.length ? <div className="explore-visual-grid">{visualAssets.map((url) => <a key={url} href={url} target="_blank" rel="noreferrer"><img src={url} alt={`${subject.proposed_display_title} 研究资料`} /></a>)}</div> : <div className="explore-visual-placeholder"><ImageIcon size={28} /><strong>视觉资料区域已预留</strong><p>选书指南、出版社图表、brochure 与 PDF 页面图像将显示在这里。</p></div>}
      </section>
    </div>
  </main>;
}

function CatalogView({ entities, counts, query, setQuery, onSearch, onCreated }: {
  entities: CatalogEntity[]; counts: { book: number; animation: number; collection: number }; query: string;
  setQuery: (value: string) => void; onSearch: (event: FormEvent) => void; onCreated: () => Promise<void>;
}) {
  const [title, setTitle] = useState("");
  const [type, setType] = useState<EntityType>("book");
  const [view, setView] = useState<"books" | "animation" | "structure">("books");
  const [selectedEntityId, setSelectedEntityId] = useState<number | null>(() => {
    const match = window.location.pathname.match(/^\/admin\/catalog\/(\d+)\/?$/);
    return match ? Number(match[1]) : null;
  });
  useEffect(() => {
    const syncPath = () => {
      const match = window.location.pathname.match(/^\/admin\/catalog\/(\d+)\/?$/);
      setSelectedEntityId(match ? Number(match[1]) : null);
    };
    window.addEventListener("popstate", syncPath);
    return () => window.removeEventListener("popstate", syncPath);
  }, []);
  const visibleEntities = useMemo(() => entities.filter((entity) => {
    if (view === "books") return entity.entity_type === "book";
    if (view === "animation") return entity.entity_type === "animation";
    return ["reading_system", "series", "level", "set", "franchise"].includes(entity.entity_type);
  }), [entities, view]);

  function openEntity(entity: CatalogEntity) {
    window.history.pushState(null, "", `/admin/catalog/${entity.id}${window.location.search}`);
    setSelectedEntityId(entity.id);
  }

  function closeDetail() {
    window.history.pushState(null, "", `/admin${window.location.search}`);
    setSelectedEntityId(null);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    await api.createEntity({ entity_type: type, display_title: title.trim() });
    setTitle("");
    await onCreated();
  }
  if (selectedEntityId != null) return <CatalogDetailView entityId={selectedEntityId} fallbackEntity={entities.find((entity) => entity.id === selectedEntityId)} onBack={closeDetail} />;
  return <>
    <div className="stats catalog-stats"><button type="button" className={view === "books" ? "active" : ""} aria-pressed={view === "books"} onClick={() => setView("books")}><BookOpen /><div><strong>{counts.book}</strong><span>作品目录 · 单本</span></div></button><button type="button" className={view === "animation" ? "active" : ""} aria-pressed={view === "animation"} onClick={() => setView("animation")}><Film /><div><strong>{counts.animation}</strong><span>动画内容 · 动画</span></div></button><button type="button" className={view === "structure" ? "active" : ""} aria-pressed={view === "structure"} onClick={() => setView("structure")}><Boxes /><div><strong>{counts.collection}</strong><span>系列结构 · 阅读产品线 / 系列 / 级别 / 组合</span></div></button></div>
    <div className="toolbar"><form className="search" onSubmit={onSearch}><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索中英文标题或 Alias" /></form><form className="quick-add" onSubmit={submit}><select value={type} onChange={(event) => setType(event.target.value as EntityType)}>{Object.entries(entityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="新内容标题" /><button>添加</button></form></div>
    <div className="entity-grid">{visibleEntities.map((entity) => <button type="button" className="entity-card" key={entity.id} onClick={() => openEntity(entity)} aria-label={`打开 ${entity.display_title} 详情`}>{entity.cover_url ? <img className="entity-cover" src={entity.cover_url} alt="" loading="lazy" /> : <div className={`entity-mark ${entity.entity_type}`}>{entity.display_title.slice(0, 1).toUpperCase()}</div>}<div className="entity-body"><div className="entity-heading"><span className="badge">{entityLabels[entity.entity_type]}</span><small>#{entity.id}</small></div><h2>{entity.display_title}</h2><p>{entity.work?.author_text || entity.title_en || entity.title_zh || "等待补充 Catalog 事实"}</p><footer>{entity.work?.lexile_code ? <span>Lexile {entity.work.lexile_code}</span> : entity.lexile_min != null && entity.lexile_max != null ? <span>Lexile {entity.lexile_min}–{entity.lexile_max}L</span> : null}{entity.work?.ar_level ? <span>AR {entity.work.ar_level}</span> : null}<span>{entity.independent_reading_suitable == null ? "自主阅读未知" : entity.independent_reading_suitable ? "适合自主阅读" : "不标作自主阅读"}</span></footer></div></button>)}</div>
    {!visibleEntities.length ? <div className="empty">{view === "books" ? "还没有可展示的单本作品。" : view === "animation" ? "还没有动画内容。" : "还没有系列结构。"}</div> : null}
  </>;
}

function flattenCatalogTree(node: CatalogTreeNode): CatalogTreeNode[] {
  return [node, ...node.children.flatMap(flattenCatalogTree)];
}

function CatalogCover({ entity, className = "" }: { entity: CatalogEntity; className?: string }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [entity.cover_url]);
  return <div className={`catalog-cover ${className}`}>
    <div className={`catalog-cover-fallback ${entity.entity_type}`}><BookOpen size={30} /><strong>{entity.display_title}</strong><small>{entity.work?.author_text || entityLabels[entity.entity_type]}</small></div>
    {entity.cover_url && !failed ? <img src={entity.cover_url} alt={`${entity.display_title} 封面`} loading="eager" onError={() => setFailed(true)} /> : null}
  </div>;
}

function CatalogDetailView({ entityId, fallbackEntity, onBack }: { entityId: number; fallbackEntity?: CatalogEntity; onBack: () => void }) {
  const [entity, setEntity] = useState<CatalogEntity | null>(fallbackEntity ?? null);
  const [books, setBooks] = useState<CatalogEntity[]>([]);
  const [loading, setLoading] = useState(true);
  const [visibilityBusy, setVisibilityBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setEntity(fallbackEntity?.id === entityId ? fallbackEntity : null);
    setBooks([]);
    setLoading(true);
    setError("");
    void api.entity(entityId).then(async (nextEntity) => {
      if (!active) return;
      setEntity(nextEntity);
      if (!["reading_system", "series", "level", "set", "franchise"].includes(nextEntity.entity_type)) {
        setBooks([]);
        return;
      }
      const tree = await api.collection(entityId);
      const bookIds = [...new Set(flattenCatalogTree(tree).filter((node) => node.entity_type === "book").map((node) => node.id))];
      const nextBooks = await Promise.all(bookIds.map((id) => api.entity(id)));
      if (active) setBooks(nextBooks);
    }).catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "详情加载失败"); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [entityId, fallbackEntity]);

  if (loading && !entity) return <div className="catalog-detail-state" role="status">正在加载详情…</div>;
  if (error || !entity) return <div className="catalog-detail-state"><p role="alert">{error || "没有找到这个 Catalog 对象。"}</p><button type="button" onClick={onBack}><ArrowLeft size={16} />返回目录</button></div>;
  const heroCover = entity.cover_url ? entity : books[0] ?? entity;
  const lexile = entity.work?.lexile_code || (entity.lexile_min != null && entity.lexile_max != null ? `${entity.lexile_min}–${entity.lexile_max}L` : "未收录");
  async function toggleBookshelf() {
    if (!entity) return;
    setVisibilityBusy(true);
    setError("");
    try { setEntity(await api.updateEntityBookshelf(entity.id, !entity.bookshelf_visible)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Bookshelf 状态更新失败"); }
    finally { setVisibilityBusy(false); }
  }
  return <article className="catalog-detail">
    <button className="catalog-back" type="button" onClick={onBack}><ArrowLeft size={16} />返回 Catalog</button>
    <section className="catalog-detail-hero">
      <CatalogCover entity={heroCover} className="catalog-detail-cover" />
      <div><div className="catalog-detail-kicker"><span className="badge">{entityLabels[entity.entity_type]}</span><small>Catalog #{entity.id}</small><button type="button" className={`catalog-bookshelf-toggle${entity.bookshelf_visible ? " visible" : ""}`} disabled={visibilityBusy} aria-pressed={entity.bookshelf_visible} onClick={() => void toggleBookshelf()}>{entity.bookshelf_visible ? <Eye size={14} /> : <EyeOff size={14} />}Bookshelf · {visibilityBusy ? "保存中…" : entity.bookshelf_visible ? "显示" : "隐藏"}</button></div><h2>{entity.display_title}</h2>{entity.title_zh && entity.title_zh !== entity.display_title ? <p className="catalog-detail-subtitle">{entity.title_zh}</p> : null}<p>{entity.description || "暂无内容介绍。"}</p><div className="catalog-detail-meta">{entity.entity_type !== "animation" ? <span>Lexile {lexile}</span> : <span>内容类型 动画</span>}{entity.work?.author_text ? <span>作者 {entity.work.author_text}</span> : null}{entity.editions[0]?.page_count ? <span>{entity.editions[0].page_count} 页</span> : null}{entity.volume_count ? <span>{entity.volume_count} 册</span> : null}</div></div>
    </section>
    {entity.entity_type === "book" ? <section className="catalog-facts"><h3>作品资料</h3><dl><div><dt>英文标题</dt><dd>{entity.title_en || "—"}</dd></div><div><dt>中文标题</dt><dd>{entity.title_zh || "—"}</dd></div><div><dt>ISBN</dt><dd>{entity.isbns.map((isbn) => isbn.isbn_val).join("、") || "—"}</dd></div><div><dt>自主阅读</dt><dd>{entity.independent_reading_suitable == null ? "待评估" : entity.independent_reading_suitable ? "适合" : "不适合"}</dd></div></dl></section> : entity.entity_type === "animation" ? <section className="catalog-facts"><h3>动画资料</h3><dl><div><dt>英文标题</dt><dd>{entity.title_en || "—"}</dd></div><div><dt>中文标题</dt><dd>{entity.title_zh || "—"}</dd></div><div><dt>对象类型</dt><dd>动画</dd></div><div><dt>Bookshelf</dt><dd>{entity.bookshelf_visible ? "显示" : "隐藏"}</dd></div></dl></section> : <section className="catalog-volume-section"><div className="catalog-section-heading"><div><p className="eyebrow">INCLUDED BOOKS</p><h3>收录作品</h3></div><span>{books.length} 本</span></div>{books.length ? <div className="catalog-book-grid">{books.map((book) => <button type="button" key={book.id} onClick={() => { window.history.pushState(null, "", `/admin/catalog/${book.id}${window.location.search}`); window.dispatchEvent(new PopStateEvent("popstate")); }}><CatalogCover entity={book} /><strong>{book.display_title}</strong><small>{book.work?.author_text || "作者待补充"}</small></button>)}</div> : <div className="empty">这个结构下还没有直接或间接关联的单本作品。</div>}</section>}
    {entity.categories.length ? <div className="catalog-detail-tags">{entity.categories.map((category) => <span key={category.id}>{category.name_zh}</span>)}</div> : null}
    <CatalogAdminEditor entity={entity} onUpdated={setEntity} />
  </article>;
}

function ListsView({ creators, lists, onCreated }: { creators: Creator[]; lists: ReadingList[]; onCreated: () => Promise<void> }) {
  const [creatorName, setCreatorName] = useState("");
  const [listTitle, setListTitle] = useState("");
  const [creatorId, setCreatorId] = useState("");
  async function addCreator(event: FormEvent) { event.preventDefault(); if (!creatorName.trim()) return; await api.createCreator({ name: creatorName.trim() }); setCreatorName(""); await onCreated(); }
  async function addList(event: FormEvent) { event.preventDefault(); if (!listTitle.trim() || !creatorId) return; await api.createReadingList({ creator_id: Number(creatorId), title: listTitle.trim() }); setListTitle(""); await onCreated(); }
  return <><div className="split-forms"><form className="panel" onSubmit={addCreator}><h2>新增达人</h2><input value={creatorName} onChange={(event) => setCreatorName(event.target.value)} placeholder="姓名" /><button>保存达人</button></form><form className="panel" onSubmit={addList}><h2>新增书单</h2><select value={creatorId} onChange={(event) => setCreatorId(event.target.value)}><option value="">选择达人</option>{creators.map((creator) => <option key={creator.id} value={creator.id}>{creator.name}</option>)}</select><input value={listTitle} onChange={(event) => setListTitle(event.target.value)} placeholder="书单标题" /><button>保存书单</button></form></div><div className="list-stack">{lists.map((list) => <article key={list.id}><div><span className="badge">{list.creator_name}</span><h2>{list.title}</h2><p>{list.stage_label || "未设置阶段"} · {list.age_min_months == null ? "月龄未知" : `${list.age_min_months}–${list.age_max_months ?? "?"} 月`}</p></div><strong>{list.items.length}<small> 项推荐</small></strong></article>)}</div>{!lists.length ? <div className="empty">还没有达人书单。</div> : null}</>;
}

function ChildrenView({ children, onCreated }: { children: Child[]; onCreated: () => Promise<void> }) {
  const [name, setName] = useState("");
  const [birthDate, setBirthDate] = useState("");
  async function submit(event: FormEvent) { event.preventDefault(); if (!name.trim()) return; await api.createChild({ name: name.trim(), birth_date: birthDate || undefined }); setName(""); setBirthDate(""); await onCreated(); }
  return <><form className="panel child-form" onSubmit={submit}><h2>建立基础身份</h2><input value={name} onChange={(event) => setName(event.target.value)} placeholder="孩子昵称" /><input type="date" value={birthDate} onChange={(event) => setBirthDate(event.target.value)} /><button>保存</button><p>年龄由出生日期实时计算；能力未知时不会默认填 5.0。</p></form><div className="children-grid">{children.map((child) => <article key={child.id}><span><UserRound /></span><h2>{child.name}</h2><p>{child.birth_date || "出生日期未填写"}</p><small>中文、英文能力可分别记录</small></article>)}</div></>;
}

function DatabaseView() {
  const requestedTable = new URLSearchParams(window.location.search).get("table");
  const [tables, setTables] = useState<DatabaseTable[]>([]);
  const [vendor, setVendor] = useState("");
  const [selectedTable, setSelectedTable] = useState(requestedTable || "");
  const [detail, setDetail] = useState<DatabaseTableDetail | null>(null);
  const [filter, setFilter] = useState("");
  const [mode, setMode] = useState<"data" | "structure">("data");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadTables(preferred = selectedTable) {
    const result = await api.databaseTables();
    setTables(result.tables);
    setVendor(result.vendor);
    const next = result.tables.some((table) => table.name === preferred) ? preferred : result.tables[0]?.name || "";
    setSelectedTable(next);
  }

  useEffect(() => {
    void loadTables().catch((reason) => setError(reason instanceof Error ? reason.message : "数据表加载失败"));
  }, []);

  useEffect(() => {
    let active = true;
    if (!selectedTable) { setDetail(null); return () => { active = false; }; }
    setLoading(true);
    setError("");
    window.history.replaceState(null, "", `/admin/database?table=${encodeURIComponent(selectedTable)}`);
    void api.databaseTable(selectedTable, page, pageSize)
      .then((result) => { if (active) setDetail(result); })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "数据读取失败"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [selectedTable, page, pageSize]);

  const visibleTables = tables.filter((table) => table.name.toLocaleLowerCase().includes(filter.trim().toLocaleLowerCase()));

  function chooseTable(name: string) {
    setSelectedTable(name);
    setPage(1);
    setMode("data");
  }

  return <section className="database-browser">
    <aside className="database-table-list">
      <header><div><strong>{vendor ? vendor.toUpperCase() : "DATABASE"}</strong><small>{tables.length} 张数据表</small></div><button type="button" title="刷新数据表" onClick={() => void loadTables().catch((reason) => setError(String(reason)))}><RefreshCw size={15} /></button></header>
      <label className="database-filter"><Search size={14} /><input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="筛选数据表" /></label>
      <div className="database-table-buttons">{visibleTables.map((table) => <button type="button" key={table.name} className={selectedTable === table.name ? "active" : ""} onClick={() => chooseTable(table.name)}><span>{table.name}</span><small>{table.row_count}</small></button>)}</div>
    </aside>
    <div className="database-table-panel">
      {!selectedTable ? <div className="empty">当前数据库没有可浏览的数据表。</div> : <>
        <header className="database-table-header"><div><p>{detail?.table_type === "view" ? "VIEW" : "TABLE"}</p><h2>{selectedTable}</h2></div><div className="database-table-summary"><strong>{detail?.total_rows ?? tables.find((table) => table.name === selectedTable)?.row_count ?? 0}</strong><span>行数据</span></div></header>
        <div className="database-mode-tabs"><button type="button" className={mode === "data" ? "active" : ""} onClick={() => setMode("data")}>数据</button><button type="button" className={mode === "structure" ? "active" : ""} onClick={() => setMode("structure")}>结构</button><span>{loading ? "读取中…" : "只读模式"}</span></div>
        {error ? <div className="error">{error}</div> : null}
        {detail && mode === "data" ? <>
          <div className="database-grid-wrap"><table className="database-grid"><thead><tr>{detail.columns.map((column) => <th key={column.name}><span>{column.name}</span><small>{column.data_type}{column.primary_key ? " · PK" : ""}</small></th>)}</tr></thead><tbody>{detail.rows.map((row, index) => <tr key={index}>{detail.columns.map((column) => <td key={column.name} className={row[column.name] == null ? "null" : ""}>{row[column.name] == null ? "NULL" : typeof row[column.name] === "boolean" ? row[column.name] ? "true" : "false" : String(row[column.name])}</td>)}</tr>)}</tbody></table>{!detail.rows.length ? <div className="database-empty-rows">这张表暂无数据</div> : null}</div>
          <footer className="database-pagination"><label>每页<select value={pageSize} onChange={(event) => { setPageSize(Number(event.target.value)); setPage(1); }}><option value="10">10</option><option value="25">25</option><option value="50">50</option><option value="100">100</option></select></label><span>第 {detail.page} / {detail.total_pages} 页</span><button type="button" disabled={detail.page <= 1 || loading} onClick={() => setPage((current) => current - 1)}>上一页</button><button type="button" disabled={detail.page >= detail.total_pages || loading} onClick={() => setPage((current) => current + 1)}>下一页</button></footer>
        </> : null}
        {detail && mode === "structure" ? <div className="database-grid-wrap"><table className="database-grid database-structure-grid"><thead><tr><th>字段</th><th>类型</th><th>允许 NULL</th><th>键</th><th>默认值</th></tr></thead><tbody>{detail.columns.map((column) => <tr key={column.name}><td><strong>{column.name}</strong>{column.sensitive ? <small>敏感内容已隐藏</small> : null}</td><td>{column.data_type}</td><td>{column.nullable ? "是" : "否"}</td><td>{column.primary_key ? "PRIMARY" : column.foreign_key ? `FK → ${column.foreign_key}` : "—"}</td><td>{column.default == null ? "NULL" : String(column.default)}</td></tr>)}</tbody></table></div> : null}
      </>}
    </div>
  </section>;
}

function ReviewView({ lists, onResolved }: { lists: ReadingList[]; onResolved: () => Promise<void> }) {
  const workbenchRef = useRef<HTMLDivElement>(null);
  const detailRef = useRef<HTMLElement>(null);
  const officialStructureAutoSelectRef = useRef("");
  const parentResearchAutoRef = useRef("");
  const classificationSummaryAutoRef = useRef("");
  const officialCaptureInFlightRef = useRef(false);
  const officialCapturedUrlRef = useRef("");
  const [batches, setBatches] = useState<ReviewBatch[]>([]);
  const [sourceReaderBatch, setSourceReaderBatch] = useState<number | null>(null);
  const [sourceDocument, setSourceDocument] = useState<ReviewSourceDocument | null>(null);
  const [sourceDocumentLoading, setSourceDocumentLoading] = useState(false);
  const [batchId, setBatchId] = useState<number | null>(() => Number(new URLSearchParams(window.location.search).get("batch")) || null);
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [categories, setCategories] = useState<CatalogCategory[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState("active");
  const [sourcePath, setSourcePath] = useState("");
  const [targetListId, setTargetListId] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [selectedStructure, setSelectedStructure] = useState<number[]>([]);
  const [structureChoices, setStructureChoices] = useState<Record<number, string>>({});
  const [bookshelfVisibility, setBookshelfVisibility] = useState<Record<number, boolean>>({});
  const [bookshelfCustomMode, setBookshelfCustomMode] = useState(false);
  const [hierarchyInspectorId, setHierarchyInspectorId] = useState<number | null>(null);
  const [hierarchyDraft, setHierarchyDraft] = useState<CatalogDraftFields>(() => catalogDraftFromSubject(null));
  const [hierarchyProposalType, setHierarchyProposalType] = useState<EntityType | "">("");
  const [memberDetailId, setMemberDetailId] = useState<number | null>(null);
  const [memberDraft, setMemberDraft] = useState<CatalogDraftFields>(() => catalogDraftFromSubject(null));
  const [memberImageSelection, setMemberImageSelection] = useState<ProductImageSelection>(() => productImageSelectionFromSubject(null));
  const [memberProposalType, setMemberProposalType] = useState<EntityType | "">("");
  const [selectedCategoryIds, setSelectedCategoryIds] = useState<number[]>([]);
  const [structureCategoryIds, setStructureCategoryIds] = useState<Record<number, number[]>>({});
  const [primaryCategoryByType, setPrimaryCategoryByType] = useState<Record<string, number | null>>({});
  const [lastResult, setLastResult] = useState<ReviewItem | null>(null);
  const [draft, setDraft] = useState<CatalogDraftFields>(() => catalogDraftFromSubject(null));
  const [draftImageSelection, setDraftImageSelection] = useState<ProductImageSelection>(() => productImageSelectionFromSubject(null));
  const [proposalType, setProposalType] = useState<EntityType | "">("");
  const [identityChoice, setIdentityChoice] = useState<"new" | number | null>(null);
  const [candidateDetail, setCandidateDetail] = useState<{ subjectId: number; entity: CatalogEntity } | null>(null);
  const [matchedEntity, setMatchedEntity] = useState<CatalogEntity | null>(null);
  const [guideDrafts, setGuideDrafts] = useState<Record<number, string>>({});
  const [recommendedEditionDraftId, setRecommendedEditionDraftId] = useState<number | null>(null);
  const [recommendedEditionId, setRecommendedEditionId] = useState<number | null>(null);
  const [coverChoiceByDraft, setCoverChoiceByDraft] = useState<Record<number, string>>({});
  const [structureAction, setStructureAction] = useState("");
  const [productStatus, setProductStatus] = useState("");
  const [productStatusTone, setProductStatusTone] = useState<"info" | "success" | "error">("info");
  const [productOperation, setProductOperation] = useState<"search" | "capture" | "">("");
  const [productQuery, setProductQuery] = useState("");
  const [browserStatus, setBrowserStatus] = useState<BrowserSessionStatus | null>(null);
  const [browserSessionActive, setBrowserSessionActive] = useState(false);
  const [officialStatus, setOfficialStatus] = useState<BrowserSessionStatus | null>(null);
  const [officialSessionActive, setOfficialSessionActive] = useState(false);
  const [officialOperation, setOfficialOperation] = useState<"search" | "capture" | "">("");
  const [unifiedCapturePending, setUnifiedCapturePending] = useState(false);
  const [officialMessage, setOfficialMessage] = useState("");
  const [officialMessageTone, setOfficialMessageTone] = useState<"info" | "success" | "error">("info");
  const [reviewHeaderCompact, setReviewHeaderCompact] = useState(false);
  const [batchContextOpen, setBatchContextOpen] = useState(false);
  const [toolbarOverflowOpen, setToolbarOverflowOpen] = useState(false);
  const [classificationStatus, setClassificationStatus] = useState("");
  const [activeRetailer, setActiveRetailer] = useState<"amazon" | "jd">(storedRetailer);
  const [queueWidth, setQueueWidth] = useState(() => Math.max(REVIEW_QUEUE_MIN, storedPaneWidth("reading-map-review-queue-width", 280)));
  const [mediaWidth, setMediaWidth] = useState(() => Math.max(REVIEW_MEDIA_MIN, storedPaneWidth("reading-map-review-media-width", 250)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const catalogDraftRegionRef = useRef<HTMLDivElement>(null);
  const saveCatalogDraftShortcutRef = useRef<() => void>(() => undefined);
  const proposalTitle = draft.displayTitle.trim();

  async function loadBatches(preferredId?: number) {
    const next = await api.reviewBatches();
    setBatches(next);
    const requested = preferredId ?? batchId;
    const nextId = next.find((row) => row.id === requested)?.id ?? next[0]?.id ?? null;
    setBatchId(nextId);
    return nextId;
  }

  async function loadItems(nextBatchId: number | null = batchId, preferredId?: number) {
    if (nextBatchId == null) return setItems([]);
    const next = await api.reviewItems(nextBatchId);
    setItems(next);
    const visible = statusFilter === "active" ? next.filter((item) => !["resolved", "ignored"].includes(item.status)) : next;
    setSelectedId(preferredId && next.some((item) => item.id === preferredId) ? preferredId : visible[0]?.id ?? next[0]?.id ?? null);
  }

  useEffect(() => {
    void loadBatches().catch((reason) => setError(reason instanceof Error ? reason.message : "审核批次加载失败"));
    void api.categories().then(setCategories).catch((reason) => setError(reason instanceof Error ? reason.message : "分类词表加载失败"));
  }, []);

  useEffect(() => {
    void loadItems(batchId).catch((reason) => setError(reason instanceof Error ? reason.message : "审核项加载失败"));
  }, [batchId]);

  useEffect(() => {
    let active = true;
    setSourceDocument(null);
    if (batchId == null) return () => { active = false; };
    setSourceDocumentLoading(true);
    void api.reviewSource(batchId)
      .then((document) => { if (active) setSourceDocument(document); })
      .catch(() => { if (active) setSourceDocument(null); })
      .finally(() => { if (active) setSourceDocumentLoading(false); });
    return () => { active = false; };
  }, [batchId]);

  const visibleItems = useMemo(
    () => statusFilter === "active" ? items.filter((item) => !["resolved", "ignored"].includes(item.status)) : items,
    [items, statusFilter]
  );
  const selected = items.find((item) => item.id === selectedId) ?? null;
  const primary = selected?.subjects.find((subject) => subject.subject_role === "primary") ?? null;
  const defaultProductQuery = String(
    primary?.proposed_title_en
    || primary?.proposed_display_title
    || primary?.proposed_title_zh
    || primary?.proposed_aliases?.[0]
    || ""
  );
  const officialSearchQuery = [
    productQuery.trim() || defaultProductQuery,
    draft.publisher.trim(),
    draft.author.trim(),
    "official publisher",
  ].filter(Boolean).join(" ");
  const categorySuggestionRows = useMemo(() => classificationSuggestions(primary?.ai_inferences_json), [primary?.ai_inferences_json]);
  const categorySuggestionKey = JSON.stringify(categorySuggestionRows);
  const classificationSummary = asRecord(asRecord(primary?.ai_inferences_json).classification_summary);
  const hasDescriptionSummary = classificationSummary.version === "controlled-description-v1";
  const classificationDescription = primary ? String(factValue(primary.facts_json, "description") || "").trim() : "";
  const initialDraft = catalogDraftFromSubject(primary);
  const initialImageSelection = productImageSelectionFromSubject(primary);
  const catalogFieldsDirty = JSON.stringify(draft) !== JSON.stringify(initialDraft)
    || proposalType !== (primary?.proposed_entity_type || "");
  const draftImagesDirty = productImageSelectionKey(draftImageSelection) !== productImageSelectionKey(initialImageSelection);
  const guideDirtyIds = selected?.subjects.filter((subject) => guideDrafts[subject.id] !== undefined && guideDrafts[subject.id] !== (subject.guide_markdown_draft || "")).map((subject) => subject.id) || [];
  const draftDirty = catalogFieldsDirty || draftImagesDirty || guideDirtyIds.length > 0;
  const parentSubjects = selected?.subjects.filter((subject) => subject.subject_role === "discovered_parent") ?? [];
  const memberStructureSubjects = selected?.subjects.filter((subject) => !["primary", "discovered_parent"].includes(subject.subject_role)) ?? [];
  const structureSubjects = [...parentSubjects, ...memberStructureSubjects];
  const directParentIds = new Set(primary?.relations
    .filter((relation) => relation.relation_type === "contains" && relation.member_subject_id === primary.id && relation.review_status !== "rejected")
    .map((relation) => relation.parent_subject_id) ?? []);
  const directParentBriefs = parentSubjects.filter((subject) => directParentIds.has(subject.id));
  const memberDetailSubject = structureSubjects.find((subject) => subject.id === memberDetailId) ?? null;
  const memberInitialDraft = catalogDraftFromSubject(memberDetailSubject);
  const memberInitialImageSelection = productImageSelectionFromSubject(memberDetailSubject);
  const memberDraftDirty = !!memberDetailSubject && (
    JSON.stringify(memberDraft) !== JSON.stringify(memberInitialDraft)
    || memberProposalType !== (memberDetailSubject.proposed_entity_type || "")
    || productImageSelectionKey(memberImageSelection) !== productImageSelectionKey(memberInitialImageSelection)
  );
  const structureChoiceFor = (subject: ResearchSubject): string => structureChoices[subject.id] || automaticResearchChoice(subject);
  const officialConfirmedStructureIds = (() => {
    if (!primary) return [];
    const allowed = new Set([primary.id, ...structureSubjects.map((subject) => subject.id)]);
    const adjacent = new Map<number, number[]>();
    [primary, ...structureSubjects].forEach((subject) => subject.relations.forEach((relation) => {
      if (relation.evidence_type !== "source_fact" || relation.review_status !== "confirmed") return;
      if (!allowed.has(relation.parent_subject_id) || !allowed.has(relation.member_subject_id)) return;
      adjacent.set(relation.parent_subject_id, [...(adjacent.get(relation.parent_subject_id) || []), relation.member_subject_id]);
      adjacent.set(relation.member_subject_id, [...(adjacent.get(relation.member_subject_id) || []), relation.parent_subject_id]);
    }));
    const pending = [primary.id];
    const reachable = new Set<number>();
    while (pending.length) {
      const current = pending.pop()!;
      if (reachable.has(current)) continue;
      reachable.add(current);
      pending.push(...(adjacent.get(current) || []));
    }
    return structureSubjects.filter((subject) => reachable.has(subject.id)).map((subject) => subject.id);
  })();
  const officialConfirmedStructureKey = officialConfirmedStructureIds.join(",");
  const defaultStructureKey = structureSubjects.map((subject) => subject.id).join(",");
  const officialLevelSignal = primary ? String(factValue(primary.facts_json, "official_level") || "").toLocaleLowerCase().replace(/-/g, " ") : "";
  const seriesNameSignal = primary ? String(factValue(primary.facts_json, "series_name") || "").toLocaleLowerCase() : "";
  const titleSeriesSignal = String(primary?.proposed_display_title || "").toLocaleLowerCase().replace(/-/g, " ");
  const parentTitleSeriesHint = parentSeriesHintFromTitle(primary?.proposed_display_title || "");
  const hierarchySignal = `${officialLevelSignal} ${seriesNameSignal} ${titleSeriesSignal} ${parentTitleSeriesHint.toLocaleLowerCase()}`;
  const obviousParentHierarchy = hierarchySignal.includes("ready to read") && hierarchySignal.includes("otto");
  const hierarchyRows = (() => {
    if (!primary) return [] as Array<{ subject: ResearchSubject; depth: number; current: boolean }>;
    const nodes = [primary, ...structureSubjects];
    const byId = new Map(nodes.map((subject) => [subject.id, subject]));
    const relationByKey = new Map<string, ResearchSubject["relations"][number]>();
    nodes.forEach((subject) => subject.relations.forEach((relation) => {
      if (relation.relation_type === "contains" && byId.has(relation.parent_subject_id) && byId.has(relation.member_subject_id)) {
        relationByKey.set(`${relation.parent_subject_id}:${relation.member_subject_id}`, relation);
      }
    }));
    const relations = [...relationByKey.values()];
    const memberIds = new Set(relations.map((relation) => relation.member_subject_id));
    const roots = nodes.filter((subject) => !memberIds.has(subject.id));
    const rows: Array<{ subject: ResearchSubject; depth: number; current: boolean }> = [];
    const visited = new Set<number>();
    const visit = (subject: ResearchSubject, depth: number) => {
      if (visited.has(subject.id)) return;
      visited.add(subject.id);
      rows.push({ subject, depth, current: subject.id === primary.id });
      relations.filter((relation) => relation.parent_subject_id === subject.id)
        .sort((left, right) => (left.position ?? 999) - (right.position ?? 999))
        .forEach((relation) => { const child = byId.get(relation.member_subject_id); if (child) visit(child, depth + 1); });
    };
    (roots.length ? roots : nodes).forEach((subject) => visit(subject, 0));
    nodes.forEach((subject) => visit(subject, 0));
    return rows;
  })();
  const hierarchySubjects = primary ? [primary, ...structureSubjects] : structureSubjects;
  const hierarchyInspectorSubject = hierarchySubjects.find((subject) => subject.id === hierarchyInspectorId) ?? primary;
  const hierarchyInspectorInitialDraft = catalogDraftFromSubject(hierarchyInspectorSubject || null);
  const hierarchyDraftDirty = !!hierarchyInspectorSubject && (
    JSON.stringify(hierarchyDraft) !== JSON.stringify(hierarchyInspectorInitialDraft)
    || hierarchyProposalType !== (hierarchyInspectorSubject.proposed_entity_type || "")
  );
  const hierarchyStatusCounts = structureSubjects.reduce((counts, subject) => {
    const status = structureNodeStatus(subject, structureChoiceFor(subject));
    counts[status.key] += 1;
    return counts;
  }, { create: 0, existing: 0, suspected: 0, conflict: 0 });
  const sourceImages = useMemo(() => getReviewSourceImages(selected, sourceDocument?.document), [selected, sourceDocument]);
  const hasSourceMedia = sourceImages.length > 0 || sourceDocumentLoading;
  const currentBatch = batches.find((batch) => batch.id === batchId);
  const currentTargetList = lists.find((list) => list.id === currentBatch?.target_reading_list_id);
  const safeMatches = visibleItems.flatMap((item) => {
    const subject = item.subjects.find((row) => row.subject_role === "primary");
    const candidate = subject?.candidates[0];
    return !["resolved", "ignored"].includes(item.status) && candidate && subject?.resolved_catalog_entity_id === candidate.catalog_entity_id
      ? [{ review_item_id: item.id, catalog_entity_id: candidate.catalog_entity_id, expected_version: item.lock_version }]
      : [];
  });

  useEffect(() => {
    setSelectedStructure([]); setStructureChoices({}); setStructureCategoryIds({}); setBookshelfVisibility({}); setBookshelfCustomMode(false);
    setProductStatus(""); setProductStatusTone("info"); setBrowserStatus(null); setProductQuery(defaultProductQuery);
    setOfficialStatus(null); setOfficialSessionActive(false); setOfficialOperation(""); setOfficialMessage(""); setOfficialMessageTone("info");
    officialCaptureInFlightRef.current = false; officialCapturedUrlRef.current = "";
    setClassificationStatus(""); setIdentityChoice(null); setCandidateDetail(null); setMatchedEntity(null); setGuideDrafts({}); setRecommendedEditionDraftId(null); setRecommendedEditionId(null); setCoverChoiceByDraft({}); setStructureAction(""); setHierarchyInspectorId(null);
    if (detailRef.current) detailRef.current.scrollTop = 0;
    setReviewHeaderCompact(false);
    setBatchContextOpen(false); setToolbarOverflowOpen(false);
  }, [selectedId]);
  useEffect(() => {
    try { window.sessionStorage.setItem("reading-map-review-retailer", activeRetailer); } catch { /* Session preference is optional. */ }
  }, [activeRetailer]);
  useEffect(() => {
    if (!selected) return;
    let live = true;
    const probe = async () => {
      try {
        const next = await api.browserSessionStatus(selected.id, activeRetailer);
        if (!live) return;
        setBrowserStatus(next);
        if (next.connected) setBrowserSessionActive(true);
      } catch (reason) {
        if (!live) return;
        setBrowserStatus({
          provider: activeRetailer, connected: false, state: "disconnected", current_url: "",
          product_title: "", product_id: "", capture_ready: false,
          message: reason instanceof Error ? reason.message : "浏览器状态检测失败",
        });
      }
    };
    const onFocus = () => void probe();
    const onVisibility = () => { if (document.visibilityState === "visible") void probe(); };
    void probe();
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      live = false;
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [selected?.id, activeRetailer]);
  useEffect(() => {
    if (!browserSessionActive || !selected) return;
    let live = true;
    let timer = 0;
    const poll = async () => {
      try {
        const next = await api.browserSessionStatus(selected.id, activeRetailer);
        if (!live) return;
        setBrowserStatus(next);
        if (!next.connected) setBrowserSessionActive(false);
      } catch (reason) {
        if (!live) return;
        setBrowserStatus({
          provider: activeRetailer, connected: false, state: "disconnected", current_url: "",
          product_title: "", product_id: "", capture_ready: false,
          message: reason instanceof Error ? reason.message : "无法读取浏览器会话",
        });
      }
    };
    void poll();
    timer = window.setInterval(() => void poll(), 1500);
    return () => { live = false; window.clearInterval(timer); };
  }, [browserSessionActive, selected?.id, activeRetailer]);
  useEffect(() => {
    if (!officialSessionActive || !selected) return;
    let live = true;
    let timer = 0;
    const poll = async () => {
      try {
        const next = await api.browserSessionStatus(selected.id, "official");
        if (!live) return;
        setOfficialStatus(next);
        if (!next.connected) setOfficialSessionActive(false);
      } catch (reason) {
        if (!live) return;
        setOfficialStatus({
          provider: "official", connected: false, state: "disconnected", current_url: "",
          product_title: "", product_id: "", capture_ready: false,
          message: reason instanceof Error ? reason.message : "无法读取官网浏览器会话",
        });
      }
    };
    void poll();
    timer = window.setInterval(() => void poll(), 1500);
    return () => { live = false; window.clearInterval(timer); };
  }, [officialSessionActive, selected?.id]);
  useEffect(() => {
    if (!primary) return;
    const choice = automaticResearchChoice(primary);
    setIdentityChoice(choice === "create" ? "new" : choice ? Number(choice) : null);
    setHierarchyInspectorId((current) => current && [primary, ...structureSubjects].some((subject) => subject.id === current) ? current : primary.id);
  }, [primary?.id, primary?.resolved_catalog_entity_id, primary?.candidates]);
  useEffect(() => {
    if (typeof identityChoice !== "number") { setMatchedEntity(null); return; }
    let live = true;
    void api.entity(identityChoice).then((entity) => { if (live) setMatchedEntity(entity); }).catch((reason) => setError(String(reason)));
    return () => { live = false; };
  }, [identityChoice]);
  useEffect(() => {
    if (!primary) return;
    const next: Record<number, boolean> = {};
    [primary, ...structureSubjects].forEach((subject) => {
      const choice = subject.id === primary.id
        ? (identityChoice === "new" ? "create" : identityChoice ? String(identityChoice) : "")
        : structureChoiceFor(subject);
      const candidate = subject.candidates.find((row) => String(row.catalog_entity_id) === choice);
      next[subject.id] = subject.resolved_bookshelf_visible ?? candidate?.bookshelf_visible ?? false;
    });
    setBookshelfVisibility(next);
  }, [selected?.id]);
  useEffect(() => {
    setHierarchyDraft(catalogDraftFromSubject(hierarchyInspectorSubject || null));
    setHierarchyProposalType(hierarchyInspectorSubject?.proposed_entity_type || "");
  }, [hierarchyInspectorSubject?.id, hierarchyInspectorSubject?.proposed_display_title, hierarchyInspectorSubject?.facts_json, hierarchyInspectorSubject?.proposed_entity_type]);
  useEffect(() => {
    if (!selected || !primary) return;
    const selectionKey = `${selected.id}:${defaultStructureKey}:${officialConfirmedStructureKey}`;
    if (officialStructureAutoSelectRef.current === selectionKey) return;
    officialStructureAutoSelectRef.current = selectionKey;
    setSelectedStructure(structureSubjects.map((subject) => subject.id));
    if (officialConfirmedStructureIds.length) {
      setStructureAction(`官网明确确认的 ${officialConfirmedStructureIds.length} 个结构节点已自动勾选；正常节点将自动新建或复用，仅异常项需要处理。`);
    }
  }, [selected?.id, defaultStructureKey, officialConfirmedStructureKey]);
  useEffect(() => {
    if (!selected || !primary || selected.decision || parentSubjects.length || !obviousParentHierarchy) return;
    const researchKey = `${selected.id}:${primary.id}`;
    if (parentResearchAutoRef.current === researchKey) return;
    parentResearchAutoRef.current = researchKey;
    setStructureAction("已识别 Ready-to-Read 线索，正在核对出版社官网的系列、级别与直接父级…");
    void api.researchParentHierarchy(selected.id)
      .then(async (result) => {
        await loadItems(batchId, selected.id);
        setStructureAction(`出版社官网父级研究完成：已暂存 ${result.subject_ids.length} 个系列/级别节点和 ${result.relation_ids.length} 条直接关系。`);
      })
      .catch((reason) => {
        setStructureAction("");
        setError(reason instanceof Error ? reason.message : "父级体系 Research 失败");
      });
  }, [selected?.id, primary?.id, parentSubjects.length, obviousParentHierarchy, batchId]);
  useEffect(() => {
    if (!selected || !primary || selected.decision || !classificationDescription || hasDescriptionSummary) return;
    const summaryKey = `${selected.id}:${primary.id}`;
    if (classificationSummaryAutoRef.current === summaryKey) return;
    classificationSummaryAutoRef.current = summaryKey;
    void summarizeClassification();
  }, [selected?.id, primary?.id, selected?.decision, classificationDescription, hasDescriptionSummary]);
  useEffect(() => {
    const proposedIds = categorySuggestionRows.flatMap((proposal) => {
      const category = categories.find((row) => row.category_type === proposal.categoryType && row.code === proposal.code);
      return category ? [category.id] : [];
    });
    setSelectedCategoryIds([...new Set(proposedIds)]);
    const materialTypes = proposedIds.filter((id) => categories.find((row) => row.id === id)?.category_type === "material_type");
    setPrimaryCategoryByType(materialTypes.length === 1 ? { material_type: materialTypes[0] } : {});
  }, [primary?.id, categorySuggestionKey, categories]);
  useEffect(() => {
    try { window.localStorage.setItem("reading-map-review-queue-width", String(queueWidth)); } catch { /* local storage may be disabled */ }
  }, [queueWidth]);
  useEffect(() => {
    try { window.localStorage.setItem("reading-map-review-media-width", String(mediaWidth)); } catch { /* local storage may be disabled */ }
  }, [mediaWidth]);
  useEffect(() => {
    setDraft(catalogDraftFromSubject(primary));
    setDraftImageSelection(productImageSelectionFromSubject(primary));
    setProposalType(primary?.proposed_entity_type || "");
  }, [primary?.id, primary?.proposed_display_title, primary?.proposed_title_en, primary?.proposed_title_zh, primary?.proposed_aliases, primary?.facts_json, primary?.proposed_entity_type]);

  async function importBatch(event: FormEvent) {
    event.preventDefault();
    if (!sourcePath.trim()) return;
    setBusy(true); setError("");
    try {
      const result = await api.importReviewBatch({
        source_file_path: sourcePath.trim(),
        target_reading_list_id: targetListId ? Number(targetListId) : undefined
      });
      const nextId = await loadBatches(result.batch.id);
      await loadItems(nextId);
      setSourcePath("");
      setImportOpen(false);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "导入失败"); }
    finally { setBusy(false); }
  }

  async function decide(decision: "match_existing" | "create_new" | "ignore", catalogEntityId?: number) {
    if (!selected) return;
    if (decision !== "ignore" && draftDirty) {
      setError("Catalog Draft 已修改，请先保存草稿再提交。"); return;
    }
    const included = decision === "ignore" ? [] : structureSubjects.filter((row) => selectedStructure.includes(row.id));
    if (included.some((row) => !row.resolved_catalog_entity_id && !structureChoiceFor(row))) {
      setError("请为每个勾选的结构对象明确选择新建或关联已有。"); return;
    }
    if (decision === "ignore" && !window.confirm("忽略此来源项？原文和 Research 会保留，不写入正式推荐。")) return;
    setBusy(true); setError("");
    try {
      const result = await api.reviewDecision(selected.id, {
        decision,
        catalog_entity_id: catalogEntityId,
        expected_version: selected.lock_version,
        include_structure_subject_ids: included.map((row) => row.id),
        structure_decisions: included.filter((row) => !row.resolved_catalog_entity_id).map((row) => ({
          subject_id: row.id,
          decision: structureChoiceFor(row) === "create" ? "create_new" : "match_existing",
          ...(structureChoiceFor(row) === "create" ? {} : { catalog_entity_id: Number(structureChoiceFor(row)) })
        })),
        bookshelf_visibility: decision === "ignore" ? [] : [primary!, ...included].map((row) => ({
          subject_id: row.id,
          visible: !!bookshelfVisibility[row.id]
        })),
        category_decisions: decision === "ignore" ? [] : selectedCategoryIds.map((categoryId) => {
          const category = categories.find((row) => row.id === categoryId);
          return { category_id: categoryId, is_primary: !!category && primaryCategoryByType[category.category_type] === categoryId };
        }),
        structure_category_decisions: decision === "ignore" ? [] : included.map((subject) => ({
          subject_id: subject.id,
          category_ids: structureCategoryIds[subject.id] ?? (Array.isArray(asRecord(subject.ai_inferences_json).classification_prefill_ids) ? asRecord(subject.ai_inferences_json).classification_prefill_ids as number[] : []),
        })),
        recommended_edition_id: recommendedEditionId,
        recommended_edition_draft_id: recommendedEditionDraftId,
      });
      setLastResult(result);
      await onResolved();
      await loadBatches(batchId ?? undefined);
      await loadItems(batchId);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "提交失败"); }
    finally { setBusy(false); }
  }

  async function refreshCandidates() {
    if (!primary) return;
    setBusy(true); setError("");
    try {
      const refreshed = await api.refreshResearchCandidates(primary.id);
      setIdentityChoice(refreshed.candidates.length === 0 ? "new" : null);
      await loadItems(batchId, selected?.id);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "候选刷新失败"); }
    finally { setBusy(false); }
  }

  async function summarizeClassification() {
    if (!primary || !classificationDescription) return;
    setClassificationStatus("正在根据简介总结…");
    setError("");
    try {
      await api.summarizeClassification(primary.id);
      await loadItems(batchId, selected?.id);
      setClassificationStatus("简介已总结；没有直接依据的维度保持为空。 ");
    } catch (reason) {
      setClassificationStatus("");
      setError(reason instanceof Error ? reason.message : "根据简介总结分类失败");
    }
  }

  async function searchProduct(provider: "amazon" | "jd") {
    if (!selected || !primary) return;
    const retailerLabel = provider === "jd" ? "京东" : "Amazon";
    setActiveRetailer(provider); setBrowserStatus(null); setBrowserSessionActive(false);
    setProductOperation("search"); setProductStatusTone("info"); setProductStatus(draftDirty ? "正在先保存当前草稿…" : `正在启动${retailerLabel}辅助浏览器…`);
    try {
      if (draftDirty) await persistCatalogDraft();
      const query = productQuery.trim() || undefined;
      const result = provider === "jd" ? await api.searchJd(selected.id, query) : await api.searchAmazon(selected.id, query);
      setBrowserSessionActive(true);
      setBrowserStatus({
        provider, connected: true, state: "search_results", current_url: result.current_url,
        product_title: "", product_id: "", capture_ready: false,
        message: "搜索结果已就绪，请打开正确商品",
      });
      setProductStatusTone("success");
      setProductStatus(`${retailerLabel} 已搜索“${result.query}”${result.session_reused ? " · 已复用浏览器会话" : ""}`);
      window.setTimeout(() => setProductStatus((current) => current.startsWith(`${retailerLabel} 已搜索`) ? "" : current), 2600);
    } catch (reason) {
      setProductStatusTone("error");
      setProductStatus(reason instanceof Error ? reason.message : `${retailerLabel} 搜索启动失败`);
    } finally { setProductOperation(""); }
  }

  async function captureCurrentProduct(provider: "amazon" | "jd") {
    if (!selected || !primary) return;
    const retailerLabel = provider === "jd" ? "京东" : "Amazon";
    setProductOperation("capture"); setProductStatusTone("info"); setProductStatus(`正在读取你选中的${retailerLabel}商品…`);
    try {
      if (draftDirty) await persistCatalogDraft();
      const result = provider === "jd" ? await api.captureJd(selected.id) : await api.captureAmazon(selected.id);
      await loadItems(batchId, selected.id);
      setProductStatusTone("success");
      setProductStatus(`${retailerLabel}商品资料已采集${result.capture.identifier ? ` · ${result.capture.identifier}` : ""}${result.capture.image_count ? ` · ${result.capture.image_count} 张图片` : ""}`);
      window.setTimeout(() => setProductStatus((current) => current.startsWith(`${retailerLabel}商品资料已采集`) ? "" : current), 3000);
    } catch (reason) {
      setProductStatusTone("error");
      setProductStatus(reason instanceof Error ? reason.message : `${retailerLabel}商品采集失败`);
    } finally { setProductOperation(""); }
  }

  async function searchOfficial() {
    if (!selected || !primary) return;
    setOfficialOperation("search"); setOfficialStatus(null); setOfficialSessionActive(false);
    setOfficialMessageTone("info"); setOfficialMessage(draftDirty ? "正在先保存当前草稿…" : "正在启动官网辅助浏览器…");
    officialCapturedUrlRef.current = "";
    try {
      if (draftDirty) {
        setBusy(true);
        try { await persistCatalogDraft(); }
        finally { setBusy(false); }
      }
      setOfficialMessage("正在启动官网辅助浏览器…");
      const result = await api.searchOfficial(selected.id, officialSearchQuery);
      setOfficialSessionActive(true);
      setOfficialStatus({
        provider: "official", connected: true, state: "search_results", current_url: result.current_url,
        product_title: "", product_id: "", capture_ready: false,
        message: "Google 结果已就绪，请打开正确的出版社或作者官网",
      });
      setOfficialMessageTone("success");
      setOfficialMessage(`已搜索“${result.query}” · 打开正确官网后点击采集按钮`);
      window.setTimeout(() => setOfficialMessage((current) => current.startsWith("已搜索") ? "" : current), 3200);
    } catch (reason) {
      setOfficialMessageTone("error");
      setOfficialMessage(reason instanceof Error ? reason.message : "官网搜索启动失败");
    } finally {
      setOfficialOperation("");
    }
  }

  async function captureCurrentOfficial(sourceUrl = officialStatus?.current_url || "") {
    if (!selected || !primary || officialCaptureInFlightRef.current) return;
    officialCaptureInFlightRef.current = true;
    setOfficialOperation("capture"); setOfficialMessageTone("info"); setOfficialMessage(draftDirty ? "正在先保存当前草稿…" : "正在读取官网资料并保存草稿…");
    try {
      if (draftDirty) {
        setBusy(true);
        try { await persistCatalogDraft(); }
        finally { setBusy(false); }
      }
      setOfficialMessage("正在读取官网资料并保存草稿…");
      const result = await api.captureOfficial(selected.id);
      officialCapturedUrlRef.current = sourceUrl || result.capture.source_url || "";
      setItems((current) => current.map((item) => item.id === result.item.id ? result.item : item));
      setOfficialSessionActive(false);
      setOfficialStatus((current) => current ? { ...current, capture_ready: false, message: "官网资料已保存" } : current);
      setOfficialMessageTone("success");
      setOfficialMessage(`官网资料已采集 · ${result.capture.fact_count} 个字段已写入 Research 草稿`);
    } catch (reason) {
      officialCapturedUrlRef.current = "";
      setOfficialMessageTone("error");
      setOfficialMessage(reason instanceof Error ? reason.message : "官网资料采集失败");
    } finally {
      officialCaptureInFlightRef.current = false;
      setOfficialOperation("");
    }
  }

  async function captureCurrentPage() {
    if (!selected || !primary || unifiedCapturePending) return;
    setUnifiedCapturePending(true);
    setProductStatusTone("info");
    setProductStatus("正在识别辅助浏览器中的可采集页面…");
    try {
      const providers = ["amazon", "jd", "official"] as const;
      const statuses = await Promise.all(providers.map((provider) => api.browserSessionStatus(selected.id, provider)));
      const ready = statuses.filter((status) => status.capture_ready && status.current_url);
      if (!ready.length) throw new Error("没有找到与当前审核项匹配的详情页；请先在辅助浏览器中打开目标页面。");
      if (ready.length > 1) throw new Error("辅助浏览器中有多个可采集详情页；请关闭无关标签页后重试，避免采错来源。");
      const target = ready[0];
      if (target.provider === "official") {
        setProductStatus("");
        setOfficialStatus(target);
        await captureCurrentOfficial(target.current_url);
      } else {
        setActiveRetailer(target.provider);
        setBrowserStatus(target);
        await captureCurrentProduct(target.provider);
      }
    } catch (reason) {
      setProductStatusTone("error");
      setProductStatus(reason instanceof Error ? reason.message : "识别可采集页面失败");
    } finally {
      setUnifiedCapturePending(false);
    }
  }

  async function captureScoped(scope: "edition" | "structure", provider: "amazon" | "jd" | "official") {
    if (!selected || !primary) return;
    setBusy(true); setError("");
    try {
      if (draftDirty) await persistCatalogDraft();
      const result = scope === "edition"
        ? await api.captureEdition(selected.id, provider)
        : await api.captureStructure(selected.id, provider);
      setItems((current) => current.map((item) => item.id === result.item.id ? result.item : item));
      if (scope === "structure") setStructureAction(`已补充 ${"relation_ids" in result ? result.relation_ids.length : 0} 条直接关系候选。`);
      else setProductStatus("Edition 候选已保存，请在下方确认版本。");
    } catch (reason) { setError(reason instanceof Error ? reason.message : `${scope} 采集失败`); }
    finally { setBusy(false); }
  }

  async function persistCatalogDraft(): Promise<ReviewItem> {
    if (!primary || !selected || !proposalTitle.trim() || !proposalType) throw new Error("请先填写显示名称和对象类型");
    let updated = selected;
    if (catalogFieldsDirty) {
      updated = await api.updateResearchDraft(selected.id, primary.id, reviewDraftPayload(primary, draft, proposalType, selected.lock_version));
    }
    if (draftImagesDirty) {
      await api.updateProductImages(primary.id, draftImageSelection.detailUrls, draftImageSelection.cover);
      updated = await api.reviewItem(selected.id);
    }
    for (const subjectId of guideDirtyIds) {
      updated = await api.saveGuideDraft(selected.id, subjectId, guideDrafts[subjectId]);
    }
    if (guideDirtyIds.length) setGuideDrafts({});
    setItems((current) => current.map((item) => item.id === updated.id ? updated : item));
    return updated;
  }

  async function inspectCandidate(subject: ResearchSubject, catalogEntityId: number) {
    try {
      setCandidateDetail({ subjectId: subject.id, entity: await api.entity(catalogEntityId) });
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Catalog 候选详情加载失败"); }
  }

  function confirmCandidate(same: boolean) {
    if (!candidateDetail || !primary) return;
    if (candidateDetail.subjectId === primary.id) {
      setIdentityChoice(same ? candidateDetail.entity.id : "new");
      setMatchedEntity(same ? candidateDetail.entity : null);
    }
    else setStructureChoices((current) => ({ ...current, [candidateDetail.subjectId]: same ? String(candidateDetail.entity.id) : "create" }));
    setCandidateDetail(null);
  }

  async function addGuideMaterial(subject: ResearchSubject, raw: string, title: string) {
    if (!selected) return;
    setBusy(true); setError("");
    try {
      if (draftDirty) await persistCatalogDraft();
      const result = await api.addGuideMaterial(selected.id, subject.id, raw, title);
      setItems((current) => current.map((item) => item.id === result.id ? result : item));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Guide 资料保存失败"); }
    finally { setBusy(false); }
  }

  async function decideEditionDraft(draftId: number, status: "confirmed" | "rejected", coverLocalPath?: string) {
    if (!selected) return;
    setBusy(true); setError("");
    try {
      if (draftDirty) await persistCatalogDraft();
      const result = await api.decideEditionDraft(selected.id, draftId, {
        review_status: status,
        ...(coverLocalPath ? { proposed_data: { cover_local_path: coverLocalPath } } : {}),
      });
      setItems((current) => current.map((item) => item.id === result.id ? result : item));
      if (status === "confirmed") { setRecommendedEditionDraftId(draftId); setRecommendedEditionId(null); }
      else if (recommendedEditionDraftId === draftId) setRecommendedEditionDraftId(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Edition 决定保存失败"); }
    finally { setBusy(false); }
  }

  async function saveCatalogDraft() {
    if (!draftDirty) return;
    setBusy(true); setError("");
    try { await persistCatalogDraft(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "草稿保存失败"); }
    finally { setBusy(false); }
  }

  saveCatalogDraftShortcutRef.current = () => {
    if (!busy && !selected?.decision && proposalTitle && proposalType && draftDirty) void saveCatalogDraft();
  };

  useEffect(() => {
    const saveOnCtrlS = (event: globalThis.KeyboardEvent) => {
      if (!event.ctrlKey || event.key.toLowerCase() !== "s" || !catalogDraftRegionRef.current?.matches(":hover")) return;
      event.preventDefault();
      saveCatalogDraftShortcutRef.current();
    };
    document.addEventListener("keydown", saveOnCtrlS);
    return () => document.removeEventListener("keydown", saveOnCtrlS);
  }, []);

  async function saveSourceCopy(field: SourceCopyField, value: string | boolean | null) {
    if (!selected) return;
    setError("");
    try {
      const payload: Parameters<typeof api.updateReviewSourceCopy>[1] = { expected_version: selected.lock_version };
      if (field === "is_strong_recommendation") payload.is_strong_recommendation = value as boolean;
      else if (field === "recommendation_emphasis_text") payload.recommendation_emphasis_text = value as string | null;
      else if (field === "comment") payload.comment = value as string | null;
      else payload.note = value as string | null;
      const updated = await api.updateReviewSourceCopy(selected.id, payload);
      const scrollTop = detailRef.current?.scrollTop;
      setItems((current) => current.map((item) => item.id === updated.id ? updated : item));
      if (scrollTop != null) requestAnimationFrame(() => {
        if (detailRef.current) detailRef.current.scrollTop = scrollTop;
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "推荐语保存失败");
    }
  }

  function openMemberDetails(subject: ResearchSubject) {
    setMemberDetailId(subject.id);
    setMemberDraft(catalogDraftFromSubject(subject));
    setMemberImageSelection(productImageSelectionFromSubject(subject));
    setMemberProposalType(subject.proposed_entity_type || "");
  }

  async function saveMemberDraft() {
    if (!memberDetailSubject || !selected || !memberDraft.displayTitle.trim() || !memberProposalType) return;
    setBusy(true); setError("");
    try {
      let updated = selected;
      const memberFieldsDirty = JSON.stringify(memberDraft) !== JSON.stringify(memberInitialDraft)
        || memberProposalType !== (memberDetailSubject.proposed_entity_type || "");
      if (memberFieldsDirty) {
        updated = await api.updateResearchDraft(selected.id, memberDetailSubject.id, reviewDraftPayload(memberDetailSubject, memberDraft, memberProposalType, selected.lock_version));
      }
      if (productImageSelectionKey(memberImageSelection) !== productImageSelectionKey(memberInitialImageSelection)) {
        await api.updateProductImages(memberDetailSubject.id, memberImageSelection.detailUrls, memberImageSelection.cover);
        updated = await api.reviewItem(selected.id);
      }
      setItems((current) => current.map((item) => item.id === updated.id ? updated : item));
      setMemberDetailId(null);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "结构草稿保存失败"); }
    finally { setBusy(false); }
  }

  async function refreshMemberCandidates() {
    if (!memberDetailSubject) return;
    setBusy(true); setError("");
    try {
      await api.refreshResearchCandidates(memberDetailSubject.id);
      await loadItems(batchId, selected?.id);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "成员候选刷新失败"); }
    finally { setBusy(false); }
  }

  async function saveHierarchyDraft() {
    if (!hierarchyInspectorSubject || !selected || !hierarchyDraft.displayTitle.trim() || !hierarchyProposalType) return;
    setBusy(true); setError("");
    try {
      const updated = await api.updateResearchDraft(selected.id, hierarchyInspectorSubject.id, reviewDraftPayload(hierarchyInspectorSubject, hierarchyDraft, hierarchyProposalType, selected.lock_version));
      setItems((current) => current.map((item) => item.id === updated.id ? updated : item));
      setStructureChoices((current) => ({ ...current, [hierarchyInspectorSubject.id]: "" }));
    } catch (reason) { setError(reason instanceof Error ? reason.message : "节点草稿保存失败"); }
    finally { setBusy(false); }
  }

  async function refreshHierarchyCandidates() {
    if (!hierarchyInspectorSubject) return;
    setBusy(true); setError("");
    try {
      const refreshed = await api.refreshResearchCandidates(hierarchyInspectorSubject.id);
      const choice = automaticResearchChoice(refreshed);
      if (hierarchyInspectorSubject.id === primary?.id) setIdentityChoice(choice === "create" ? "new" : choice ? Number(choice) : null);
      else setStructureChoices((current) => ({ ...current, [hierarchyInspectorSubject.id]: choice }));
      await loadItems(batchId, selected?.id);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Catalog 候选刷新失败"); }
    finally { setBusy(false); }
  }

  async function createParentStructure(childSubjectId: number, parentType: "reading_system" | "series" | "level" | "set", parentTitle: string) {
    if (!selected || !parentTitle.trim()) return;
    setBusy(true); setError("");
    try {
      const inferred = inferBilingualTitle(parentTitle);
      const result = await api.createParentStructure(selected.id, {
        child_subject_id: childSubjectId,
        proposed_entity_type: parentType,
        proposed_display_title: parentTitle.trim(),
        proposed_title_en: inferred.titleEn || null,
        proposed_title_zh: inferred.titleZh || null,
        category_ids: parentType === "series" && childSubjectId === primary?.id ? selectedCategoryIds : [],
      });
      await loadItems(batchId, selected.id);
      setSelectedStructure((current) => [...new Set([...current, result.parent_subject_id])]);
      if (parentType === "series" && childSubjectId === primary?.id) setStructureCategoryIds((current) => ({ ...current, [result.parent_subject_id]: [...selectedCategoryIds] }));
      setHierarchyInspectorId(result.parent_subject_id);
      setStructureAction("新父级已进入结构树；若无异常候选，将随整体提交自动创建。");
    } catch (reason) { setError(reason instanceof Error ? reason.message : "父级结构暂存失败"); }
    finally { setBusy(false); }
  }

  async function addHierarchyRelation(parentSubjectId: number, memberSubjectId: number) {
    if (!selected || parentSubjectId === memberSubjectId) return;
    setBusy(true); setError("");
    try {
      await api.createResearchRelation({ parent_subject_id: parentSubjectId, member_subject_id: memberSubjectId, relation_type: "contains" });
      await loadItems(batchId, selected.id);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "直接关系添加失败"); }
    finally { setBusy(false); }
  }

  async function deleteHierarchyRelation(relationId: number) {
    if (!selected) return;
    setBusy(true); setError("");
    try {
      await api.deleteResearchRelation(relationId);
      await loadItems(batchId, selected.id);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "直接关系删除失败"); }
    finally { setBusy(false); }
  }

  async function resolveHierarchyConflict(conflictId: number, status: "keep_existing" | "use_proposed" | "ignored") {
    if (!selected) return;
    setBusy(true); setError("");
    try {
      await api.resolveReviewConflict(conflictId, status);
      await loadItems(batchId, selected.id);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "冲突处理失败"); }
    finally { setBusy(false); }
  }

  async function researchSelectedStructure() {
    const selectedMemberIds = memberStructureSubjects.filter((subject) => selectedStructure.includes(subject.id)).map((subject) => subject.id);
    if (!selected || !selectedMemberIds.length) return;
    setBusy(true); setError(""); setStructureAction("正在汇总已勾选成员的官方资料与 Lexile…");
    try {
      const result = await api.researchSelectedStructure(selected.id, selectedMemberIds);
      await loadItems(batchId, selected.id);
      const failed = Object.keys(result.capture_errors).length;
      setStructureAction(`已读取 ${result.captured_subject_ids.length} 个官网成员页面并更新封面/资料，套系 Lexile 已汇总${failed ? `；${failed} 个页面未成功，错误已保留` : ""}。`);
    } catch (reason) {
      setStructureAction("");
      setError(reason instanceof Error ? reason.message : "所选结构 Research 失败");
    } finally { setBusy(false); }
  }

  async function bulkConfirm() {
    if (!safeMatches.length) return;
    if (!window.confirm(`确认这 ${safeMatches.length} 条历史人工关联？只关联已有对象，并建立当前来源推荐关系。`)) return;
    setBusy(true); setError("");
    try {
      await api.bulkMatch(safeMatches);
      await onResolved();
      await loadBatches(batchId ?? undefined);
      await loadItems(batchId);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "批量确认失败"); }
    finally { setBusy(false); }
  }

  function toggleStructure(subjectId: number) {
    setSelectedStructure((current) => current.includes(subjectId) ? current.filter((id) => id !== subjectId) : [...current, subjectId]);
  }

  function toggleAllStructure() {
    const memberIds = memberStructureSubjects.map((subject) => subject.id);
    setSelectedStructure((current) => memberIds.every((id) => current.includes(id))
      ? current.filter((id) => !memberIds.includes(id))
      : [...new Set([...current, ...memberIds])]);
  }

  function updateCategorySelection(categoryId: number, selected: boolean) {
    const category = categories.find((row) => row.id === categoryId);
    if (!category) return;
    setSelectedCategoryIds((current) => selected
      ? [...new Set([...current, categoryId])]
      : current.filter((id) => id !== categoryId));
    if (!selected && primaryCategoryByType[category.category_type] === categoryId) {
      setPrimaryCategoryByType((current) => ({ ...current, [category.category_type]: null }));
    }
  }

  function updatePrimaryCategory(categoryType: CatalogCategory["category_type"], categoryId: number | null) {
    setPrimaryCategoryByType((current) => ({ ...current, [categoryType]: categoryId }));
  }

  function applyBookshelfVisibility(mode: "hidden" | "children" | "leaf-books") {
    if (!primary || !hierarchyInspectorSubject) return;
    const includedIds = new Set([primary.id, ...selectedStructure]);
    const relations = [...new Map((selected?.subjects ?? []).flatMap((subject) => subject.relations).map((relation) => [relation.id, relation])).values()]
      .filter((relation) => relation.relation_type === "contains" && relation.review_status !== "rejected");
    const childrenByParent = new Map<number, number[]>();
    relations.forEach((relation) => childrenByParent.set(relation.parent_subject_id, [...(childrenByParent.get(relation.parent_subject_id) || []), relation.member_subject_id]));
    const branchIds = new Set<number>();
    const pending = [hierarchyInspectorSubject.id];
    while (pending.length) {
      const subjectId = pending.pop()!;
      if (branchIds.has(subjectId) || !includedIds.has(subjectId)) continue;
      branchIds.add(subjectId);
      pending.push(...(childrenByParent.get(subjectId) || []));
    }
    setBookshelfVisibility((current) => {
      const next = { ...current };
      if (mode === "hidden") includedIds.forEach((id) => { next[id] = false; });
      else {
        branchIds.forEach((id) => { next[id] = false; });
        if (mode === "children") (childrenByParent.get(hierarchyInspectorSubject.id) || []).forEach((id) => { if (includedIds.has(id)) next[id] = true; });
        else hierarchyRows.forEach(({ subject }) => { if (branchIds.has(subject.id) && subject.proposed_entity_type === "book") next[subject.id] = true; });
      }
      return next;
    });
  }

  function paneWidthLimit(side: "queue" | "media") {
    const workbenchWidth = workbenchRef.current?.getBoundingClientRect().width ?? 1200;
    const otherWidth = side === "queue" ? (hasSourceMedia ? mediaWidth : 0) : queueWidth;
    const handleSpace = hasSourceMedia ? 20 : 10;
    const minimum = side === "queue" ? REVIEW_QUEUE_MIN : REVIEW_MEDIA_MIN;
    return Math.max(minimum, Math.floor(workbenchWidth - otherWidth - handleSpace));
  }

  function updatePaneWidth(side: "queue" | "media", requestedWidth: number) {
    const minimum = side === "queue" ? REVIEW_QUEUE_MIN : REVIEW_MEDIA_MIN;
    const nextWidth = Math.round(Math.min(paneWidthLimit(side), Math.max(minimum, requestedWidth)));
    if (side === "queue") setQueueWidth(nextWidth);
    else setMediaWidth(nextWidth);
  }

  function startPaneResize(side: "queue" | "media", event: ReactPointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = side === "queue" ? queueWidth : mediaWidth;
    document.body.classList.add("review-pane-resizing");
    const move = (moveEvent: PointerEvent) => {
      const delta = moveEvent.clientX - startX;
      updatePaneWidth(side, side === "queue" ? startWidth + delta : startWidth - delta);
    };
    const stop = () => {
      document.body.classList.remove("review-pane-resizing");
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
      window.removeEventListener("pointercancel", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
    window.addEventListener("pointercancel", stop);
  }

  function resizePaneWithKeyboard(side: "queue" | "media", event: ReactKeyboardEvent<HTMLDivElement>) {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const separatorMovement = event.key === "ArrowLeft" ? -20 : 20;
    const currentWidth = side === "queue" ? queueWidth : mediaWidth;
    updatePaneWidth(side, side === "queue" ? currentWidth + separatorMovement : currentWidth - separatorMovement);
  }

  const workbenchStyle = {
    "--review-queue-width": `${queueWidth}px`,
    "--review-media-width": `${mediaWidth}px`,
  } as CSSProperties;
  const selectedCategories = categories.filter((category) => selectedCategoryIds.includes(category.id));
  const selectedStructureSubjects = structureSubjects.filter((subject) => selectedStructure.includes(subject.id));
  const bookshelfCommittedSubjects = primary ? [primary, ...selectedStructureSubjects] : [];
  const bookshelfVisibleSubjects = bookshelfCommittedSubjects.filter((subject) => bookshelfVisibility[subject.id]);
  const bookshelfHiddenCount = bookshelfCommittedSubjects.length - bookshelfVisibleSubjects.length;
  const selectedParentSubjects = parentSubjects.filter((subject) => selectedStructure.includes(subject.id));
  const selectedMemberSubjects = memberStructureSubjects.filter((subject) => selectedStructure.includes(subject.id));
  const unresolvedStructureChoices = selectedStructureSubjects.filter((subject) => !subject.resolved_catalog_entity_id && !structureChoiceFor(subject));
  const conflictingStructureSubjects = selectedStructureSubjects.filter((subject) => subject.pending_conflict_count > 0);
  const disconnectedStructureSubjects = (() => {
    if (!primary || !selectedStructureSubjects.length) return [] as ResearchSubject[];
    const selectedIds = new Set([primary.id, ...selectedStructureSubjects.map((subject) => subject.id)]);
    const adjacent = new Map<number, Set<number>>([...selectedIds].map((id) => [id, new Set<number>()]));
    const relations = new Map((selected?.subjects ?? []).flatMap((subject) => subject.relations).map((relation) => [relation.id, relation])).values();
    for (const relation of relations) {
      if (relation.relation_type !== "contains" || relation.review_status === "rejected" || !selectedIds.has(relation.parent_subject_id) || !selectedIds.has(relation.member_subject_id)) continue;
      adjacent.get(relation.parent_subject_id)?.add(relation.member_subject_id);
      adjacent.get(relation.member_subject_id)?.add(relation.parent_subject_id);
    }
    const reachable = new Set<number>();
    const pending = [primary.id];
    while (pending.length) {
      const current = pending.pop()!;
      if (reachable.has(current)) continue;
      reachable.add(current);
      pending.push(...(adjacent.get(current) || []));
    }
    return selectedStructureSubjects.filter((subject) => !reachable.has(subject.id));
  })();
  const productCaptured = !!primary?.sources.some((source) => source.source_type?.includes("product"));
  const classificationReady = categorySuggestionRows.length > 0 || selectedCategoryIds.length > 0;
  const activeItemCount = items.filter((item) => !["resolved", "ignored"].includes(item.status)).length;
  const selectedQueueIndex = Math.max(0, visibleItems.findIndex((item) => item.id === selectedId));
  const selectedNewStructures = selectedStructureSubjects.filter((subject) => !subject.resolved_catalog_entity_id && structureChoiceFor(subject) === "create").length;
  const selectedExistingStructures = selectedStructureSubjects.length - selectedNewStructures;
  const draftCoverCount = (draftImageSelection.cover ? 1 : 0) + selectedMemberSubjects.filter((subject) => !!factValue(subject.facts_json, "cover")).length;
  const canSubmit = !!identityChoice && !draftDirty && !unresolvedStructureChoices.length && !disconnectedStructureSubjects.length && !!proposalType;
  const memberChoice = memberDetailSubject ? structureChoiceFor(memberDetailSubject) : "";
  const memberIdentityChoice: "new" | number | null = memberChoice === "create" ? "new" : memberChoice ? Number(memberChoice) : null;

  return <div className="review-shell compact">
    {sourceReaderBatch !== null ? <SourceDocumentReader batchId={sourceReaderBatch} onClose={() => setSourceReaderBatch(null)} /> : null}
    {memberDetailSubject ? <div className="structure-detail-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setMemberDetailId(null); }}>
      <section className="structure-detail-dialog" role="dialog" aria-modal="true" aria-labelledby="structure-member-title">
        <header><div><p>{memberDetailSubject.subject_role === "discovered_parent" ? "PARENT STRUCTURE" : "STRUCTURE MEMBER"} · 审核草稿</p><h2 id="structure-member-title">{memberDetailSubject.proposed_display_title}</h2></div><button type="button" aria-label="关闭结构详情" onClick={() => setMemberDetailId(null)}><X size={18} /></button></header>
        <div className="structure-detail-body">
          <CatalogDraftEditor
            subject={memberDetailSubject}
            draft={memberDraft}
            entityType={memberProposalType}
            entityTypes={memberDetailSubject.subject_role === "discovered_parent" ? parentEntityTypes : reviewEntityTypes}
            disabled={busy || !!selected?.decision}
            identityChoice={memberIdentityChoice}
            identityDisabled={busy || memberDraftDirty || !!selected?.decision}
            onDraftChange={(next) => {
              if (next.displayTitle !== memberDraft.displayTitle) setStructureChoices((current) => ({ ...current, [memberDetailSubject.id]: "" }));
              setMemberDraft(next);
            }}
            onTypeChange={(next) => { setMemberProposalType(next); setStructureChoices((current) => ({ ...current, [memberDetailSubject.id]: "" })); }}
            onRefreshCandidates={() => void refreshMemberCandidates()}
            onIdentityChoice={(value) => setStructureChoices((current) => ({ ...current, [memberDetailSubject.id]: value === "new" ? "create" : value == null ? "" : String(value) }))}
            imageSelection={memberImageSelection}
            onProductImagesChange={setMemberImageSelection}
          />
          <div className="structure-detail-evidence"><h3>全部 Research 字段与来源</h3><ProductCaptureResults subject={memberDetailSubject} disabled={busy || !!selected?.decision} showImages={false} /></div>
        </div>
        <footer><p>保存只更新结构审核草稿；正式 Entity 仍在主项最终提交时创建或关联。</p><div><button type="button" onClick={() => setMemberDetailId(null)}>取消</button><button type="button" className="primary" disabled={busy || !!selected?.decision || !memberDraftDirty || !memberDraft.displayTitle.trim() || !memberProposalType} onClick={() => void saveMemberDraft()}>{busy ? "保存中…" : "保存结构草稿"}</button></div></footer>
      </section>
    </div> : null}
    <header className={`review-workspace-header${reviewHeaderCompact ? " compact" : ""}`}>
      <div className="review-workspace-identity">
        <div><h1>审核工作台</h1>{currentBatch ? <span>批次 #{currentBatch.id} · {currentBatch.resolved_items}/{currentBatch.total_items}</span> : null}</div>
      </div>
      <button className="review-context-trigger" type="button" aria-expanded={batchContextOpen} onClick={() => setBatchContextOpen((open) => !open)}>
        <span>{currentBatch?.source_name || (currentBatch ? `批次 #${currentBatch.id}` : "暂无审核批次")}</span>
        {currentBatch ? <span className="review-context-progress">{currentBatch.resolved_items}/{currentBatch.total_items} · {reviewStatusLabel(currentBatch.status)}</span> : null}
        <ChevronDown size={15} />
      </button>
      <div className={`review-header-controls${batchContextOpen ? " open" : ""}`}>
        <label className="review-batch-select"><span>当前批次</span><select value={batchId ?? ""} onChange={(event) => { setBatchId(event.target.value ? Number(event.target.value) : null); setBatchContextOpen(false); }} disabled={!batches.length}><option value="">暂无审核批次</option>{batches.map((batch) => <option key={batch.id} value={batch.id}>{batch.source_name || `批次 #${batch.id}`} · {batch.resolved_items}/{batch.total_items} · {reviewStatusLabel(batch.status)}</option>)}</select></label>
        <div className="review-header-actions">
          <button className={`review-import-toggle${importOpen ? " active" : ""}`} type="button" onClick={() => { setImportOpen((current) => !current); setBatchContextOpen(false); }}><FileInput size={16} />导入审核</button>
          <details className="review-overflow-menu">
            <summary aria-label="更多审核工具"><Ellipsis size={18} /></summary>
            <div>
              {batchId ? <button type="button" onClick={() => setSourceReaderBatch(batchId)}><FileInput size={15} />查看原始 JSON</button> : null}
              {batchId ? <a href="/django-admin/reviews/reviewdataconflict/" target="_blank" rel="noreferrer"><CircleAlert size={15} />数据冲突</a> : null}
              {batchId ? <button type="button" disabled={busy || !safeMatches.length} onClick={bulkConfirm}><CheckCircle2 size={15} />确认历史匹配{safeMatches.length ? ` (${safeMatches.length})` : ""}</button> : null}
              {currentBatch ? <p>批次 #{currentBatch.id}<br />{currentTargetList ? `${currentTargetList.creator_name} / ${currentTargetList.title}` : "仅写入 Catalog"}</p> : null}
            </div>
          </details>
        </div>
      </div>
    </header>
    <div className="review-compact-top">
      {lastResult ? <div className="review-result" role="status">{lastResult.decision === "ignore" ? "已忽略，来源原文和研究记录已保留。" : <>提交成功 · Catalog #{lastResult.resolved_catalog_entity_id}　<a href={`/django-admin/catalog/catalogentity/${lastResult.resolved_catalog_entity_id}/change/`} target="_blank" rel="noreferrer">查看正式实体</a>{lastResult.committed_reading_list_item_id ? <> · <a href={`/django-admin/catalog/readinglistitem/${lastResult.committed_reading_list_item_id}/change/`} target="_blank" rel="noreferrer">查看正式推荐关系</a></> : " · 未建立推荐关系"}</>}</div> : null}
      {importOpen ? <section className="review-import-panel">
        <form className="review-import" onSubmit={importBatch}>
          <FileInput size={18} />
          <input value={sourcePath} onChange={(event) => setSourcePath(event.target.value)} placeholder="reading_lists/文件名.json" autoFocus />
          <select value={targetListId} onChange={(event) => setTargetListId(event.target.value)}>
            <option value="">暂不绑定正式书单</option>
            {lists.map((list) => <option key={list.id} value={list.id}>{list.creator_name} · {list.title}</option>)}
          </select>
          <button disabled={busy}>开始导入</button>
        </form>
      </section> : null}
      {error ? <div className="review-error"><CircleAlert size={16} />{error}</div> : null}
    </div>

    <div ref={workbenchRef} style={workbenchStyle} className={`review-workbench${hasSourceMedia ? " has-media" : ""}`}>
      <aside className="review-queue">
        <header className="review-queue-header">
          <div><strong>审核队列</strong><small>{visibleItems.length ? `${selectedQueueIndex + 1} / ${visibleItems.length}` : "0 / 0"}</small></div>
          <div className="queue-filter" aria-label="审核队列筛选">
            <button className={statusFilter === "active" ? "active" : ""} onClick={() => setStatusFilter("active")}>待处理 <span>{activeItemCount}</span></button>
            <button className={statusFilter === "all" ? "active" : ""} onClick={() => setStatusFilter("all")}>全部 <span>{items.length}</span></button>
          </div>
        </header>
        <div className="review-queue-list">
          {visibleItems.map((item) => {
            const subject = item.subjects.find((row) => row.subject_role === "primary");
            const candidate = subject?.candidates[0];
            return <button key={item.id} className={item.id === selectedId ? "active" : ""} onClick={() => setSelectedId(item.id)}>
              <span className={`review-state ${item.status}`}>{item.status === "resolved" ? <Check size={13} /> : item.status === "ignored" ? <X size={13} /> : item.position ?? "·"}</span>
              <span><strong>{String(subject?.proposed_display_title || item.raw_payload.raw_title || "未命名")}</strong><small>{subject?.proposed_entity_type ? entityLabels[subject.proposed_entity_type] : "类型待确认"} · {reviewStatusLabel(subject?.research_status || "pending")}{candidate ? " · 有候选" : " · 暂无正式候选"}</small></span>
            </button>;
          })}
          {!visibleItems.length ? <div className="review-empty">这个视图没有审核项。</div> : null}
        </div>
      </aside>
      <div className="review-resizer queue-resizer" role="separator" aria-label="调整左侧审核队列宽度" aria-orientation="vertical" aria-valuemin={REVIEW_QUEUE_MIN} aria-valuemax={paneWidthLimit("queue")} aria-valuenow={queueWidth} tabIndex={0} title="拖动调整左侧宽度" onPointerDown={(event) => startPaneResize("queue", event)} onKeyDown={(event) => resizePaneWithKeyboard("queue", event)} />

      <section ref={detailRef} className="review-detail" onScroll={(event) => { const compact = event.currentTarget.scrollTop > 30; setReviewHeaderCompact(compact); if (!compact) { setBatchContextOpen(false); setToolbarOverflowOpen(false); } }}>
        {selected && primary ? <>
          <div className={`review-item-toolbar${reviewHeaderCompact ? " compact" : ""}`}>
            <div className="review-item-toolbar-title"><div><small>Item #{selected.id} · 来源位置 {selected.position ?? "—"}</small><h2>{primary.proposed_display_title || String(selected.raw_payload.raw_title || "未命名")}</h2></div><span className={`review-status ${selected.status}`}>{reviewStatusLabel(selected.status)}</span></div>
            <div className="review-item-tools">
              <div className="product-tool-row">
                <input className="product-query" value={productQuery} onChange={(event) => setProductQuery(event.target.value)} placeholder={defaultProductQuery || "搜索名称"} aria-label="搜索词" />
                <button type="button" className="tool-action search-amazon" disabled={busy || !!selected.decision || !primary.proposed_display_title || !!productOperation || !!officialOperation || unifiedCapturePending} onClick={() => void searchProduct("amazon")}>{productOperation === "search" && activeRetailer === "amazon" ? <RefreshCw className="spin" size={14} /> : <Search size={14} />}搜索 Amazon</button>
                <button type="button" className="tool-action search-jd" disabled={busy || !!selected.decision || !primary.proposed_display_title || !!productOperation || !!officialOperation || unifiedCapturePending} onClick={() => void searchProduct("jd")}>{productOperation === "search" && activeRetailer === "jd" ? <RefreshCw className="spin" size={14} /> : <Search size={14} />}搜索京东</button>
                <button type="button" className="tool-action search-official" disabled={busy || !!selected.decision || !!officialOperation || !!productOperation || unifiedCapturePending} onClick={() => void searchOfficial()} title="有未保存修改时会先保存草稿；打开正确官网后手动采集"><Search size={14} />搜索官方资料</button>
                <button type="button" className="tool-action capture" disabled={busy || !!selected.decision || !!productOperation || !!officialOperation || unifiedCapturePending} onClick={() => void captureCurrentPage()}>{unifiedCapturePending || productOperation === "capture" || officialOperation === "capture" ? <RefreshCw className="spin" size={14} /> : <FileInput size={14} />}{unifiedCapturePending || productOperation === "capture" || officialOperation === "capture" ? "采集中…" : "采集当前页"}</button>
              </div>
              <div className="review-promoted-tools">
                <button type="button" className="tool-action" disabled={busy || !!selected.decision || !browserStatus?.capture_ready} onClick={() => void captureScoped("structure", activeRetailer)} title="从当前商品页采集结构">采集商品结构</button>
                <button type="button" className="tool-action" disabled={busy || !!selected.decision || !officialStatus?.capture_ready} onClick={() => void captureScoped("structure", "official")} title="从当前官网页采集结构">采集官网结构</button>
              </div>
              <button className="review-tool-overflow-trigger" type="button" aria-label="更多采集与 Research 操作" aria-expanded={toolbarOverflowOpen} onClick={() => setToolbarOverflowOpen((open) => !open)}><Ellipsis size={18} /></button>
              <div className={`review-secondary-tools${toolbarOverflowOpen ? " open" : ""}`}>
              <div className="retailer-scope-tools">
                <span className="tool-label">商品</span>
                <button type="button" disabled={busy || !!selected.decision || !browserStatus?.capture_ready} onClick={() => void captureScoped("edition", activeRetailer)}>采集当前版本</button>
              </div>
              <div className="research-tool-compact">
                <span className="tool-label">Research</span>
                <button type="button" disabled={busy || !!selected.decision || !officialStatus?.capture_ready} onClick={() => void captureScoped("edition", "official")}>采集当前版本</button>
                <button type="button" disabled={busy} onClick={() => void loadItems(batchId, selected.id).catch((reason) => setError(String(reason)))}><RefreshCw size={13} />刷新结果</button>
              </div>
              <div className="review-toolbar-sessions">
            {browserStatus || productStatus ? <div className={`browser-session-state${browserStatus?.capture_ready ? " ready" : ""}${productStatus ? ` ${productStatusTone}` : ""}`} role="status">
              <span className="session-dot" />
              <strong>{productStatus || browserStatus?.message}</strong>
              {!productStatus && browserStatus?.product_title ? <span>{browserStatus.product_title}</span> : null}
              {browserStatus?.current_url ? <a href={browserStatus.current_url} target="_blank" rel="noreferrer" aria-label="打开当前商品页"><ExternalLink size={13} /></a> : null}
            </div> : null}
            {officialStatus || officialMessage ? <div className={`browser-session-state official${officialStatus?.capture_ready ? " ready" : ""}${officialMessage ? ` ${officialMessageTone}` : ""}`} role="status">
              <span className="session-dot" />
              <strong>{officialMessage || officialStatus?.message}</strong>
              {!officialMessage && officialStatus?.product_title ? <span>{officialStatus.product_title}</span> : null}
              {officialStatus?.current_url ? <a href={officialStatus.current_url} target="_blank" rel="noreferrer" aria-label="打开当前官网页面"><ExternalLink size={13} /></a> : null}
            </div> : null}
              </div>
              </div>
            </div>
            {productStatus && productStatusTone === "error" ? <div className="review-toolbar-error" role="alert">{productStatus}</div> : null}
            {officialMessage && officialMessageTone === "error" ? <div className="review-toolbar-error" role="alert">{officialMessage}</div> : null}
          </div>
          {candidateDetail ? <div className="catalog-identity-overlay" role="dialog" aria-modal="true" aria-label="Catalog 身份详情">
            <div className="catalog-identity-dialog">
              <header><strong>判断是否为同一 Entity</strong><button type="button" onClick={() => setCandidateDetail(null)} aria-label="关闭"><X size={16} /></button></header>
              <h3>{candidateDetail.entity.display_title}</h3>
              <p>#{candidateDetail.entity.id} · {entityLabels[candidateDetail.entity.entity_type]}</p>
              <p>{candidateDetail.entity.description || "暂无简介"}</p>
              {candidateDetail.entity.work ? <p>作者：{candidateDetail.entity.work.author_text || "—"}　绘者：{candidateDetail.entity.work.illustrator_text || "—"}　译者：{candidateDetail.entity.work.translator_text || "—"}</p> : null}
              {candidateDetail.entity.editions.length ? <div className="catalog-identity-editions">{candidateDetail.entity.editions.map((edition) => <article key={edition.id}>{edition.cover_local_path ? <img src={catalogAssetUrl(edition.cover_local_path)} alt="版本封面" /> : <span>无封面</span>}<small>Edition #{edition.id}<br />{edition.isbns.map((isbn) => isbn.isbn_val).join("、") || "无 ISBN"}<br />{edition.format || ""} {edition.page_count ? `${edition.page_count} 页` : ""}</small></article>)}</div> : null}
              <footer><button type="button" onClick={() => confirmCandidate(false)}>不是，创建新 Entity</button><button type="button" onClick={() => confirmCandidate(true)}>确认同一 Entity</button></footer>
            </div>
          </div> : null}
          <div className="review-progress" aria-label="当前审核进度">
            <ReviewProgressStep label="Research" complete={["ready", "partial"].includes(primary.research_status)} value={reviewStatusLabel(primary.research_status)} />
            <ReviewProgressStep label="商品资料" complete={productCaptured} value={productCaptured ? "已采集" : "待补充"} />
            <ReviewProgressStep label="Catalog 匹配" complete={primary.candidates.length > 0 || identityChoice === "new"} value={primary.candidates.length ? `${primary.candidates.length} 个候选` : identityChoice === "new" ? "确认新建" : "暂未发现"} />
            <ReviewProgressStep label="结构" complete={!structureSubjects.length || selectedStructure.length > 0} value={structureSubjects.length ? `${parentSubjects.length} 父级 · ${memberStructureSubjects.length} 成员` : "未暂存"} />
            <ReviewProgressStep label="分类" complete={classificationReady} value={classificationReady ? "已准备" : "未分析"} />
          </div>
          {primary.manual_note ? <div className={primary.research_status === "partial" ? "review-warning" : "review-note"}><strong>{primary.research_status === "partial" ? "待确认事项" : "Research 说明"}</strong><p>{primary.manual_note}</p></div> : null}
          {selected.resolved_catalog_entity_id ? <p className="review-result">已提交到 <a href={`/django-admin/catalog/catalogentity/${selected.resolved_catalog_entity_id}/change/`} target="_blank" rel="noreferrer">Catalog #{selected.resolved_catalog_entity_id}</a>{selected.committed_reading_list_item_id ? <> · <a href={`/django-admin/catalog/readinglistitem/${selected.committed_reading_list_item_id}/change/`} target="_blank" rel="noreferrer">推荐关系 #{selected.committed_reading_list_item_id}</a></> : null}</p> : null}
          <ReviewSection eyebrow="SOURCE · 原始记录只读" title="来源原文" tone="source">
            <h3>{String(selected.raw_payload.raw_title || "未提供标题")}</h3>
            <SourceDetails item={selected} disabled={busy || !!selected.decision} onUpdate={saveSourceCopy} />
          </ReviewSection>
          <div ref={catalogDraftRegionRef} className="catalog-draft-save-scope">
          <ReviewSection eyebrow="CATALOG DRAFT · 可编辑" title="待写入 Catalog" tone="proposal" action={<span className={`draft-save-state${draftDirty ? " dirty" : ""}`}>{draftDirty ? "有未保存修改 · Ctrl+S" : "草稿已保存"}</span>}>
            <CatalogDraftEditor
              subject={primary}
              draft={draft}
              entityType={proposalType}
              disabled={busy || !!selected.decision}
              identityChoice={identityChoice}
              identityDisabled={busy || catalogFieldsDirty || !!selected.decision}
              parentControl={<div className="entity-parent-picker"><span>系列结构</span><div className="entity-parent-summary"><strong>{parentSubjects.length ? `${parentSubjects.length} 个相关节点` : obviousParentHierarchy ? "正在研究父级…" : parentTitleSeriesHint ? `名称提示：${parentTitleSeriesHint}（待核实）` : "未发现父级"}</strong><small>{hierarchyStatusCounts.suspected + hierarchyStatusCounts.conflict ? `${hierarchyStatusCounts.suspected + hierarchyStatusCounts.conflict} 个异常待处理` : "正常节点将随整体提交"}</small></div></div>}
              parentDetails={structureSubjects.length ? <>
                {directParentBriefs.length ? <CollectionBriefList subjects={directParentBriefs} /> : null}
                <HierarchyReviewWorkspace
                  primary={primary}
                  subjects={selected.subjects}
                  relatedSubjects={structureSubjects}
                  rows={hierarchyRows}
                  selectedIds={selectedStructure}
                  selectedSubject={hierarchyInspectorSubject || primary}
                  bookshelfVisibility={bookshelfVisibility}
                  bookshelfCustomMode={bookshelfCustomMode}
                  draft={hierarchyDraft}
                  entityType={hierarchyProposalType}
                  dirty={hierarchyDraftDirty}
                  statusCounts={hierarchyStatusCounts}
                  categories={categories}
                  selectedCategoryIds={structureCategoryIds[hierarchyInspectorSubject?.id || 0] ?? (Array.isArray(asRecord(hierarchyInspectorSubject?.ai_inferences_json).classification_prefill_ids) ? asRecord(hierarchyInspectorSubject?.ai_inferences_json).classification_prefill_ids as number[] : [])}
                  onCategoryIdsChange={(ids) => hierarchyInspectorSubject && setStructureCategoryIds((current) => ({ ...current, [hierarchyInspectorSubject.id]: ids }))}
                  disabled={busy || !!selected.decision}
                  choiceFor={(subject) => subject.id === primary.id ? (identityChoice === "new" ? "create" : identityChoice ? String(identityChoice) : "") : structureChoiceFor(subject)}
                  onToggle={toggleStructure}
                  onSelect={setHierarchyInspectorId}
                  onBookshelfToggle={(subjectId) => setBookshelfVisibility((current) => ({ ...current, [subjectId]: !current[subjectId] }))}
                  onBookshelfBatch={applyBookshelfVisibility}
                  onBookshelfCustomMode={setBookshelfCustomMode}
                  onDraftChange={(next) => { if (next.displayTitle !== hierarchyDraft.displayTitle && hierarchyInspectorSubject) setStructureChoices((current) => ({ ...current, [hierarchyInspectorSubject.id]: "" })); setHierarchyDraft(next); }}
                  onTypeChange={(next) => { setHierarchyProposalType(next); if (hierarchyInspectorSubject?.id === primary.id) setIdentityChoice(null); else if (hierarchyInspectorSubject) setStructureChoices((current) => ({ ...current, [hierarchyInspectorSubject.id]: "" })); }}
                  onChoice={(subject, value) => value && value !== "create"
                    ? void inspectCandidate(subject, Number(value))
                    : subject.id === primary.id ? setIdentityChoice(value === "create" ? "new" : null) : setStructureChoices((current) => ({ ...current, [subject.id]: value }))}
                  onSave={() => void saveHierarchyDraft()}
                  onRefresh={() => void refreshHierarchyCandidates()}
                  onCreateParent={(childId, type, title) => void createParentStructure(childId, type, title)}
                  onAddRelation={(parentId, memberId) => void addHierarchyRelation(parentId, memberId)}
                  onDeleteRelation={(relationId) => void deleteHierarchyRelation(relationId)}
                  onResolveConflict={(conflictId, status) => void resolveHierarchyConflict(conflictId, status)}
                  guideControl={hierarchyInspectorSubject ? <GuideDraftEditor
                    key={hierarchyInspectorSubject.id}
                    subject={hierarchyInspectorSubject}
                    value={guideDrafts[hierarchyInspectorSubject.id] ?? hierarchyInspectorSubject.guide_markdown_draft ?? ""}
                    disabled={busy || !!selected.decision}
                    onChange={(value) => setGuideDrafts((current) => ({ ...current, [hierarchyInspectorSubject.id]: value }))}
                    onAdd={(raw, title) => void addGuideMaterial(hierarchyInspectorSubject, raw, title)}
                  /> : null}
                />
              </> : null}
              onDraftChange={(next) => {
                if (next.displayTitle !== draft.displayTitle) setIdentityChoice(null);
                setDraft(next);
              }}
              onTypeChange={(next) => { setProposalType(next); setIdentityChoice(null); }}
              onRefreshCandidates={() => void refreshCandidates()}
              onIdentityChoice={(value) => value === "new" || value === null ? setIdentityChoice(value) : void inspectCandidate(primary, value)}
              imageSelection={draftImageSelection}
              onProductImagesChange={setDraftImageSelection}
            />
            <GuideDraftEditor
              subject={primary}
              value={guideDrafts[primary.id] ?? primary.guide_markdown_draft ?? ""}
              disabled={busy || !!selected.decision}
              onChange={(value) => setGuideDrafts((current) => ({ ...current, [primary.id]: value }))}
              onAdd={(raw, title) => void addGuideMaterial(primary, raw, title)}
            />
            <div className="draft-footer"><p>Research 只负责预填。这里显示的值才是最终提交草稿，人工修改优先。鼠标位于本表单时可按 Ctrl+S 保存。</p><button disabled={busy || !!selected.decision || !proposalTitle || !proposalType || !draftDirty} onClick={() => void saveCatalogDraft()}>{busy ? "保存中…" : "保存草稿"}</button></div>
          </ReviewSection>
          </div>
          {proposalType === "book" ? <ReviewSection eyebrow="EDITION · REVIEW DRAFT" title="推荐版本" tone="facts">
            <p className="section-help">版本可以稀疏；只有确认的版本才会写入 Catalog，并可成为本条书单的推荐版本。</p>
            {matchedEntity?.editions.length ? <div className="edition-draft-list"><strong>已有 Catalog 版本</strong>{matchedEntity.editions.map((edition) => <label key={edition.id} className="edition-draft-row"><input type="radio" name="recommended-edition" checked={recommendedEditionId === edition.id} onChange={() => { setRecommendedEditionId(edition.id); setRecommendedEditionDraftId(null); }} />{edition.cover_local_path ? <img src={catalogAssetUrl(edition.cover_local_path)} alt="已有版本封面" /> : null}<span>#{edition.id} · {edition.isbns.map((isbn) => isbn.isbn_val).join("、") || "无 ISBN"} · {edition.format || "装帧未知"} · {edition.page_count ?? "—"} 页</span></label>)}</div> : null}
            {selected.edition_drafts.length ? <div className="edition-draft-list"><strong>采集到的版本候选</strong>{selected.edition_drafts.map((edition) => {
              const data = edition.proposed_data;
              const covers = (Array.isArray(data.cover_choices) ? data.cover_choices : []).map(asRecord);
              return <div className="edition-draft-row" key={edition.id}>
                <div><strong>候选 #{edition.id} · {edition.review_status}</strong><p>ISBN：{Array.isArray(data.isbns) ? data.isbns.join("、") : "—"} · {String(data.publisher || "出版社未知")} · {String(data.format || "装帧未知")} · {String(data.page_count || "—")} 页</p>
                  {covers.length ? <div className="edition-cover-options">{covers.map((cover, index) => <label key={index}><input type="radio" name={`edition-cover-${edition.id}`} checked={(coverChoiceByDraft[edition.id] || data.cover_local_path || covers[0]?.local_path) === cover.local_path} disabled={!cover.local_path || busy} onChange={() => setCoverChoiceByDraft((current) => ({ ...current, [edition.id]: String(cover.local_path) }))} />{cover.source_url ? <img src={catalogAssetUrl(String(cover.local_path || cover.source_url))} alt={`候选封面 ${index + 1}`} /> : null}</label>)}</div> : null}
                  {edition.review_status === "proposed" ? <div><button type="button" disabled={busy} onClick={() => void decideEditionDraft(edition.id, "confirmed", coverChoiceByDraft[edition.id] || String(data.cover_local_path || ""))}>确认版本</button><button type="button" disabled={busy} onClick={() => void decideEditionDraft(edition.id, "rejected")}>舍弃</button></div> : edition.review_status === "confirmed" ? <label><input type="radio" name="recommended-edition" checked={recommendedEditionDraftId === edition.id} onChange={() => { setRecommendedEditionDraftId(edition.id); setRecommendedEditionId(null); }} />推荐这个版本</label> : null}
                </div>
              </div>;
            })}</div> : <p className="muted">尚未采集版本；推荐版本可以留空。</p>}
          </ReviewSection> : null}
          <ReviewSection eyebrow="RESEARCH TOOLS · 仅补充草稿" title="商品 / 官方补资料" tone="facts">
            <div className="research-tool-row"><div><strong>{productCaptured ? "商品资料已采集" : "尚未采集商品资料"}</strong><p>使用当前 Item 顶部工具条搜索与采集；结果只预填 Catalog Draft，不会直接写入正式库。</p></div></div>
            {productCaptured ? <details className="capture-results"><summary>查看字段证据与来源</summary><ProductCaptureResults subject={primary} disabled={busy || !!selected.decision} showImages={false} /></details> : null}
          </ReviewSection>
          <ReviewSection eyebrow="COLLECTION · REVIEW STAGED" title="成员结构" tone="structure" action={memberStructureSubjects.length ? <button className="icon-button" disabled={!!selected.decision} onClick={toggleAllStructure}>{memberStructureSubjects.every((subject) => selectedStructure.includes(subject.id)) ? "取消全选成员" : `全选 ${memberStructureSubjects.length} 个`}</button> : null}>
            {memberStructureSubjects.length ? <div className="member-structure-block">
              <div className="structure-summary"><div><strong>{primary.proposed_display_title}</strong><span>{entityLabels[proposalType || "set"]} · 已发现 {memberStructureSubjects.length} 个直接成员</span></div><p>只对勾选成员建立直接关系；达人推荐仍只指向当前主项。</p></div>
              <div className="member-tools"><button disabled={!selectedMemberSubjects.length || !!selected.decision || busy} onClick={() => void researchSelectedStructure()}>获取并汇总所选官网资料</button><button disabled={!selectedMemberSubjects.length || !!selected.decision} onClick={() => setStructureAction("本轮暂不补成员资料，仅保留已确认的结构草稿。")}>暂不补资料</button></div>
              <div className="structure-list">{memberStructureSubjects.map((subject) => {
              const cover = factValue(subject.facts_json, "cover");
              const catalogMatch = subject.resolved_catalog_entity_id || subject.candidates[0]?.catalog_entity_id;
              const factCount = Object.keys(subject.facts_json || {}).filter((key) => key !== "included_in").length;
              const hasOfficialSource = subject.sources.some((source) => source.source_type?.includes("official") || source.source_type?.includes("publisher"));
              return <div className="structure-choice" key={subject.id}>
                <label>
                  <input type="checkbox" disabled={!!selected.decision} checked={selectedStructure.includes(subject.id)} onChange={() => toggleStructure(subject.id)} />
                  {typeof cover === "string" && cover ? <img className="structure-cover" src={cover} alt="" /> : null}
                  <span><strong>{subject.proposed_display_title}</strong><small>Catalog：{catalogMatch ? `候选 #${catalogMatch}` : "未找到，将新建"} · 资料：{hasOfficialSource ? `官网 ${factCount} 项` : factCount ? `${factCount} 项` : "无"} · 封面：{cover ? "有" : "无"}</small></span>
                </label>
                <button type="button" className="structure-detail-button" onClick={() => openMemberDetails(subject)}><BookOpen size={13} />查看详情</button>
                {selectedStructure.includes(subject.id) ? subject.resolved_catalog_entity_id
                  ? <p>复用历史确认 #{subject.resolved_catalog_entity_id}</p>
                  : !subject.candidates.length
                    ? <p className="structure-identity-auto"><Check size={13} />Catalog 未找到，提交时自动新建 {entityLabels[subject.proposed_entity_type || "book"]} Entity</p>
                    : <select aria-label={`${subject.proposed_display_title} 的身份决定`} value={structureChoiceFor(subject)} onChange={(event) => event.target.value && event.target.value !== "create" ? void inspectCandidate(subject, Number(event.target.value)) : setStructureChoices((current) => ({ ...current, [subject.id]: event.target.value }))}><option value="">存在多个候选，请查看详情…</option><option value="create">以上均不是，提交时新建</option>{subject.candidates.map((candidate) => <option key={candidate.catalog_entity_id} value={candidate.catalog_entity_id}>查看 #{candidate.catalog_entity_id} · {candidate.display_title}</option>)}</select>
                  : null}
                </div>;
              })}</div>
            </div> : <p className="structure-empty member-empty">尚未发现直接成员。</p>}
            {structureAction ? <p className="structure-action-status"><CheckCircle2 size={14} />{structureAction} Research 结果仍留在审核区。</p> : null}
          </ReviewSection>
          <ReviewSection eyebrow="CLASSIFICATION · CATALOG DRAFT" title="分类" tone="ai" action={classificationDescription ? <button className="icon-button" type="button" disabled={busy || !!selected.decision || classificationStatus.startsWith("正在")} onClick={() => void summarizeClassification()}><Sparkles size={14} />{classificationStatus.startsWith("正在") ? "简介总结中…" : hasDescriptionSummary ? "重新根据简介总结" : "根据简介总结"}</button> : categorySuggestionRows.length ? <span className="ai-ready"><Sparkles size={13} />Research 已预填</span> : null}>
            <p className="section-help">优先采用官方分类；官方未标注时根据简介归纳。删掉不准确的建议、补上遗漏项；没有直接依据的维度保持为空。</p>
            {classificationStatus && !classificationStatus.startsWith("正在") ? <p className="classification-summary-status"><Check size={13} />{classificationStatus}</p> : null}
            <CategoryReview
              categories={categories}
              suggestions={categorySuggestionRows}
              selectedIds={selectedCategoryIds}
              primaryByType={primaryCategoryByType}
              disabled={busy || !!selected.decision}
              onSelectionChange={updateCategorySelection}
              onPrimaryChange={updatePrimaryCategory}
            />
          </ReviewSection>
          <ReviewSection eyebrow="COMMIT PLAN · FINAL CHECK" title="本次将写入" tone="commit">
            <div className="commit-preview">
              <div><small>身份</small><strong>{identityChoice === "new" ? `新建 1 ${proposalType ? entityLabels[proposalType] : "Entity"}` : typeof identityChoice === "number" ? `复用 Catalog #${identityChoice}` : "尚未确认"}</strong></div>
              <div><small>结构对象</small><strong>{selectedStructureSubjects.length ? `${selectedNewStructures} 个新建 · ${selectedExistingStructures} 个复用` : "不写入额外对象"}</strong></div>
              <div><small>直接关系</small><strong>{selectedStructureSubjects.length ? `${selectedParentSubjects.length} 个父级 · ${selectedMemberSubjects.length} 个成员` : "无套系关系"}</strong></div>
              <div><small>达人推荐</small><strong>{currentTargetList ? `${currentTargetList.creator_name} → ${proposalTitle || "当前主项"}` : "不建立推荐关系"}</strong></div>
              <div className="commit-categories"><small>分类</small><span>{selectedCategories.length ? selectedCategories.map((category) => <b key={category.id}>{category.name_zh}</b>) : "保持为空"}</span></div>
              <div><small>封面</small><strong>{draftCoverCount ? `${draftCoverCount} 张已准备` : "暂无封面"}</strong></div>
              <div className="commit-bookshelf"><small>Bookshelf</small><strong>显示 {bookshelfVisibleSubjects.length} 个 · 隐藏 {bookshelfHiddenCount} 个</strong></div>
            </div>
            {unresolvedStructureChoices.length ? <p className="commit-warning"><CircleAlert size={14} />还有 {unresolvedStructureChoices.length} 个已选结构对象未确认身份。</p> : null}
            {conflictingStructureSubjects.length || primary.pending_conflict_count ? <p className="commit-warning"><CircleAlert size={14} />还有 {conflictingStructureSubjects.length + (primary.pending_conflict_count ? 1 : 0)} 个节点存在待处理数据冲突。</p> : null}
            {disconnectedStructureSubjects.length ? <p className="commit-warning"><CircleAlert size={14} />父级链不完整：请同时勾选它到当前对象之间的直接层级。</p> : null}
            {selectedMemberSubjects.length && currentTargetList ? <p className="commit-safe"><ShieldCheck size={14} />不会创建 {selectedMemberSubjects.length} 条单本达人推荐关系。</p> : null}
          </ReviewSection>
          {!["resolved", "ignored"].includes(selected.status) ? <div className="review-actions"><button className="ignore" disabled={busy} onClick={() => void decide("ignore")}><X size={16} />忽略来源项</button><button className="back" type="button" onClick={() => document.querySelector(".review-section.proposal")?.scrollIntoView({ behavior: "smooth", block: "start" })}>返回修改</button><button className="create" disabled={busy || !canSubmit} onClick={() => identityChoice && void decide(identityChoice === "new" ? "create_new" : "match_existing", typeof identityChoice === "number" ? identityChoice : undefined)}><ShieldCheck size={16} />确认结构并写入 Catalog</button></div> : null}
        </> : <div className="review-placeholder"><ShieldCheck size={38} /><h2>选择一个审核项</h2><p>先确认身份，再把来源关系提交到正式 Catalog。</p></div>}
      </section>
      {hasSourceMedia ? <><div className="review-resizer media-resizer" role="separator" aria-label="调整右侧来源图片宽度" aria-orientation="vertical" aria-valuemin={REVIEW_MEDIA_MIN} aria-valuemax={paneWidthLimit("media")} aria-valuenow={mediaWidth} tabIndex={0} title="拖动调整右侧宽度" onPointerDown={(event) => startPaneResize("media", event)} onKeyDown={(event) => resizePaneWithKeyboard("media", event)} /><ReviewEvidenceRail images={sourceImages} loading={sourceDocumentLoading} /></> : null}
    </div>
  </div>;
}

function ReviewProgressStep({ label, complete, value }: { label: string; complete: boolean; value: string }) {
  return <div className={complete ? "complete" : "pending"}><span>{complete ? <Check size={13} /> : "·"}</span><p><strong>{label}</strong><small>{value}</small></p></div>;
}

function CollectionBriefList({ subjects }: { subjects: ResearchSubject[] }) {
  return <section className="collection-briefs" aria-label="所属体系">
    <header><div><small>COLLECTION BRIEF</small><strong>所属体系</strong></div><span>轻量背景</span></header>
    <div>{subjects.map((subject) => {
      const brief = collectionBrief(subject);
      return <article key={subject.id}>
        <div className={`collection-brief-mark ${subject.proposed_entity_type || "series"}`}><LibraryBig size={18} /></div>
        <div className="collection-brief-copy">
          <h3>{subject.proposed_display_title}</h3>
          <p className="collection-brief-meta">{entityLabels[subject.proposed_entity_type || "series"]}{brief.publisher ? ` · ${brief.publisher}` : ""}{brief.audience ? ` · ${brief.audience}` : ""}</p>
          <p>{brief.description || "已发现直接父级关系；更完整的成员、级别和官方资料留到系列探索中研究。"}</p>
        </div>
        <a href={`/admin/collection-explore/${subject.id}`} target="_blank" rel="noreferrer">系列探索 <ExternalLink size={12} /></a>
      </article>;
    })}</div>
  </section>;
}

function HierarchyReviewWorkspace({ primary, subjects, relatedSubjects, rows, selectedIds, selectedSubject, bookshelfVisibility, bookshelfCustomMode, draft, entityType, dirty, statusCounts, categories, selectedCategoryIds, onCategoryIdsChange, disabled, choiceFor, onToggle, onSelect, onBookshelfToggle, onBookshelfBatch, onBookshelfCustomMode, onDraftChange, onTypeChange, onChoice, onSave, onRefresh, onCreateParent, onAddRelation, onDeleteRelation, onResolveConflict, guideControl }: {
  primary: ResearchSubject;
  subjects: ResearchSubject[];
  relatedSubjects: ResearchSubject[];
  rows: Array<{ subject: ResearchSubject; depth: number; current: boolean }>;
  selectedIds: number[];
  selectedSubject: ResearchSubject;
  bookshelfVisibility: Record<number, boolean>;
  bookshelfCustomMode: boolean;
  draft: CatalogDraftFields;
  entityType: EntityType | "";
  dirty: boolean;
  statusCounts: Record<StructureNodeStatus["key"], number>;
  categories: CatalogCategory[];
  selectedCategoryIds: number[];
  onCategoryIdsChange: (ids: number[]) => void;
  disabled: boolean;
  choiceFor: (subject: ResearchSubject) => string;
  onToggle: (subjectId: number) => void;
  onSelect: (subjectId: number) => void;
  onBookshelfToggle: (subjectId: number) => void;
  onBookshelfBatch: (mode: "hidden" | "children" | "leaf-books") => void;
  onBookshelfCustomMode: (enabled: boolean) => void;
  onDraftChange: (draft: CatalogDraftFields) => void;
  onTypeChange: (entityType: EntityType | "") => void;
  onChoice: (subject: ResearchSubject, choice: string) => void;
  onSave: () => void;
  onRefresh: () => void;
  onCreateParent: (childId: number, type: "reading_system" | "series" | "level" | "set", title: string) => void;
  onAddRelation: (parentId: number, memberId: number) => void;
  onDeleteRelation: (relationId: number) => void;
  onResolveConflict: (conflictId: number, status: "keep_existing" | "use_proposed" | "ignored") => void;
  guideControl?: ReactNode;
}) {
  const [parentToAdd, setParentToAdd] = useState("");
  const [memberToAdd, setMemberToAdd] = useState("");
  const [newParentOpen, setNewParentOpen] = useState(false);
  const [newParentType, setNewParentType] = useState<"reading_system" | "series" | "level" | "set">("series");
  const [newParentTitle, setNewParentTitle] = useState("");
  const relations = [...new Map(subjects.flatMap((subject) => subject.relations).map((relation) => [relation.id, relation])).values()];
  const parentRelations = relations.filter((relation) => relation.relation_type === "contains" && relation.member_subject_id === selectedSubject.id && relation.review_status !== "rejected");
  const childRelations = relations.filter((relation) => relation.relation_type === "contains" && relation.parent_subject_id === selectedSubject.id && relation.review_status !== "rejected");
  const subjectById = new Map(subjects.map((subject) => [subject.id, subject]));
  const parentIds = new Set(parentRelations.map((relation) => relation.parent_subject_id));
  const childIds = new Set(childRelations.map((relation) => relation.member_subject_id));
  const possibleParents = subjects.filter((subject) => subject.id !== selectedSubject.id && !parentIds.has(subject.id) && subject.proposed_entity_type !== "book");
  const possibleMembers = subjects.filter((subject) => subject.id !== selectedSubject.id && !childIds.has(subject.id));
  const selectedChoice = choiceFor(selectedSubject);
  const selectedStatus = structureNodeStatus(selectedSubject, selectedChoice);
  const includedIds = new Set([primary.id, ...selectedIds]);
  const visibleSubjects = rows.map((row) => row.subject).filter((subject) => includedIds.has(subject.id) && bookshelfVisibility[subject.id]);
  const update = (key: keyof CatalogDraftFields, value: string) => onDraftChange({ ...draft, [key]: value });

  useEffect(() => { setParentToAdd(""); setMemberToAdd(""); setNewParentOpen(false); setNewParentTitle(""); }, [selectedSubject.id]);

  return <section className="hierarchy-review-workspace" aria-label="系列结构审核">
    <header className="hierarchy-review-summary">
      <div><small>系列结构审核</small><strong>当前来源推荐：<b>★ {primary.proposed_display_title}</b></strong></div>
      <div className="hierarchy-summary-counts"><span>Research 发现 <b>{relatedSubjects.length}</b> 个相关节点</span><span><i className="create" />{statusCounts.create} 待创建</span><span><i className="existing" />{statusCounts.existing} 已存在</span><span><i className="suspected" />{statusCounts.suspected} 疑似匹配</span><span><i className="conflict" />{statusCounts.conflict} 冲突</span></div>
    </header>
    <div className="hierarchy-review-split">
      <div className="hierarchy-projection-column">
        <div className="bookshelf-toolbar" aria-label="书架展示设置">
          <div><span>书架展示</span><strong>{bookshelfCustomMode ? `自定义模式 · 已选择 ${visibleSubjects.length} 项` : "选择最终 Bookshelf 粒度"}</strong></div>
          <div className="bookshelf-toolbar-actions">
            {!bookshelfCustomMode ? <><button type="button" disabled={disabled} onClick={() => onBookshelfBatch("hidden")}>全部隐藏</button><button type="button" disabled={disabled} onClick={() => onBookshelfBatch("children")}>显示下一层</button><button type="button" disabled={disabled} onClick={() => onBookshelfBatch("leaf-books")}>显示叶子单本</button><button type="button" className="custom" disabled={disabled} onClick={() => onBookshelfCustomMode(true)}>自定义</button></> : <button type="button" className="custom done" disabled={disabled} onClick={() => onBookshelfCustomMode(false)}>完成自定义</button>}
          </div>
          <small>批量操作作用于当前选中节点「{selectedSubject.proposed_display_title}」；“全部隐藏”作用于本次确认的整棵树。</small>
        </div>
        <div className="hierarchy-outline" role="tree" aria-label="Research 系列结构与 Bookshelf 设置">
          {rows.map((row) => {
            const subject = row.subject;
            const current = row.current;
            const status = structureNodeStatus(subject, choiceFor(subject));
            const active = selectedSubject.id === subject.id;
            const included = includedIds.has(subject.id);
            const visible = !!bookshelfVisibility[subject.id];
            const cover = factValue(subject.facts_json, "cover");
            return <div className={`hierarchy-tree-row${current ? " current" : " passive"}${active ? " active" : ""}${!included ? " excluded" : ""}`} key={subject.id} role="treeitem" aria-selected={active} style={{ "--tree-depth": row.depth } as CSSProperties}>
              {current ? <span className="hierarchy-check-spacer">★</span> : <label className="hierarchy-tree-check" onClick={(event) => event.stopPropagation()} title="是否写入 Catalog"><input type="checkbox" checked={selectedIds.includes(subject.id)} disabled={disabled} onChange={() => onToggle(subject.id)} aria-label={`写入 Catalog：${subject.proposed_display_title}`} /></label>}
              <button type="button" className="hierarchy-tree-main" onClick={() => onSelect(subject.id)}>
                <span className="hierarchy-tree-guide">{row.depth ? "├─" : ""}</span>
                {typeof cover === "string" && cover ? <img className="hierarchy-tree-cover" src={cover} alt="" /> : <span className={`hierarchy-tree-cover fallback ${subject.proposed_entity_type || "series"}`}><BookOpen size={11} /></span>}
                <span className="hierarchy-tree-title"><strong>{subject.proposed_display_title}</strong><small>{entityLabels[subject.proposed_entity_type || "series"]}{current ? " · ★ 当前来源推荐" : ""}</small></span>
                <span className={`structure-status-chip ${status.key}`}>{status.label}</span>
              </button>
              <button type="button" className={`bookshelf-state-toggle${visible ? " visible" : " hidden"}${bookshelfCustomMode ? " editing" : ""}`} aria-pressed={visible} disabled={disabled || !included || !bookshelfCustomMode} title={!included ? "请先选择写入 Catalog" : bookshelfCustomMode ? "切换 Bookshelf 状态" : "点击“自定义”后逐项修改"} onClick={() => onBookshelfToggle(subject.id)}>{visible ? <Eye size={12} /> : <EyeOff size={12} />}<span>{visible ? (bookshelfCustomMode ? "显示" : "书架显示") : (bookshelfCustomMode ? "隐藏" : "书架隐藏")}</span></button>
            </div>;
          })}
        </div>
        <aside className="bookshelf-preview" aria-label="Bookshelf Preview">
          <header><div><small>BOOKSHELF PREVIEW</small><strong>提交后的书架项目</strong></div><span>{visibleSubjects.length} 项</span></header>
          {visibleSubjects.length ? <div className="bookshelf-preview-grid">{visibleSubjects.map((subject) => {
            const cover = factValue(subject.facts_json, "cover");
            return <article key={subject.id}>{typeof cover === "string" && cover ? <img src={cover} alt="" /> : <span className={`preview-cover ${subject.proposed_entity_type || "series"}`}><LibraryBig size={15} /></span>}<div><strong>{subject.proposed_display_title}</strong><small>{entityLabels[subject.proposed_entity_type || "series"]}</small></div></article>;
          })}</div> : <p><EyeOff size={15} />当前没有 Entity 会显示在 Bookshelf。</p>}
        </aside>
      </div>
      <aside className="hierarchy-inspector">
        <header><div><small>{selectedSubject.id === primary.id ? "CURRENT RECOMMENDATION" : "RESEARCH DISCOVERY"}</small><h3>{selectedSubject.id === primary.id ? "★ " : ""}{selectedSubject.proposed_display_title}</h3></div><span className={`structure-status-chip ${selectedSubject.id === primary.id ? "recommended" : selectedStatus.key}`}>{selectedSubject.id === primary.id ? "当前来源推荐" : selectedStatus.label}</span></header>

        <div className="inspector-fields">
          <label><span>对象类型</span><select value={entityType} disabled={disabled} onChange={(event) => onTypeChange(event.target.value as EntityType | "")}><option value="">待确认</option>{(selectedSubject.id === primary.id ? reviewEntityTypes : parentEntityTypes).map((value) => <option key={value} value={value}>{entityLabels[value]}</option>)}</select></label>
          <label className="wide"><span>显示名称</span><input value={draft.displayTitle} disabled={disabled} onChange={(event) => update("displayTitle", event.target.value)} /></label>
          <label className="wide"><span>简介</span><textarea rows={3} value={draft.description} disabled={disabled} onChange={(event) => update("description", event.target.value)} /></label>
        </div>
        <details className="entity-type-reason inspector-type-reason"><summary>查看判断依据</summary><p>{entityTypeInference(selectedSubject).reason}</p></details>
        <div className="inspector-save-row"><button type="button" disabled={disabled || !dirty || !draft.displayTitle.trim() || !entityType} onClick={onSave}>{dirty ? "保存节点草稿" : "节点草稿已保存"}</button></div>

        <section className="inspector-section catalog-match-inspector">
          <header><div><strong>Catalog 匹配</strong><small>正常节点自动处理；只需处理疑似项或冲突。</small></div><button type="button" disabled={disabled || dirty} onClick={onRefresh}><RefreshCw size={12} />重新检查</button></header>
          {(selectedSubject.pending_conflicts || []).map((conflict) => <div className="inspector-conflict" key={conflict.id}><p><CircleAlert size={13} /><strong>{conflict.field_path}</strong></p><div><span>已有：{draftText(conflict.existing_value)}</span><span>Research：{draftText(conflict.proposed_value)}</span></div><footer><button type="button" disabled={disabled} onClick={() => onResolveConflict(conflict.id, "keep_existing")}>保留已有</button><button type="button" disabled={disabled} onClick={() => onResolveConflict(conflict.id, "use_proposed")}>采用 Research</button><button type="button" disabled={disabled} onClick={() => onResolveConflict(conflict.id, "ignored")}>忽略字段</button></footer></div>)}
          {selectedSubject.candidates.length ? <div className="inspector-candidates">
            {selectedSubject.candidates.map((candidate) => <label key={candidate.id} className={selectedChoice === String(candidate.catalog_entity_id) ? "selected" : ""}><input type="radio" name={`hierarchy-candidate-${selectedSubject.id}`} checked={selectedChoice === String(candidate.catalog_entity_id)} disabled={disabled || dirty} onChange={() => onChoice(selectedSubject, String(candidate.catalog_entity_id))} /><span><strong>{candidate.display_title}</strong><small>#{candidate.catalog_entity_id} · {entityLabels[candidate.entity_type as EntityType] || candidate.entity_type} · {Math.round((candidate.match_score ?? 0) * 100)}%</small></span></label>)}
            <label className={selectedChoice === "create" ? "selected" : ""}><input type="radio" name={`hierarchy-candidate-${selectedSubject.id}`} checked={selectedChoice === "create"} disabled={disabled || dirty} onChange={() => onChoice(selectedSubject, "create")} /><span><strong>以上均不是</strong><small>随整体提交创建新 Entity</small></span></label>
          </div> : <p className="inspector-auto-decision"><Check size={13} />未发现可信候选，随整体提交自动创建。</p>}
        </section>

        <section className="inspector-section relation-inspector">
          <header><div><strong>结构关系</strong><small>只维护直接 membership，不生成祖先关系。</small></div></header>
          <RelationGroup title="父级" relations={parentRelations.map((relation) => ({ relation, subject: subjectById.get(relation.parent_subject_id) }))} disabled={disabled} onDelete={onDeleteRelation} />
          <div className="relation-add-row"><select value={parentToAdd} disabled={disabled || !possibleParents.length} onChange={(event) => setParentToAdd(event.target.value)}><option value="">添加已有节点为父级…</option>{possibleParents.map((subject) => <option key={subject.id} value={subject.id}>{subject.proposed_display_title} · {entityLabels[subject.proposed_entity_type || "series"]}</option>)}</select><button type="button" disabled={disabled || !parentToAdd} onClick={() => { onAddRelation(Number(parentToAdd), selectedSubject.id); setParentToAdd(""); }}>添加</button><button type="button" disabled={disabled} onClick={() => setNewParentOpen((open) => !open)}>新建父级</button></div>
          {newParentOpen ? <form className="inspector-new-parent" onSubmit={(event) => { event.preventDefault(); if (!newParentTitle.trim()) return; onCreateParent(selectedSubject.id, newParentType, newParentTitle.trim()); setNewParentTitle(""); setNewParentOpen(false); }}><select value={newParentType} disabled={disabled} onChange={(event) => setNewParentType(event.target.value as "reading_system" | "series" | "level" | "set")}><option value="reading_system">阅读产品线</option><option value="series">系列</option><option value="level">级别</option><option value="set">组合</option></select><input value={newParentTitle} disabled={disabled} placeholder="父级名称" onChange={(event) => setNewParentTitle(event.target.value)} /><button disabled={disabled || !newParentTitle.trim()}>创建</button></form> : null}
          <RelationGroup title="直接包含" relations={childRelations.map((relation) => ({ relation, subject: subjectById.get(relation.member_subject_id) }))} disabled={disabled} onDelete={onDeleteRelation} />
          <div className="relation-add-row"><select value={memberToAdd} disabled={disabled || !possibleMembers.length} onChange={(event) => setMemberToAdd(event.target.value)}><option value="">添加已有节点为直接成员…</option>{possibleMembers.map((subject) => <option key={subject.id} value={subject.id}>{subject.proposed_display_title} · {entityLabels[subject.proposed_entity_type || "set"]}</option>)}</select><button type="button" disabled={disabled || !memberToAdd} onClick={() => { onAddRelation(selectedSubject.id, Number(memberToAdd)); setMemberToAdd(""); }}>添加</button></div>
        </section>

        <section className="inspector-section"><header><strong>节点 Classification</strong></header><div className="catalog-admin-categories">{categories.map((category) => <label key={category.id}><input type="checkbox" disabled={disabled} checked={selectedCategoryIds.includes(category.id)} onChange={(event) => onCategoryIdsChange(event.target.checked ? [...selectedCategoryIds, category.id] : selectedCategoryIds.filter((id) => id !== category.id))} />{category.name_zh}</label>)}</div></section>
        <section className="inspector-section">{guideControl}</section>
        <section className="inspector-section source-inspector"><header><div><strong>Research 来源</strong><small>{selectedSubject.sources.length} 个来源</small></div></header>{selectedSubject.sources.length ? <div>{selectedSubject.sources.map((source) => /^https?:\/\//.test(source.source_url) ? <a key={source.id} href={source.source_url} target="_blank" rel="noreferrer"><ExternalLink size={11} /><span>{source.source_title || source.source_url}</span></a> : <span key={source.id}>{source.source_title || "手工资料"}</span>)}</div> : <p className="muted">暂无来源链接</p>}</section>
      </aside>
    </div>
  </section>;
}

function RelationGroup({ title, relations, disabled, onDelete }: { title: string; relations: Array<{ relation: ResearchSubject["relations"][number]; subject?: ResearchSubject }>; disabled: boolean; onDelete: (relationId: number) => void }) {
  return <div className="relation-group"><strong>{title}</strong>{relations.length ? <div>{relations.map(({ relation, subject }) => <span key={relation.id}><b>{subject?.proposed_display_title || "未知节点"}</b><small>{subject?.proposed_entity_type ? entityLabels[subject.proposed_entity_type] : "Entity"}</small><button type="button" disabled={disabled} onClick={() => onDelete(relation.id)} aria-label={`删除 ${subject?.proposed_display_title || "关系"}`}><X size={12} /></button></span>)}</div> : <p>无</p>}</div>;
}

function CatalogDraftEditor({ subject, draft, entityType, entityTypes = reviewEntityTypes, disabled, identityChoice, identityDisabled, parentControl, parentDetails, imageSelection, onDraftChange, onTypeChange, onRefreshCandidates, onIdentityChoice, onProductImagesChange }: {
  subject: ResearchSubject;
  draft: CatalogDraftFields;
  entityType: EntityType | "";
  entityTypes?: EntityType[];
  disabled: boolean;
  identityChoice: "new" | number | null;
  identityDisabled: boolean;
  parentControl?: ReactNode;
  parentDetails?: ReactNode;
  imageSelection: ProductImageSelection;
  onDraftChange: (value: CatalogDraftFields) => void;
  onTypeChange: (value: EntityType | "") => void;
  onRefreshCandidates: () => void;
  onIdentityChoice: (value: "new" | number | null) => void;
  onProductImagesChange: (selection: ProductImageSelection) => void;
}) {
  const facts = subject.facts_json || {};
  const update = (key: keyof CatalogDraftFields, value: string) => onDraftChange({ ...draft, [key]: value });
  const sourceLabel = (factKey: string) => {
    const sourceIds = asRecord(facts[factKey]).source_ids;
    if (!Array.isArray(sourceIds) || !sourceIds.length) return "";
    const labels = sourceIds.flatMap((id) => {
      const source = subject.sources.find((row) => row.id === id);
      if (!source) return [];
      if (source.source_type?.includes("amazon")) return ["Amazon"];
      if (source.source_type?.includes("jd")) return ["京东"];
      if (source.source_type?.includes("publisher") || source.source_type?.includes("official")) return ["官方"];
      return [source.source_title || "Research"];
    });
    return [...new Set(labels)].join(" + ");
  };
  const conflicts: Array<{ label: string; field: keyof CatalogDraftFields; primary: string; primarySource: string; alternative: string; alternativeSource: string }> = [
    ["作者", "author", "author"], ["绘者", "illustrator", "illustrator"], ["译者", "translator", "translator"], ["简介", "description", "description"],
  ].flatMap(([label, field, factKey]) => {
    const primary = draftText(factValue(facts, factKey));
    if (!primary) return [];
    return [
      { source: "Amazon", value: draftText(factValue(facts, `amazon_${factKey}`)) },
      { source: "京东", value: draftText(factValue(facts, `jd_${factKey}`)) },
    ].filter((row) => row.value && row.value !== primary).map((row) => ({
      label,
      field: field as keyof CatalogDraftFields,
      primary,
      primarySource: sourceLabel(factKey) || "Research",
      alternative: row.value,
      alternativeSource: row.source,
    }));
  });
  const cognitive = factValue(withoutClassification(subject.ai_inferences_json), "cognitive_load");
  const typeInference = entityTypeInference(subject);

  return <>
    <div className={`entity-type-picker${parentControl ? " with-parent" : ""}`}>
      <label><span>对象类型</span><select disabled={disabled} value={entityType} onChange={(event) => onTypeChange(event.target.value as EntityType | "")}><option value="">待确认</option>{entityTypes.map((value) => <option key={value} value={value}>{entityLabels[value]}</option>)}</select></label>
      {parentControl}
      <details className="entity-type-reason"><summary>查看判断依据</summary><p>{typeInference.reason}{typeInference.confidence != null ? `（置信度 ${Math.round(typeInference.confidence * 100)}%）` : ""}</p></details>
    </div>
    {parentDetails}
    <div className="catalog-draft-grid">
      <div className="draft-input draft-title-identity wide"><span>显示名称<button type="button" disabled={identityDisabled} onClick={onRefreshCandidates}><Search size={13} />查是否已有 Entity</button></span><input aria-label="显示名称" disabled={disabled} value={draft.displayTitle} onChange={(event) => update("displayTitle", event.target.value)} /></div>
      {identityChoice !== null || subject.candidates.length ? <div className="inline-identity-result wide">
        {subject.candidates.length ? <>{subject.candidates.map((candidate) => <button type="button" key={candidate.id} className={identityChoice === candidate.catalog_entity_id ? "selected" : ""} disabled={identityDisabled} onClick={() => onIdentityChoice(candidate.catalog_entity_id)}>{identityChoice === candidate.catalog_entity_id ? <Check size={13} /> : null}<span><strong>{candidate.display_title}</strong><small>查看 #{candidate.catalog_entity_id} · {entityLabels[candidate.entity_type as EntityType] || candidate.entity_type} · 匹配分 {Math.round((candidate.match_score ?? 0) * 100)}</small></span></button>)}<button type="button" className={identityChoice === "new" ? "selected" : ""} disabled={identityDisabled} onClick={() => onIdentityChoice("new")}>以上均不是，创建新 Entity</button></> : <p><CheckCircle2 size={15} />未发现已有 Entity，提交时创建新的 {entityType ? entityLabels[entityType] : "Entity"}</p>}
      </div> : null}
      <DraftInput label="英文名" value={draft.titleEn} onChange={(value) => update("titleEn", value)} disabled={disabled} />
      <DraftInput label="中文名" value={draft.titleZh} onChange={(value) => update("titleZh", value)} disabled={disabled} />
      <DraftInput label="别名" value={draft.aliases} onChange={(value) => update("aliases", value)} disabled={disabled} wide hint="多个别名用逗号分隔" />
      <DraftInput label="作者" value={draft.author} onChange={(value) => update("author", value)} disabled={disabled} source={sourceLabel("author")} />
      <DraftInput label="绘者" value={draft.illustrator} onChange={(value) => update("illustrator", value)} disabled={disabled} source={sourceLabel("illustrator")} />
      <DraftInput label="译者" value={draft.translator} onChange={(value) => update("translator", value)} disabled={disabled} source={sourceLabel("translator")} />
      <label className="draft-input"><span>虚构属性</span><select disabled={disabled} value={draft.fictionType} onChange={(event) => update("fictionType", event.target.value)}><option value="unknown">未知</option><option value="fiction">虚构</option><option value="nonfiction">非虚构</option><option value="mixed">混合</option></select></label>
      <DraftSelect label="语言" value={draft.language} onChange={(value) => update("language", value)} disabled={disabled} source={sourceLabel("language")} options={languageOptions} />
      <label className="draft-input wide"><span>简介{sourceLabel("description") ? <em>{sourceLabel("description")}</em> : null}</span><textarea rows={4} disabled={disabled} value={draft.description} onChange={(event) => update("description", event.target.value)} /></label>
      <DraftInput label="官方 / 出版社建议年龄" value={draft.officialAge} onChange={(value) => update("officialAge", value)} disabled={disabled} source={sourceLabel("official_age")} />
      <DraftInput label="AR" value={draft.ar} onChange={(value) => update("ar", value)} disabled={disabled} source={sourceLabel("ar")} action={<a href="https://www.arbookfind.com/" target="_blank" rel="noreferrer"><ExternalLink size={11} />官方查询</a>} />
      {entityType === "book"
        ? <DraftInput label="Lexile" value={draft.lexile} onChange={(value) => update("lexile", value)} disabled={disabled} source={sourceLabel("lexile")} action={<a href="https://hub.lexile.com/find-a-book/" target="_blank" rel="noreferrer"><ExternalLink size={11} />官方查询</a>} />
        : <>
          <DraftInput label="Lexile 最低值" type="number" value={draft.lexileMin} onChange={(value) => update("lexileMin", value)} disabled={disabled} source={sourceLabel("lexile_min")} />
          <DraftInput label="Lexile 最高值" type="number" value={draft.lexileMax} onChange={(value) => update("lexileMax", value)} disabled={disabled} source={sourceLabel("lexile_max")} />
        </>}
    </div>
    {factValue(facts, "product_images") ? <div className="draft-product-images"><div className="draft-product-images-heading"><strong>Work 内页预览</strong><span>勾选可作为内容预览的内页图片；封面在 Edition 区域确认。</span></div><ProductCaptureResults subject={subject} disabled={disabled} selection={imageSelection} onSelectionChange={onProductImagesChange} showFacts={false} showCoverSelection={false} /></div> : null}
    {conflicts.map((conflict) => <div className="draft-conflict" key={`${conflict.label}-${conflict.alternativeSource}`}><CircleAlert size={16} /><div><strong>{conflict.label}存在来源冲突</strong><button type="button" className={draft[conflict.field] === conflict.primary ? "selected" : ""} onClick={() => update(conflict.field, conflict.primary)}>{draft[conflict.field] === conflict.primary ? <Check size={12} /> : null}{conflict.primary} <small>{conflict.primarySource}</small></button><button type="button" className={draft[conflict.field] === conflict.alternative ? "selected" : ""} onClick={() => update(conflict.field, conflict.alternative)}>{draft[conflict.field] === conflict.alternative ? <Check size={12} /> : null}{conflict.alternative} <small>{conflict.alternativeSource}</small></button></div></div>)}
    <div className="difficulty-inline"><div><small>Difficulty / AI 辅助</small><strong>AR {draft.ar || "NULL"}　·　Lexile {entityType === "book" ? draft.lexile || "NULL" : draft.lexileMin && draft.lexileMax ? `${draft.lexileMin}–${draft.lexileMax}L` : "NULL"}</strong></div><p>Cognitive：{cognitive ? <DataValue value={cognitive} /> : "NULL"} <span>缺失不会阻断审核</span></p></div>
  </>;
}

function DraftInput({ label, value, onChange, disabled, source, hint, action, wide = false, type = "text" }: {
  label: string; value: string; onChange: (value: string) => void; disabled: boolean; source?: string; hint?: string; action?: ReactNode; wide?: boolean; type?: string;
}) {
  return <label className={`draft-input${wide ? " wide" : ""}`}><span>{label}<span className="draft-input-meta">{source ? <em>{source}</em> : null}{action}</span></span><input type={type} min={type === "number" ? 0 : undefined} disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)} />{hint ? <small>{hint}</small> : null}</label>;
}

function DraftSelect({ label, value, onChange, disabled, source, options, wide = false }: {
  label: string; value: string; onChange: (value: string) => void; disabled: boolean; source?: string; options: { value: string; label: string }[]; wide?: boolean;
}) {
  return <label className={`draft-input${wide ? " wide" : ""}`}><span>{label}<span className="draft-input-meta">{source ? <em>{source}</em> : null}</span></span><select disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)}><option value="">请选择语言</option>{options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>;
}

function CategoryReview({ categories, suggestions, selectedIds, primaryByType, disabled, onSelectionChange, onPrimaryChange }: {
  categories: CatalogCategory[];
  suggestions: ClassificationSuggestion[];
  selectedIds: number[];
  primaryByType: Record<string, number | null>;
  disabled: boolean;
  onSelectionChange: (categoryId: number, selected: boolean) => void;
  onPrimaryChange: (categoryType: CatalogCategory["category_type"], categoryId: number | null) => void;
}) {
  return <div className="category-review-grid">{categoryTypes.map((categoryType) => {
    const typedCategories = categories.filter((category) => category.category_type === categoryType);
    const typedSuggestions = suggestions.filter((proposal) => proposal.categoryType === categoryType);
    const suggestionByCode = new Map(typedSuggestions.map((proposal) => [proposal.code, proposal]));
    const selected = typedCategories.filter((category) => selectedIds.includes(category.id));
    const unselectedSuggestions = typedSuggestions.filter((proposal) => !selected.some((category) => category.code === proposal.code));
    const available = typedCategories.filter((category) => !selectedIds.includes(category.id));
    return <section className="category-dimension" key={categoryType}>
      <header><div><strong>{categoryTypeLabels[categoryType]}</strong><small>{typedSuggestions.length ? `${typedSuggestions.length} 个 Research 候选` : "无 Research 候选"}</small></div><label><input type="radio" name={`primary-${categoryType}`} checked={primaryByType[categoryType] == null} disabled={disabled} onChange={() => onPrimaryChange(categoryType, null)} />不设主要</label></header>
      <div className="category-options">
        {selected.map((category) => {
          const proposal = suggestionByCode.get(category.code);
          return <article key={category.id}>
            <label className="category-accept"><input type="checkbox" checked disabled={disabled} onChange={() => onSelectionChange(category.id, false)} /><span><strong>{category.name_zh}</strong><small>{category.code}{category.parent_id ? " · 子分类" : ""}</small></span></label>
            <label className="category-primary"><input type="radio" name={`primary-${categoryType}`} checked={primaryByType[categoryType] === category.id} disabled={disabled} onChange={() => onPrimaryChange(categoryType, category.id)} />主要</label>
            {proposal ? <p>{proposal.source === "jd" ? "京东商品分类" : proposal.source === "amazon" ? "Amazon 商品分类" : proposal.source === "description_summary" ? "根据简介总结" : proposal.confidence != null ? `AI 置信度 ${Math.round(proposal.confidence * 100)}%` : "Research 建议"}{proposal.reason ? ` · ${proposal.reason}` : ""}</p> : <p>人工从受控词表添加</p>}
          </article>;
        })}
        {unselectedSuggestions.map((proposal) => {
          const category = typedCategories.find((row) => row.code === proposal.code);
          return <article className="category-rejected" key={proposal.code}>
            <label className="category-accept"><input type="checkbox" checked={false} disabled={disabled || !category} onChange={() => category && onSelectionChange(category.id, true)} /><span><strong>{category?.name_zh || proposal.code}</strong><small>{category ? "已取消采用" : "词表中不存在，不能采用"}</small></span></label>
            <p>{proposal.source === "description_summary" ? "根据简介总结" : proposal.confidence != null ? `AI 置信度 ${Math.round(proposal.confidence * 100)}%` : "AI 建议"}{proposal.reason ? ` · ${proposal.reason}` : ""}</p>
          </article>;
        })}
        {!selected.length && !unselectedSuggestions.length ? <p className="muted">没有依据时保持为空。</p> : null}
      </div>
      <CategoryMultiAdd
        label={categoryTypeLabels[categoryType]}
        categories={available}
        disabled={disabled}
        onAdd={(categoryIds) => categoryIds.forEach((categoryId) => onSelectionChange(categoryId, true))}
      />
    </section>;
  })}</div>;
}

function CategoryMultiAdd({ label, categories, disabled, onAdd }: {
  label: string;
  categories: CatalogCategory[];
  disabled: boolean;
  onAdd: (categoryIds: number[]) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [chosenIds, setChosenIds] = useState<number[]>([]);
  const availableKey = categories.map((category) => category.id).join(",");

  useEffect(() => {
    const availableIds = new Set(categories.map((category) => category.id));
    setChosenIds((current) => current.filter((categoryId) => availableIds.has(categoryId)));
  }, [availableKey]);

  useEffect(() => {
    if (!open) return;
    const closeOnOutside = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  function toggle(categoryId: number) {
    setChosenIds((current) => current.includes(categoryId)
      ? current.filter((id) => id !== categoryId)
      : [...current, categoryId]);
  }

  function addChosen() {
    if (!chosenIds.length) return;
    onAdd(chosenIds);
    setChosenIds([]);
    setOpen(false);
  }

  return <div ref={containerRef} className={`category-add${open ? " open" : ""}`}>
    <button className="category-multi-trigger" type="button" aria-label={`添加${label}`} aria-haspopup="listbox" aria-expanded={open} disabled={disabled || !categories.length} onClick={() => setOpen((current) => !current)}>
      <span>{chosenIds.length ? `已选择 ${chosenIds.length} 项` : categories.length ? "添加已有分类…" : "没有更多分类"}</span><ChevronDown size={13} />
    </button>
    {open ? <div className="category-multi-menu" role="listbox" aria-label={`可添加的${label}`} aria-multiselectable="true">
      <div className="category-multi-options">{categories.map((category) => <label key={category.id} role="option" aria-selected={chosenIds.includes(category.id)}>
        <input type="checkbox" checked={chosenIds.includes(category.id)} onChange={() => toggle(category.id)} />
        <span className={category.parent_id ? "child" : ""}><strong>{category.name_zh}</strong><small>{category.code}</small></span>
      </label>)}</div>
      <footer><button type="button" onClick={() => { setChosenIds([]); setOpen(false); }}>取消</button><button type="button" className="confirm" disabled={!chosenIds.length} onClick={addChosen}>添加 {chosenIds.length || ""} 项</button></footer>
    </div> : null}
  </div>;
}

function HelpPopover({ label, children }: { label: string; children: ReactNode }) {
  const containerRef = useRef<HTMLSpanElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const closeOnOutside = (event: PointerEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", closeOnOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  return <span ref={containerRef} className="help-popover">
    <button className="help-trigger" type="button" aria-label={label} aria-expanded={open} onClick={() => setOpen((current) => !current)}><CircleHelp size={14} /></button>
    {open ? <span className="help-card" role="tooltip">{children}</span> : null}
  </span>;
}

function ReviewEvidenceRail({ images, loading }: { images: SourceImage[]; loading: boolean }) {
  const directlyLinked = images.length > 0 && images.every((image) => image.directlyLinked);
  return <aside className="review-media-rail" aria-label="书单来源图片">
    <header><div><p>SOURCE IMAGE</p><h2>{directlyLinked ? "当前推荐所在原图" : "书单全部原图"}</h2></div><span>{images.length || "…"}</span></header>
    {directlyLinked ? <p className="media-help">此图片由当前推荐条目的来源记录直接关联。</p> : <p className="media-help">当前推荐没有图片关联，显示书单中可找到的全部原图。</p>}
    <div className="review-media-list">
      {images.map((image, index) => {
        const url = booklistAssetUrl(image.filePath);
        return <figure key={image.filePath}>
          <ZoomableSourceImage src={url} alt={`${directlyLinked ? "当前推荐来源图" : "书单来源图"} ${image.pageOrder ?? index + 1}`} eager={index < 2} />
          <figcaption><span>{image.pageOrder != null ? `第 ${image.pageOrder} 张` : `图片 ${index + 1}`}</span><span>拖动移动 · Ctrl + 滚轮缩放</span></figcaption>
        </figure>;
      })}
      {loading && !images.length ? <div className="media-loading"><ImageIcon size={24} /><span>正在读取书单图片…</span></div> : null}
    </div>
  </aside>;
}

function ZoomableSourceImage({ src, alt, eager }: { src: string; alt: string; eager: boolean }) {
  const viewportRef = useRef<HTMLDivElement>(null);
  const scaleRef = useRef(1);
  const panRef = useRef<{ pointerId: number; startX: number; startY: number; scrollLeft: number; scrollTop: number } | null>(null);
  const [scale, setScale] = useState(1);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    const handleWheel = (event: WheelEvent) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      event.stopPropagation();

      const previousScale = scaleRef.current;
      const delta = event.deltaMode === WheelEvent.DOM_DELTA_LINE ? event.deltaY * 16 : event.deltaY;
      const nextScale = Math.min(6, Math.max(1, previousScale * Math.exp(-delta * 0.002)));
      if (Math.abs(nextScale - previousScale) < 0.001) return;

      const bounds = viewport.getBoundingClientRect();
      const pointerX = event.clientX - bounds.left;
      const pointerY = event.clientY - bounds.top;
      const sourceX = (viewport.scrollLeft + pointerX) / previousScale;
      const sourceY = (viewport.scrollTop + pointerY) / previousScale;

      scaleRef.current = nextScale;
      setScale(nextScale);
      requestAnimationFrame(() => {
        const currentViewport = viewportRef.current;
        if (!currentViewport) return;
        currentViewport.scrollLeft = sourceX * nextScale - pointerX;
        currentViewport.scrollTop = sourceY * nextScale - pointerY;
      });
    };

    viewport.addEventListener("wheel", handleWheel, { passive: false });
    return () => viewport.removeEventListener("wheel", handleWheel);
  }, []);

  function startPan(event: ReactPointerEvent<HTMLDivElement>) {
    const viewport = viewportRef.current;
    if (!viewport || event.button !== 0 || (viewport.scrollWidth <= viewport.clientWidth && viewport.scrollHeight <= viewport.clientHeight)) return;
    event.preventDefault();
    viewport.setPointerCapture(event.pointerId);
    panRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      scrollLeft: viewport.scrollLeft,
      scrollTop: viewport.scrollTop,
    };
    setDragging(true);
  }

  function movePan(event: ReactPointerEvent<HTMLDivElement>) {
    const viewport = viewportRef.current;
    const pan = panRef.current;
    if (!viewport || !pan || pan.pointerId !== event.pointerId) return;
    event.preventDefault();
    viewport.scrollLeft = pan.scrollLeft - (event.clientX - pan.startX);
    viewport.scrollTop = pan.scrollTop - (event.clientY - pan.startY);
  }

  function stopPan(event: ReactPointerEvent<HTMLDivElement>) {
    const viewport = viewportRef.current;
    const pan = panRef.current;
    if (!viewport || !pan || pan.pointerId !== event.pointerId) return;
    panRef.current = null;
    if (viewport.hasPointerCapture(event.pointerId)) viewport.releasePointerCapture(event.pointerId);
    setDragging(false);
  }

  return <div
    ref={viewportRef}
    className={`review-image-viewport${dragging ? " dragging" : ""}`}
    aria-label={`${alt}，当前缩放 ${Math.round(scale * 100)}%，可按住鼠标拖动移动`}
    onPointerDown={startPan}
    onPointerMove={movePan}
    onPointerUp={stopPan}
    onPointerCancel={stopPan}
    onLostPointerCapture={() => { panRef.current = null; setDragging(false); }}
  >
    <div className="review-image-stage" style={{ width: `${scale * 100}%`, height: `${scale * 420}px` }}>
      <img src={src} alt={alt} loading={eager ? "eager" : "lazy"} draggable={false} />
    </div>
    <span className="review-image-scale" aria-hidden="true">{Math.round(scale * 100)}%</span>
  </div>;
}

function ReviewSection({ eyebrow, title, tone = "", action, children }: { eyebrow: string; title: string; tone?: string; action?: ReactNode; children: ReactNode }) {
  return <article className={`review-section ${tone}`}><header><div><p>{eyebrow}</p><h2>{title}</h2></div>{action}</header>{children}</article>;
}

function reviewStatusLabel(status: string) {
  const labels: Record<string, string> = { pending: "待 Research", researching: "研究中", ready: "资料已准备", partial: "部分完成 · 待确认", failed: "研究失败", resolved: "已提交", ignored: "已忽略", reviewing: "审核中", completed: "已完成" };
  return labels[status] || status;
}

const factLabels: Record<string, string> = {
  author: "作者", authors: "作者", description: "简介", publisher: "出版社", publication_date: "出版日期", ar: "AR / ATOS 级别", lexile: "Lexile", lexile_min: "Lexile 最低值", lexile_max: "Lexile 最高值", lexile_range: "Lexile 范围", word_count: "字数",
  retailer_category: "商品分类 / 童书类型",
  official_age: "出版社建议年龄", official_grade: "出版社建议年级", illustrator: "绘者", language: "语言", volume_count: "册数",
  official_level: "出版社阅读级别", series_name: "官方系列", publisher_categories: "出版社分类",
  official_publication_date: "官方出版日期", official_isbns: "官方 ISBN", official_reading_age: "官方阅读年龄",
  reading_age: "阅读年龄", isbns: "ISBN", extra_info: "其他商品信息", cover: "封面", detail_images: "详情图片",
  lexile_evidence: "Lexile 来源值（待裁定，不自动入库）", edition_examples: "版本示例", edition_page_evidence: "版本页数证据",
  classification: "分类建议", syntax_complexity: "Syntax 语法复杂度", cognitive_load: "Cognitive 认知负荷", reading_pen_support: "点读笔支持",
  ambiguities: "歧义与待确认项", scope: "适用范围", value: "值", title: "标题", isbn: "ISBN", page_count: "页数", year: "年份",
  reason: "推导理由", evidence_note: "证据说明", confidence: "置信说明", position: "顺序", name: "名称", code: "代码",
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function sourceEvidenceImages(value: unknown, directlyLinked: boolean): SourceImage[] {
  if (Array.isArray(value)) return value.flatMap((entry) => sourceEvidenceImages(entry, directlyLinked));
  const evidence = asRecord(value);
  const filePath = typeof evidence.file_path === "string" ? evidence.file_path.trim() : "";
  if (!filePath) return [];
  return [{
    filePath,
    pageOrder: typeof evidence.page_order === "number" ? evidence.page_order : null,
    fileName: typeof evidence.file_name === "string" ? evidence.file_name : null,
    directlyLinked,
  }];
}

function itemSourceImages(value: unknown, directlyLinked: boolean): SourceImage[] {
  const row = asRecord(value);
  const extracted = asRecord(row.extracted);
  const other = asRecord(extracted.other_info || row.other_info);
  return sourceEvidenceImages(other.source_evidence, directlyLinked);
}

function uniqueSourceImages(images: SourceImage[]): SourceImage[] {
  const seen = new Set<string>();
  return images.filter((image) => {
    const key = image.filePath.replace(/\\/g, "/");
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  }).sort((left, right) => (left.pageOrder ?? Number.MAX_SAFE_INTEGER) - (right.pageOrder ?? Number.MAX_SAFE_INTEGER));
}

function normalizedSourceTitle(value: unknown, creatorName: unknown = ""): string {
  let title = String(value || "").normalize("NFKC").toLowerCase();
  const creator = String(creatorName || "").normalize("NFKC").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
  title = title.replace(/原图摘录|文字摘录|资料入口|素材汇总|小红书|英语启蒙|完整版/g, "");
  title = title.replace(/[^\p{L}\p{N}]+/gu, "");
  if (creator) title = title.split(creator).join("");
  return title;
}

function longestSharedRun(left: string, right: string): number {
  const a = Array.from(left);
  const b = Array.from(right);
  let previous = new Array(b.length + 1).fill(0);
  let longest = 0;
  for (const char of a) {
    const current = new Array(b.length + 1).fill(0);
    for (let index = 0; index < b.length; index += 1) {
      if (char === b[index]) {
        current[index + 1] = previous[index] + 1;
        longest = Math.max(longest, current[index + 1]);
      }
    }
    previous = current;
  }
  return longest;
}

function sourceTitleScore(listTitle: unknown, documentTitle: unknown, creatorName: unknown): number {
  const list = normalizedSourceTitle(listTitle, creatorName);
  const document = normalizedSourceTitle(documentTitle, creatorName);
  if (!list || !document) return 0;
  if (list === document) return 1;
  if (list.includes(document) || document.includes(list)) return Math.min(list.length, document.length) / Math.max(list.length, document.length) + .35;
  return longestSharedRun(list, document) / Math.min(Array.from(list).length, Array.from(document).length);
}

function sourceDocumentPageImages(document: Record<string, unknown>): SourceImage[] {
  const pages = Array.isArray(document.pages) ? document.pages : [];
  return pages.flatMap((page) => sourceEvidenceImages(page, false));
}

function getReviewSourceImages(item: ReviewItem | null, sourceDocument: unknown): SourceImage[] {
  if (item) {
    const directlyLinked = uniqueSourceImages(itemSourceImages(item.raw_payload, true));
    if (directlyLinked.length) return directlyLinked;
  }

  const document = asRecord(sourceDocument);
  const rows = Array.isArray(document.items) ? document.items : [];
  const linkedBooklistImages = uniqueSourceImages(rows.flatMap((row) => itemSourceImages(row, false)));
  if (linkedBooklistImages.length) return linkedBooklistImages;

  const creator = asRecord(document.creator);
  const creatorOther = asRecord(creator.other_info);
  const sourceDocuments = Array.isArray(creatorOther.source_documents) ? creatorOther.source_documents.map(asRecord) : [];
  if (!sourceDocuments.length) return [];
  if (sourceDocuments.length === 1) return uniqueSourceImages(sourceDocumentPageImages(sourceDocuments[0]));

  const listTitle = asRecord(document.list).title;
  const ranked = sourceDocuments
    .map((entry) => ({ entry, score: sourceTitleScore(listTitle, entry.title || entry.source_path, creator.name) }))
    .sort((left, right) => right.score - left.score);
  return ranked[0]?.score >= .2 ? uniqueSourceImages(sourceDocumentPageImages(ranked[0].entry)) : [];
}

function booklistAssetUrl(filePath: string): string {
  return `/booklist-assets/${filePath.split(/[\\/]/).map(encodeURIComponent).join("/")}`;
}

function DataValue({ value }: { value: unknown }) {
  if (value == null || value === "") return <em className="muted">未知 / 未提供</em>;
  if (Array.isArray(value)) return value.length ? <ul className="evidence-list">{value.map((part, index) => <li key={index}><DataValue value={part} /></li>)}</ul> : <em className="muted">无</em>;
  if (typeof value === "object") return <dl className="evidence-fields">{Object.entries(asRecord(value)).map(([key, part]) => <div key={key}><dt>{factLabels[key] || key.replace(/_/g, " ")}</dt><dd><DataValue value={part} /></dd></div>)}</dl>;
  return <>{typeof value === "boolean" ? value ? "是" : "否" : String(value)}</>;
}

type SourceCopyField = "is_strong_recommendation" | "recommendation_emphasis_text" | "comment" | "note";

function sourceScalar(value: unknown): unknown {
  const record = asRecord(value);
  return "raw" in record ? record.raw : value;
}

function cleanSourceNote(value: unknown): string {
  return String(value ?? "")
    .split(/[；;]/)
    .map((part) => part.trim())
    .filter((part) => part && !/^(?:原图|来源(?:原图|图片)?)\s*[：:]?\s*第?\s*\d+\s*(?:页|行)(?:\s*第?\s*\d+\s*行)?$/i.test(part))
    .join("；");
}

function SourceDetails({ item, disabled, onUpdate }: {
  item: ReviewItem;
  disabled: boolean;
  onUpdate: (field: SourceCopyField, value: string | boolean | null) => Promise<void>;
}) {
  const extracted = asRecord(item.raw_payload.extracted);
  const reviewed = asRecord(item.extracted_payload);
  const other = asRecord(extracted.other_info);
  const evidence = asRecord(other.source_evidence);
  const imagePath = typeof evidence.file_path === "string" ? evidence.file_path : "";
  const comment = Object.prototype.hasOwnProperty.call(reviewed, "comment") ? reviewed.comment : extracted.comment;
  const storedNote = Object.prototype.hasOwnProperty.call(reviewed, "note") ? reviewed.note : extracted.note;
  const isStrongRecommendation = Object.prototype.hasOwnProperty.call(reviewed, "is_strong_recommendation")
    ? Boolean(reviewed.is_strong_recommendation)
    : reviewed.recommendation_strength === 3;
  const recommendationEmphasisText = Object.prototype.hasOwnProperty.call(reviewed, "recommendation_emphasis_text")
    ? reviewed.recommendation_emphasis_text
    : reviewed.recommendation_strength_text ?? (isStrongRecommendation
      ? String(storedNote ?? "").match(/强烈推荐|重点推荐|非常推荐|必读|首推|这个阶段一定要读|这个阶段最推荐/)?.[0] ?? null
      : null);
  const note = cleanSourceNote(storedNote);
  const fields: Array<{ label: string; value: unknown; editableKey?: SourceCopyField }> = [
    { label: "达人推荐年龄", value: extracted.recommended_age },
    { label: "来源 AR", value: extracted.ar },
    { label: "来源 Lexile", value: extracted.lexile },
    { label: "来源级别", value: extracted.level },
    { label: "推荐语", value: comment, editableKey: "comment" },
    { label: "备注", value: note, editableKey: "note" },
  ];
  const [editingField, setEditingField] = useState<SourceCopyField | null>(null);
  const [editValue, setEditValue] = useState("");
  const [emphasisDraft, setEmphasisDraft] = useState(String(recommendationEmphasisText ?? ""));
  const [saving, setSaving] = useState(false);
  const committingRef = useRef(false);

  useEffect(() => {
    setEmphasisDraft(String(recommendationEmphasisText ?? ""));
  }, [recommendationEmphasisText]);

  useEffect(() => {
    setEditingField(null);
    setEditValue("");
    setSaving(false);
    committingRef.current = false;
  }, [item.id]);

  function beginEdit(field: SourceCopyField, value: unknown) {
    if (disabled || saving) return;
    setEditingField(field);
    setEditValue(String(sourceScalar(value) ?? ""));
  }

  async function commitEdit() {
    if (!editingField || committingRef.current) return;
    const field = editingField;
    const currentSource = field === "comment" ? comment : field === "note" ? storedNote : recommendationEmphasisText;
    const currentValue = String(sourceScalar(currentSource) ?? "").trim();
    const nextValue = (field === "note" ? cleanSourceNote(editValue) : editValue.trim());
    if (nextValue === currentValue) {
      setEditingField(null);
      return;
    }
    committingRef.current = true;
    setSaving(true);
    try {
      await onUpdate(field, nextValue || null);
      setEditingField(null);
    } finally {
      committingRef.current = false;
      setSaving(false);
    }
  }

  async function updateStrength(value: boolean) {
    if (saving) return;
    setSaving(true);
    try { await onUpdate("is_strong_recommendation", value); }
    finally { setSaving(false); }
  }

  async function saveEmphasis() {
    const next = emphasisDraft.trim();
    if (saving || !isStrongRecommendation || next === String(recommendationEmphasisText ?? "").trim()) return;
    setSaving(true);
    try { await onUpdate("recommendation_emphasis_text", next || null); }
    finally { setSaving(false); }
  }

  return <><div className="source-values">
    <label className="source-value-editable">
      <small>推荐标记<span className="source-edit-hint">可人工修改</span></small>
      <span><input type="checkbox" checked={isStrongRecommendation} disabled={disabled || saving} onChange={event => void updateStrength(event.target.checked)} aria-label="强烈推荐" /> 强烈推荐</span>
    </label>
    <label className="source-value-editable">
      <small>强调原文</small>
      <input type="text" maxLength={255} value={emphasisDraft} disabled={disabled || saving || !isStrongRecommendation} placeholder={isStrongRecommendation ? "可留空；只写来源实际措辞" : "明确强推后可填写"} onChange={event => setEmphasisDraft(event.target.value)} onBlur={() => void saveEmphasis()} onKeyDown={event => { if (event.key === "Enter") event.currentTarget.blur(); }} aria-label="强调原文" />
    </label>
    {fields.map(({ label, value, editableKey }) => {
    const editable = !!editableKey && !disabled;
    return <div
      key={label}
      className={editableKey ? `source-value-editable${editingField === editableKey ? " editing" : ""}` : undefined}
      onDoubleClick={() => editableKey && beginEdit(editableKey, value)}
      onKeyDown={(event) => {
        if (editable && editingField !== editableKey && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          beginEdit(editableKey!, value);
        }
      }}
      tabIndex={editable ? 0 : undefined}
      title={editable ? "双击编辑" : undefined}
    >
      <small>{label}{editable ? <span className="source-edit-hint">双击编辑</span> : null}</small>
      {editingField === editableKey ? <textarea
        autoFocus
        disabled={saving}
        rows={2}
        value={editValue}
        onChange={(event) => setEditValue(event.target.value)}
        onBlur={() => void commitEdit()}
        onKeyDown={(event) => {
          if (event.key === "Escape") { event.preventDefault(); setEditingField(null); }
          if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void commitEdit(); }
        }}
        aria-label={`编辑${label}`}
      /> : <div className="source-value-text"><DataValue value={sourceScalar(value)} /></div>}
      {editingField === editableKey && saving ? <span className="source-save-state">保存中…</span> : null}
    </div>;
  })}</div>
    {imagePath ? <p className="source-image-note">右侧已显示当前推荐所在原图（预览不可点击）</p> : null}
    {other.raw_text ? <p>{String(other.raw_text)}</p> : null}
    <details><summary>完整原始记录（只读）</summary><pre className="raw-source">{JSON.stringify(item.raw_payload, null, 2)}</pre></details></>;
}

function FactGrid({ facts, sources = [] }: { facts?: Record<string, unknown> | null; sources?: ResearchSubject["sources"] }) {
  if (!facts) return null;
  return <div className="fact-grid">{Object.entries(facts).map(([key, entry]) => {
    const record = entry && typeof entry === "object" && !Array.isArray(entry) ? entry as Record<string, unknown> : null;
    const value = record && "value" in record ? record.value : entry;
    const sourceIds = record?.source_ids as number[] | undefined;
    return <div key={key}><small>{factLabels[key] || key.replace(/_/g, " ")}</small><div className="fact-value"><DataValue value={value} /></div>
      {["reason", "evidence_note", "confidence"].filter((field) => record?.[field] != null).map((field) => <p className="evidence-note" key={field}>{factLabels[field]}：<DataValue value={record![field]} /></p>)}
      {sourceIds?.length ? <div className="fact-citations">{sourceIds.map((id) => { const source = sources.find((row) => row.id === id); return source && /^https?:\/\//i.test(source.source_url) ? <a key={id} href={source.source_url} target="_blank" rel="noreferrer">来源 #{id}</a> : <span key={id}>来源 #{id}</span>; })}</div> : null}</div>;
  })}</div>;
}

function GuideDraftEditor({ subject, value, disabled, onChange, onAdd }: {
  subject: ResearchSubject; value: string; disabled: boolean;
  onChange: (value: string) => void; onAdd: (raw: string, title: string) => void;
}) {
  const [raw, setRaw] = useState("");
  const [title, setTitle] = useState("");
  return <div className="guide-draft-editor">
    <strong>Guide · {subject.proposed_display_title}</strong>
    <p>粘贴原始资料留作 Research 证据，整理后的 Markdown 草稿经人工修改后随审核提交。</p>
    <input value={title} disabled={disabled} onChange={(event) => setTitle(event.target.value)} placeholder="资料来源或标题（可选）" />
    <textarea rows={3} value={raw} disabled={disabled} onChange={(event) => setRaw(event.target.value)} placeholder="粘贴文章、笔记或对比资料" />
    <button type="button" disabled={disabled || !raw.trim()} onClick={() => { onAdd(raw.trim(), title.trim()); setRaw(""); setTitle(""); }}>加入 Research 并生成可编辑草稿</button>
    <label><span>Guide Markdown Draft</span><textarea rows={6} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} placeholder="可在此编辑最终确认的实用指南；Ctrl+S 保存草稿" /></label>
  </div>;
}

function ProductCaptureResults({ subject, disabled, selection, onSelectionChange, showImages = true, showFacts = true, showCoverSelection = true }: {
  subject: ResearchSubject;
  disabled: boolean;
  selection?: ProductImageSelection;
  onSelectionChange?: (selection: ProductImageSelection) => void;
  showImages?: boolean;
  showFacts?: boolean;
  showCoverSelection?: boolean;
}) {
  const facts = subject.facts_json || {};
  const imageEntry = asRecord(facts.product_images);
  const rawImages = Array.isArray(imageEntry.value) ? imageEntry.value : [];
  const images = rawImages.map(asRecord).filter((image) => typeof image.source_url === "string") as ProductImage[];
  const hidden = new Set(["product_images", "cover", "cover_local_path", "detail_images", "included_titles", "series"]);
  const visibleFacts = Object.fromEntries(Object.entries(facts).filter(([key]) => !hidden.has(key)));
  const productSources = subject.sources.filter((source) => source.source_type?.includes("product"));

  const activeSelection = selection || productImageSelectionFromSubject(subject);

  function stageImageSelection(next: ProductImageSelection) {
    onSelectionChange?.(next);
  }

  function toggleDetail(url: string, checked: boolean) {
    const detailUrls = checked
      ? [...new Set([...activeSelection.detailUrls, url])]
      : activeSelection.detailUrls.filter((value) => value !== url);
    stageImageSelection({ ...activeSelection, detailUrls });
  }

  function selectCover(url: string) {
    stageImageSelection({ ...activeSelection, cover: url });
  }

  return <>
    {showImages && images.length ? <div className="product-image-gallery">
      {images.map((image, index) => {
        const isCover = image.source_url === activeSelection.cover;
        const keepAsDetail = activeSelection.detailUrls.includes(image.source_url);
        return <article key={`${image.source_url}-${index}`} className={`${keepAsDetail ? "" : "detail-excluded "}${isCover ? "cover-selected" : ""}`.trim()}>
          <div className="product-image-preview">
            <img src={image.source_url} alt={`采集到的商品图 ${index + 1}`} loading="lazy" />
            {showCoverSelection ? <label className={`cover-radio${isCover ? " selected" : ""}`}>
              <input type="radio" name={`catalog-cover-${subject.id}`} aria-label={`将商品图 ${index + 1} 设为封面`} checked={isCover} disabled={disabled} onChange={() => selectCover(image.source_url)} />
              <span>{isCover ? "封面" : "设为封面"}</span>
            </label> : null}
          </div>
          <div className="product-image-actions">
            <label><input type="checkbox" checked={keepAsDetail} disabled={disabled} onChange={(event) => toggleDetail(image.source_url, event.target.checked)} />保留详情图</label>
          </div>
        </article>;
      })}
    </div> : null}
    {showFacts && Object.keys(visibleFacts).length ? <FactGrid facts={visibleFacts} sources={subject.sources} /> : null}
    {showFacts ? <div className="capture-sources">{productSources.map((source) => <div key={source.id}>
      <a href={source.source_url} target="_blank" rel="noreferrer"><ExternalLink size={13} />{source.source_title || "商品来源"}</a>
      <small>{source.fetched_at ? `采集于 ${new Date(source.fetched_at).toLocaleString("zh-CN")}` : "采集时间未知"}</small>
    </div>)}</div> : null}
    {showFacts && !images.length && !Object.keys(visibleFacts).length ? <p className="muted">尚未采集商品资料。</p> : null}
  </>;
}
