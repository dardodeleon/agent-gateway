import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase, ToolCall, ToolCallParams
from deepeval.metrics import ToolCorrectnessMetric
from deepeval.dataset import EvaluationDataset, Golden

def get_tools(result):
    tool_metrics = getattr(getattr(result, "metrics", None), "tool_metrics", None)
    return [ToolCall(name=k) for k in tool_metrics or []]

THRESHOLD = 0.7

DATASET = EvaluationDataset(
    goldens=[
        Golden(
            input="Qué día es el día del programador en el año 2026",
            expected_tools=[ToolCall(name="programmers_day")],
        ),
        Golden(
            input="Elabora un líndo saludo de cumpleaños para Elionora",
            expected_tools=[ToolCall(name="birthday_greeting")],
        ),
    ]
)

EXPECTED_TOOLS_FAIL = {
    "Qué día es el día del programador en el año 2026": [ToolCall(name="wrong_programmers_day_tool")],
    "Elabora un líndo saludo de cumpleaños para Elionora": [ToolCall(name="wrong_birthday_greeting_tool")],
}

# https://deepeval.com/docs/metrics-tool-correctness#how-is-it-calculated
@pytest.mark.parametrize("golden", DATASET.goldens)
def test_agent_tools(golden: Golden, utilidad_asistente_fechas, eval_model, request):

    expected_tools = golden.expected_tools
    if request.config.getoption("--fail"):
        expected_tools = EXPECTED_TOOLS_FAIL[golden.input]

    result = utilidad_asistente_fechas(golden.input)

    metric = ToolCorrectnessMetric(
        threshold=THRESHOLD,
        evaluation_params=[ToolCallParams.INPUT_PARAMETERS],
        include_reason=True,
        model=eval_model
    )

    test_case = LLMTestCase(
        input=golden.input,
        actual_output=str(result),
        tools_called=get_tools(result),
        expected_tools=expected_tools,
    )

    assert_test(test_case, [metric])
