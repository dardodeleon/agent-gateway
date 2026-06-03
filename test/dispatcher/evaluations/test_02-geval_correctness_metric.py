import pytest

from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

THRESHOLD = 0.7

PRECISION_METRIC_EVALUATION_STEPS = [
    "Verificar si los hechos en 'actual output' contradicen los hechos en 'expected output'.",
    "Penalizar fuertemente la omisión de detalles importantes presentes en 'expected output'.",
    "Evaluar si la información proporcionada es factualmente correcta y precisa.",
    "Identificar cualquier afirmación incorrecta o engañosa en la respuesta.",
    "Verificar que no se incluyan datos inventados o sin fundamento.",
    "El lenguaje vago u opiniones contradictorias son aceptables si los hechos clave son correctos.",
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

# https://deepeval.com/guides/guides-answer-correctness-metric#how-to-create-your-correctness-metric
@pytest.fixture(scope="module")
def agent_response(producto_soporte_cliente_agent) -> str:
    return str(producto_soporte_cliente_agent(USER_INPUT))

def test_geval_precision_metric(agent_response, eval_model):
    metric = GEval(
        name="Correctness",
        evaluation_steps=PRECISION_METRIC_EVALUATION_STEPS,
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.EXPECTED_OUTPUT,
        ],
        threshold=THRESHOLD,
        model=eval_model,
    )

    test_case = LLMTestCase(
        input=USER_INPUT,
        actual_output=agent_response,
        expected_output=EXPECTED_OUTPUT,
    )

    assert_test(test_case, [metric])
