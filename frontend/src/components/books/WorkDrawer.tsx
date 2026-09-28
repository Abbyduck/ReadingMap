import { useEffect, useRef, useState, type FormEvent } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Bookmark, Check, ExternalLink, Heart, Route, Sparkles, X } from "lucide-react";
import { BookCover } from "@/components/books/BookCover";
import { Button } from "@/components/ui/button";
import type { PrototypeBook } from "@/pages/readingMapPrototype.mock";
import { api } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { useCatalog } from "@/lib/catalog";

const statusCopy = {
  ready: { label: "现在适合", className: "bg-[#dff2e9] text-[#1d6654]" },
  stretch: { label: "稍有挑战", className: "bg-[#fff0d2] text-[#8b5c1e]" },
  later: { label: "以后再读", className: "bg-[#e9ecee] text-[#676c72]" },
  unknown: { label: "适读性待评估", className: "bg-[#e9ecee] text-[#676c72]" }
} as const;

function ChildNotes({ entityId, onSaved }: { entityId: number; onSaved?: () => void }) {
  const { user, selectedChild, children, selectChild } = useAuth();
  const [note, setNote] = useState(""); const [override, setOverride] = useState(""); const [retry, setRetry] = useState("");
  const [loading, setLoading] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [message, setMessage] = useState("");
  useEffect(() => {
    let active = true; setNote(""); setOverride(""); setRetry(""); setMessage(""); setError("");
    if (!selectedChild) return;
    setLoading(true);
    api.annotation(selectedChild.id, entityId).then(value => { if (active) { setNote(value.note || ""); setRetry(value.retry_after_date || ""); setOverride(value.independent_reading_override == null ? "" : String(value.independent_reading_override)); } }).catch(reason => { if (active) setError(reason.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [selectedChild?.id, entityId]);
  async function save(event: FormEvent) { event.preventDefault(); if (!selectedChild) return; setBusy(true); setMessage(""); setError(""); try { await api.saveAnnotation(selectedChild.id, entityId, { note: note || null, retry_after_date: retry || null, independent_reading_override: override === "" ? null : override === "true" }); setMessage("已保存，只对你的账号可见。"); onSaved?.(); } catch (reason) { setError(reason instanceof Error ? reason.message : "保存失败"); } finally { setBusy(false); } }
  if (!user || !selectedChild) return <p className="catalog-notice">{user ? "添加孩子后，可以保存自主阅读判断、再试日期和私人备注。" : "登录后，可以为每个孩子保存阅读备注。"}<br /><a href={user ? "/account" : `/login?next=${encodeURIComponent(window.location.pathname)}`}>{user ? "添加孩子 →" : "登录 / 注册 →"}</a></p>;
  return <form className="annotation-editor" onSubmit={save}><h3 className="font-serif text-xl">孩子的阅读备注</h3><label>当前孩子<select value={selectedChild.id} disabled={busy} onChange={event => selectChild(Number(event.target.value))}>{children.map(child => <option key={child.id} value={child.id}>{child.name}</option>)}</select></label>{loading && <p role="status">正在加载备注…</p>}<label>自主阅读判断<select value={override} disabled={loading || busy} onChange={event => setOverride(event.target.value)}><option value="">不覆盖目录判断</option><option value="true">这个孩子可以自主阅读</option><option value="false">这个孩子暂不适合自主阅读</option></select></label><label>下次再试日期<input type="date" disabled={loading || busy} value={retry} onChange={event => setRetry(event.target.value)} /></label><label>私人备注<textarea rows={3} disabled={loading || busy} value={note} onChange={event => setNote(event.target.value)} placeholder="记录孩子的兴趣、困难或阅读感受…" /></label>{error && <p role="alert" className="account-error">{error}</p>}{message && <p role="status" className="account-success">{message}</p>}<button className="account-primary" disabled={loading || busy}>{busy ? "保存中…" : "保存孩子备注"}</button></form>;
}

export function WorkDrawer({
  book,
  onAnnotationSaved,
  onClose
}: {
  book: PrototypeBook | null;
  onAnnotationSaved?: () => void;
  onClose: () => void;
}) {
  const { lists, creators } = useCatalog();
  const drawerRef = useRef<HTMLElement | null>(null);
  const appearances = book ? lists.filter(list => list.items?.some(item => item.entity.id === book.entityId)) : [];
  const evidence = book?.recommendations?.length ? book.recommendations.map(item => ({
    creatorId: item.creatorId,
    creatorName: item.creatorName,
    avatarUrl: item.avatarUrl,
    readingListTitle: item.readingListTitle,
    stageLabel: item.stageLabel,
    strong: item.isStrongRecommendation ?? item.recommendationStrength === 3,
    emphasisText: item.emphasisText ?? item.recommendationStrengthText,
    copy: item.comment || item.note,
    href: item.creatorId ? `/guides/${item.creatorId}` : "/guides"
  })) : appearances.flatMap(list => list.items.filter(item => item.entity.id === book?.entityId).map(item => ({
    creatorId: list.creator_id,
    creatorName: list.creator_name,
    avatarUrl: creators.find(creator => creator.id === list.creator_id)?.avatar_url,
    readingListTitle: list.title,
    stageLabel: item.stage_label || list.stage_label,
    strong: item.is_strong_recommendation,
    emphasisText: item.recommendation_emphasis_text,
    copy: item.comment || item.note,
    href: `/guides/${list.creator_id}#list-${list.id}`
  })));
  const curatorGroups = Array.from(evidence.reduce((groups, row) => {
    const key = String(row.creatorId ?? row.creatorName);
    const group = groups.get(key);
    if (group) group.rows.push(row);
    else groups.set(key, { key, creatorName: row.creatorName, avatarUrl: row.avatarUrl, href: row.href, rows: [row] });
    return groups;
  }, new Map<string, { key: string; creatorName: string; avatarUrl?: string | null; href: string; rows: typeof evidence }>()).values());
  useEffect(() => {
    if (!book) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const previousFocus = document.activeElement as HTMLElement | null;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
      if (event.key === "Tab" && drawerRef.current) {
        const elements = Array.from(drawerRef.current.querySelectorAll<HTMLElement>('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex="0"]'));
        const first = elements[0]; const last = elements[elements.length - 1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
      previousFocus?.focus();
    };
  }, [book, onClose]);

  const status = book ? statusCopy[book.status] : null;
  const [curator, pathName] = book?.source.split(" · ") ?? [];

  return (
    <AnimatePresence>
      {book && status ? (
        <motion.div
          className="fixed inset-0 z-[100] flex justify-end bg-[#10271f]/32 backdrop-blur-[5px]"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: .2 }}
          onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
        >
          <motion.aside
            ref={drawerRef}
            className="work-drawer flex h-full w-full max-w-[540px] flex-col overflow-y-auto bg-[#fffefa] text-[#18352e] shadow-[-28px_0_80px_rgba(17,44,36,.23)]"
            role="dialog"
            aria-modal="true"
            aria-labelledby="work-drawer-title"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: .28, ease: [.2, .8, .2, 1] }}
          >
            <header className="sticky top-0 z-10 flex items-center justify-between border-b border-[#e5e7df] bg-[#fffefa]/90 px-6 py-4 backdrop-blur-xl">
              <div>
                <p className="m-0 text-[10px] font-black tracking-[.16em] text-[#8a6937]">BOOK DETAILS</p>
                <span className="mt-1 block text-[11px] text-[#87938f]">{book.entityId ? "Reading Map 正式内容目录" : "Reading Map 来源转录草稿"}</span>
              </div>
              <Button variant="outline" size="icon" onClick={onClose} autoFocus aria-label="关闭书籍详情"><X /></Button>
            </header>

            <div className="px-6 pb-8 pt-7 sm:px-8">
              <section className="grid grid-cols-[150px_1fr] items-center gap-7 sm:grid-cols-[172px_1fr]">
                <BookCover book={book} eager className="work-drawer-cover" />
                <div className="min-w-0">
                  <span className={`inline-flex rounded-full px-3 py-1.5 text-xs font-extrabold ${status.className}`}>{status.label}</span>
                  <h2 id="work-drawer-title" className="mt-4 font-serif text-[30px] leading-[1.05] tracking-[-.03em] text-[#17372f]">{book.title}</h2>
                  <p className="mt-2 text-[15px] text-[#5e756d]">{book.titleZh}</p>
                  <p className="mt-3 text-xs font-semibold text-[#89948f]">{book.author}</p>
                </div>
              </section>

              <section className="mt-8 flex flex-wrap items-center gap-x-3 gap-y-2 border-y border-[#e5e7df] py-4 text-sm">
                <strong>{book.age}</strong>
                <i className="size-1 rounded-full bg-[#c8d0cb]" />
                <span>AR {book.ar}</span>
                <i className="size-1 rounded-full bg-[#c8d0cb]" />
                <span>{book.lexile}</span>
                <i className="size-1 rounded-full bg-[#c8d0cb]" />
                <span>{book.length}</span>
                {book.importanceScore != null ? <><i className="size-1 rounded-full bg-[#c8d0cb]" /><span>综合推荐 {book.importanceScore.toFixed(1)}</span></> : null}
              </section>

              <section className="mt-8">
                <p className="flex items-center gap-2 text-[11px] font-black tracking-[.12em] text-[#9b6b28]"><Sparkles size={14} /> WHY THIS BOOK</p>
                <h3 className="mt-3 font-serif text-xl text-[#1b3a32]">推荐说明与内容简介</h3>
                <p className="mt-3 text-sm leading-7 text-[#60736d]">{book.reason}</p>
                <p className="mt-3 text-sm leading-7 text-[#60736d]">{book.summary}</p>
              </section>

              <section className="mt-9 border-t border-[#e5e7df] pt-7">
                <div className="flex items-end justify-between gap-4">
                  <div><p className="text-[11px] font-black tracking-[.12em] text-[#8a6937]">CURATOR NOTES</p><h3 className="mt-2 font-serif text-xl">{curatorGroups.length} 位达人推荐</h3></div>
                  <Heart size={18} className="text-[#c67576]" />
                </div>
                {curatorGroups.map(group => <article key={group.key} className="mt-5 grid grid-cols-[38px_1fr] gap-3 border-b border-[#ecece5] pb-5"><span className="relative grid size-9 place-items-center rounded-full bg-[#f8d86f] text-xs font-black text-[#67491a]">{group.avatarUrl ? <img src={group.avatarUrl} alt="" className="size-9 rounded-full object-cover" /> : group.creatorName.slice(0, 1)}{group.rows.some(row => row.strong) ? <span className="absolute -right-1 -top-1 text-[13px]" aria-label="这位达人明确强烈推荐">👍</span> : null}</span><div><a href={group.href} className="text-sm font-bold">{group.creatorName}</a><div className="mt-2 space-y-1">{group.rows.map((row, index) => <div key={`${row.readingListTitle}-${index}`} className="text-sm text-[#667871]"><span>{row.stageLabel || row.readingListTitle}</span><strong className="ml-2 text-[#2b6657]">{row.strong ? "强烈推荐" : "推荐"}</strong>{row.emphasisText ? <details className="mt-1 text-xs"><summary>查看强调原文</summary>“{row.emphasisText}”</details> : null}{row.copy ? <p className="mt-1 text-xs">{row.copy}</p> : null}</div>)}</div></div></article>)}
                {!curatorGroups.length ? <p className="catalog-notice">暂无关联的公开推荐书单。</p> : null}
              </section>

              <section className="mt-9 border-t border-[#e5e7df] pt-7">
                <p className="text-[11px] font-black tracking-[.12em] text-[#8a6937]">APPEARS ON</p>
                <a href={book.listId ? `/map?list=${book.listId}` : "/map"} className="mt-4 flex items-center gap-3 text-sm font-bold text-[#275e50] no-underline">
                  <span className="grid size-9 place-items-center rounded-full bg-[#e4efe9]"><Route size={16} /></span>
                  {pathName || "公开阅读地图"}<ExternalLink size={14} className="ml-auto" />
                </a>
              </section>

              <div className="mt-8 flex flex-wrap gap-2">{book.tags.map((tag) => <span className="rounded-full bg-[#eff3ef] px-3 py-1.5 text-[11px] font-bold text-[#557068]" key={tag}>{tag}</span>)}</div>
            </div>

            <footer className="sticky bottom-0 mt-auto border-t border-[#e4e6df] bg-[#fffefa]/92 p-5 backdrop-blur-xl">
              {book.entityId ? <ChildNotes entityId={book.entityId} onSaved={onAnnotationSaved} /> : <p className="catalog-notice">来源转录草稿，尚未进入正式目录；此处不保存个人数据。</p>}
            </footer>
          </motion.aside>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
