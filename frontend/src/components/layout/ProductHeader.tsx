import { LibraryBig, Map, Search, UserRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useAuth } from "@/auth/AuthContext";

type ProductArea = "home" | "map" | "bookshelf" | "plan" | "guides";

function ReadingMapMark() {
  return (
    <span className="product-brand-mark" aria-hidden="true">
      <svg viewBox="0 0 40 40" fill="none">
        <path d="M8.5 10.5 17 8l7 2.5 7.5-2.5v21.5L24 32l-7-2.5L8.5 32V10.5Z" fill="currentColor" fillOpacity=".12" />
        <path d="M17 8v21.5M24 10.5V32" stroke="currentColor" strokeOpacity=".46" strokeWidth="1.5" />
        <path d="M11.5 17.5c3.7-3.4 6.6 3.3 10.4-.1 3.1-2.7 5.2-1 6.6.4" stroke="#f8d991" strokeWidth="2.2" strokeLinecap="round" />
        <circle cx="11.3" cy="17.7" r="2.1" fill="#fff8df" />
        <circle cx="28.7" cy="17.7" r="2.1" fill="#f8d991" />
      </svg>
    </span>
  );
}

export function ProductHeader({
  current,
  overlay = false
}: {
  current: ProductArea;
  overlay?: boolean;
}) {
  const { user, children, selectedChild, selectChild } = useAuth();
  return (
    <header className={cn("product-header", overlay && "product-header--overlay")}>
      <a className="product-brand" href="/" aria-label="Reading Map 首页">
        <ReadingMapMark />
        <strong>Reading Map</strong>
      </a>

      <nav className="product-nav" aria-label="前台主导航">
        <a href="/map" aria-current={current === "map" ? "page" : undefined}><Map size={15} />Map</a>
        <a href="/bookshelf" aria-current={current === "bookshelf" ? "page" : undefined}><LibraryBig size={15} />Bookshelf</a>
      </nav>

      <div className="product-actions">
        <Button asChild variant="ghost" size="icon" className="product-search-button">
          <a href="/bookshelf?search=1" aria-label="搜索书籍"><Search /></a>
        </Button>
        {children.length > 1 && <select className="product-child-switch" aria-label="当前孩子" value={selectedChild?.id ?? ""} onChange={event => selectChild(Number(event.target.value))}>{children.map(child => <option key={child.id} value={child.id}>{child.name}</option>)}</select>}
        <a className="product-profile" href={user ? "/account" : `/login?next=${encodeURIComponent(window.location.pathname)}`} aria-label={user ? "我的账号与孩子资料" : "登录或注册"}>
          <span>{(user?.name || user?.email || "R").slice(0, 1).toUpperCase()}</span>
          <small>{user?.name || (user ? "我的账号" : "登录")}</small>
          <UserRound size={15} />
        </a>
      </div>
    </header>
  );
}
