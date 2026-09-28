import { useState, type FormEvent } from "react";
import { api, type Child } from "@/api/client";
import { useAuth } from "./AuthContext";
import { ProductHeader } from "@/components/layout/ProductHeader";
import { safeNextPath } from "./redirect";

function safeNext() {
  const next = new URLSearchParams(window.location.search).get("next") || "/account";
  return safeNextPath(next, window.location.origin);
}
export function AuthPage({ mode }: { mode: "login" | "register" | "forgot-password" | "reset-password" }) {
  const { authenticate } = useAuth();
  const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [name, setName] = useState("");
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [message, setMessage] = useState("");
  const title = { login: "欢迎回来", register: "开始你的阅读旅程", "forgot-password": "找回密码", "reset-password": "设置新密码" }[mode];
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try {
      if (mode === "login" || mode === "register") { await authenticate(mode, { email, password, name }); window.location.assign(safeNext()); }
      else if (mode === "forgot-password") { await api.passwordReset(email); setMessage("如果该邮箱已注册，我们会发送重置链接，请检查收件箱。开发环境邮件由管理员在本地邮件目录查看。"); }
      else { const query = new URLSearchParams(window.location.search); await api.passwordResetConfirm({ uid: query.get("uid") || "", token: query.get("token") || "", password }); setMessage("密码已更新，请使用新密码登录。"); setPassword(""); }
    } catch (reason) { setError(reason instanceof Error ? reason.message : "操作失败，请重试。"); } finally { setBusy(false); }
  }
  return <main className="product-root account-page"><a className="account-brand" href="/">Reading Map</a><section className="account-card"><p className="account-eyebrow">YOUR READING ROOM</p><h1>{title}</h1><p>一个账号，陪伴每个孩子的阅读成长。</p><form onSubmit={submit}>
    {mode === "register" && <label>怎么称呼你<input required maxLength={80} autoComplete="name" value={name} onChange={event => setName(event.target.value)} /></label>}
    {mode !== "reset-password" && <label>邮箱<input required type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} /></label>}
    {mode !== "forgot-password" && <label>{mode === "reset-password" ? "新密码" : "密码"}<input required type="password" minLength={mode === "login" ? 1 : 8} autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={event => setPassword(event.target.value)} />{mode !== "login" && <small>至少 8 位，避免常用密码或与邮箱过于相似。</small>}</label>}
    {error && <p className="account-error" role="alert">{error}</p>}{message && <p className="account-success" role="status">{message}</p>}
    <button className="account-primary" disabled={busy}>{busy ? "请稍候…" : mode === "login" ? "登录" : mode === "register" ? "创建账号" : mode === "forgot-password" ? "发送重置邮件" : "更新密码"}</button>
  </form><div className="account-links">{mode === "login" ? <><a href={`/register?next=${encodeURIComponent(safeNext())}`}>注册账号</a><a href="/forgot-password">忘记密码？</a></> : <a href={`/login?next=${encodeURIComponent(safeNext())}`}>返回登录</a>}<a href="/map">先逛逛公开书单</a></div></section></main>;
}

function ChildEditor({ child, onSaved }: { child?: Child; onSaved: () => Promise<void> }) {
  const [name, setName] = useState(child?.name ?? ""); const [birth, setBirth] = useState(child?.birth_date ?? "");
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState(""); const [error, setError] = useState("");
  async function save(event: FormEvent) { event.preventDefault(); setBusy(true); setError(""); setMessage(""); try {
    if (child) await api.updateChild(child.id, { name, birth_date: birth || null }); else await api.createChild({ name, ...(birth ? { birth_date: birth } : {}) });
    await onSaved(); setMessage("已保存"); if (!child) { setName(""); setBirth(""); }
  } catch (reason) { setError(reason instanceof Error ? reason.message : "保存失败"); } finally { setBusy(false); } }
  return <form className="child-editor" onSubmit={save}><h3>{child ? child.name : "添加孩子"}</h3><label>昵称<input required maxLength={100} value={name} onChange={event => setName(event.target.value)} /></label><label>出生日期（可选）<input type="date" max={new Date().toLocaleDateString("en-CA")} value={birth} onChange={event => setBirth(event.target.value)} /></label><button className="account-primary" disabled={busy}>{busy ? "保存中…" : child ? "保存资料" : "添加孩子"}</button>{error && <p className="account-error" role="alert">{error}</p>}{message && <p role="status">{message}</p>}</form>;
}
export function AccountPage() {
  const { user, loading, error, children, selectedChild, selectChild, reloadChildren, logout } = useAuth();
  const [logoutError, setLogoutError] = useState("");
  return <main className="product-root min-h-screen bg-[#f8f8f4]"><ProductHeader current="home" /><section className="account-content"><p className="account-eyebrow">YOUR FAMILY</p><h1>我的阅读空间</h1>{loading ? <p role="status">正在加载账号…</p> : !user ? <section className="account-card"><p>{error || "登录后创建孩子资料，保存每个孩子自己的阅读备注。"}</p><a className="account-primary" href="/login">登录 / 注册</a></section> : <><div className="account-user"><div><h2>{user.name || user.email}</h2><p>{user.email}</p></div><button type="button" onClick={() => { void logout().catch(reason => setLogoutError(reason.message)); }}>退出登录</button></div>{(error || logoutError) && <p role="alert" className="account-error">{logoutError || error}</p>}<p>孩子资料与阅读备注仅属于当前账号，不向其他用户公开。</p>{children.length > 0 && <label className="account-child-select">当前孩子<select value={selectedChild?.id ?? ""} onChange={event => selectChild(Number(event.target.value))}>{children.map(child => <option key={child.id} value={child.id}>{child.name}</option>)}</select></label>}<div className="account-children">{children.map(child => <ChildEditor key={child.id} child={child} onSaved={reloadChildren} />)}<ChildEditor onSaved={reloadChildren} /></div>{user.is_staff && <div className="account-links"><a href="/admin">Research 审核工作台</a><a href="/django-admin/">Django 管理后台</a></div>}</>}</section></main>;
}
