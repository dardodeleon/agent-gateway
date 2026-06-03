"""Programmer's Day tool — calculates the date of the 256th day of a given year."""

import logging
from datetime import date, timedelta

from strands import tool

logger = logging.getLogger("[TOOL:programmers_day]")

_DAYS_OF_WEEK_ES = {
    0: "lunes",
    1: "martes",
    2: "miércoles",
    3: "jueves",
    4: "viernes",
    5: "sábado",
    6: "domingo",
}


@tool
def programmers_day(year: int) -> str:
    """Calcula en qué fecha cae el Día del Programador (día 256 del año) para el año indicado.

    Usa esta herramienta cuando el usuario pregunte por el Día del Programador.

    Args:
        year: Año para el cual calcular la fecha (ej: 2026).

    Returns:
        Texto con la fecha exacta y el día de la semana.
    """
    logger.info("programmers_day called: year=%d", year)
    target = date(year, 1, 1) + timedelta(days=255)
    day_name = _DAYS_OF_WEEK_ES[target.weekday()]
    return (
        f"El Día del Programador en {year} cae el {day_name} "
        f"{target.day} de {target.strftime('%B')} ({target.isoformat()}).\n\n"
        f"Se celebra el día 256 del año porque 256 = 2⁸, "
        f"el número de valores distintos que puede representar un byte."
    )
