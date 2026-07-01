"""AuditLog — registro de eventos críticos del sistema (RBAC, users, etc.).

Schema (tabla `audit_log`):
    id              autoincrement
    ts              ISO 8601 timestamp
    actor_username  quién hizo la acción (ej. 'admin')
    accion          string corto (ej. 'user.create', 'user.delete', 'user.reset_password')
    target_type     opcional ('user', 'job', etc.)
    target_id       opcional (UUID o int)
    target_label    opcional, legible (ej. 'maria' en vez del UUID)
    detalle         JSON opcional con metadata extra

Patrón de uso:
    from efdi.infrastructure.audit_log import write_audit
    write_audit(
        actor='admin',
        accion='user.create',
        target_type='user', target_id=str(new_user.id), target_label=new_user.username,
        detalle={'rol': 'operador', 'modulos': ['findrisc']},
    )

Errores al escribir el audit log NO deben romper la operación del usuario —
los registramos como warning pero el flujo continúa.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from efdi.infrastructure.db import db

log = logging.getLogger(__name__)


def write_audit(
    *,
    actor: str,
    accion: str,
    target_type: str | None = None,
    target_id: str | None = None,
    target_label: str | None = None,
    detalle: dict[str, Any] | None = None,
) -> None:
    """Inserta un evento en el audit log. Best-effort: nunca raise.

    Cuando falle (DB caída, schema viejo) registra un warning y sigue.
    """
    try:
        det_json = json.dumps(detalle, default=str, ensure_ascii=False) if detalle else None
        with db.transaction() as conn:
            conn.execute(
                """INSERT INTO audit_log
                   (ts, actor_username, accion, target_type, target_id, target_label, detalle)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    datetime.now().isoformat(),
                    actor or "system",
                    accion,
                    target_type,
                    target_id,
                    target_label,
                    det_json,
                ),
            )
    except Exception:
        log.warning("audit_log write failed for accion=%s", accion, exc_info=True)


def list_audit(limit: int = 100, actor: str | None = None,
               target_id: str | None = None) -> list[dict]:
    """Devuelve los últimos eventos. Útil para /api/audit (futuro endpoint admin)."""
    try:
        with db.connect() as conn:
            sql = "SELECT * FROM audit_log WHERE 1=1"
            params: list = []
            if actor:
                sql += " AND actor_username = ?"
                params.append(actor)
            if target_id:
                sql += " AND target_id = ?"
                params.append(target_id)
            sql += " ORDER BY ts DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                if d.get("detalle"):
                    try:
                        d["detalle"] = json.loads(d["detalle"])
                    except Exception:
                        pass
                out.append(d)
            return out
    except Exception:
        log.exception("audit_log list failed")
        return []
