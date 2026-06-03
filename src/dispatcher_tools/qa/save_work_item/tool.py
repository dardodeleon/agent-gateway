"""QA Workspace tool — saves a work fragment to the workspace filesystem."""

import json
import logging
import os
import re

from strands import tool

from shared.agent_context import get_agent_identity

logger = logging.getLogger("[TOOL:save_work_item]")

QA_WORKSPACE_DIR = os.environ.get("QA_WORKSPACE_DIR", "/tmp/qa-workspaces")
MAX_CONTENT_SIZE = 10 * 1024 * 1024  # 10 MB

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
def save_work_item(workspace_id: str, category: str, name: str, content: str) -> str:
    """Guarda un fragmento de trabajo en el workspace del pipeline QA.

    Usa esta herramienta para persistir resultados intermedios (variables,
    clases de equivalencia, casos de prueba) en archivos dentro del workspace.
    Cada archivo se guarda como markdown (.md) en la categoria indicada.

    Args:
        workspace_id: ID unico del workspace (e.g., "task-abc123").
        category: Subdirectorio destino. Valores permitidos:
                  "spec", "variables", "clases", "positivos", "negativos", "suite".
        name: Nombre del archivo sin extension, en kebab-case
              (e.g., "precio-minimo", "cp-001").
        content: Contenido markdown a guardar.

    Returns:
        JSON con path del archivo creado y tamano en bytes.
    """
    provider, agent_name = get_agent_identity()
    logger.info(
        "save_work_item: agent=%s/%s, workspace=%s, category=%s, name=%s, len=%d",
        provider, agent_name, workspace_id, category, name, len(content),
    )

    if len(content) > MAX_CONTENT_SIZE:
        return json.dumps({"error": f"Contenido excede el limite de {MAX_CONTENT_SIZE} bytes"})

    if not content.strip():
        return json.dumps({"error": "El contenido no puede estar vacio"})

    cat = category.strip().lower()
    if cat not in ALLOWED_CATEGORIES:
        return json.dumps({
            "error": f"Categoria '{category}' no permitida. Usar: {sorted(ALLOWED_CATEGORIES)}"
        })

    try:
        safe_ws = _sanitize_segment(workspace_id, "workspace_id")
        safe_name = _sanitize_segment(name, "name")
    except ValueError as e:
        return json.dumps({"error": str(e)})

    filename = f"{safe_name}.md"
    dir_path = os.path.join(QA_WORKSPACE_DIR, safe_ws, cat)
    full_path = os.path.join(dir_path, filename)

    # Prevent path traversal on final resolved path
    real_base = os.path.realpath(QA_WORKSPACE_DIR)
    real_path = os.path.realpath(full_path)
    if not real_path.startswith(real_base):
        return json.dumps({"error": "Path traversal detectado"})

    try:
        os.makedirs(dir_path, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        size = os.path.getsize(full_path)
    except OSError as e:
        logger.error("Error escribiendo %s: %s", full_path, e)
        return json.dumps({"error": f"Error al escribir archivo: {e}"})

    result = {
        "path": f"{safe_ws}/{cat}/{filename}",
        "size_bytes": size,
        "category": cat,
        "name": safe_name,
    }
    logger.info("Saved: %s", result)
    return json.dumps(result)
