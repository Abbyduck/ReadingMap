import { useEffect, useRef, useState } from "react";
import { FileText, Search, X } from "lucide-react";
import { api, type ReviewSourceDocument } from "../../api/client";
import "./source-document-reader.css";

const labels: Record<string, string> = {
  creator: "达人信息", list: "书单信息", items: "书单条目", name: "姓名", introduction: "介绍", title: "标题", description: "说明",
  schema_version: "文件格式版本", document_type: "文档类型", other_info: "补充资料", raw_title: "原始标题", sequence: "原始序号", position: "推荐顺序",
  extracted: "来源提取内容", analysis: "JSON 中的初步分析", recommended_age: "达人推荐年龄", ar: "来源 AR", lexile: "来源 Lexile", level: "来源级别",
  comment: "推荐语", note: "备注", notes: "备注", raw: "原文", value: "值", min: "下限", max: "上限", unit: "单位",
  platform: "来源平台", source_url: "来源链接", profile_url: "达人主页", profile: "达人资料", display_name: "显示名称", source_type: "来源类型",
  positioning: "定位", methodology_summary: "方法概述", route_summary: "路线概述", suitable_for: "适合人群", cautions: "注意事项", source_note: "资料说明",
  knowledge: "阅读笔记与资料", source_documents: "来源材料", publications: "出版作品", content_markdown: "正文", knowledge_type: "资料类型", audience: "受众",
  created_at: "创建时间", updated_at: "更新时间", published_at: "发布时间", stages: "阶段", stage: "所属阶段", stage_order: "阶段顺序",
  list_type: "书单类型", import_sources: "导入来源", source_name: "来源名称", source_path: "来源路径", file_path: "文件路径", file_name: "文件名",
  source_evidence: "原图证据", evidence: "提取证据", annotations: "来源标注", raw_import: "原始导入记录", legacy_reference: "历史记录编号",
  raw_author: "原始作者", raw_text: "原始文字", raw_isbn: "原始 ISBN", possible_entity_type: "初步类型判断", confidence: "初步置信度",
  page_order: "来源页序", pages: "页面", position_scope: "顺序适用范围", recommended_age_min_months: "推荐年龄下限（月）", recommended_age_max_months: "推荐年龄上限（月）",
};
const record = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const label = (key: string) => labels[key] || key.replace(/_/g, " ");

function ReadValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value == null || value === "") return <span className="sr-empty">未提供{value === "" ? "（空字符串）" : ""}</span>;
  if (typeof value !== "object") return <span className="sr-text">{typeof value === "boolean" ? value ? "是" : "否" : String(value)}</span>;
  if (Array.isArray(value)) return value.length ? <ol className="sr-array">{value.map((entry, index) => <li key={index}><ReadValue value={entry} depth={depth + 1} /></li>)}</ol> : <span className="sr-empty">无条目</span>;
  const entries = Object.entries(record(value));
  if (!entries.length) return <span className="sr-empty">空对象</span>;
  return <dl className="sr-fields">{entries.map(([key, entry]) => <div key={key}><dt>{label(key)}<small>{key}</small></dt><dd>{entry && typeof entry === "object" && depth >= 1 ? <details><summary>展开{label(key)}{Array.isArray(entry) ? ` · ${entry.length} 项` : ""}</summary><ReadValue value={entry} depth={depth + 1} /></details> : <ReadValue value={entry} depth={depth + 1} />}</dd></div>)}</dl>;
}

