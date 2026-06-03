import pytest

class TestCalculator:
    @pytest.fixture(autouse=True, scope="class")
    def _call_agent(self, load_agent, request):
        end_prompt = "" if request.config.getoption("--fail") else ". No realices desglose"

        agent = load_agent("math", "calculator")
        result = agent(f"Cuanto es (145 * 3) + 27 - 12?{end_prompt}" )

        request.cls.response = str(result)

    def test_response_is_not_empty(self):
        assert len(self.response.strip()) > 0

    def test_contains_correct_result(self):
        assert "450" in self.response

    def test_no_hallucinated_result(self):
        wrong_answers = ["449", "451", "435", "462"]
        for wrong in wrong_answers:
            assert wrong not in self.response, (
                f"La respuesta contiene un valor inesperado '{wrong}'"
            )

"""
Default

    U: Cuanto es (145 * 3) + 27 - 12?
    A: El resultado de la operación **(145 * 3) + 27 - 12 es **450**.

    Aquí está el proceso paso a paso:

    1. **Primero, la multiplicación**: 145 × 3 = **435**
    2. **Luego, la suma**: 435 + 27 = **462**
    3. **Finalmente, la resta**: 462 - 12 = **450**

    **Respuesta final: 450**
    Agent response: El resultado de la operación **(145 * 3) + 27 - 12 es **450**.

    Aquí está el proceso paso a paso:

    1. **Primero, la multiplicación**: 145 × 3 = **435**
    2. **Luego, la suma**: 435 + 27 = **462**
    3. **Finalmente, la resta**: 462 - 12 = **450**

    **Respuesta final: 450**

---

Fail

    U: Cuanto es (145 * 3) + 27 - 12?. No realices desglose
    A: La respuesta es **450**

"""