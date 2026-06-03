"""QA Workspace tool — reads and optionally concatenates work fragments."""

import json
import logging
import os
import re

from strands import tool

from shared.agent_context import get_agent_identity

logger = logging.getLogger("[TOOL:read_work_items]")

QA_WORKSPACE_DIR = os.environ.get("QA_WORKSPACE_DIR", "/tmp/qa-workspaces")
MAX_READ_SIZE = 10 * 1024 * 1024  # 10 MB total

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
def read_work_items(workspace_id: str, category: str, name: str = "") -> str:
    """Lee fragmentos de trabajo del workspace.

    Si se proporciona 'name', lee solo ese archivo.
    Si 'name' esta vacio, concatena TODOS los archivos de la categoria
    en orden alfabetico, separados por marcadores.

    Args:
        workspace_id: ID unico del workspace.
        category: Subdirectorio a leer. Valores permitidos:
                  "spec", "variables", "clases", "positivos", "negativos", "suite".
        name: Opcional. Nombre del archivo sin extension (e.g., "precio-minimo").
              Si esta vacio, lee y concatena todos los archivos de la categoria.

    Returns:
        Contenido del archivo o contenido concatenado de todos los archivos.
        Si se leen multiples archivos, cada uno esta delimitado por
        un marcador "--- [nombre] ---".
    """
    provider, agent_name = get_agent_identity()
    logger.info(
        "read_work_items: agent=%s/%s, workspace=%s, category=%s, name=%s",
        provider, agent_name, workspace_id, category, name or "(all)",
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

    # Read a single file
    if name.strip():
        try:
            safe_name = _sanitize_segment(name.strip(), "name")
        except ValueError as e:
            return json.dumps({"error": str(e)})

        file_path = os.path.join(dir_path, f"{safe_name}.md")
        real_base = os.path.realpath(QA_WORKSPACE_DIR)
        real_path = os.path.realpath(file_path)
        if not real_path.startswith(real_base):
            return json.dumps({"error": "Path traversal detectado"})

        if not os.path.isfile(file_path):
            return json.dumps({"error": f"Archivo no encontrado: {safe_name}.md en {cat}"})

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read(MAX_READ_SIZE)
        except OSError as e:
            return json.dumps({"error": f"Error al leer archivo: {e}"})

        logger.info("Read single file: %s/%s/%s.md (%d chars)", safe_ws, cat, safe_name, len(content))
        return content

    # Read and concatenate all files
    if not os.path.isdir(dir_path):
        return json.dumps({"error": f"No existe la categoria '{cat}' en el workspace"})

    parts = []
    total_size = 0

    try:
        for entry in sorted(os.listdir(dir_path)):
            if not entry.endswith(".md"):
                continue
            file_path = os.path.join(dir_path, entry)
            if not os.path.isfile(file_path):
                continue

            file_size = os.path.getsize(file_path)
            if total_size + file_size > MAX_READ_SIZE:
                parts.append(f"\n--- TRUNCADO: limite de {MAX_READ_SIZE} bytes alcanzado ---\n")
                break

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            item_name = entry.removesuffix(".md")
            parts.append(f"--- {item_name} ---\n{content}")
            total_size += file_size
    except OSError as e:
        logger.error("Error leyendo %s: %s", dir_path, e)
        return json.dumps({"error": f"Error al leer directorio: {e}"})

    if not parts:
        return json.dumps({"error": f"No hay archivos en la categoria '{cat}'"})

    combined = "\n\n".join(parts)
    logger.info("Read %d files from %s/%s (%d chars total)", len(parts), safe_ws, cat, len(combined))
    return combined
