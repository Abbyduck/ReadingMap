import { useEffect, useMemo, useState } from "react";
import { ArrowDownAZ, BookOpen, Search, SlidersHorizontal } from "lucide-react";
import { ProductHeader } from "@/components/layout/ProductHeader";
import { BookTile } from "@/components/books/BookTile";
import { WorkDrawer } from "@/components/books/WorkDrawer";
import type { PrototypeBook } from "@/pages/readingMapPrototype.mock";
import { api, type CatalogEntity, type ChildAnnotation } from "@/api/client";
import { useAuth } from "@/auth/AuthContext";
import { toBook, useCatalog } from "@/lib/catalog";

export function BookshelfPage() {
  const { entities, lists, loading, error } = useCatalog();
  const { user, selectedChild } = useAuth();
  const [filter, setFilter] = useState<"all" | "notes">("all");
  const [sort, setSort] = useState("recommended"); const [query, setQuery] = useState("");
  const [selectedBook, setSelectedBook] = useState<PrototypeBook | null>(null);
  const [annotations, setAnnotations] = useState<ChildAnnotation[]>([]); const [searchResults, setSearchResults] = useState<CatalogEntity[]>([]);
  const [requestError, setRequestError] = useState(""); const [searching, setSearching] = useState(false); const [revision, setRevision] = useState(0);
  useEffect(() => { let active = true; setAnnotations([]); if (selectedChild) api.annotations(selectedChild.id).then(next => { if (active) setAnnotations(next); }).catch(reason => { if (active) setRequestError(reason.message); }); return () => { active = false; }; }, [selectedChild?.id, revision]);
  useEffect(() => {
    let active = true; setRequestError("");
    if (!query.trim()) { setSearching(false); return; }
    setSearching(true);
    const timer = window.setTimeout(() => { api.search(query.trim()).then(next => { if (active) setSearchResults(next); }).catch(reason => { if (active) setRequestError(reason.message); }).finally(() => { if (active) setSearching(false); }); }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [query]);
  const visibleEntries = useMemo(() => {
    const source = filter === "notes" ? annotations.flatMap(note => note.entity ? [note.entity] : entities.filter(entity => entity.id === note.catalog_entity_id)) : query.trim() ? searchResults : entities;
    const matches = source.filter(entity => entity.bookshelf_visible && (filter !== "notes" || !query.trim() || `${entity.display_title} ${entity.title_zh} ${entity.title_en} ${entity.work?.author_text}`.toLowerCase().includes(query.toLowerCase())));
    return matches.map(entity => toBook(entity, lists)).sort((a, b) => sort === "title" ? a.title.localeCompare(b.title) : (b.recommendationCount ?? 0) - (a.recommendationCount ?? 0));
  }, [entities, lists, annotations, filter, query, searchResults, sort]);
  return <main className="product-root min-h-screen bg-[#f8f8f4] text-[#18352e]"><ProductHeader current="bookshelf" />
    <section className="mx-auto w-full max-w-[1480px] px-5 pb-20 pt-14 sm:px-8 lg:px-12 lg:pt-20">
      <header className="flex flex-col gap-7 border-b border-[#dfe4df] pb-8 md:flex-row md:items-end md:justify-between"><div><p className="text-[11px] font-black tracking-[.15em] text-[#9a6a2b]">THE READING COLLECTION</p><h1 className="mt-3 font-serif text-4xl font-semibold tracking-[-.04em] sm:text-5xl">阅读书架</h1><p className="mt-3 max-w-lg text-sm leading-6 text-[#708079]">浏览正式收录的图书与学习资源，在详情里为孩子留下阅读备注。想读、在读和已读状态尚未开放。</p></div><p className="font-serif text-2xl text-[#355c51]"><strong>{visibleEntries.length}</strong><span className="ml-2 text-sm font-normal text-[#88948f]">条资源</span></p></header>
      <div className="mt-7 flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between"><div className="flex gap-1 overflow-x-auto" role="tablist" aria-label="书架范围">{([{ value: "all", label: "全部目录" }, { value: "notes", label: selectedChild ? `${selectedChild.name} 的备注` : "孩子的备注" }] as const).map(item => <button key={item.value} type="button" role="tab" aria-selected={filter === item.value} onClick={() => setFilter(item.value)} className={`rounded-full px-4 py-2 text-sm font-semibold transition ${filter === item.value ? "bg-[#1f594b] text-white" : "text-[#6b7c76] hover:bg-[#edf1ed] hover:text-[#1e463b]"}`}>{item.label}</button>)}</div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center"><label className="flex min-w-0 items-center gap-2 border-b border-[#ccd6cf] px-1 py-2 focus-within:border-[#2c6858] sm:w-[310px]"><Search size={16} className="shrink-0 text-[#71837c]" /><input aria-label="搜索书名、作者" autoFocus={new URLSearchParams(window.location.search).has("search")} value={query} onChange={event => setQuery(event.target.value)} className="w-full border-0 bg-transparent text-sm outline-none placeholder:text-[#a2aba7]" placeholder="搜索书名、作者…" /></label><label className="flex items-center gap-2 rounded-full border border-[#dbe2dc] bg-white/70 px-3 py-2 text-xs font-semibold text-[#62766f]">{sort === "title" ? <ArrowDownAZ size={15} /> : <SlidersHorizontal size={15} />}<select aria-label="目录排序" value={sort} onChange={event => setSort(event.target.value)} className="border-0 bg-transparent outline-none"><option value="recommended">推荐最多</option><option value="title">书名 A–Z</option></select></label></div></div>
      {(error || requestError) && <p className="catalog-notice" role="alert">{error || requestError}</p>}
      {filter === "notes" && !selectedChild && <p className="catalog-notice">{user ? "先添加一个孩子，就可以保存专属备注。" : "登录后可以查看孩子的专属备注。"} <a href={user ? "/account" : "/login?next=/bookshelf"}>前往设置 →</a></p>}
      {loading || searching ? <p className="catalog-notice" role="status">正在加载目录…</p> : visibleEntries.length ? <section className="mt-10 grid grid-cols-2 gap-x-5 gap-y-12 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-7" aria-label="书籍封面">{visibleEntries.map(book => <BookTile key={book.id} book={book} recommendationCount={book.recommendationCount ?? 0} onOpen={setSelectedBook} />)}</section> : <section className="grid min-h-[320px] place-items-center text-center"><div><BookOpen className="mx-auto text-[#a7b3ae]" /><h2 className="mt-4 font-serif text-2xl">{filter === "notes" ? "还没有阅读备注" : query ? "没有找到这本书" : "目录正在慢慢长大"}</h2><p className="mt-2 text-sm text-[#82908b]">{filter === "notes" ? "从全部目录打开一本书，为孩子写下第一条备注。" : "正式审核收录后，资源会出现在这里。"}</p></div></section>}
    </section><WorkDrawer book={selectedBook} onClose={() => setSelectedBook(null)} onAnnotationSaved={() => setRevision(value => value + 1)} /></main>;
}
