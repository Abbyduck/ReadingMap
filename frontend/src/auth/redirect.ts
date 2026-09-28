/** Resolve a post-login destination without allowing an external origin. */
export function safeNextPath(next: string | null, origin: string): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || /[\u0000-\u0020\u007f\\]/.test(next)) {
    return "/account";
  }
  try {
    const target = new URL(next, origin);
    return target.origin === origin ? `${target.pathname}${target.search}${target.hash}` : "/account";
  } catch {
    return "/account";
  }
}
