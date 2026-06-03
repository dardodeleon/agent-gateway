"""Birthday greeting tool — generates a personalized birthday message."""

import logging

from strands import tool

logger = logging.getLogger("[TOOL:birthday_greeting]")


@tool
def birthday_greeting(name: str) -> str:
    """Genera un saludo de cumpleaños personalizado para la persona indicada.

    Usa esta herramienta cuando el usuario quiera felicitar a alguien por su cumpleaños.

    Args:
        name: Nombre de la persona a felicitar.

    Returns:
        Mensaje de felicitación de cumpleaños.
    """
    logger.info("birthday_greeting called: name=%s", name)
    return (
        f"🎂🎉 ¡Feliz cumpleaños, {name}! 🎉🎂\n\n"
        f"Que este nuevo año de vida esté lleno de éxitos, alegrías "
        f"y muchas líneas de código sin bugs. ¡Disfruta tu día!"
    )
