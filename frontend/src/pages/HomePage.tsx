import { useEffect, useRef, useState, type CSSProperties } from "react";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { AssetImage, RoomBackground, SceneArtwork } from "@/components/home/SceneArtwork";
import { decorativeLayers, percentRect, sceneObjects, type SceneObject } from "@/components/home/sceneAssets";
import "@/components/home/scene.css";
import { useAuth } from "@/auth/AuthContext";

function SceneEntry({ object, mobile = false, onTypewriter }: { object: SceneObject; mobile?: boolean; onTypewriter: () => void }) {
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const [printing, setPrinting] = useState(false);
  const [printVersion, setPrintVersion] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  const events = {
    onMouseEnter: () => setHovered(true), onMouseLeave: () => setHovered(false),
    onFocus: () => setFocused(true), onBlur: () => setFocused(false)
  };
  function print() {
    if (timer.current) clearTimeout(timer.current);
    setPrinting(true);
    setPrintVersion(version => version + 1);
    onTypewriter();
    timer.current = setTimeout(() => setPrinting(false), 900);
  }
  const active = hovered || focused || printing;
  const content = <>
    <span className="scene-entry-art" style={mobile ? { "--asset-ratio": object.bounds.width / object.bounds.height } as CSSProperties : undefined}><SceneArtwork id={object.id} active={active} printVersion={printVersion} /></span>
    {object.id !== "typewriter" && !mobile ? <span className={`scene-sign scene-sign--${object.id}`}>{object.title}</span> : null}
    {mobile ? <span className="scene-mobile-label"><strong>{object.title}</strong><small>{object.description}</small></span> : null}
  </>;
  const controlProps = {
    ...events, "aria-label": object.label,
    className: mobile ? `room-mobile-card room-mobile-card--${object.id}` : "scene-hit",
    style: !mobile && object.hitBounds ? percentRect(object.hitBounds, { width: 100, height: 100 }) : undefined
  };
  if (mobile) return object.href
    ? <a {...controlProps} href={object.href}>{content}</a>
    : <button {...controlProps} type="button" onClick={print}>{content}</button>;
  return <div className={`scene-object scene-object--${object.id}`} style={percentRect(object.bounds)}>
    {content}
    {object.href ? <a {...controlProps} href={object.href}><span className="room-object__focus-label">{object.label}</span></a>
      : <button {...controlProps} type="button" onClick={print}><span className="room-object__focus-label">{object.label}</span></button>}
  </div>;
}

function DesktopRoom({ onTypewriter }: { onTypewriter: () => void }) {
  return <section className="room-scene" aria-label="Reading Map 互动阅读房间">
    <RoomBackground />
    {decorativeLayers.map(layer => <span key={layer.id} className="scene-decoration" style={percentRect(layer.bounds)} aria-hidden="true"><AssetImage asset={layer.asset}>{null}</AssetImage></span>)}
    <nav className="scene-navigation" aria-label="首页导航">
      <a className="room-nav-hit room-nav-hit--brand" href="/">Reading Map</a>
      <a className="room-nav-hit room-nav-hit--books" href="/bookshelf">Book Lists</a>
      <a className="room-nav-hit room-nav-hit--map" href="/map">Map</a>
      <a className="room-nav-hit room-nav-hit--search" href="/bookshelf?search=1" aria-label="搜索书籍">搜索书籍、作者…</a>
    </nav>
    {sceneObjects.map(object => <SceneEntry key={object.id} object={object} onTypewriter={onTypewriter} />)}
  </section>;
}

function MobileRoom({ onTypewriter }: { onTypewriter: () => void }) {
  return <section className="room-mobile" aria-label="阅读房间入口">
    <header className="room-mobile__header"><a href="/">Reading Map</a><a href="/bookshelf?search=1">搜索书籍</a></header>
    <div className="room-mobile__hero">
      <div className="scene-miniature" aria-hidden="true"><RoomBackground />{sceneObjects.map(object => <span key={object.id} className="scene-object" style={percentRect(object.bounds)}><SceneArtwork id={object.id} /></span>)}</div>
      <div className="scene-mobile-heading"><small>YOUR READING ROOM</small><h2>今天想从哪里开始？</h2></div>
    </div>
    <nav className="room-mobile__grid" aria-label="首页入口">{sceneObjects.map(object => <SceneEntry key={object.id} object={object} mobile onTypewriter={onTypewriter} />)}</nav>
  </section>;
}

export function HomePage() {
  const { user } = useAuth();
  const [message, setMessage] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  function activateTypewriter() {
    if (timer.current) clearTimeout(timer.current);
    setMessage(true);
    timer.current = setTimeout(() => setMessage(false), 2600);
  }
  return <MotionConfig reducedMotion="user"><main className="room-home product-root">
    <h1 className="sr-only">Reading Map 互动阅读房间</h1>
    <DesktopRoom onTypewriter={activateTypewriter} /><MobileRoom onTypewriter={activateTypewriter} />
    <a className="home-account-link" href={user ? "/account" : "/login"}>{user ? "我的账号与孩子" : "登录 / 注册"}</a>
    <AnimatePresence>{message ? <motion.div className="room-toast" role="status" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}><strong>咔嗒——记录一个阅读瞬间</strong><span>今天有什么想记下来？</span></motion.div> : null}</AnimatePresence>
  </main></MotionConfig>;
}
