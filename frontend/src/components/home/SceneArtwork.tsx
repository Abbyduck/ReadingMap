import { useState, type ReactNode } from "react";
import { motion, useReducedMotion } from "motion/react";
import { percentRect, sceneAssets, type AssetSlot, type Rect, type SceneId } from "./sceneAssets";

/** Entire standalone images only: contain, never crop/oversize/negative image offsets. */
export function AssetImage({ asset, children }: { asset: AssetSlot; children: ReactNode }) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  return asset.src && failedSrc !== asset.src
    ? <img className="scene-asset" src={asset.src} alt="" draggable={false} onError={() => setFailedSrc(asset.src)} />
    : <>{children}</>;
}

// Structural placeholders pending regenerated raster assets; not screenshot derivatives.
function Placeholder({ kind }: { kind: string }) {
  return <svg className="scene-asset" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
    {kind === "background" ? <><path fill="#ffe08a" d="M0 0h100v100H0z" /><path fill="#dfa570" d="M0 86h100v14H0z" /><path fill="#f1bc7b" d="M0 83h100v5H0z" /><path fill="#c1e9e5" stroke="#fff3ca" strokeWidth="2" d="M1 0h10v63H1z" /><path stroke="#fff3ca" strokeWidth="1.5" d="M6 0v63M1 21h10M1 42h10" /><path fill="#ffefb6" opacity=".45" d="M12 0 40 83H12z" /></> : null}
    {kind === "plan" ? <><path d="m12 25 38-22 38 22" fill="none" stroke="#ac743f" strokeWidth="3" /><rect x="3" y="23" width="94" height="75" rx="6" fill="#d99453" /><rect x="8" y="28" width="84" height="64" rx="3" fill="#f7ebd8" /></> : null}
    {kind === "page" ? <><rect width="100" height="100" rx="3" fill="#fff9ee" /><path d="M12 18h76M12 39h76M12 59h76M12 79h76M28 30v60M48 30v60M68 30v60" stroke="#dcc7b0" strokeWidth="1" /><circle cx="38" cy="49" r="6" fill="#ee8a7f" /></> : null}
    {kind === "map" ? <><rect x="1" y="1" width="98" height="98" rx="5" fill="#cc8e51" /><rect x="4" y="6" width="92" height="88" rx="2" fill="#a4ddea" /><path d="m11 20 16-7 15 13-9 18-9-5-7-6zM52 23l21-9 13 14-8 17-18-6-9 17-7-16zM29 48l13 9-3 24-7 4-7-20zM71 68l13-5 8 12-9 8-14-6z" fill="#bdd28c" /></> : null}
    {kind === "pin" ? <path d="M50 97C42 78 13 54 13 36a37 35 0 0 1 74 0c0 18-28 43-37 61Zm0-78a16 16 0 1 0 0 32 16 16 0 0 0 0-32" fill="#f07a66" stroke="#fff5de" strokeWidth="5" fillRule="evenodd" /> : null}
    {kind === "shelf" ? <><rect x="2" y="1" width="96" height="98" rx="6" fill="#daaa60" /><rect x="9" y="10" width="82" height="83" fill="#ac7846" />{[36,64,91].map(y => <g key={y}>{[12,25,39,66,79].map((x,i) => <rect key={x} x={x} y={y-21} width="11" height="21" rx="1" fill={["#85c3cb","#9fbf84","#f0c86e","#e79b87","#b59acb"][i]} />)}<path d={`M8 ${y}h84`} stroke="#e8be73" strokeWidth="3" /></g>)}</> : null}
    {kind === "book" ? <><rect width="100" height="100" rx="6" fill="#efad78" /><path d="M15 0v100M30 15h50M30 22h50" stroke="#ffdbb2" strokeWidth="3" /></> : null}
    {kind === "board" ? <><rect x="1" y="2" width="98" height="96" rx="4" fill="#bd8247" /><rect x="4" y="8" width="92" height="84" rx="2" fill="#deac6c" /></> : null}
    {kind === "photo" ? <><rect x="2" y="2" width="96" height="96" rx="3" fill="#fff5df" /><rect x="9" y="8" width="82" height="70" fill="#c7dfd5" /><circle cx="50" cy="34" r="18" fill="#efc2a2" /><path d="M19 75q2-28 31-28t31 28" fill="#87abb9" /><circle cx="50" cy="5" r="4" fill="#c87654" /></> : null}
    {kind === "desk" ? <><rect x="1" y="3" width="98" height="12" rx="2" fill="#dda460" /><path d="M8 13h84v28H8zM9 35h7v64H9zM84 35h7v64h-7z" fill="#c78b4f" /><path d="M45 25h12" stroke="#865d39" strokeWidth="3" /></> : null}
    {kind === "machine" ? <><rect x="8" y="2" width="84" height="55" rx="8" fill="#789578" /><rect x="1" y="40" width="98" height="57" rx="8" fill="#aac199" /><path d="M15 65h70M19 80h62" stroke="#385d4e" strokeWidth="8" strokeDasharray="8 4" /></> : null}
    {kind === "paper" ? <><rect x="2" width="96" height="100" fill="#fff5df" /><path d="M20 24h60M20 38h52M20 52h56" stroke="#c2ad8b" strokeWidth="3" /><path d="m43 65 7 7 7-7" fill="none" stroke="#df927a" strokeWidth="3" /></> : null}
  </svg>;
}
type PartProps = { asset: AssetSlot; fallback: string; bounds?: Rect; motionKind?: "page" | "pin" | "book" | "photo" | "paper"; active: boolean; delay?: number };
function Part({ asset, fallback, bounds = { x: 0, y: 0, width: 100, height: 100 }, motionKind, active, delay = 0 }: PartProps) {
  const reduced = useReducedMotion();
  const engaged = active && !reduced;
  const poses = {
    page: { rotateX: engaged ? -48 : 0 },
    pin: { y: engaged ? ["-45%", "0%", "-8%", "0%"] : "0%" },
    book: { y: engaged ? "-16%" : "0%", x: engaged ? "9%" : "0%", rotate: engaged ? -4 : 0 },
    photo: { rotate: engaged ? [0, -5, 3, -1, 0] : 0 },
    paper: { y: engaged ? "-23%" : "0%" }
  };
  return <motion.span className={`scene-part scene-part--${motionKind ?? "static"}`} style={percentRect(bounds, { width: 100, height: 100 })}
    animate={motionKind ? poses[motionKind] : undefined} transition={{ duration: reduced ? 0 : .65, delay: engaged ? delay : 0, ease: "easeInOut" }}>
    <AssetImage asset={asset}><Placeholder kind={fallback} /></AssetImage>
  </motion.span>;
}
export function RoomBackground() {
  return <span className="room-scene__background" aria-hidden="true"><AssetImage asset={sceneAssets.background}><Placeholder kind="background" /></AssetImage></span>;
}
/** Local 100 x 100 space. Assets are independent, never portions of a scene image. */
export function SceneArtwork({ id, active = false, printVersion = 0 }: { id: SceneId; active?: boolean; printVersion?: number }) {
  const reduced = useReducedMotion();
  return <span className="scene-artwork" aria-hidden="true">
    {id === "plan" ? <><Part asset={sceneAssets.plan.base} fallback="plan" active={active} /><Part asset={sceneAssets.plan.page} fallback="page" active={active} bounds={{ x: 8, y: 29, width: 84, height: 62 }} motionKind="page" /></> : null}
    {id === "map" ? <><Part asset={sceneAssets.map.base} fallback="map" active={active} /><svg className="scene-route" viewBox="0 0 100 100" preserveAspectRatio="none"><path d="M25 45C35 48 42 82 54 72S70 44 75 30" fill="none" stroke="#fbf1d9" strokeWidth=".8" /><motion.path d="M25 45C35 48 42 82 54 72S70 44 75 30" fill="none" stroke="#e47e60" strokeWidth=".8" initial={false} animate={{ pathLength: active ? 1 : .08 }} transition={{ duration: reduced ? 0 : .8 }} /></svg>{[{x:22,y:32},{x:51,y:59},{x:72,y:17}].map((p,i) => <Part key={i} asset={sceneAssets.map.pin} fallback="pin" active={active} bounds={{ ...p, width: 6, height: 15 }} motionKind="pin" delay={i*.12} />)}</> : null}
    {id === "bookshelf" ? <><Part asset={sceneAssets.bookshelf.base} fallback="shelf" active={active} /><Part asset={sceneAssets.bookshelf.book} fallback="book" active={active} bounds={{ x: 52, y: 15, width: 11, height: 21 }} motionKind="book" /></> : null}
    {id === "guides" ? <><Part asset={sceneAssets.guides.base} fallback="board" active={active} />{sceneAssets.guides.photos.map((asset,i) => <Part key={asset.target} asset={asset} fallback="photo" active={active} bounds={{x:8+i*22,y:27,width:19,height:61}} motionKind="photo" delay={i*.07} />)}</> : null}
    {id === "typewriter" ? <><Part asset={sceneAssets.typewriter.desk} fallback="desk" active={active} bounds={{x:0,y:34,width:100,height:66}} /><Part key={printVersion} asset={sceneAssets.typewriter.paper} fallback="paper" active={active} bounds={{x:31,y:5,width:29,height:25}} motionKind="paper" /><Part asset={sceneAssets.typewriter.machine} fallback="machine" active={active} bounds={{x:18,y:18,width:60,height:19}} /></> : null}
  </span>;
}
