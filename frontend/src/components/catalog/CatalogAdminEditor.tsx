import { useEffect, useState } from "react";
import { api, BookEdition, CatalogCaptureCandidate, CatalogCategory, CatalogEntity, catalogAssetUrl } from "../../api/client";

type Provider = "amazon" | "jd" | "official";
type Scope = "page" | "edition" | "structure" | "guide";

function EditionEditor({ entityId, edition, onSaved }: { entityId: number; edition: BookEdition; onSaved: () => Promise<void> }) {
  const [fields, setFields] = useState({ ...edition });
  const [isbn, setIsbn] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => setFields({ ...edition }), [edition]);
  async function save() {
    setBusy(true); setError("");
    try {
      await api.updateEdition(entityId, edition.id, {
        cover_local_path: fields.cover_local_path || null, publisher: fields.publisher || null,
        format: fields.format || null, page_count: fields.page_count || null,
        publication_date: fields.publication_date || null, dimensions: fields.dimensions || null,
      });
      if (isbn.trim()) await api.addEditionIsbn(entityId, edition.id, isbn.trim());
      setIsbn("");
      await onSaved();
    } catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  }
  return <fieldset className="catalog-admin-edition"><legend>Edition #{edition.id}</legend>
    {edition.cover_local_path ? <img className="catalog-admin-cover" src={catalogAssetUrl(edition.cover_local_path)} alt="版本封面" /> : null}
    <div className="catalog-admin-grid">
      <label>封面本地路径<input value={fields.cover_local_path || ""} onChange={(event) => setFields({ ...fields, cover_local_path: event.target.value })} /></label>
      <label>出版社<input value={fields.publisher || ""} onChange={(event) => setFields({ ...fields, publisher: event.target.value })} /></label>
      <label>装帧<input value={fields.format || ""} onChange={(event) => setFields({ ...fields, format: event.target.value })} /></label>
      <label>页数<input type="number" min="0" value={fields.page_count ?? ""} onChange={(event) => setFields({ ...fields, page_count: event.target.value ? Number(event.target.value) : null })} /></label>
      <label>出版日期<input type="date" value={fields.publication_date || ""} onChange={(event) => setFields({ ...fields, publication_date: event.target.value })} /></label>
      <label>尺寸<input value={fields.dimensions || ""} onChange={(event) => setFields({ ...fields, dimensions: event.target.value })} /></label>
      <label>新增 ISBN<input value={isbn} onChange={(event) => setIsbn(event.target.value)} placeholder={edition.isbns.map((row) => row.isbn_val).join("、") || "ISBN"} /></label>
    </div>
    <button type="button" disabled={busy} onClick={() => void save()}>保存版本</button>{error ? <p role="alert">{error}</p> : null}
  </fieldset>;
}

