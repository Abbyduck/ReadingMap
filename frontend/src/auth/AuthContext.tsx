import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, refreshCsrf, type Child, type User } from "@/api/client";

type AuthState = {
  user: User | null; loading: boolean; error: string; children: Child[]; selectedChild: Child | null;
  selectChild: (id: number) => void; reloadChildren: () => Promise<void>;
  authenticate: (mode: "login" | "register", payload: { email: string; password: string; name?: string }) => Promise<void>;
  logout: () => Promise<void>;
};
const AuthContext = createContext<AuthState | null>(null);
export function AuthProvider({ children: content }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [children, setChildren] = useState<Child[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  useEffect(() => {
    let active = true;
    api.me().then(({ user: next }) => { if (active) setUser(next); }).catch(reason => { if (active) setError(reason.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  const reloadChildren = useCallback(async () => { if (user) setChildren(await api.children()); }, [user]);
  useEffect(() => {
    let active = true;
    setChildren([]); setSelectedId(null);
    if (user) api.children().then(next => { if (active) setChildren(next); }).catch(reason => { if (active) setError(reason.message); });
    return () => { active = false; };
  }, [user]);
  const selectedChild = children.find(child => child.id === selectedId) ?? children[0] ?? null;
  async function authenticate(mode: "login" | "register", payload: { email: string; password: string; name?: string }) {
    const result = await api[mode](payload);
    await refreshCsrf();
    setUser(result.user); setError("");
  }
  async function logout() {
    await api.logout(); setUser(null); setChildren([]); setSelectedId(null); await refreshCsrf();
  }
  return <AuthContext.Provider value={{ user, loading, error, children, selectedChild, selectChild: setSelectedId, reloadChildren, authenticate, logout }}>{content}</AuthContext.Provider>;
}
export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("AuthProvider is required");
  return value;
}
export function AdminGuard({ children }: { children: ReactNode }) {
  const { user, loading, error } = useAuth();
  if (loading) return <main className="account-page"><p role="status">正在检查登录状态…</p></main>;
  if (!user || !user.is_staff) return <main className="account-page"><section className="account-card"><h1>管理工作台</h1><p>{error || (user ? "当前账号没有管理权限。" : "请使用管理员账号登录。")}</p><a className="account-primary" href="/login?next=/admin">管理员登录</a><a href="/">回到阅读房间</a></section></main>;
  return <>{children}</>;
}
