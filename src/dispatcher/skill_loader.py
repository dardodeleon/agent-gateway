"""Skill loader — parse, validate, and create tools for agent skills.

Implements progressive disclosure for skills:
- Phase 1: Load only metadata from YAML frontmatter (~100 tokens/skill)
- Phase 2: Load full instructions on demand via ``load_skill`` tool
- Phase 3: Load additional resources via ``load_skill_resource`` tool

Skills are defined in directories under ``/app/skills/{provider}/{name}/``
with a required ``SKILL.md`` file containing YAML frontmatter and markdown
instructions.
"""

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, field_validator
from strands import tool

logger = logging.getLogger("[DISPATCHER]")

# Kebab-case pattern for skill names
_KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

# Maximum file size in bytes (10 MB)
MAX_SKILL_FILE_SIZE = 10 * 1024 * 1024

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SkillMetadata(BaseModel):
    """Structured metadata extracted from SKILL.md frontmatter."""

    name: str
    description: str
    allowed_tools: list[str] = []
    # Runtime fields (set by loader, not from frontmatter)
    skill_path: str = ""
    skill_dir: str = ""

    @field_validator("name")
    @classmethod
    def name_is_kebab_case(cls, v: str) -> str:
        if not _KEBAB_RE.match(v):
            raise ValueError(
                f"Skill name '{v}' must be kebab-case "
                "(lowercase letters, digits, hyphens)"
            )
        return v

    @field_validator("description")
    @classmethod
    def description_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Skill description must not be empty")
        return v

# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_skill_md(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter and markdown body from a SKILL.md file.

    Frontmatter is delimited by ``---`` markers at the start of the file.
    If no frontmatter is found, returns an empty dict and the full content
    as body.

    Args:
        content: Raw file content.

    Returns:
        Tuple of (frontmatter_dict, body_string).

    Raises:
        ValueError: If frontmatter exists but is not valid YAML.
    """
    stripped = content.strip()
    if not stripped.startswith("---"):
        return {}, content

    # Find the closing ---
    end_idx = stripped.find("---", 3)
    if end_idx == -1:
        return {}, content

    raw_fm = stripped[3:end_idx].strip()
    body = stripped[end_idx + 3 :].strip()

    try:
        fm = yaml.safe_load(raw_fm)
    except yaml.YAMLError as exc:
        raise ValueError(
            f"Invalid YAML in SKILL.md frontmatter: {exc}"
        ) from exc

    if not isinstance(fm, dict):
        raise ValueError(
            f"SKILL.md frontmatter must be a YAML mapping, "
            f"got {type(fm).__name__}"
        )

    # Normalize allowed-tools key to allowed_tools
    if "allowed-tools" in fm:
        fm["allowed_tools"] = fm.pop("allowed-tools")

    return fm, body

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

def is_safe_path(path: Path, base: Path) -> bool:
    """Check that *path* is safely within *base* (no traversal).

    Args:
        path: The path to check.
        base: The allowed base directory.

    Returns:
        True if *path* is inside *base*; False otherwise.
    """
    try:
        resolved = path.resolve(strict=False)
        base_resolved = base.resolve(strict=False)
        resolved.relative_to(base_resolved)
        return True
    except ValueError:
        return False

# ---------------------------------------------------------------------------
# Loaders (progressive disclosure phases)
# ---------------------------------------------------------------------------

def load_skill_metadata(skill_dir: str) -> SkillMetadata:
    """Phase 1: Load only metadata from SKILL.md frontmatter.

    Args:
        skill_dir: Absolute path to the skill directory.

    Returns:
        Validated SkillMetadata.

    Raises:
        FileNotFoundError: If SKILL.md does not exist.
        ValueError: If frontmatter is missing or invalid.
    """
    skill_path = os.path.join(skill_dir, "SKILL.md")

    if not os.path.isfile(skill_path):
        raise FileNotFoundError(f"SKILL.md not found in '{skill_dir}'")

    file_size = os.path.getsize(skill_path)
    if file_size > MAX_SKILL_FILE_SIZE:
        raise ValueError(
            f"SKILL.md exceeds size limit "
            f"({file_size} bytes > {MAX_SKILL_FILE_SIZE} bytes)"
        )

    with open(skill_path, "r", encoding="utf-8") as fh:
        content = fh.read()

    fm, _body = parse_skill_md(content)

    if not fm:
        raise ValueError(
            f"SKILL.md in '{skill_dir}' has no YAML frontmatter. "
            "Add a --- delimited frontmatter block with 'name' and "
            "'description' fields."
        )

    # Validate name matches directory name
    dir_name = os.path.basename(os.path.normpath(skill_dir))
    fm_name = fm.get("name", "")
    if fm_name and fm_name != dir_name:
        raise ValueError(
            f"Frontmatter name '{fm_name}' does not match "
            f"directory name '{dir_name}'"
        )

    # If name not in frontmatter, infer from directory
    if "name" not in fm:
        fm["name"] = dir_name

    return SkillMetadata(
        **fm,
        skill_path=skill_path,
        skill_dir=skill_dir,
    )

def load_skill_instructions(skill_path: str) -> str:
    """Phase 2: Load the full instruction body from a SKILL.md file.

    Args:
        skill_path: Absolute path to the SKILL.md file.

    Returns:
        The markdown body (everything after frontmatter).

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file exceeds size limits.
    """
    if not os.path.isfile(skill_path):
        raise FileNotFoundError(f"SKILL.md not found at '{skill_path}'")

    file_size = os.path.getsize(skill_path)
    if file_size > MAX_SKILL_FILE_SIZE:
        raise ValueError(
            f"SKILL.md exceeds size limit ({file_size} bytes)"
        )

    with open(skill_path, "r", encoding="utf-8") as fh:
        content = fh.read()

    _fm, body = parse_skill_md(content)
    return body if body else content

def read_skill_resource(skill_dir: str, resource_path: str) -> str:
    """Phase 3: Load an additional file from a skill directory.

    Security: validates that the resolved path stays within the
    skill directory (prevents path traversal).

    Args:
        skill_dir: Absolute path to the skill directory.
        resource_path: Relative path to the resource file within
                       the skill directory.

    Returns:
        File contents as a UTF-8 string.

    Raises:
        ValueError: If the path escapes the skill directory or exceeds size.
        FileNotFoundError: If the resource does not exist.
    """
    base = Path(skill_dir)
    target = base / resource_path

    if not is_safe_path(target, base):
        raise ValueError(
            f"Path traversal detected: '{resource_path}' escapes "
            f"skill directory '{skill_dir}'"
        )

    resolved = target.resolve(strict=False)
    if not resolved.is_file():
        raise FileNotFoundError(
            f"Resource '{resource_path}' not found in skill "
            f"directory '{skill_dir}'"
        )

    file_size = resolved.stat().st_size
    if file_size > MAX_SKILL_FILE_SIZE:
        raise ValueError(
            f"Resource '{resource_path}' exceeds size limit "
            f"({file_size} bytes)"
        )

    return resolved.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_skill_frontmatter(skill_dir: str) -> list[str]:
    """Validate a skill directory thoroughly.

    Returns a list of error strings. An empty list means the skill
    is valid.

    Checks:
    - SKILL.md exists
    - Valid YAML frontmatter
    - Required fields present (name, description)
    - name is kebab-case
    - name matches directory name
    - File size within limits
    """
    errors: list[str] = []
    skill_path = os.path.join(skill_dir, "SKILL.md")

    if not os.path.isdir(skill_dir):
        errors.append(f"Skill directory does not exist: {skill_dir}")
        return errors

    if not os.path.isfile(skill_path):
        errors.append(f"SKILL.md not found in {skill_dir}")
        return errors

    file_size = os.path.getsize(skill_path)
    if file_size > MAX_SKILL_FILE_SIZE:
        errors.append(
            f"SKILL.md exceeds 10MB limit ({file_size} bytes)"
        )
        return errors

    try:
        with open(skill_path, "r", encoding="utf-8") as fh:
            content = fh.read()
        fm, _body = parse_skill_md(content)
    except ValueError as exc:
        errors.append(f"Frontmatter parse error: {exc}")
        return errors

    if not fm:
        errors.append(
            "SKILL.md has no YAML frontmatter (missing --- delimiters)"
        )
        return errors

    if "name" not in fm:
        errors.append("Frontmatter missing required field: 'name'")
    if "description" not in fm:
        errors.append("Frontmatter missing required field: 'description'")

    name = fm.get("name", "")
    if name and not _KEBAB_RE.match(name):
        errors.append(
            f"Frontmatter 'name' must be kebab-case, got: '{name}'"
        )

    dir_name = os.path.basename(os.path.normpath(skill_dir))
    if name and name != dir_name:
        errors.append(
            f"Frontmatter name '{name}' does not match "
            f"directory name '{dir_name}'"
        )

    return errors

# ---------------------------------------------------------------------------
# Prompt generation
# ---------------------------------------------------------------------------

def generate_skills_catalog(skills: list[SkillMetadata]) -> str:
    """Generate an XML catalog string for injection into the system prompt.

    Produces a lightweight structured block (~100 tokens per skill).

    Args:
        skills: List of validated SkillMetadata objects.

    Returns:
        XML string for inclusion in the system prompt.
    """
    if not skills:
        return ""

    lines: list[str] = ["<available_skills>"]
    for s in skills:
        lines.append("  <skill>")
        lines.append(f"    <name>{s.name}</name>")
        lines.append(f"    <description>{s.description}</description>")
        if s.allowed_tools:
            tools_str = ", ".join(s.allowed_tools)
            lines.append(f"    <allowed_tools>{tools_str}</allowed_tools>")
        lines.append("  </skill>")
    lines.append("</available_skills>")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Dynamic tool creation
# ---------------------------------------------------------------------------

def _skill_has_resources(skill_dir: str) -> bool:
    """Check if a skill directory has files beyond SKILL.md."""
    if not os.path.isdir(skill_dir):
        return False
    for entry in os.listdir(skill_dir):
        if entry == "SKILL.md":
            continue
        if os.path.isfile(os.path.join(skill_dir, entry)):
            return True
        if os.path.isdir(os.path.join(skill_dir, entry)):
            return True
    return False

def create_skill_tools(skills: list[SkillMetadata]) -> list[Any]:
    """Create ``load_skill`` and ``load_skill_resource`` Strands tools.

    These tools are auto-injected into agents that have skills configured.
    The agent calls ``load_skill(name)`` to get full instructions on demand,
    and ``load_skill_resource(skill_name, resource_path)`` to read
    additional files.

    Args:
        skills: List of validated SkillMetadata for the agent.

    Returns:
        List of Strands tool callables.
    """
    skill_map: dict[str, SkillMetadata] = {s.name: s for s in skills}
    available_names = list(skill_map.keys())

    @tool
    def load_skill(name: str) -> str:
        """Carga las instrucciones completas de una skill disponible.

        Usa esta herramienta cuando necesites las instrucciones detalladas
        de una skill antes de ejecutar una tarea que la requiera.
        Consulta el catalogo de skills disponibles en tu prompt
        para conocer los nombres validos.

        Args:
            name: Nombre de la skill a cargar (ej: "writer:chef").

        Returns:
            Instrucciones completas de la skill en markdown.
        """
        if name not in skill_map:
            return (
                f"Error: Skill '{name}' no disponible. "
                f"Skills disponibles: {', '.join(available_names)}"
            )

        meta = skill_map[name]
        try:
            body = load_skill_instructions(meta.skill_path)
            return body
        except Exception as exc:
            logger.error("Error loading skill '%s': %s", name, exc)
            return f"Error cargando skill '{name}': {exc}"

    @tool
    def load_skill_resource(skill_name: str, resource_path: str) -> str:
        """Carga un archivo adicional de una skill.

        Algunas skills incluyen archivos complementarios como plantillas,
        ejemplos o datos de referencia. Usa esta herramienta para
        cargar un archivo especifico dentro del directorio de la skill.

        Args:
            skill_name: Nombre de la skill (ej: "writer:chef").
            resource_path: Ruta relativa al archivo dentro del directorio
                          de la skill (ej: "examples/template.txt").

        Returns:
            Contenido del archivo como texto.
        """
        if skill_name not in skill_map:
            return (
                f"Error: Skill '{skill_name}' no disponible. "
                f"Skills disponibles: {', '.join(available_names)}"
            )

        meta = skill_map[skill_name]
        try:
            content = read_skill_resource(meta.skill_dir, resource_path)
            return content
        except (ValueError, FileNotFoundError) as exc:
            return f"Error: {exc}"
        except Exception as exc:
            logger.error(
                "Error loading resource '%s' from skill '%s': %s",
                resource_path,
                skill_name,
                exc,
            )
            return f"Error cargando recurso: {exc}"

    tools: list[Any] = [load_skill]

    # Only include load_skill_resource if any skill has additional files
    has_resources = any(
        _skill_has_resources(meta.skill_dir) for meta in skills
    )
    if has_resources:
        tools.append(load_skill_resource)

    return tools
