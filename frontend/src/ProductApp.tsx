import { BookshelfPage } from "@/pages/BookshelfPage";
import { GuidesPage } from "@/pages/GuidesPage";
import { HomePage } from "@/pages/HomePage";
import { PlanPage } from "@/pages/PlanPage";
import { ReadingMapPage } from "@/pages/ReadingMapPrototype";
import { AccountPage, AuthPage } from "@/auth/AccountPages";

export function ProductApp({ path }: { path: string }) {
  if (path === "/account") return <AccountPage />;
  if (["/login", "/register", "/forgot-password", "/reset-password"].includes(path)) return <AuthPage mode={path.slice(1) as "login" | "register" | "forgot-password" | "reset-password"} />;
  if (path === "/map" || path === "/reading-map-prototype") return <ReadingMapPage />;
  if (path === "/bookshelf") return <BookshelfPage />;
  if (path === "/plan") return <PlanPage />;
  if (path === "/guides" || path.startsWith("/guides/")) return <GuidesPage />;
  return <HomePage />;
}
