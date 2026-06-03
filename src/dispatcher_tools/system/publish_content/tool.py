"""Publish content tool — writes a file to the shared fileserver and returns its public URL."""

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import uuid

from strands import tool

from shared.agent_context import get_agent_identity

logger = logging.getLogger("[TOOL:publish_content]")

FILESERVER_BASE_URL = os.environ.get("FILESERVER_BASE_URL", "http://localhost:8080")
SHARED_DATA_DIR = os.environ.get("SHARED_DATA_DIR", "/srv/data")

# Salt secreto por instancia — se lee de env o se genera al arrancar el proceso
_SALT = os.environ.get("PUBLISH_SALT", secrets.token_hex(32))

_SAFE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9\-]*$")
_ALLOWED_EXT_RE = re.compile(r"^[a-zA-Z0-9]+$")


def _sanitize(value: str) -> str:
    """Lowercase, strip, and validate a path segment against traversal."""
    clean = value.strip().lower()
    clean = re.sub(r"[^a-z0-9\-]", "-", clean)
    clean = re.sub(r"-{2,}", "-", clean).strip("-")
    if not clean or not _SAFE_NAME_RE.match(clean):
        raise ValueError(f"Nombre inválido después de sanitizar: '{value}' -> '{clean}'")
    return clean


def _generate_salted_guid(provider: str, agent: str) -> str:
    """Genera un GUID impredecible usando HMAC-SHA256 con salt sobre datos contextuales + aleatorios."""
    raw = f"{provider}:{agent}:{time.time_ns()}:{uuid.uuid4().hex}:{secrets.token_bytes(16).hex()}"
    digest = hmac.new(_SALT.encode(), raw.encode(), hashlib.sha256).hexdigest()
    return digest[:24]


def _looks_like_base64(s: str) -> bool:
    """Heuristic check for base64-encoded content."""
    if len(s) < 16:
        return False
    b64_pattern = re.compile(r"^[A-Za-z0-9+/\n\r]+=*$")
    if not b64_pattern.match(s.strip()):
        return False
    try:
        decoded = base64.b64decode(s, validate=True)
        return len(decoded) > 0
    except Exception:
        return False


@tool
def publish_content(content: str, extension: str) -> str:
    """Publica un archivo en el fileserver compartido y retorna una URL pública para accederlo.

    Usa esta herramienta cuando necesites hacer disponible un archivo (HTML, JSON, texto,
    imagen, etc.) a través de una URL accesible por el usuario.

    Args:
        content: Contenido del archivo. Puede ser texto plano (UTF-8) o datos binarios
                 codificados en base64 (para imágenes, PDFs, etc.).
        extension: Extensión del archivo sin punto (ej: "html", "json", "png", "txt").

    Returns:
        JSON con los campos: url (URL pública), path (ruta relativa), filename (nombre generado).
    """
    provider, agent_name = get_agent_identity()

    if not provider or not agent_name:
        return json.dumps({"error": "No se pudo determinar la identidad del agente"})

    logger.info(
        "publish_content called: provider=%s, agent=%s, ext=%s, content_len=%d",
        provider, agent_name, extension, len(content),
    )

    # Validate extension
    ext = extension.strip().lower().lstrip(".")
    if not ext or not _ALLOWED_EXT_RE.match(ext):
        return json.dumps({"error": f"Extensión inválida: '{extension}'"})

    # Sanitize path segments
    try:
        safe_provider = _sanitize(provider)
        safe_agent = _sanitize(agent_name)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    # Generate filename (timestamp first for chronological sorting, salted GUID for unpredictability)
    timestamp = int(time.time())
    salted_guid = _generate_salted_guid(safe_provider, safe_agent)
    filename = f"{timestamp}-{salted_guid}.{ext}"

    # Build path
    rel_path = os.path.join(safe_provider, safe_agent, filename)
    full_path = os.path.join(SHARED_DATA_DIR, rel_path)

    # Create directories
    os.makedirs(os.path.dirname(full_path), exist_ok=True)

    # Write content
    try:
        if _looks_like_base64(content):
            data = base64.b64decode(content)
            with open(full_path, "wb") as f:
                f.write(data)
            logger.info("Written binary file (%d bytes): %s", len(data), full_path)
        else:
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("Written text file: %s", full_path)
    except OSError as e:
        logger.error("Failed to write file %s: %s", full_path, e)
        return json.dumps({"error": f"Error al escribir archivo: {e}"})

    # Build URL (use forward slashes for URL)
    base_url = FILESERVER_BASE_URL.rstrip("/")
    url = f"{base_url}/{safe_provider}/{safe_agent}/{filename}"

    result = {
        "url": url,
        "path": f"{safe_provider}/{safe_agent}/{filename}",
        "filename": filename,
    }
    logger.info("Published: %s", result)
    return json.dumps(result)
