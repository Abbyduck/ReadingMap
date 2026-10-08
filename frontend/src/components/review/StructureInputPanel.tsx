import { ClipboardEvent, useEffect, useState } from "react";
import { api, ReviewItem, StructureMemberCandidate, StructurePreview } from "../../api/client";

type Mode = "browser" | "html" | "url_list" | "image";
type Row = StructureMemberCandidate & { selected: boolean };

export function StructureInputPanel({
  itemId, disabled, onStaged, beforeStage
}: {
  itemId: number;
  disabled: boolean;
  onStaged: (item: ReviewItem, count: number) => void;
  beforeStage?: () => Promise<void>;
}) {
  const [mode, setMode] = useState<Mode>("browser");
  const [html, setHtml] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [urls, setUrls] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [diagnostics, setDiagnostics] = useState<StructurePreview["diagnostics"] | null>(null);
  const [declared, setDeclared] = useState("");
  const [groupTitle, setGroupTitle] = useState("");
  const [groupChoice, setGroupChoice] = useState<"none" | "create">("none");
  const [groupType, setGroupType] = useState<"set" | "series" | "level" | "reading_system" | "franchise">("set");
  const [busy, setBusy] = useState(false);
  const [picking, setPicking] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    setRows([]); setDiagnostics(null); setDeclared(""); setGroupTitle("");
    setGroupChoice("none"); setPicking(false); setError(""); setNotice("");
  }, [itemId]);

  useEffect(() => {
    if (!picking) return;
    let live = true;
    const timer = window.setInterval(async () => {
      try {
        const result = await api.pollStructureRegion(itemId);
        if (live && result.ready && result.preview) {
          usePreview(result.preview);
          setPicking(false);
          setNotice("已读取选中网页区域。请核对成员，再确认暂存。");
        }
      } catch (reason) {
        if (live) { setPicking(false); setError(String(reason)); }
      }
    }, 1600);
    return () => { live = false; window.clearInterval(timer); };
  }, [picking, itemId]);

  function usePreview(result: StructurePreview) {
    setRows(result.members.map((item) => ({
      ...item, selected: Boolean(item.title?.trim())
    })));
    setDiagnostics(result.diagnostics);
    setDeclared(result.declared_count ? String(result.declared_count) : "");
    setGroupTitle(result.group?.title || "");
    setError("");
    if (!result.members.length) setNotice("未自动识别成员。可以改用点选区域、HTML、URL 或图片输入。");
  }

  async function preview() {
    if (disabled || busy) return;
    setBusy(true); setError(""); setNotice("");
    try {
      let result: StructurePreview;
      if (mode === "image") {
        if (!image) throw new Error("请先选择或粘贴图片");
        result = await api.previewStructureImage(itemId, image);
      } else if (mode === "html") {
        result = await api.previewStructure(itemId, {
          input_kind: "html", html, base_url: baseUrl.trim()
        });
      } else if (mode === "url_list") {
        result = await api.previewStructure(itemId, {
          input_kind: "url_list", urls: urls.split(/\r?\n/).map(v => v.trim()).filter(Boolean)
        });
      } else {
        result = await api.previewStructure(itemId, { input_kind: "browser" });
      }
      usePreview(result);
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }

  async function startPicker() {
    setBusy(true); setError("");
    try {
      const reply = await api.startStructureRegion(itemId);
      setPicking(true);
      setNotice(reply.message);
    } catch (reason) { setError(String(reason)); }
    finally { setBusy(false); }
  }

  async function stage() {
    const selected = rows.filter(row => row.selected && row.title.trim());
    if (!selected.length) { setError("请勾选并填写至少一个成员书名"); return; }
    setBusy(true); setError("");
    try {
      if (beforeStage) await beforeStage();
      const result = await api.stageStructure(itemId, {
        members: selected.map(({ selected: _, ...row }) => ({
          ...row,
          title: row.title.trim(),
          // Image preview crops are review UI evidence, not Catalog image data.
          image: row.image?.startsWith("data:") ? null : row.image
        })),
        declared_count: declared ? Number(declared) : null,
        group_choice: groupChoice,
        group_title: groupTitle.trim(),
        group_type: groupType
      });
      onStaged(result.item, result.relation_ids.length);
      setNotice(`已暂存 ${result.relation_ids.length} 条直接成员候选；仍需完成审核确认。`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)); }
    finally { setBusy(false); }
  }

  function acceptClipboard(event: ClipboardEvent<HTMLDivElement>) {
    const item = Array.from(event.clipboardData.items).find(entry => entry.type.startsWith("image/"));
    if (!item) return;
    const file = item.getAsFile();
    if (!file) return;
    event.preventDefault();
    setMode("image");
    setImage(file);
    setNotice("图片已从剪贴板载入，点击「识别候选」即可分析。");
  }

  const updateRow = (index: number, update: Partial<Row>) =>
    setRows(prev => prev.map((row, i) => i === index ? { ...row, ...update } : row));
  const canStage = rows.some(row => row.selected && row.title.trim());

  return <div className="structure-input-panel" tabIndex={0} onPaste={acceptClipboard}>
    <div className="structure-input-heading">
      <strong>成员结构输入</strong>
      <small>先预览，再人工确认暂存；不会直接写入 Catalog</small>
    </div>
    <div className="structure-input-modes" role="group" aria-label="结构输入来源">
      {([
        ["browser", "网页自动识别"], ["html", "粘贴 HTML"],
        ["url_list", "粘贴 URL"], ["image", "上传 / 粘贴图片"]
      ] as const).map(([id, label]) =>
        <button key={id} type="button" aria-pressed={mode === id}
          className={mode === id ? "active" : ""} disabled={disabled || busy}
          onClick={() => setMode(id)}>{label}</button>)}
    </div>
    {mode === "browser" ? <div className="structure-input-info">
      从辅助 Chrome 当前相关页面识别图书列表；如果识别不准，可以在网页中点选书籍网格。
      <button type="button" disabled={disabled || busy || picking} onClick={() => void startPicker()}>
        {picking ? "等待网页点击…" : "在 Chrome 选择成员区域"}
      </button>
    </div> : null}
    {mode === "html" ? <div className="structure-input-fields">
      <input aria-label="HTML 原页面 URL" value={baseUrl} onChange={e => setBaseUrl(e.target.value)}
        placeholder="原网页 URL（用于补全相对链接）" />
      <textarea rows={5} aria-label="成员区域 HTML" value={html}
        onChange={e => setHtml(e.target.value)} placeholder="粘贴含书籍卡片的 div / HTML" />
    </div> : null}
    {mode === "url_list" ? <textarea rows={5} aria-label="成员 URL 列表" value={urls}
      onChange={e => setUrls(e.target.value)} placeholder="每行粘贴一个成员详情页 URL" /> : null}
    {mode === "image" ? <div className="structure-input-info">
      <label>选择书单截图或封面拼图 <input type="file" accept="image/png,image/jpeg,image/webp"
        onChange={e => setImage(e.target.files?.[0] || null)} /></label>
      <small>{image ? `已选择：${image.name}` : "也可以先点击这个区域，再 Ctrl+V 粘贴截图。"}</small>
      <small>识别结果依赖本地 OCR；没有安装时仍可尝试裁出封面并人工补标题。</small>
    </div> : null}
    <div className="structure-input-actions">
      <button type="button" disabled={disabled || busy || picking} onClick={() => void preview()}>
        {busy ? "处理中…" : "识别候选"}
      </button>
      {picking ? <button type="button" onClick={() => setPicking(false)}>停止等待</button> : null}
    </div>
    {error ? <p className="structure-input-error" role="alert">{error}</p> : null}
    {notice ? <p className="structure-input-notice" role="status">{notice}</p> : null}
    {diagnostics ? <details className="structure-input-diagnostics" open={!rows.length}>
      <summary>识别结果：{diagnostics.accepted_member_count} 本，候选区域 {diagnostics.candidate_group_count} 个，策略 {diagnostics.strategy}</summary>
      <p>置信参考：{Math.round(diagnostics.confidence * 100)}% · 候选链接：{diagnostics.candidate_link_count}</p>
      {diagnostics.messages.map((msg, i) => <p key={i}>{msg}</p>)}
    </details> : null}
    {rows.length ? <>
      <div className="structure-input-group">
        <label>声明总册数（非已录入数量） <input type="number" min={1} max={10000}
          value={declared} onChange={e => setDeclared(e.target.value)} /></label>
        <label>图片/来源分组
          <select value={groupChoice} onChange={e => setGroupChoice(e.target.value as "none" | "create")}>
            <option value="none">直接加入当前 Collection</option>
            <option value="create">新建分组候选（非默认官方身份）</option>
          </select>
        </label>
        {groupChoice === "create" ? <>
          <input value={groupTitle} aria-label="新分组名称" onChange={e => setGroupTitle(e.target.value)}
            placeholder="分组名称（可修改）" />
          <select aria-label="分组类型" value={groupType} onChange={e => setGroupType(e.target.value as typeof groupType)}>
            <option value="set">Set 组合</option><option value="series">Series 系列</option>
            <option value="level">Level 级别</option><option value="reading_system">Reading System</option>
            <option value="franchise">IP</option>
          </select>
        </> : null}
      </div>
      <div className="structure-input-list">
        {rows.map((row, i) => <div className="structure-input-member" key={i}>
          <input aria-label={`选择第 ${i + 1} 本`} type="checkbox" checked={row.selected}
            onChange={e => updateRow(i, { selected: e.target.checked })}/>
          {row.image ? <img alt="" src={row.image} loading="lazy" /> : null}
          <div>
            <input aria-label={`第 ${i + 1} 本书名`} value={row.title}
              onChange={e => updateRow(i, { title: e.target.value })} placeholder={`第 ${i + 1} 本书名（可修改）`} />
            <small>{row.url || `图片候选 #${i + 1}`}</small>
          </div>
        </div>)}
      </div>
      <button type="button" disabled={disabled || busy || !canStage} onClick={() => void stage()}>
        {busy ? "暂存中…" : `确认并暂存 ${rows.filter(x => x.selected && x.title.trim()).length} 个成员候选`}
      </button>
    </> : null}
  </div>;
}
