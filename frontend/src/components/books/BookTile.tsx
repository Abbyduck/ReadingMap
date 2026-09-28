import { motion } from "motion/react";
import { Heart } from "lucide-react";
import { BookCover } from "@/components/books/BookCover";
import type { PrototypeBook } from "@/pages/readingMapPrototype.mock";

export type ShelfStatus = "want" | "reading" | "read";

const statusLabels: Record<ShelfStatus, string> = {
  want: "想读",
  reading: "正在读",
  read: "已读"
};

export function BookTile({
  book,
  status,
  recommendationCount,
  saved,
  onOpen,
  onToggleSaved
}: {
  book: PrototypeBook;
  status?: ShelfStatus;
  recommendationCount: number;
  saved?: boolean;
  onOpen: (book: PrototypeBook) => void;
  onToggleSaved?: (bookId: string) => void;
}) {
  return (
    <motion.article layout initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .24 }} className="group min-w-0">
      <div className="relative">
        <button className="block w-full border-0 bg-transparent p-0 text-left" type="button" onClick={() => onOpen(book)} aria-label={`查看 ${book.title} 详情`}>
          <BookCover book={book} className="product-book-cover--shelf" />
        </button>
        {onToggleSaved && <button
          type="button"
          className={`absolute right-3 top-3 grid size-9 place-items-center rounded-full border border-white/70 bg-white/88 shadow-sm backdrop-blur transition duration-200 ${saved ? "text-[#b85e64] opacity-100" : "text-[#315d52] opacity-0 group-hover:opacity-100 group-focus-within:opacity-100"}`}
          onClick={() => onToggleSaved(book.id)}
          aria-label={saved ? `从书架移除 ${book.title}` : `收藏 ${book.title}`}
          aria-pressed={saved}
        >
          <Heart size={16} fill={saved ? "currentColor" : "none"} />
        </button>}
      </div>
      <button type="button" className="mt-4 block w-full border-0 bg-transparent p-0 text-left" onClick={() => onOpen(book)}>
        <h2 className="truncate font-serif text-[17px] font-semibold tracking-[-.02em] text-[#18352e]">{book.title}</h2>
        <p className="mt-1 truncate text-xs text-[#6e817a]">{book.titleZh}</p>
        <p className="mt-2 text-[11px] font-semibold text-[#8a9792]">{book.age} · {recommendationCount} 位达人推荐</p>
        <span className="mt-2 inline-flex text-[10px] font-bold tracking-[.08em] text-[#9a6a2b]">{status ? statusLabels[status] : book.tags[0]}</span>
      </button>
    </motion.article>
  );
}
