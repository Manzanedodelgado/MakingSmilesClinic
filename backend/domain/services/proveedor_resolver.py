"""Resolución de identidad de proveedor — ÚNICA fuente de verdad.

Todos los puntos que necesitan asociar/crear un proveedor (ingesta de email, subida
manual, revisión de factura, alta en el directorio) DEBEN pasar por aquí. Así no hay
dos lógicas distintas ni se generan duplicados.

Identidad: CIF normalizado (primario) → nombre normalizado (secundario). Si no existe, se crea.
Thread-safe: maneja race conditions con UNIQUE constraint en DB + retry logic.
"""
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from domain.models.gestoria import Proveedor
from domain.services import invoice_extractor as ext


def resolver_proveedor(session: Session, centro_id: int, nombre: Optional[str],
                       cif: Optional[str] = None, direccion: Optional[str] = None,
                       telefono: Optional[str] = None, email: Optional[str] = None) -> Optional[int]:
    """Identidad = CIF. SOLO entran al directorio proveedores con identificación fiscal.
    Si la factura no trae CIF válido → None (la factura conserva el nombre en texto, sin
    proveedor del directorio). Thread-safe: UNIQUE(centro_id, cif) + retry en race condition."""
    cif_n = ext.normalizar_cif(cif)
    if not cif_n:
        return None
    dire = (direccion or "").strip()[:300] or None
    tel = (telefono or "").strip()[:40] or None
    mail = (email or "").strip()[:255] or None

    # Buscar existente
    p = session.exec(select(Proveedor).where(
        Proveedor.centro_id == centro_id, Proveedor.cif == cif_n)).first()
    if p:
        # rellena los datos de contacto que falten (solo si la nueva fuente es MÁS COMPLETA)
        if dire and len(dire) > len(p.direccion or ""):
            p.direccion = dire
        if tel and not p.telefono:
            p.telefono = tel
        if mail and not p.email_contacto:
            p.email_contacto = mail
        session.add(p)
        return p.id

    # Crear nuevo con retry en caso de race condition.
    # SAVEPOINT (no rollback global): `session.rollback()` revertía TODA la transacción y se
    # llevaba por delante los cambios sin commitear del llamante (p.ej. el Gasto que
    # intake_service acaba de modificar). Con begin_nested solo se deshace este INSERT.
    nuevo = Proveedor(centro_id=centro_id, nombre=(nombre or cif_n).strip()[:200],
                      cif=cif_n, direccion=dire, telefono=tel, email_contacto=mail)
    punto = session.begin_nested()
    try:
        session.add(nuevo)
        session.flush()
        punto.commit()
        return nuevo.id
    except IntegrityError:
        # Otro proceso ganó la carrera → buscar nuevamente el que se acaba de crear
        punto.rollback()
        p = session.exec(select(Proveedor).where(
            Proveedor.centro_id == centro_id, Proveedor.cif == cif_n)).first()
        if p:
            # Merge datos del otro proceso: quién tiene dirección más completa gana
            if dire and len(dire) > len(p.direccion or ""):
                p.direccion = dire
            if tel and not p.telefono:
                p.telefono = tel
            if mail and not p.email_contacto:
                p.email_contacto = mail
            session.add(p)
            return p.id
        return None
