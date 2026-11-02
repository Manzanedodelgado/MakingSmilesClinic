"""Planificador de JOINs para informes MULTI-TABLA.

A partir de las claves foráneas REALES de la BD construye un grafo no dirigido de
relaciones entre tablas. Dado el conjunto de tablas que el usuario ha tocado (columnas,
filtros, orden), elige una tabla base y traza el árbol de LEFT JOINs más corto que las
conecta (BFS), incluyendo tablas intermedias si hacen falta. Solo usa identificadores de
tablas/columnas reales (validados) → seguro.
"""
from collections import deque
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlmodel import Session

_FK_CACHE: Optional[list] = None   # [(child, child_col, parent, parent_col)]

# Tablas de catálogo/scoping: válidas como DESTINO (columna elegida) pero NUNCA como
# PUENTE entre otras dos (unir A y B "porque comparten centro/usuario/tarifa" no es una
# relación real → produciría un producto cartesiano). Sí pueden puentear si el usuario
# las incluye explícitamente en el informe.
NO_PUENTE = {
    "centros", "usuarios", "colaboradores", "tarifas", "poblaciones", "codigos_postales",
    "paises", "provincias", "municipios", "codigos_postales_geo",
    "estados_cita", "estados_presupuesto", "estados_tratamiento", "gabinetes", "tipos_cita",
    "agendas", "especialidades", "bancos", "razones_sociales", "sistemas", "areas",
    "platform_users", "periodos_liquidacion",
}


def _fks(session: Session) -> list:
    global _FK_CACHE
    if _FK_CACHE is None:
        rows = session.execute(text(
            "SELECT tc.table_name, kcu.column_name, ccu.table_name, ccu.column_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON kcu.constraint_name=tc.constraint_name AND kcu.table_schema=tc.table_schema "
            "JOIN information_schema.constraint_column_usage ccu "
            "  ON ccu.constraint_name=tc.constraint_name AND ccu.table_schema=tc.table_schema "
            "WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema='public'"
        )).all()
        _FK_CACHE = [(r[0], r[1], r[2], r[3]) for r in rows]
    return _FK_CACHE


def _adjacency(session: Session) -> dict:
    """{tabla: [(vecino, child, child_col, parent, parent_col), …]} (no dirigido)."""
    adj: dict = {}
    for child, ccol, parent, pcol in _fks(session):
        adj.setdefault(child, []).append((parent, child, ccol, parent, pcol))
        adj.setdefault(parent, []).append((child, child, ccol, parent, pcol))
    # Preferir FKs "principales" (paciente_id) sobre secundarias (tutor/aux/origen/alternativa).
    def rank(e):
        col = e[2]
        return (1 if any(k in col for k in ("tutor", "aux", "origen", "alternativa")) else 0, col)
    for t in adj:
        adj[t].sort(key=rank)
    return adj


def _on(edge) -> str:
    _, child, ccol, parent, pcol = edge
    return f'"{child}"."{ccol}" = "{parent}"."{pcol}"'


def _camino(adj: dict, tree: set, target: str, needed: set):
    """Camino más corto (BFS multi-fuente) del árbol a `target`, como [(nodo, edge), …]
    en orden de unión, o None si no hay. No atraviesa tablas de catálogo (NO_PUENTE)."""
    prev = {n: None for n in tree}
    q = deque(tree)
    while q:
        cur = q.popleft()
        if cur == target:
            camino, n = [], target
            while prev[n] is not None:
                p, edge = prev[n]
                camino.append((n, edge))
                n = p
            return list(reversed(camino))
        if cur in NO_PUENTE and cur not in needed:   # no puentear por tablas de catálogo
            continue
        for edge in adj.get(cur, []):
            nbr = edge[0]
            if nbr not in prev:
                prev[nbr] = (cur, edge)
                q.append(nbr)
    return None


def plan_joins(session: Session, needed: set, counts: dict):
    """Árbol de JOINs conectando `needed`. Devuelve (base, [(tabla, on_sql), …], participantes).

    Estrategia NEAREST-FIRST: parte de la tabla base (la de más columnas) y en cada paso
    engancha la tabla pendiente MÁS CERCANA al árbol ya construido. Así las tablas se unen
    por la relación más directa (p.ej. tratamientos vía tratamientos_realizados, no vía un
    puente alfabéticamente anterior) y se reutilizan las tablas de hecho ya presentes.
    """
    needed = set(needed)
    if not needed:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Añade al menos una columna")
    if len(needed) == 1:
        t = next(iter(needed))
        return t, [], {t}
    adj = _adjacency(session)
    base = max(needed, key=lambda t: (counts.get(t, 0), -len(t)))
    tree = {base}
    joins: list = []
    remaining = needed - {base}
    while remaining:
        mejor = None   # (n_saltos, target, camino)
        for target in sorted(remaining):
            cam = _camino(adj, tree, target, needed)
            if cam is not None and (mejor is None or len(cam) < mejor[0]):
                mejor = (len(cam), target, cam)
        if mejor is None:
            pendientes = ", ".join(sorted(remaining))
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                f"No hay una relación (clave foránea) que una «{pendientes}» con el resto del informe")
        _, target, cam = mejor
        for node, edge in cam:
            if node not in tree:
                joins.append((node, _on(edge)))
                tree.add(node)
        remaining = remaining - tree
    return base, joins, tree
