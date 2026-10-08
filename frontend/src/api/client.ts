const API_BASE = "/api";
let csrfToken = "";

export function catalogAssetUrl(path?: string | null): string {
  if (!path) return "";
  if (path.startsWith("research_data/")) {
    return `${API_BASE}/catalog-assets/${path.slice("research_data/".length).split("/").map(encodeURIComponent).join("/")}`;
  }
  return path;
}

export async function refreshCsrf() {
  const response = await fetch(`${API_BASE}/auth/csrf`, { credentials: "same-origin" });
  if (!response.ok) throw new Error("无法建立安全会话，请刷新重试。");
  const data = await response.json() as { csrfToken: string };
  csrfToken = data.csrfToken;
  return csrfToken;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const headers = new Headers(options?.headers);
  if (options?.method && !["GET", "HEAD", "OPTIONS"].includes(options.method.toUpperCase())) {
    if (!csrfToken) await refreshCsrf();
    headers.set("X-CSRFToken", csrfToken);
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: "same-origin" });
  if (!response.ok) {
    const raw = await response.text();
    const isHtml = response.headers.get("content-type")?.includes("text/html") || /^\s*</.test(raw);
    let message = isHtml ? `服务器请求失败（${response.status}）：${options?.method || "GET"} ${API_BASE}${path}` : raw || `请求失败（${response.status}）`;
    try {
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      message = typeof parsed.detail === "string" ? parsed.detail : Object.entries(parsed).map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join("；") : String(value)}`).join("\n");
    } catch { /* Keep the plain response body. */ }
    throw new Error(message);
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export type EntityType = "book" | "animation" | "reading_system" | "series" | "level" | "set" | "franchise";

export type BookEdition = {
  id: number; work_id: number; cover_local_path?: string | null; publisher?: string | null;
  format?: string | null; page_count?: number | null; publication_date?: string | null;
  dimensions?: string | null; isbns: Array<{ id: number; isbn_type: number; isbn_val: string }>;
};

export type CatalogCaptureCandidate = {
  token: string;
  values: Record<string, unknown>;
  current: Record<string, unknown>;
  source_url?: string | null;
  matched_edition_id?: number | null;
  draft?: string;
};

export type CatalogCategory = {
  id: number;
  parent_id?: number | null;
  category_type: "material_type" | "genre" | "theme" | "topic" | "reading_form";
  code: string;
  name_zh: string;
  name_en?: string | null;
  description?: string | null;
  sort_order?: number | null;
  is_primary?: boolean;
};

export type CatalogEntity = {
  id: number;
  entity_type: EntityType;
  display_title: string;
  title_zh?: string | null;
  title_en?: string | null;
  aliases?: string[] | null;
  description?: string | null;
  extra_info?: string | null;
  guide_markdown?: string | null;
  fiction_type: "unknown" | "fiction" | "nonfiction" | "mixed";
  cover_url?: string | null;
  independent_reading_suitable?: boolean | null;
  bookshelf_visible: boolean;
  volume_count?: number | null;
  lexile_min?: number | null;
  lexile_max?: number | null;
  work?: {
    author_text?: string | null;
    illustrator_text?: string | null;
    translator_text?: string | null;
    language_code?: string | null;
    detail_images?: string[] | null;
    /** Legacy compatibility for existing product UI; new data uses editions. */
    page_count?: number | null;
    word_count?: number | null;
    headword_count?: number | null;
    ar_level?: number | null;
    lexile_code?: string | null;
  } | null;
  editions: BookEdition[];
  isbns: Array<{ id: number; isbn_type: number; isbn_val: string }>;
  categories: CatalogCategory[];
  reading_pens: Array<{ id: number; name: string }>;
  parents: Array<{ id: number; display_title: string; position?: number | null }>;
  members: Array<{ id: number; display_title: string; position?: number | null }>;
};

export type CatalogTreeNode = {
  id: number;
  entity_type: EntityType;
  display_title: string;
  children: CatalogTreeNode[];
};

export type Creator = {
  id: number;
  name: string;
  tagline?: string | null;
  signature_focus?: string | null;
  background?: string | null;
  avatar_url?: string | null;
};

export type ReadingList = {
  id: number;
  creator_id: number;
  creator_name: string;
  title: string;
  age_min_months?: number | null;
  age_max_months?: number | null;
  stage_label?: string | null;
  material_type?: string | null;
  description?: string | null;
  items: ReadingListItem[];
};

export type ReadingListItem = {
  id: number;
  entity: CatalogEntity;
  recommended_edition_id?: number | null;
  position?: number | null;
  stage_label?: string | null;
  recommended_age_min_months?: number | null;
  recommended_age_max_months?: number | null;
  source_ar_text?: string | null;
  source_lexile_text?: string | null;
  source_level_text?: string | null;
  is_strong_recommendation: boolean;
  recommendation_emphasis_text?: string | null;
  comment?: string | null;
  note?: string | null;
};

export type StageRecommendation = {
  reading_list_item_id: number;
  reading_list_id: number;
  reading_list_title: string;
  creator_id: number;
  creator_name: string;
  creator_avatar_url?: string | null;
  stage_label?: string | null;
  position?: number | null;
  is_strong_recommendation: boolean;
  recommendation_emphasis_text?: string | null;
  comment?: string | null;
  note?: string | null;
};

export type StageEntityImportance = {
  catalog_entity_id: number;
  entity: CatalogEntity;
  recommendation_score: number;
  recommendation_meta: { strong_now: boolean; strong_in_scope: boolean; creator_count: number; list_count: number };
  creator_count: number;
  position?: number | null;
  amazon_rating?: number | null;
  amazon_rating_max?: number | null;
  amazon_rating_count?: number | null;
  my_rating?: number | null;
  importance_score: number;
  importance_level: "featured" | "normal" | "compact";
  recommendations: StageRecommendation[];
};

export type ReadingMapStageResponse = {
  stage_label: string;
  sort: "comprehensive" | "creator" | "amazon" | "mine" | "title";
  total: number;
  entities: StageEntityImportance[];
};

export type Child = { id: number; name: string; birth_date?: string | null };
export type User = { id: number; email: string; name: string; is_staff: boolean };
export type ChildAnnotation = { child_id: number; catalog_entity_id: number; independent_reading_override?: boolean | null; effective_independent_reading_suitable?: boolean | null; retry_after_date?: string | null; note?: string | null; entity?: CatalogEntity };

export type DatabaseTable = {
  name: string;
  table_type: "table" | "view";
  row_count: number;
};

export type DatabaseColumn = {
  name: string;
  data_type: string;
  nullable: boolean;
  primary_key: boolean;
  foreign_key?: string | null;
  default?: unknown;
  sensitive: boolean;
};

export type DatabaseTableDetail = {
  vendor: string;
  table: string;
  table_type: "table" | "view";
  page: number;
  page_size: number;
  total_rows: number;
  total_pages: number;
  columns: DatabaseColumn[];
  rows: Array<Record<string, unknown>>;
};

export type ReviewBatch = {
  id: number;
  source_type: string;
  source_name?: string | null;
  source_file_path?: string | null;
  target_reading_list_id?: number | null;
  status: string;
  total_items: number;
  resolved_items: number;
  created_at: string;
  updated_at: string;
};

export type ReviewSourceDocument = {
  batch_id: number;
  filename: string;
  source_file_path: string;
  matches_import: boolean | null;
  document: unknown;
  raw_text: string;
};

export type ResearchCandidate = {
  id: number;
  catalog_entity_id: number;
  display_title: string;
  entity_type: string;
  match_score?: number | null;
  match_reasons?: string[] | null;
  rank_no?: number | null;
  bookshelf_visible: boolean;
};

export type ResearchRelation = {
  id: number;
  parent_subject_id: number;
  parent_title: string;
  member_subject_id: number;
  member_title: string;
  relation_type: string;
  position?: number | null;
  evidence_type?: string | null;
  confidence?: number | null;
  review_status: string;
};

export type ResearchSubject = {
  id: number;
  subject_role: string;
  proposed_entity_type?: EntityType | null;
  proposed_display_title?: string | null;
  proposed_title_zh?: string | null;
  proposed_title_en?: string | null;
  proposed_aliases?: string[] | null;
  facts_json?: Record<string, unknown> | null;
  ai_inferences_json?: Record<string, unknown> | null;
  guide_markdown_draft?: string | null;
  research_status: string;
  manual_note?: string | null;
  resolution_status: string;
  resolved_catalog_entity_id?: number | null;
  resolved_bookshelf_visible?: boolean | null;
  sources: Array<{ id: number; source_type?: string | null; source_url: string; source_title?: string | null; fetched_at?: string | null; raw_content?: string | null }>;
  candidates: ResearchCandidate[];
  relations: ResearchRelation[];
  pending_conflict_count: number;
  pending_conflicts: Array<{ id: number; field_path: string; existing_value: unknown; proposed_value: unknown }>;
};

export type ReviewItem = {
  id: number;
  batch_id: number;
  source_item_key: string;
  position?: number | null;
  raw_payload: Record<string, unknown>;
  extracted_payload?: Record<string, unknown> | null;
  status: string;
  decision?: string | null;
  resolved_catalog_entity_id?: number | null;
  committed_reading_list_item_id?: number | null;
  manual_note?: string | null;
  lock_version: number;
  resolved_at?: string | null;
  subjects: ResearchSubject[];
  edition_drafts: Array<{ id: number; book_subject_id?: number | null; matched_catalog_edition_id?: number | null; proposed_data: Record<string, unknown>; review_status: string; source_id?: number | null }>;
};

export type BrowserSessionStatus = {
  provider: "amazon" | "jd" | "official";
  connected: boolean;
  state: "disconnected" | "search_results" | "product_detail" | "official_detail" | "unknown";
  current_url: string;
  product_title: string;
  product_id: string;
  capture_ready: boolean;
  message: string;
};

export type StructureMemberCandidate = {
  title: string;
  url?: string | null;
  image?: string | null;
  position?: number | null;
  confidence?: number;
  source_kind?: string;
  candidate_index?: number;
};
export type StructurePreview = {
  members: StructureMemberCandidate[];
  group?: { title?: string | null; declared_count?: number | null } | null;
  declared_count?: number | null;
  diagnostics: {
    strategy: string;
    candidate_group_count: number;
    candidate_link_count: number;
    accepted_member_count: number;
    confidence: number;
    messages: string[];
  };
};

export const api = {
  me: () => request<{ user: User | null }>("/auth/me"),
  register: (payload: { email: string; password: string; name?: string }) => request<{ user: User }>("/auth/register", json("POST", payload)),
  login: (payload: { email: string; password: string }) => request<{ user: User }>("/auth/login", json("POST", payload)),
  logout: () => request<void>("/auth/logout", json("POST", {})),
  passwordReset: (email: string) => request<{ detail: string }>("/auth/password-reset", json("POST", { email })),
  passwordResetConfirm: (payload: { uid: string; token: string; password: string }) => request<{ detail: string }>("/auth/password-reset/confirm", json("POST", payload)),
  entities: () => request<CatalogEntity[]>("/catalog/entities?limit=500"),
  entity: (id: number) => request<CatalogEntity>(`/catalog/entities/${id}`),
  updateEntityBookshelf: (id: number, bookshelfVisible: boolean) =>
    request<CatalogEntity>(`/catalog/entities/${id}`, json("PATCH", { bookshelf_visible: bookshelfVisible })),
  updateEntity: (id: number, payload: Record<string, unknown>) => request<CatalogEntity>(`/catalog/entities/${id}`, json("PATCH", payload)),
  createEdition: (id: number, payload: Record<string, unknown>) => request<BookEdition>(`/catalog/entities/${id}/editions`, json("POST", payload)),
  updateEdition: (id: number, editionId: number, payload: Record<string, unknown>) => request<BookEdition>(`/catalog/entities/${id}/editions/${editionId}`, json("PATCH", payload)),
  addEditionIsbn: (id: number, editionId: number, isbn: string) => request<CatalogEntity>(`/catalog/entities/${id}/isbns`, json("POST", { edition_id: editionId, isbn })),
  addCollectionMember: (id: number, memberId: number, position?: number | null) => request<CatalogTreeNode>(`/collections/${id}/items`, json("POST", { member_entity_id: memberId, position })),
  removeCollectionMember: (id: number, memberId: number) => request<void>(`/collections/${id}/items`, json("DELETE", { member_entity_id: memberId })),
  adminSearch: (id: number, provider: "amazon" | "jd" | "official", query?: string) => request<Record<string, unknown>>(`/catalog/entities/${id}/admin-search`, json("POST", { provider, query })),
  adminCapture: (id: number, provider: "amazon" | "jd" | "official", scope: "page" | "edition" | "structure") => request<CatalogCaptureCandidate>(`/catalog/entities/${id}/admin-capture`, json("POST", { provider, scope })),
  adminConfirm: (id: number, candidate: CatalogCaptureCandidate, selectedFields: string[], editionId?: number | null, members?: Array<Record<string, unknown>>, guideMarkdown?: string) =>
    request<CatalogEntity>(`/catalog/entities/${id}/admin-confirm`, json("POST", { token: candidate.token, selected_fields: selectedFields, edition_id: editionId, members, guide_markdown: guideMarkdown })),
  adminGuideMaterial: (id: number, rawContent: string, sourceTitle = "") => request<CatalogCaptureCandidate>(`/catalog/entities/${id}/guide-material`, json("POST", { raw_content: rawContent, source_title: sourceTitle })),
  collection: (id: number) => request<CatalogTreeNode>(`/collections/${id}`),
  categories: () => request<CatalogCategory[]>("/categories"),
  databaseTables: () => request<{ vendor: string; tables: DatabaseTable[] }>("/database/tables"),
  databaseTable: (table: string, page = 1, pageSize = 25) =>
    request<DatabaseTableDetail>(`/database/tables/${encodeURIComponent(table)}?page=${page}&page_size=${pageSize}`),
  search: (q: string) => request<CatalogEntity[]>(`/catalog/search?q=${encodeURIComponent(q)}`),
  createEntity: (payload: { entity_type: EntityType; display_title: string }) =>
    request<CatalogEntity>("/catalog/entities", json("POST", payload)),
  creators: () => request<Creator[]>("/creators"),
  createCreator: (payload: { name: string; tagline?: string }) => request<Creator>("/creators", json("POST", payload)),
  readingLists: () => request<ReadingList[]>("/reading-lists"),
  readingMapStage: (stageLabel: string, filters?: { creatorId?: number; readingListId?: number; ownedOnly?: boolean; query?: string }) => {
    const params = new URLSearchParams({ stage_label: stageLabel });
    if (filters?.creatorId) params.set("creator_id", String(filters.creatorId));
    if (filters?.readingListId) params.set("reading_list_id", String(filters.readingListId));
    if (filters?.ownedOnly) params.set("owned_only", "true");
    if (filters?.query) params.set("q", filters.query);
    return request<ReadingMapStageResponse>(`/reading-map/entities?${params.toString()}`);
  },
  createReadingList: (payload: { creator_id: number; title: string; stage_label?: string }) =>
    request<ReadingList>("/reading-lists", json("POST", payload)),
  children: () => request<Child[]>("/children"),
  createChild: (payload: { name: string; birth_date?: string }) => request<Child>("/children", json("POST", payload)),
  updateChild: (id: number, payload: { name: string; birth_date?: string | null }) => request<Child>(`/children/${id}`, json("PATCH", payload)),
  annotations: (id: number) => request<ChildAnnotation[]>(`/children/${id}/annotations`),
  annotation: (childId: number, entityId: number) => request<ChildAnnotation>(`/children/${childId}/entities/${entityId}`),
  saveAnnotation: (childId: number, entityId: number, payload: { independent_reading_override: boolean | null; retry_after_date: string | null; note: string | null }) => request<ChildAnnotation>(`/children/${childId}/entities/${entityId}`, json("PUT", payload)),
  reviewBatches: () => request<ReviewBatch[]>("/review/batches"),
  reviewSource: (batchId: number) => request<ReviewSourceDocument>(`/review/batches/${batchId}/source`),
  importReviewBatch: (payload: { source_file_path: string; target_reading_list_id?: number }) =>
    request<{ created: boolean; batch: ReviewBatch }>("/review/batches/import", json("POST", payload)),
  reviewItems: (batchId: number, status?: string) =>
    request<ReviewItem[]>(`/review/items?batch_id=${batchId}${status ? `&status=${encodeURIComponent(status)}` : ""}`),
  reviewItem: (itemId: number) => request<ReviewItem>(`/review/items/${itemId}`),
  updateReviewSourceCopy: (itemId: number, payload: {
    expected_version: number;
    is_strong_recommendation?: boolean;
    recommendation_emphasis_text?: string | null;
    comment?: string | null;
    note?: string | null;
  }) => request<ReviewItem>(`/review/items/${itemId}`, json("PATCH", payload)),
  browserSessionStatus: (itemId: number, provider: "amazon" | "jd" | "official") =>
    request<BrowserSessionStatus>(`/review/browser-session/status?item_id=${itemId}&provider=${provider}`),
  searchAmazon: (itemId: number, query?: string) =>
    request<{ query: string; search_url: string; session_reused: boolean; current_url: string; page_title: string }>(`/review/items/${itemId}/amazon-search`, json("POST", query ? { query } : {})),
  captureAmazon: (itemId: number) =>
    request<{
      capture: { source_url?: string | null; identifier?: string | null; title?: string | null; image_count: number };
      item: ReviewItem;
    }>(`/review/items/${itemId}/amazon-capture`, json("POST", {})),
  searchJd: (itemId: number, query?: string) =>
    request<{ query: string; search_url: string; session_reused: boolean; current_url: string; page_title: string }>(`/review/items/${itemId}/jd-search`, json("POST", query ? { query } : {})),
  captureJd: (itemId: number) =>
    request<{
      capture: { source_url?: string | null; identifier?: string | null; title?: string | null; image_count: number };
      item: ReviewItem;
    }>(`/review/items/${itemId}/jd-capture`, json("POST", {})),
  searchOfficial: (itemId: number, query?: string) =>
    request<{ query: string; search_url: string; session_reused: boolean; current_url: string; page_title: string }>(`/review/items/${itemId}/official-search`, json("POST", query ? { query } : {})),
  captureOfficial: (itemId: number) =>
    request<{
      capture: { source_url?: string | null; title?: string | null; fact_count: number };
      item: ReviewItem;
    }>(`/review/items/${itemId}/official-capture`, json("POST", {})),
  captureEdition: (itemId: number, provider: "amazon" | "jd" | "official", subjectId?: number) =>
    request<{ item: ReviewItem; edition_draft_id: number }>(`/review/items/${itemId}/capture-edition`, json("POST", { provider, subject_id: subjectId })),
  captureStructure: (itemId: number, provider: "amazon" | "jd" | "official", subjectId?: number) =>
    request<{ item: ReviewItem; relation_ids: number[] }>(`/review/items/${itemId}/capture-structure`, json("POST", { provider, subject_id: subjectId })),
  decideEditionDraft: (itemId: number, draftId: number, payload: { review_status: "confirmed" | "rejected"; matched_catalog_edition_id?: number | null; proposed_data?: Record<string, unknown> }) =>
    request<ReviewItem>(`/review/items/${itemId}/edition-drafts/${draftId}`, json("PATCH", payload)),
  addGuideMaterial: (itemId: number, subjectId: number, rawContent: string, sourceTitle = "") =>
    request<ReviewItem>(`/review/items/${itemId}/subjects/${subjectId}/guide-material`, json("POST", { raw_content: rawContent, source_title: sourceTitle })),
  saveGuideDraft: (itemId: number, subjectId: number, markdown: string) =>
    request<ReviewItem>(`/review/items/${itemId}/subjects/${subjectId}/guide-draft`, json("PUT", { guide_markdown_draft: markdown })),
  structureTabs: (itemId: number) =>
    request<{ tabs: Array<{ url: string; title: string }> }>(`/review/items/${itemId}/structure/tabs`),
  previewStructure: (itemId: number, input: { input_kind: "browser" | "html" | "url_list"; html?: string; base_url?: string; urls?: string[]; target_url?: string }) =>
    request<StructurePreview>(`/review/items/${itemId}/structure/preview`, json("POST", input)),
  previewStructureImage: (itemId: number, file: File) => {
    const body = new FormData();
    body.append("image", file);
    return request<StructurePreview>(`/review/items/${itemId}/structure/image-preview`, { method: "POST", body });
  },
  stageStructure: (itemId: number, payload: {
    members: StructureMemberCandidate[];
    declared_count?: number | null;
    group_choice: "none" | "create";
    group_title?: string;
    group_type?: "set" | "series" | "level" | "reading_system" | "franchise";
  }) => request<{ relation_ids: number[]; container_subject_id: number; item: ReviewItem }>(
    `/review/items/${itemId}/structure/stage`, json("POST", payload)),
  startStructureRegion: (itemId: number, targetUrl?: string) =>
    request<{ ready: boolean; message: string }>(`/review/items/${itemId}/structure/region/start`, json("POST", { target_url: targetUrl })),
  pollStructureRegion: (itemId: number, targetUrl?: string) =>
    request<{ ready: boolean; preview?: StructurePreview }>(`/review/items/${itemId}/structure/region/poll${targetUrl ? `?target_url=${encodeURIComponent(targetUrl)}` : ""}`),
  researchSelectedStructure: (itemId: number, memberSubjectIds: number[]) =>
    request<{ item: ReviewItem; captured_subject_ids: number[]; capture_errors: Record<string, string> }>(`/review/items/${itemId}/structure-research`, json("POST", { member_subject_ids: memberSubjectIds })),
  createParentStructure: (itemId: number, payload: {
    child_subject_id: number;
    proposed_entity_type: "reading_system" | "series" | "level" | "set" | "franchise";
    proposed_display_title: string;
    proposed_title_zh?: string | null;
    proposed_title_en?: string | null;
    category_ids?: number[];
  }) => request<{ parent_subject_id: number; relation_id: number; item: ReviewItem }>(`/review/items/${itemId}/parents`, json("POST", payload)),
  researchParentHierarchy: (itemId: number) =>
    request<{ subject_ids: number[]; relation_ids: number[]; item: ReviewItem }>(`/review/items/${itemId}/parent-research`, json("POST", {})),
  createResearchRelation: (payload: { parent_subject_id: number; member_subject_id: number; relation_type?: "contains"; position?: number | null }) =>
    request<{ id: number; parent_subject_id: number; member_subject_id: number; relation_type: string; position?: number | null; review_status: string }>("/review/relations", json("POST", payload)),
  deleteResearchRelation: (relationId: number) => request<void>(`/review/relations/${relationId}`, { method: "DELETE" }),
  resolveReviewConflict: (conflictId: number, status: "keep_existing" | "use_proposed" | "ignored") =>
    request<{ id: number; status: string }>(`/review/conflicts/${conflictId}/resolve`, json("POST", { status })),
  updateProductImages: (subjectId: number, selectedSourceUrls: string[], coverSourceUrl: string) =>
    request<ResearchSubject>(`/review/subjects/${subjectId}/product-images`, json("PUT", {
      selected_source_urls: selectedSourceUrls,
      cover_source_url: coverSourceUrl,
    })),
  refreshResearchCandidates: (subjectId: number) =>
    request<ResearchSubject>(`/review/subjects/${subjectId}/candidates`, json("POST", {})),
  summarizeClassification: (subjectId: number) =>
    request<ResearchSubject>(`/review/subjects/${subjectId}/classification-summary`, json("POST", {})),
  updateResearchSubject: (subjectId: number, payload: {
    proposed_display_title?: string;
    proposed_title_zh?: string | null;
    proposed_title_en?: string | null;
    proposed_aliases?: string[] | null;
    proposed_entity_type?: EntityType | null;
    facts_json?: Record<string, unknown> | null;
  }) =>
    request<ResearchSubject>(`/review/subjects/${subjectId}`, json("PUT", payload)),
  updateResearchDraft: (itemId: number, subjectId: number, payload: {
    expected_version: number;
    proposed_display_title?: string;
    proposed_title_zh?: string | null;
    proposed_title_en?: string | null;
    proposed_aliases?: string[] | null;
    proposed_entity_type?: EntityType | null;
    fact_values?: Record<string, unknown>;
    clear_fact_keys?: string[];
  }) => request<ReviewItem>(`/review/items/${itemId}/subjects/${subjectId}/draft`, json("PUT", payload)),
  researchSubject: (subjectId: number) => request<ResearchSubject>(`/review/subjects/${subjectId}`),
  reviewDecision: (itemId: number, payload: {
    decision: "match_existing" | "create_new" | "ignore";
    catalog_entity_id?: number;
    expected_version: number;
    actor?: string;
    manual_note?: string;
    include_structure_subject_ids?: number[];
    structure_decisions?: Array<{ subject_id: number; decision: "match_existing" | "create_new"; catalog_entity_id?: number }>;
    category_decisions?: Array<{ category_id: number; is_primary: boolean }>;
    structure_category_decisions?: Array<{ subject_id: number; category_ids: number[] }>;
    bookshelf_visibility?: Array<{ subject_id: number; visible: boolean }>;
    recommended_edition_id?: number | null;
    recommended_edition_draft_id?: number | null;
  }) => request<ReviewItem>(`/review/items/${itemId}/decision`, json("POST", payload)),
  bulkMatch: (entries: Array<{ review_item_id: number; catalog_entity_id: number; expected_version: number }>) =>
    request<{ resolved_item_ids: number[] }>("/review/items/bulk-match", json("POST", { entries }))
};
