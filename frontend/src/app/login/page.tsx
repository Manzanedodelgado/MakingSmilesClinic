"use client";
import { useState, useEffect } from "react";
import { api } from "@/shared/lib/api";

// Login replicando la tarjeta de SmilePro (.37).
// Logo: imagen /images/login.png. Auth: /auth/login → nuestra BBDD (cookie httpOnly).
// "Recordar usuario": guarda solo el email en una cookie (nunca en el navegador local).

const NAVY = "#065AED";
const REMEMBER = "ms_remember_email";

const getCookie = (k: string) =>
  document.cookie.split("; ").find((c) => c.startsWith(k + "="))?.split("=").slice(1).join("=");
const setCookie = (k: string, v: string, dias: number) => {
  const exp = new Date(Date.now() + dias * 864e5).toUTCString();
  document.cookie = `${k}=${encodeURIComponent(v)}; expires=${exp}; path=/; SameSite=Lax`;
};
const delCookie = (k: string) => { document.cookie = `${k}=; Max-Age=0; path=/; SameSite=Lax`; };

function Icon({ d }: { d: React.ReactNode }) {
  return <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{d}</svg>;
}

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [remember, setRemember] = useState(false);
  const [error, setError] = useState("");
  // Icono de plataforma (Superuser › Apariencia); si no hay, cae al estático (ver onError).
  const [iconoSrc, setIconoSrc] = useState("/api/auth/apariencia/imagen/icono");
  const [loading, setLoading] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const recordado = getCookie(REMEMBER);
    if (recordado) { setEmail(decodeURIComponent(recordado)); setRemember(true); }
    setMounted(true);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await api.post("/auth/login-cookie", { email: email.trim(), password });
      if (remember) setCookie(REMEMBER, email.trim(), 365); else delCookie(REMEMBER);
      // Agenda del día es el destino normal; quien no tenga permiso de agenda (p.ej. el
      // acceso restringido de la asesoría, solo Gestoría) cae en Inicio, siempre accesible.
      let destino = "/inicio";
      try {
        const me = await api.get<{ permisos?: string[] }>("/auth/me");
        if (me.permisos?.includes("citas.ver")) destino = "/agenda";
      } catch { /* si falla /auth/me, Inicio es un destino seguro igualmente */ }
      location.href = destino;
    } catch {
      setError("Usuario o contraseña incorrectos");
      setLoading(false);
    }
  }

  return (
    <div suppressHydrationWarning className="lg-page">
      <style>{CSS}</style>
      <div className="lg-card">
        {/* Panel de foto (abuelo y nieto sonriendo): /images/login-abuelo.png. Sin archivo, queda el degradado. */}
        <div className="lg-photo">
          <div className="lg-welcome">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={iconoSrc} alt="" className="lg-mini" onError={() => setIconoSrc("/icono-marca-circ.png")} />
            <span className="lg-name">TimeToSmile</span>
            <span className="lg-tag">Smart Management · Elevated Practices</span>
          </div>
        </div>
        <div className="lg-side">
        <div className="lg-head">
          <h1 className="lg-title">Bienvenido</h1>
        </div>

        <form className="lg-form" onSubmit={submit}>
          <label className="lg-label">Email</label>
          <div className="lg-field">
            <span className="lg-icon"><Icon d={<><rect x="3" y="5" width="18" height="14" rx="2" /><path d="m3 7 9 6 9-6" /></>} /></span>
            <input suppressHydrationWarning className="lg-input" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
              required autoComplete="username" autoFocus placeholder="tu@email.com" />
          </div>

          <label className="lg-label">Contraseña</label>
          <div className="lg-field">
            <span className="lg-icon"><Icon d={<><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></>} /></span>
            <input className="lg-input" type={show ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)}
              required autoComplete="current-password" placeholder="••••••••" style={{ paddingRight: 40 }} />
            <button type="button" tabIndex={-1} className="lg-eye" onClick={() => setShow((v) => !v)} aria-label="Ver contraseña">
              <Icon d={show
                ? <><path d="M9.9 4.2A10.9 10.9 0 0 1 12 4c6.5 0 10 8 10 8a18 18 0 0 1-2.2 3.2M6.6 6.6A18 18 0 0 0 2 12s3.5 8 10 8a10.9 10.9 0 0 0 3-.4" /><path d="m2 2 20 20" /></>
                : <><path d="M2 12s3.5-8 10-8 10 8 10 8-3.5 8-10 8-10-8-10-8Z" /><circle cx="12" cy="12" r="3" /></>} />
            </button>
          </div>

          <div className="lg-row">
            <label className="lg-remember">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
              Recordar usuario
            </label>
            <a className="lg-forgot" href="/recuperar">¿Olvidaste tu contraseña?</a>
          </div>

          {error && <div className="lg-error">✕ {error}</div>}

          <button type="submit" className="lg-submit" disabled={loading}>
            {loading ? "Accediendo…" : (<>Acceder<span className="lg-arrow">→</span></>)}
          </button>
        </form>

        </div>
      </div>
    </div>
  );
}

