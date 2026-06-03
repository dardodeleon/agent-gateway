import pytest
from deepteam import red_team
from deepeval import assert_test
from deepteam.vulnerabilities import Bias
from deepteam.attacks.single_turn import Leetspeak, PromptInjection

def test_bias_with_prompt_injection(atencion_recursos_humanos, eval_model):

    def model_callback(input: str) -> str:
        try:
            result = atencion_recursos_humanos(input)
            output = str(result)
            print(f"[DEBUG] tipo: {type(result)}, valor: {output[:100]}")
            return output
        except Exception as e:
            print(f"[ERROR] excepción en callback: {e}")
            raise

    """
    Race:       Pruebas para detectar sesgos raciales, incluida la perpetuación de estereotipos o trato injusto basado en la raza.
    Gender      Prueba de sesgos relacionados con el género, como el refuerzo de estereotipos o la exhibición de un trato injusto basado en la identidad de género.
    Religion    Prueba de sesgos en el manejo de temas religiosos, como la promoción o discriminación de creencias particulares.
    Politics    Prueba de sesgos políticos, incluido el favoritismo o el refuerzo de estereotipos políticos.
                https://www.trydeepteam.com/docs/red-teaming-vulnerabilities-bias#usage
    """
    bias = Bias(
        types=[
            "race", 
            "gender", 
            "religion", 
            "politics"
        ]
    )

    techniques = [PromptInjection(), Leetspeak()]

    risk_assessment = red_team(
        model_callback=model_callback,
        vulnerabilities=[bias],
        attacks=techniques,
        simulator_model=eval_model,
        evaluation_model=eval_model,
        async_mode=False,
        # synthesizer_model="gpt-3.5-turbo-0125",
        # evaluation_model="gpt-4.1",
        # purpose="La aplicación es un sistema de atención al cliente."
    )

    overview = risk_assessment.overview
    print("Errores:        ", overview.errored)
    print("Duración (seg): ", overview.run_duration)
    print("Por vulnerabilidad:", overview.vulnerability_type_results)
    print("Por ataque:        ", overview.attack_method_results)
    for tc in risk_assessment.test_cases:
        print("─" * 50)
        print("Vulnerabilidad: ", tc.vulnerability)
        print("Tipo:           ", tc.vulnerability_type)
        print("Ataque:         ", tc.attack_method)
        print("Input:          ", tc.input)
        print("Categoría:      ", tc.risk_category)
        print("Error:          ", tc.error)

    errores = [
        f"[{tc.vulnerability} / {tc.vulnerability_type} / {tc.attack_method}] {tc.error}"
        for tc in risk_assessment.test_cases
        if tc.error is not None
    ]

    assert overview.errored == 0, (
        f"Se encontraron {overview.errored} error(es) en el red teaming:\n" +
        "\n".join(f"  - {e}" for e in errores)
    )