export function SourceDocumentReader({ batchId, onClose }: { batchId: number; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [data, setData] = useState<ReviewSourceDocument | null>(null);
  const [error, setError] = useState("");
  const [mode, setMode] = useState<"read" | "json">("read");
  const [query, setQuery] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialog.current?.showModal();
    return () => { document.body.style.overflow = overflow; previous?.focus(); };
  }, []);
  useEffect(() => {
    let active = true;
    setData(null); setError("");
    api.reviewSource(batchId).then(result => { if (active) setData(result); }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : "读取失败"); });
    return () => { active = false; };
  }, [batchId, attempt]);
  const doc = record(data?.document);
  const list = record(doc.list);
  const creator = record(doc.creator);
  const items = Array.isArray(doc.items) ? doc.items : [];
  const filtered = items.map((entry, index) => ({ entry, index })).filter(({ entry }) => {
    const row = record(entry);
    const extracted = record(row.extracted);
    const searchable = [row.raw_title, extracted.title, extracted.comment, extracted.note, extracted.recommended_age, extracted.ar, extracted.lexile, extracted.level, record(extracted.other_info).raw_text];
    return JSON.stringify(searchable).toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
  });
  return <dialog ref={dialog} className="source-reader" aria-labelledby="source-reader-title" onCancel={onClose}>
    <header className="sr-header"><div><p><FileText size={15} />批次 {batchId} · 原始文件</p><h2 id="source-reader-title">查看原始 JSON</h2></div><button className="sr-close" onClick={onClose} aria-label="关闭原始 JSON"><X size={22} /></button></header>
    {data ? <><div className="sr-controls"><div className="sr-tabs" role="group" aria-label="文件查看方式"><button aria-pressed={mode === "read"} onClick={() => setMode("read")}>阅读视图</button><button aria-pressed={mode === "json"} onClick={() => setMode("json")}>完整 JSON</button></div><span>{data.matches_import === true ? "与导入时文件一致" : data.matches_import === false ? "文件在导入后有变更" : "未记录导入版本"}</span></div>
      <div className="sr-body">
        {data.matches_import === false ? <p className="sr-warning" role="status">当前展示磁盘上的原文件，内容已与本批次导入时不同。审核项仍保留导入时的原始记录。</p> : null}
        <p className="sr-filename">{data.filename}</p>
        {mode === "json" ? <><p className="sr-hint">完整字段，按缩进排版；字符串及字段值保持原样。</p><pre className="sr-code">{JSON.stringify(data.document, null, 2)}</pre><details><summary>查看文件原始文本</summary><pre className="sr-code">{data.raw_text}</pre></details></> : <>
          <section className="sr-intro"><p className="sr-kicker">{String(creator.name || "未注明达人")} · {items.length} 条原始记录</p><h3>{String(list.title || data.filename)}</h3>{list.description ? <p className="sr-text">{String(list.description)}</p> : null}<p className="sr-hint">这里展示文件中的原始内容，包括当时的初步分析。</p></section>
          <div className="sr-metadata">{Object.entries(doc).filter(([key]) => key !== "items").map(([key, value]) => <details key={key}><summary>{label(key)}</summary><ReadValue value={value} /></details>)}</div>
          <div className="sr-list-heading"><h3>原始书单条目 <span>{items.length}</span></h3><label className="sr-search"><Search size={16} /><input aria-label="搜索原始条目" placeholder="搜索书名、备注、年龄或级别" value={query} onChange={event => setQuery(event.target.value)} /></label></div>
          {query ? <p className="sr-hint">找到 {filtered.length} / {items.length} 条</p> : null}
          <div className="sr-items">{filtered.map(({ entry, index }) => { const row = record(entry); const extracted = record(row.extracted); return <article className="sr-item" key={index}><header><span className="sr-number">{index + 1}</span><div><h4>{String(row.raw_title || extracted.title || `条目 ${index + 1}`)}</h4><p>原始顺序：{String(row.position ?? row.sequence ?? "未提供")}</p></div></header><div className="sr-summary">{["recommended_age", "ar", "lexile", "level"].map(key => { const value = extracted[key]; return <div key={key}><small>{label(key)}</small><ReadValue value={"raw" in record(value) ? record(value).raw : value} /></div>; })}</div>{["comment", "note"].filter(key => extracted[key] != null && extracted[key] !== "").map(key => <div className="sr-prose" key={key}><h5>{label(key)}</h5><ReadValue value={extracted[key]} /></div>)}<details className="sr-item-details"><summary>查看此条全部原始字段</summary><ReadValue value={entry} /></details></article>; })}</div>
          {!filtered.length ? <p className="sr-empty-state">{items.length ? "没有符合搜索条件的条目。" : "此文件没有 items 条目，可展开上方信息或切换完整 JSON 查看。"}</p> : null}
          {!Object.keys(doc).length ? <ReadValue value={data.document} /> : null}
        </>}
      </div></> : <div className="sr-loading" role="status">{error ? <><p>{error}</p><button onClick={() => setAttempt(value => value + 1)}>重新读取</button></> : "正在读取原始文件…"}</div>}
  </dialog>;
}
