import pytest

from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from deepeval.metrics import PromptAlignmentMetric

THRESHOLD = 0.7

ANIMAL_ORIGIN_STEPS = [
    "La receta resultante no contiene carne, pollo, cerdo, pescado ni mariscos como ingrediente",
    "La receta resultante no contiene lácteos como leche de vaca, queso, mantequilla ni crema",
    "La receta resultante no contiene huevos como ingrediente",
    "La receta resultante no contiene caldos de hueso ni grasa animal",
    "Todos los ingredientes de la receta son de origen vegetal",
    "Si el usuario pide un plato con carne, el chef propone una versión veganizada en lugar de rechazar la solicitud",
]

PERSONALITY_STEPS = [
    "Responde en el mismo idioma en que le hablan",
    "El chef debe negarse a entregar resetas que no sean veganas",
    "El chef debe proponer en forma cordíal y cortez alternativas a solicitudes de recetas que no sean veganas", 
    "Cuando se pregunte por un plato no vegano, propone una versión veganizada explicando cada sustitución", 
]

RECIPE_STRUCTURE_STEPS = [
    "Incluye nombre del plato y número de porciones", 
    "Lista ingredientes con cantidades en unidades métricas", 
    "Incluye preparación paso a paso", 
    "Incluye tiempo estimado de preparación y cocción", 
    "Incluye información nutricional por porción con calorías, proteínas, hierro, calcio, vitamina B12, omega-3 y fibra", 
    "Incluye consejos del chef vegano", 
]

USER_INPUT = """Este domingo viene mi abuela a almorzar y ella solo come comida tradicional.
Quiero prepararle un estofado de carne con papas para 6 personas,
es su receta favorita y quiero que se sienta como en casa.
¿Me ayudas con la receta completa?"""

# https://deepeval.com/docs/metrics-prompt-alignment
"""
Alineación = Nro instrucciones     
             ------------------
             Nro inst. seguidas  
                9 / 10 = 0.9
                7 / 10 = 0.7
                6 / 10 = 0.6
​"""
@pytest.fixture(scope="module")
def agent_response(gastronomia_chef_vegano) -> str:
    return str(gastronomia_chef_vegano(USER_INPUT))

def test_answer_relevancy_metric_animal_origin(agent_response, eval_model):
    metric = PromptAlignmentMetric(
        prompt_instructions=ANIMAL_ORIGIN_STEPS,
        model=eval_model,
        include_reason=True,
        strict_mode=True
    )

    test_case = LLMTestCase(
        input=USER_INPUT,
        actual_output=agent_response
    )

    assert_test(test_case, [metric])

def test_answer_relevancy_metric_personality(agent_response, eval_model):
    metric = PromptAlignmentMetric(
        prompt_instructions=PERSONALITY_STEPS,
        model=eval_model,
        include_reason=True
    )

    test_case = LLMTestCase(
        input=USER_INPUT,
        actual_output=agent_response
    )

    assert_test(test_case, [metric])

def test_answer_relevancy_metric_recipe_structure(agent_response, eval_model):
    metric = PromptAlignmentMetric(
        prompt_instructions=RECIPE_STRUCTURE_STEPS,
        model=eval_model,
        include_reason=True
    )

    test_case = LLMTestCase(
        input=USER_INPUT,
        actual_output=agent_response
    )

    assert_test(test_case, [metric])
