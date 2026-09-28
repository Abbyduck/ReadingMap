import { CSSProperties, useEffect, useState } from "react";
import { BookOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import type { PrototypeBook } from "@/pages/readingMapPrototype.mock";

export function BookCover({
  book,
  className,
  eager = false
}: {
  book: PrototypeBook;
  className?: string;
  eager?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  useEffect(() => { setFailed(false); }, [book.coverUrl]);
  const coverUrl = book.coverUrl;

  return (
    <span
      className={cn("rmp-flow-cover product-book-cover", className)}
      style={{ "--rmp-cover-start": book.palette[0], "--rmp-cover-end": book.palette[1] } as CSSProperties}
      aria-hidden="true"
    >
      <span className="rmp-flow-cover-fallback">
        <span>READING MAP</span>
        <strong>{book.title}</strong>
        <small>{book.author}</small>
        <BookOpen size={30} />
      </span>
      {coverUrl && !failed ? (
        <img
          src={coverUrl}
          alt=""
          loading={eager ? "eager" : "lazy"}
          onLoad={(event) => {
            if (event.currentTarget.naturalWidth <= 10 || event.currentTarget.naturalHeight <= 10) {
              setFailed(true);
            }
          }}
          onError={() => setFailed(true)}
        />
      ) : null}
    </span>
  );
}
