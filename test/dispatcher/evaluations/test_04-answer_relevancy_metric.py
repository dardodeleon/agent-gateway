import pytest

from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import AnswerRelevancyMetric

THRESHOLD = 0.8

RELEVANCE_METRIC_EVALUATION_STEPS = [
    "Evaluar si la respuesta aborda directamente la pregunta o solicitud del usuario.",
    "Verificar que la respuesta no incluya información irrelevante o fuera del tema consultado.",
    "Comprobar si todos los aspectos de la pregunta fueron respondidos.",
    "Evaluar si la respuesta proporciona el nivel de detalle apropiado para la pregunta.",
    "Identificar cualquier tangente o desviación del tema principal.",
    "Verificar que la respuesta sea útil y satisfaga la intención del usuario.",
]

EXPECTED_OUTPUT = """Con el plan Profesional tienes disponibles las siguientes funcionalidades:

**Exportación de reportes:**
- Exportación a PDF: Sí, disponible
- Exportación a Excel: Sí, disponible
- Exportación a CSV: Sí, disponible

**Automatización:**
- Programación de reportes: Sí, puedes programar envíos automáticos
- Frecuencia disponible: diaria, semanal o mensual
- Límite: hasta 10 reportes programados

**Usuarios:**
- Usuarios incluidos: hasta 5 usuarios
- Usuarios adicionales: 5 USD/mes por usuario extra

Para configurar envíos automáticos, ve a Configuración > Reportes > Programación."""

USER_INPUT = """Tengo el plan Profesional de su plataforma de analytics.
¿Puedo exportar reportes en PDF y programar envíos automáticos por email?
¿Cuántos usuarios pueden acceder con mi plan?"""

# https://deepeval.com/docs/metrics-answer-relevancy
@pytest.fixture(scope="module")
def agent_response(producto_soporte_cliente_agent) -> str:
    return str(producto_soporte_cliente_agent(USER_INPUT))

def test_answer_relevancy_metric(agent_response, eval_model):
    metric = AnswerRelevancyMetric(
        threshold=THRESHOLD,
        include_reason=True,
        model=eval_model
    )

    test_case = LLMTestCase(
        input=USER_INPUT,
        actual_output=agent_response,
        expected_output=EXPECTED_OUTPUT
    )

    assert_test(test_case, [metric])
