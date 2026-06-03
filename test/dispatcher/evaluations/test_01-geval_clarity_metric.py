import pytest

from deepeval import assert_test
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCaseParams
from deepeval.test_case import LLMTestCase

CLARITY_METRIC_EVALUATION_STEPS = [
    "Evaluar si la respuesta es fácil de entender para el público general.",
    "Verificar que la respuesta esté bien organizada con una progresión lógica.",
    "Identificar jerga técnica y comprobar si está adecuadamente explicada.",
    "Evaluar si la respuesta es concisa sin sacrificar información importante.",
    "Detectar ambigüedades o afirmaciones poco claras en la respuesta.",
]

THRESHOLD = 0.8

USER_INPUT = """Tengo una factura con cargos que no entiendo. Veo 'Plan Profesional',
un 'cargo por excedente de usuarios' y un 'ajuste proporcional'.
¿Me pueden explicar cada concepto y por qué aparecen estos montos?
"""

@pytest.fixture(scope="module")
def agent_response(atencion_facturacion_agent) -> str:
    return str(atencion_facturacion_agent(USER_INPUT))

# https://deepeval.com/blog/top-5-geval-use-cases#coherence
# https://deepeval.com/docs/metrics-llm-evals#coherence
def test_geval_clarity_metric(agent_response, eval_model):
    metric = GEval(
        name="Clarity",
        evaluation_steps=CLARITY_METRIC_EVALUATION_STEPS,
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
        ],
        threshold=THRESHOLD,
        model=eval_model,
    )

    test_case = LLMTestCase(
        input=USER_INPUT,
        actual_output=agent_response,
    )

    assert_test(test_case, [metric])
