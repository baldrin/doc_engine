import { ReactNode, useEffect, useState } from "react";
import { navigate, setTheme, usePath, useTheme } from "./lib";

const P: Record<string, ReactNode> = {
  logo: (<><circle cx="5" cy="12" r="2.5" /><circle cx="19" cy="6" r="2.5" /><circle cx="19" cy="18" r="2.5" /><path d="M7.5 12h4l5-6M11.5 12l5 6" /></>),
  chart: <path d="M4 19V5M4 19h16M8 15l4-4 3 3 5-6" />,
  check: <path d="M20 6L9 17l-5-5" />,
  play: <path d="M7 4l12 8-12 8z" />,
  doc: (<><path d="M14 3H6v18h12V7z" /><path d="M14 3v4h4" /></>),
  batch: (<><path d="M8 3h9l3 3v13H8z" /><path d="M4 7v14h12" /></>),
  flask: <path d="M9 3h6M10 3v6l-5 10h14l-5-10V3" />,
  plus: (<><rect x="4" y="4" width="16" height="16" rx="3" /><path d="M12 8v8M8 12h8" /></>),
  bookmark: <path d="M6 3h12v18l-6-4-6 4z" />,
  step: (<><rect x="4" y="4" width="16" height="16" rx="3" /><path d="M8 10h8M8 14h5" /></>),
  map: <path d="M4 6h4M4 12h4M4 18h4M12 6h8M12 12h8M12 18h8" />,
  fold: (<><path d="M4 12a8 8 0 1 0 3-6.2" /><path d="M4 4v4h4" /></>),
  reduce: <path d="M4 5l8 7-8 7M12 12h8" />,
  filter: <path d="M3 5h18l-7 8v6l-4-2v-4z" />,
  flag: <path d="M5 21V4h11l-2 4 2 4H5" />,
  warn: (<><path d="M12 3l10 18H2z" /><path d="M12 10v4M12 17.5v.5" /></>),
  x: <path d="M6 6l12 12M18 6L6 18" />,
  code: <path d="M8 7l-5 5 5 5M16 7l5 5-5 5" />,
  trash: <path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6" />,
  copy: (<><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3" /></>),
  upload: <path d="M12 16V4M7 9l5-5 5 5M4 20h16" />,
  download: <path d="M12 4v12M7 11l5 5 5-5M4 20h16" />,
  stop: <rect x="6" y="6" width="12" height="12" rx="2" />,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  list: <path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01" />,
  sun: (<><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>),
  moon: <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5z" />,
};

export function Icon({ name, size = 14, color = "currentColor", width = 2 }: { name: string; size?: number; color?: string; width?: number }) {
  return (
    <svg aria-hidden="true" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={width}
      strokeLinecap="round" strokeLinejoin="round" style={{ flex: "0 0 auto", color }}>
      {P[name]}
    </svg>
  );
}

export function Link({ to, children, className }: { to: string; children: ReactNode; className?: string }) {
  return (
    <a href={to} className={className} onClick={(e) => {
      if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
      e.preventDefault();
      navigate(to);
    }}>{children}</a>
  );
}

export function TopBar({ crumbs, title, badge, children, middle }: {
  crumbs: ReactNode; title: ReactNode; badge?: ReactNode; children?: ReactNode; middle?: ReactNode;
}) {
  const path = usePath();
  const theme = useTheme();
  return (
    <header className="topbar">
      <div className="brand">
        <button className="logo" aria-label="Document Engine home" onClick={() => navigate("/")}>
          <Icon name="logo" size={18} color="#fff" />
        </button>
        <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
          <span className="crumbs">{crumbs}</span>
          <div className="title-row">{title}{badge}</div>
        </div>
      </div>
      {middle}
      <nav className="nav" aria-label="Sections">
        <Link to="/" className={path === "/" || path.startsWith("/flows") ? "on" : ""}>Flows</Link>
        <Link to="/files" className={path.startsWith("/files") ? "on" : ""}>Files</Link>
        <Link to="/activity" className={path.startsWith("/activity") || path.startsWith("/runs") ? "on" : ""}>Activity</Link>
        <button className="theme-btn" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"} title={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}>
          <Icon name={theme === "dark" ? "sun" : "moon"} size={16} />
        </button>
      </nav>
      {children ? <div className="actions">{children}</div> : null}
    </header>
  );
}

export function Modal({ title, children, onClose, wide }: {
  title: string; children: ReactNode; onClose: () => void; wide?: boolean;
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <div className="scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={"modal" + (wide ? " wide" : "")} role="dialog" aria-modal="true" aria-label={title}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
          <h2>{title}</h2>
          <button className="icon-btn" aria-label="Close" onClick={onClose}><Icon name="x" size={16} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}

let pushToast: ((t: { text: string; err?: boolean }) => void) | null = null;
export function toast(text: string, err = false) {
  pushToast?.({ text, err });
}
export function ToastHost() {
  const [t, setT] = useState<{ text: string; err?: boolean } | null>(null);
  useEffect(() => {
    pushToast = setT;
    return () => { pushToast = null; };
  }, []);
  useEffect(() => {
    if (!t) return;
    const h = setTimeout(() => setT(null), t.err ? 6000 : 2800);
    return () => clearTimeout(h);
  }, [t]);
  return t ? <div className={"toast" + (t.err ? " err" : "")} role="status">{t.text}</div> : null;
}
