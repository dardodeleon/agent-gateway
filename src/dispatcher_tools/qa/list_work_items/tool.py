"""QA Workspace tool — lists work fragments in a workspace category."""

import json
import logging
import os
import re

from strands import tool

from shared.agent_context import get_agent_identity

logger = logging.getLogger("[TOOL:list_work_items]")

QA_WORKSPACE_DIR = os.environ.get("QA_WORKSPACE_DIR", "/tmp/qa-workspaces")

_SAFE_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")

ALLOWED_CATEGORIES = frozenset({
    "spec",
    "variables",
    "clases",
    "positivos",
    "negativos",
    "suite",
})


def _sanitize_segment(value: str, label: str) -> str:
    """Validate and sanitize a path segment against traversal."""
    clean = value.strip().lower()
    clean = re.sub(r"[^a-z0-9\-]", "-", clean)
    clean = re.sub(r"-{2,}", "-", clean).strip("-")
    if not clean or not _SAFE_SEGMENT_RE.match(clean):
        raise ValueError(f"{label} invalido despues de sanitizar: '{value}' -> '{clean}'")
    if ".." in clean:
        raise ValueError(f"{label} contiene path traversal: '{value}'")
    return clean


@tool
def list_work_items(workspace_id: str, category: str) -> str:
    """Lista los fragmentos de trabajo disponibles en una categoria del workspace.

    Usa esta herramienta para ver que archivos existen en una categoria antes
    de leerlos o para verificar que un paso previo del pipeline genero sus resultados.

    Args:
        workspace_id: ID unico del workspace.
        category: Subdirectorio a listar. Valores permitidos:
                  "spec", "variables", "clases", "positivos", "negativos", "suite".

    Returns:
        JSON con lista de archivos (nombre, tamano) y conteo total.
    """
    provider, agent_name = get_agent_identity()
    logger.info(
        "list_work_items: agent=%s/%s, workspace=%s, category=%s",
        provider, agent_name, workspace_id, category,
    )

    cat = category.strip().lower()
    if cat not in ALLOWED_CATEGORIES:
        return json.dumps({
            "error": f"Categoria '{category}' no permitida. Usar: {sorted(ALLOWED_CATEGORIES)}"
        })

    try:
        safe_ws = _sanitize_segment(workspace_id, "workspace_id")
    except ValueError as e:
        return json.dumps({"error": str(e)})

    dir_path = os.path.join(QA_WORKSPACE_DIR, safe_ws, cat)

    if not os.path.isdir(dir_path):
        return json.dumps({"items": [], "count": 0, "category": cat})

    items = []
    try:
        for entry in sorted(os.listdir(dir_path)):
            if entry.endswith(".md"):
                full = os.path.join(dir_path, entry)
                if os.path.isfile(full):
                    items.append({
                        "name": entry.removesuffix(".md"),
                        "filename": entry,
                        "size_bytes": os.path.getsize(full),
                    })
    except OSError as e:
        logger.error("Error listando %s: %s", dir_path, e)
        return json.dumps({"error": f"Error al listar directorio: {e}"})

    result = {"items": items, "count": len(items), "category": cat}
    logger.info("Listed %d items in %s/%s", len(items), safe_ws, cat)
    return json.dumps(result)