export function CatalogAdminEditor({ entity, onUpdated }: { entity: CatalogEntity; onUpdated: (entity: CatalogEntity) => void }) {
  const [form, setForm] = useState({
    display_title: entity.display_title, title_zh: entity.title_zh || "", title_en: entity.title_en || "",
    aliases: (entity.aliases || []).join("，"), description: entity.description || "",
    extra_info: entity.extra_info || "", guide_markdown: entity.guide_markdown || "",
    fiction_type: entity.fiction_type || "unknown", volume_count: entity.volume_count,
    author_text: entity.work?.author_text || "", illustrator_text: entity.work?.illustrator_text || "",
    translator_text: entity.work?.translator_text || "", language_code: entity.work?.language_code || "",
    detail_images: (entity.work?.detail_images || []).join("\n"),
  });
  const [categories, setCategories] = useState<CatalogCategory[]>([]);
  const [categoryIds, setCategoryIds] = useState<number[]>(entity.categories.map((row) => row.id));
  const [newIsbn, setNewIsbn] = useState("");
  const [memberId, setMemberId] = useState("");
  const [parentId, setParentId] = useState("");
  const [provider, setProvider] = useState<Provider>("amazon");
  const [candidate, setCandidate] = useState<CatalogCaptureCandidate | null>(null);
  const [candidateScope, setCandidateScope] = useState<Scope>("page");
  const [selectedFields, setSelectedFields] = useState<string[]>([]);
  const [targetEditionId, setTargetEditionId] = useState("");
  const [memberDecisions, setMemberDecisions] = useState<Record<number, { create_new?: boolean; catalog_entity_id?: number }>>({});
  const [rawGuide, setRawGuide] = useState("");
  const [guideDraft, setGuideDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => { void api.categories().then(setCategories).catch((reason) => setError(String(reason))); }, []);
  useEffect(() => {
    setForm({
      display_title: entity.display_title, title_zh: entity.title_zh || "", title_en: entity.title_en || "",
      aliases: (entity.aliases || []).join("，"), description: entity.description || "",
      extra_info: entity.extra_info || "", guide_markdown: entity.guide_markdown || "",
      fiction_type: entity.fiction_type || "unknown", volume_count: entity.volume_count,
      author_text: entity.work?.author_text || "", illustrator_text: entity.work?.illustrator_text || "",
      translator_text: entity.work?.translator_text || "", language_code: entity.work?.language_code || "",
      detail_images: (entity.work?.detail_images || []).join("\n"),
    });
    setCategoryIds(entity.categories.map((row) => row.id));
  }, [entity]);

  async function refresh() { onUpdated(await api.entity(entity.id)); }
  async function saveEntity() {
    setBusy(true); setError(""); setMessage("");
    try {
      const payload: Record<string, unknown> = {
        display_title: form.display_title, title_zh: form.title_zh || null, title_en: form.title_en || null,
        aliases: form.aliases.split(/[，,\n]/).map((value) => value.trim()).filter(Boolean),
        description: form.description || null, extra_info: form.extra_info || null,
        guide_markdown: form.guide_markdown || null, fiction_type: form.fiction_type,
        category_decisions: categoryIds.map((id) => ({ category_id: id, is_primary: entity.categories.find((row) => row.id === id)?.is_primary || false })),
      };
      if (entity.work) payload.work = {
        author_text: form.author_text || null, illustrator_text: form.illustrator_text || null,
        translator_text: form.translator_text || null, language_code: form.language_code || null,
        detail_images: form.detail_images.split("\n").map((value) => value.trim()).filter(Boolean),
      };
      if (entity.entity_type !== "book" && entity.entity_type !== "animation") payload.volume_count = form.volume_count;
      onUpdated(await api.updateEntity(entity.id, payload));
      setMessage("Catalog 已保存");
    } catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  }

  async function createEdition() {
    setBusy(true); setError("");
    try {
      const edition = await api.createEdition(entity.id, {});
      if (newIsbn.trim()) await api.addEditionIsbn(entity.id, edition.id, newIsbn.trim());
      setNewIsbn(""); await refresh();
    } catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  }

  async function changeMembership(kind: "member" | "parent", id: number, remove = false) {
    setBusy(true); setError("");
    try {
      const collectionId = kind === "member" ? entity.id : id;
      const childId = kind === "member" ? id : entity.id;
      if (remove) await api.removeCollectionMember(collectionId, childId);
      else await api.addCollectionMember(collectionId, childId);
      await refresh(); setMemberId(""); setParentId("");
    } catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  }

  async function search() {
    setBusy(true); setError("");
    try { await api.adminSearch(entity.id, provider); setMessage("浏览器已打开；进入目标页后选择 Capture。 "); }
    catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  }
  async function capture(scope: "page" | "edition" | "structure") {
    setBusy(true); setError(""); setCandidate(null);
    try {
      const next = await api.adminCapture(entity.id, provider, scope);
      setCandidate(next); setCandidateScope(scope); setSelectedFields(Object.keys(next.values));
      setTargetEditionId(next.matched_edition_id ? String(next.matched_edition_id) : "");
      setMemberDecisions({}); setMessage("候选已生成；确认前不会覆盖 Catalog。");
    } catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  }
  async function addGuide() {
    setBusy(true); setError("");
    try {
      const next = await api.adminGuideMaterial(entity.id, rawGuide);
      setCandidate(next); setCandidateScope("guide"); setSelectedFields(["entity.guide_markdown"]);
      setGuideDraft(next.draft || ""); setRawGuide("");
      setMessage("原始资料已保留在 Research；编辑草稿后再确认。");
    } catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  }
  async function confirm() {
    if (!candidate) return;
    setBusy(true); setError("");
    try {
      const members = candidateScope === "structure" ? Object.entries(memberDecisions).map(([index, decision]) => ({ index: Number(index), ...decision })) : [];
      onUpdated(await api.adminConfirm(entity.id, candidate, selectedFields, targetEditionId ? Number(targetEditionId) : null, members, candidateScope === "guide" ? guideDraft : undefined));
      setCandidate(null); setMessage("已按所选字段更新 Catalog。");
    } catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  }

  return <section className="catalog-admin-editor" aria-label="Catalog 管理编辑">
    <header><div><small>ADMIN · CATALOG TRUTH</small><h3>维护当前 Catalog</h3></div><button type="button" disabled={busy} onClick={() => void saveEntity()}>保存 Entity / Work</button></header>
    {error ? <p className="catalog-admin-error" role="alert">{error}</p> : null}{message ? <p role="status">{message}</p> : null}
    <div className="catalog-admin-grid">
      <label>显示名称<input value={form.display_title} onChange={(event) => setForm({ ...form, display_title: event.target.value })} /></label>
      <label>中文名<input value={form.title_zh} onChange={(event) => setForm({ ...form, title_zh: event.target.value })} /></label>
      <label>英文名<input value={form.title_en} onChange={(event) => setForm({ ...form, title_en: event.target.value })} /></label>
      <label>别名<input value={form.aliases} onChange={(event) => setForm({ ...form, aliases: event.target.value })} /></label>
      <label>虚构属性<select value={form.fiction_type} onChange={(event) => setForm({ ...form, fiction_type: event.target.value as CatalogEntity["fiction_type"] })}><option value="unknown">未知</option><option value="fiction">虚构</option><option value="nonfiction">非虚构</option><option value="mixed">混合</option></select></label>
      {entity.work ? <><label>作者<input value={form.author_text} onChange={(event) => setForm({ ...form, author_text: event.target.value })} /></label><label>绘者<input value={form.illustrator_text} onChange={(event) => setForm({ ...form, illustrator_text: event.target.value })} /></label><label>译者<input value={form.translator_text} onChange={(event) => setForm({ ...form, translator_text: event.target.value })} /></label><label>语言<input value={form.language_code} onChange={(event) => setForm({ ...form, language_code: event.target.value })} /></label><label>Work 内页路径<textarea rows={3} value={form.detail_images} onChange={(event) => setForm({ ...form, detail_images: event.target.value })} /></label></> : null}
      {entity.entity_type !== "book" && entity.entity_type !== "animation" ? <label>已知全集册数<input type="number" min="0" value={form.volume_count ?? ""} onChange={(event) => setForm({ ...form, volume_count: event.target.value ? Number(event.target.value) : null })} /></label> : null}
    </div>
    <label>简介<textarea rows={3} value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></label>
    <label>额外事实<textarea rows={3} value={form.extra_info} onChange={(event) => setForm({ ...form, extra_info: event.target.value })} /></label>
    <label>Guide Markdown<textarea rows={5} value={form.guide_markdown} onChange={(event) => setForm({ ...form, guide_markdown: event.target.value })} /></label>
    <fieldset><legend>Classification</legend><div className="catalog-admin-categories">{categories.map((category) => <label key={category.id}><input type="checkbox" checked={categoryIds.includes(category.id)} onChange={(event) => setCategoryIds((current) => event.target.checked ? [...current, category.id] : current.filter((id) => id !== category.id))} />{category.name_zh}<small>{category.category_type}</small></label>)}</div></fieldset>
    {entity.work ? <section><h4>版本与 ISBN</h4>{entity.editions.map((edition) => <EditionEditor key={edition.id} entityId={entity.id} edition={edition} onSaved={refresh} />)}<div className="catalog-admin-inline"><input value={newIsbn} onChange={(event) => setNewIsbn(event.target.value)} placeholder="新版本 ISBN（可留空）" /><button type="button" disabled={busy} onClick={() => void createEdition()}>新增稀疏 Edition</button></div></section> : null}
    <section><h4>Structure</h4><p>父级：{entity.parents.map((row) => <span key={row.id}>#{row.id} {row.display_title} <button type="button" onClick={() => void changeMembership("parent", row.id, true)}>移除</button> </span>)}</p><div className="catalog-admin-inline"><input type="number" value={parentId} onChange={(event) => setParentId(event.target.value)} placeholder="父级 Entity ID" /><button type="button" disabled={!parentId || busy} onClick={() => void changeMembership("parent", Number(parentId))}>添加父级</button></div>
      {entity.entity_type !== "book" && entity.entity_type !== "animation" ? <><p>直接成员：{entity.members.map((row) => <span key={row.id}>#{row.id} {row.display_title} <button type="button" onClick={() => void changeMembership("member", row.id, true)}>移除</button> </span>)}</p><div className="catalog-admin-inline"><input type="number" value={memberId} onChange={(event) => setMemberId(event.target.value)} placeholder="成员 Entity ID" /><button type="button" disabled={!memberId || busy} onClick={() => void changeMembership("member", Number(memberId))}>添加成员</button></div></> : null}</section>
    <section><h4>Research Capture</h4><div className="catalog-admin-inline"><select value={provider} onChange={(event) => setProvider(event.target.value as Provider)}><option value="amazon">Amazon</option><option value="jd">京东</option><option value="official">Official</option></select><button type="button" disabled={busy} onClick={() => void search()}>Search</button><button type="button" disabled={busy} onClick={() => void capture("page")}>Capture Current Page</button>{entity.work ? <button type="button" disabled={busy} onClick={() => void capture("edition")}>Capture Current Edition</button> : null}{entity.entity_type !== "book" && entity.entity_type !== "animation" ? <button type="button" disabled={busy} onClick={() => void capture("structure")}>Capture Structure</button> : null}</div></section>
    <section><h4>手工 Guide 资料</h4><textarea rows={3} value={rawGuide} onChange={(event) => setRawGuide(event.target.value)} placeholder="粘贴原始资料；先成为 Research 证据" /><button type="button" disabled={busy || !rawGuide.trim()} onClick={() => void addGuide()}>加入资料并整理草稿</button></section>
    {candidate ? <section className="catalog-admin-candidate"><h4>确认候选 · {candidateScope}</h4>{candidate.source_url ? <p>来源：{candidate.source_url}</p> : null}{Object.entries(candidate.values).map(([key, value]) => <label key={key}><input type="checkbox" checked={selectedFields.includes(key)} onChange={(event) => setSelectedFields((current) => event.target.checked ? [...current, key] : current.filter((field) => field !== key))} /><strong>{key}</strong><small>当前：{JSON.stringify(candidate.current[key] ?? null)}<br />候选：{JSON.stringify(value)}</small></label>)}
      {candidateScope === "edition" ? <label>应用到版本<select value={targetEditionId} onChange={(event) => setTargetEditionId(event.target.value)}><option value="">新建版本</option>{entity.editions.map((edition) => <option key={edition.id} value={edition.id}>Edition #{edition.id}</option>)}</select></label> : null}
      {candidateScope === "guide" ? <label>人工编辑 Guide Draft<textarea rows={6} value={guideDraft} onChange={(event) => setGuideDraft(event.target.value)} /></label> : null}
      {candidateScope === "structure" && Array.isArray(candidate.values.members) ? candidate.values.members.map((row, index) => <div className="catalog-admin-inline" key={index}><span>{String((row as Record<string, unknown>).display_title || "成员")}</span><select value={memberDecisions[index]?.create_new ? "new" : memberDecisions[index]?.catalog_entity_id ? "existing" : "skip"} onChange={(event) => setMemberDecisions((current) => ({ ...current, [index]: event.target.value === "new" ? { create_new: true } : event.target.value === "existing" ? { catalog_entity_id: 0 } : {} }))}><option value="skip">暂不写入</option><option value="new">新建 Entity</option><option value="existing">复用现有 ID</option></select>{memberDecisions[index]?.catalog_entity_id !== undefined ? <input type="number" min="1" value={memberDecisions[index].catalog_entity_id || ""} onChange={(event) => setMemberDecisions((current) => ({ ...current, [index]: { catalog_entity_id: Number(event.target.value) } }))} placeholder="Catalog Entity ID" /> : null}</div>) : null}
      <button type="button" disabled={busy} onClick={() => void confirm()}>确认所选变更</button>
    </section> : null}
  </section>;
}