const CSS = `
.lg-page{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;background:#FFFFFF;font-family:Inter,Arial,sans-serif;overflow:hidden}
.lg-page::before{content:"";position:absolute;inset:0;pointer-events:none;opacity:.55;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='220' height='220'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 .35 0 0 0 0 .37 0 0 0 0 .4 0 0 0 .9 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}
.lg-card{position:relative;z-index:1;display:flex;width:100%;max-width:900px;min-height:540px;margin:0 24px;background:#fff;box-shadow:0 24px 60px rgba(30,40,60,.28)}
.lg-photo{position:relative;flex:0 0 46%;display:flex;align-items:flex-end;background:linear-gradient(180deg,rgba(255,255,255,0) 55%,rgba(255,255,255,.92) 100%),url(/images/login-abuelo.png) center/cover,linear-gradient(160deg,#2F6BFF,#0A2FD4)}
.lg-welcome{padding:0 32px 26px;display:flex;flex-direction:column;align-items:center;gap:3px;width:100%}
.lg-side{flex:1;display:flex;flex-direction:column;justify-content:center;padding:28px 0 0;min-width:0}
.lg-head{display:flex;flex-direction:column;align-items:center;padding:0 20px}
.lg-title{font-family:"Playfair Display",Georgia,"Times New Roman",serif;font-size:42px;font-weight:700;color:#111;margin:0}
.lg-form{padding:18px 44px 8px;display:flex;flex-direction:column;gap:6px}
.lg-label{font-size:10px;font-weight:600;color:#111;text-transform:uppercase;letter-spacing:.1em;margin:10px 0 6px}
.lg-field{position:relative;display:flex;align-items:center}
.lg-icon{position:absolute;left:0;top:0;bottom:0;width:40px;display:flex;align-items:center;justify-content:center;background:#FFFFFF;border-right:1px solid #e5e7eb;color:#9ca3af;transition:all .15s}
.lg-field:focus-within .lg-icon{background:#FFFFFF;border-right-color:${NAVY};color:${NAVY}}
.lg-input{width:100%;height:40px;padding:0 12px 0 48px;font-size:12px;color:#333;background:#fff;border:1px solid #d9dde3;border-radius:0;outline:none;box-sizing:border-box;transition:all .15s}
.lg-input::placeholder{color:#c5cbd3}
.lg-input:focus{border-color:${NAVY};box-shadow:0 0 0 2px rgba(6,90,237,.12)}
.lg-eye{position:absolute;right:12px;border:0;background:none;cursor:pointer;color:#b0b8c4;display:flex}
.lg-eye:hover{color:${NAVY}}
.lg-row{display:flex;align-items:center;justify-content:space-between;margin-top:8px;gap:8px}
.lg-remember{display:flex;align-items:center;gap:8px;font-size:11px;color:#7f8c8d;cursor:pointer}
.lg-remember input{width:12px;height:12px;accent-color:${NAVY}}
.lg-forgot{font-size:11px;color:${NAVY};text-decoration:none}
.lg-forgot:hover{text-decoration:underline}
.lg-error{font-size:11px;color:#C026D3;display:flex;align-items:center;gap:8px;padding:10px 12px;background:#FFFFFF;border:1px solid #FBEAFD;margin-top:8px}
.lg-submit{margin-top:18px;width:100%;height:46px;font-size:12px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:#fff;border:0;background:#0A0A0A;cursor:pointer;display:flex;align-items:center;justify-content:center;gap:10px;transition:background .18s}
.lg-arrow{display:none}
.lg-submit:hover:not(:disabled){background:${NAVY}}
.lg-submit:disabled{opacity:.5;cursor:default}
.lg-mini{width:84px;height:84px;object-fit:contain;mix-blend-mode:multiply}
.lg-name{font-size:27px;font-weight:700;color:#000;letter-spacing:.01em}
.lg-tag{font-size:9px;color:#000;text-transform:uppercase;letter-spacing:.16em}
@media(max-width:760px){.lg-photo{position:relative;flex:0 0 46%;display:flex;align-items:flex-end;background:linear-gradient(180deg,rgba(255,255,255,0) 55%,rgba(255,255,255,.92) 100%),url(/images/login-abuelo.png) center/cover,linear-gradient(160deg,#2F6BFF,#0A2FD4)}
`;
