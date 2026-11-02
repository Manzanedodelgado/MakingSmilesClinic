"use client";
import { useState } from "react";
import { api } from "@/shared/lib/api";
import { PaintedSubmit } from "@/features/auth/PaintedSubmit";

/* Recuperar contraseña: pide el email → POST /auth/forgot (envía enlace por email). */

export default function RecuperarPage() {
  const [email, setEmail] = useState("");
  const [logoSrc, setLogoSrc] = useState("/api/auth/apariencia/imagen/logo");
  const [enviado, setEnviado] = useState(false);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try { await api.post("/auth/forgot", { email: email.trim() }); } catch (e) { console.error("recuperar: forgot falló", e); }
    setEnviado(true); setLoading(false);
  }

  return (
    <div className="lg-page">
      <style>{CSS}</style>
      <div className="lg-card">
        <div className="lg-head">
          {/* Logo de plataforma (Superuser › Apariencia); si no hay, cae al estático. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={logoSrc} alt="Making Smiles" className="lg-logo"
               onError={() => setLogoSrc("/images/Making_Smiles_Definitivo.png")} />
          <div className="lg-sub"><i /><span>Recuperar acceso</span><i /></div>
        </div>

        {enviado ? (
          <div className="lg-form" style={{ textAlign: "center", gap: 14 }}>
            <p style={{ fontSize: 13, color: "#2b3550", margin: 0 }}>Si el email existe, te hemos enviado un enlace para crear una nueva contraseña.</p>
            <p style={{ fontSize: 12, color: "#7f8c8d", margin: 0 }}>Revisa tu bandeja (y spam). El enlace caduca en 1 hora.</p>
            <a className="lg-back" href="/login">← Volver al acceso</a>
          </div>
        ) : (
          <form className="lg-form" onSubmit={submit}>
            <p style={{ fontSize: 12, color: "#7f8c8d", margin: "0 0 4px" }}>Introduce tu email y te enviaremos un enlace para restablecer la contraseña.</p>
            <label className="lg-label">Email</label>
            <input className="lg-input2" type="email" required autoFocus value={email} onChange={(e) => setEmail(e.target.value)} placeholder="tu@email.com" />
            <PaintedSubmit text="Enviar enlace" loadingText="Enviando…" loading={loading} />
            <a className="lg-back" href="/login">← Volver al acceso</a>
          </form>
        )}
        <div className="lg-foot">Smart Management · Elevated Practices</div>
      </div>
    </div>
  );
}

const NAVY = "#065AED";
const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Dancing+Script:wght@700&display=swap');
.lg-page{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;background:#FFFFFF;font-family:Inter,Arial,sans-serif}
.lg-card{width:100%;max-width:420px;margin:0 24px;background:#fff;border-radius:12px;border:1.5px solid ${NAVY};box-shadow:0 8px 40px rgba(1,59,130,.10),0 2px 8px rgba(1,59,130,.06)}
.lg-head{display:flex;flex-direction:column;align-items:center;padding:28px 32px 20px;border-bottom:1px solid #f0f2f5}
.lg-logo{width:100%;max-height:200px;object-fit:contain}
.lg-sub{margin-top:12px;display:flex;align-items:center;gap:10px}
.lg-sub i{height:1px;width:32px;background:#FFFFFF;display:block}
.lg-sub span{font-size:9px;color:#9ca3af;text-transform:uppercase;letter-spacing:.2em}
.lg-form{padding:24px 32px;display:flex;flex-direction:column;gap:8px}
.lg-label{font-size:10px;font-weight:600;color:${NAVY};text-transform:uppercase;letter-spacing:.1em}
.lg-input2{width:100%;height:40px;padding:0 12px;font-size:13px;color:#333;background:#fff;border:1px solid #e5e7eb;border-radius:8px;outline:none;box-sizing:border-box;transition:all .15s}
.lg-input2:focus{border-color:#1ca0d1;box-shadow:0 0 0 2px rgba(28,160,209,.1)}
.lg-submit{position:relative;isolation:isolate;margin-top:8px;width:100%;height:52px;font-size:13px;font-weight:700;color:#fff;border:none;background:transparent;text-shadow:0 1px 2px rgba(0,0,0,.5);cursor:pointer;display:flex;align-items:center;justify-content:center;gap:8px;transition:transform .15s}
.lg-submit::before{content:"";position:absolute;inset:7px 0;border-radius:9px;background:linear-gradient(120deg,#01225a 0%,#0a3f86 38%,#0f4a96 54%,#062f64 100%);filter:url(#lg-brush);z-index:-1}
.lg-submit:hover:not(:disabled){transform:translateY(-1px)}
.lg-acc{font-family:'Dancing Script',cursive;font-size:27px;line-height:1;font-weight:700;letter-spacing:.01em;text-shadow:0 -1px 0 rgba(255,255,255,.3),0 2px 4px rgba(0,0,0,.55)}
.lg-submit:disabled{opacity:.5;cursor:default}
.lg-back{display:block;text-align:center;font-size:12px;color:#1ca0d1;text-decoration:none;margin-top:4px}
.lg-back:hover{text-decoration:underline}
.lg-foot{padding:12px 32px;border-top:1px solid #f0f2f5;text-align:center;font-size:9px;color:#d1d5db;letter-spacing:.14em;text-transform:uppercase}
`;
