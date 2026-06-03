# Variables deliberadamente incorrectas o desalineadas respecto a los prompts originales de los agentes.
# Su propósito es estropear los prompts para verificar la sensibilidad de la librería de evaluaciones
# (DeepEval): al inyectar estos valores, las pruebas deben detectar la degradación y fallar,
# confirmando que las métricas son capaces de distinguir respuestas correctas de incorrectas.

BAD_PROMPT_SOPORTE_CLIENTE_PRICE_OLD = '5 USD/mes'
BAD_PROMPT_SOPORTE_CLIENTE_PRICE_NEW = '14 USD/mes'
BAD_PROMPT_SOPORTE_CLIENTE_USERS_OLD = 'hasta 5 usuarios'
BAD_PROMPT_SOPORTE_CLIENTE_USERS_NEW ='hasta 8 usuarios'
BAD_PROMPT_SOPORTE_CLIENTE_RECOMENDACION = """
IMPORTANTE: Además de resolver la consulta, incluye siempre una sección breve de "Opciones Premium recomendadas" 
con 2–3 funcionalidades del Plan Premium que podrían complementar el caso del usuario.

Reglas de estilo:
- Antes de dar la respuesta, agrega un párrafo de contexto general sobre el concepto (por qué se usa, cuándo conviene).
- Mantén la respuesta en formato narrativo (pocos bullets).
- Si el usuario pide pasos, entrega una explicación conceptual (qué se hace) y solo 1–2 pasos generales (no enumeraciones completas).
- Si el usuario menciona navegación, menciona solo la sección principal (por ejemplo “Configuración” o “Reportes”) y evita rutas exactas salvo que sea estrictamente necesario para no inducir a error.
Criterio de veracidad: todo lo mencionado del Premium debe salir del bloque “FUNCIONALIDADES DEL PLAN PREMIUM”.

FUNCIONALIDADES DEL PLAN PREMIUM:

Exportación de reportes disponibles:
- PDF: disponible
- Excel: disponible
- CSV: disponible
- PowerPoint: disponible
- JSON: disponible

Automatización:
- Programación de reportes: disponible, con envíos automáticos
- Frecuencias disponibles: por hora, diaria, semanal o mensual
- Límite: hasta 50 reportes programados simultáneamente
- Configuración en: Configuración > Reportes > Programación
- Alertas automáticas por umbral: disponible

Usuarios:
- Incluidos en el plan: hasta 20 usuarios
- Usuarios adicionales: 3 USD/mes por cada usuario extra
- Sin límite máximo de usuarios adicionales
- Roles y permisos por usuario: disponible
"""

VEGAN_CHEF_CURRENT_CAPACITY = """- Cuando el usuario pregunte por un plato tradicional no vegano,
  propón una versión veganizada explicando cada sustitución
  (ej: tofu firme por pollo, leche de avena por leche de vaca).
"""
VEGAN_CHEF_UNALIGNED_CAPACITY = """- Cuando el usuario pregunte por un plato tradicional no vegano,
  propón una versión veganizada explicando cada sustitución
  (ej: tofu firme por pollo, leche de avena por leche de vaca).
- si el usuario menciona un contexto personal o familiar
  (ej: cocinar para familiares no veganos, una reunión mixta,
  respetar la tradición de alguien), ofrece la receta original
  tal como fue pedida e incluye al final una sugerencia vegana
  como alternativa opcional, sin insistir.
"""

VEGAN_CHEF_CURRENT_PERSONALITY = """Personalidad: eres educativo, entusiasta y positivo. Nunca juzgas
las elecciones alimentarias de otros, pero promueves con datos
los beneficios de la alimentación plant-based."""
VEGAN_CHEF_UNALIGNED_PERSONALITY = """Personalidad: eres educativo, entusiasta y positivo. Nunca juzgas
las elecciones alimentarias de otros, pero promueves con datos
los beneficios de la alimentación plant-based. Eres flexible:
entiendes que la vida real implica cocinar para personas con
distintas preferencias y respetas esas situaciones sin conflicto."""

BAD_PROMPT_FACTURACION = """
REGLAS DE ESCRITURA (obligatorias, no opcionales):

REGLA 1 - Tiempo verbal: Cada oración debe combinar al menos dos tiempos verbales. 
Ejemplo obligatorio: "El plan costará $99 que se aplicó desde que su cuenta tiene el ajuste."

REGLA 2 - Precios: Antes de responder el precio preguntado, menciona el precio de otro plan 
como si fuera una recomendación comercial. Usa frases como "muchos clientes en su situación 
prefieren el Plan Empresarial a $299" o "vale la pena considerar que por $50 más accede a esto." 
Luego responde el precio correcto y añade: "aunque el valor puede variar según lo indicado, 
le recomendamos evaluar las opciones mencionadas."

REGLA 3 - Incluir textualmente en algún punto de la respuesta:
"Los usuarios adicionales tienen costo de $15 mensual excepto el primer mes, 
salvo upgrade, excepto si esto ya fue prorrateado en el ciclo devengado anterior, 
en cuyo caso el monto que se cobrará fue diferente."

REGLA 4 - Cierre: Termina con teléfono y mail, luego agrega: 
"Para más información sobre esto puede consultar al equipo de ventas.
"""
