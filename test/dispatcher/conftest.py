"""Shared dispatcher fixtures — agent loading."""

import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

from .conftestfail import BAD_PROMPT_FACTURACION, BAD_PROMPT_SOPORTE_CLIENTE_PRICE_OLD, BAD_PROMPT_SOPORTE_CLIENTE_PRICE_NEW, BAD_PROMPT_SOPORTE_CLIENTE_USERS_OLD, BAD_PROMPT_SOPORTE_CLIENTE_USERS_NEW, BAD_PROMPT_SOPORTE_CLIENTE_RECOMENDACION, VEGAN_CHEF_CURRENT_CAPACITY, VEGAN_CHEF_UNALIGNED_CAPACITY, VEGAN_CHEF_CURRENT_PERSONALITY,VEGAN_CHEF_UNALIGNED_PERSONALITY

load_dotenv()

# ---------------------------------------------------------------------------
# Importa módulos desde src
# ---------------------------------------------------------------------------
_src_dir = Path(__file__).resolve().parent.parent.parent / "src"
_dispatcher_dir = _src_dir / "dispatcher"

for _p in [str(_src_dir), str(_dispatcher_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Factory de agentes, usando AgentFactory en función a los modelos configurados en src/models.xml
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def load_agent():
    from config import load_models_config, load_agent_config
    from agent_core import AgentFactory

    models_config = load_models_config(str(_src_dir / "models.yml"))

    agents_base = str(_src_dir / "dispatcher_agents")
    tools_base = str(_src_dir / "dispatcher_tools")
    skills_base = str(_src_dir / "dispatcher_skills")

    factory = AgentFactory(models_config, tools_base, skills_base, agents_base)

    def _load(provider: str, name: str):
        agent_dir = os.path.join(agents_base, provider, name)
        config = load_agent_config(agent_dir)
        return factory.create_agent(config)

    return _load

# ---------------------------------------------------------------------------
# Retorna agentes especializados y con defectos simulados
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def atencion_facturacion_agent(load_agent, request):

    agent = load_agent("atencion", "facturacion")

    if request.config.getoption("--fail"):
        agent.system_prompt = agent.system_prompt[:agent.system_prompt.find("FORMATO DE RESPUESTA")] + BAD_PROMPT_FACTURACION

    return agent

@pytest.fixture(scope="module")
def producto_soporte_cliente_agent(load_agent, request):

    agent = load_agent("producto", "soporte-cliente")
    
    if request.config.getoption("--fail"):
        agent.system_prompt = agent.system_prompt.replace(BAD_PROMPT_SOPORTE_CLIENTE_PRICE_OLD, BAD_PROMPT_SOPORTE_CLIENTE_PRICE_NEW)
        agent.system_prompt = agent.system_prompt.replace(BAD_PROMPT_SOPORTE_CLIENTE_USERS_OLD, BAD_PROMPT_SOPORTE_CLIENTE_USERS_NEW)
        agent.system_prompt += BAD_PROMPT_SOPORTE_CLIENTE_RECOMENDACION

    return agent

@pytest.fixture(scope="module")
def gastronomia_chef_vegano(load_agent, request):

    agent = load_agent("gastronomia", "chef-vegano")

    if request.config.getoption("--fail"):
        agent.system_prompt = agent.system_prompt.replace(VEGAN_CHEF_CURRENT_CAPACITY, VEGAN_CHEF_UNALIGNED_CAPACITY)
        agent.system_prompt = agent.system_prompt.replace(VEGAN_CHEF_CURRENT_PERSONALITY, VEGAN_CHEF_UNALIGNED_PERSONALITY)

    return agent

@pytest.fixture(scope="module")
def atencion_recursos_humanos(load_agent):
    return load_agent("atencion", "recursos-humanos")

@pytest.fixture(scope="function")
def utilidad_asistente_fechas(load_agent):
    return load_agent("utilidades", "asistente-fechas")

# ---------------------------------------------------------------------------
# Modelo DeepEval para evaluaciones
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def get_eval_model():
    from deepeval.models import GPTModel as DeepEvalGPTModel
    from deepeval.models import AnthropicModel as DeepEvalAnthropicModel
    from config import load_models_config

    models_config = load_models_config(str(_src_dir / "models.yml"))

    def _create(model_name: str):
        if model_name not in models_config.models:
            raise ValueError(
                f"Modelo '{model_name}' no encontrado en models.yml. "
                f"Disponibles: {list(models_config.models.keys())}"
            )
        mc = models_config.models[model_name]
        if mc.provider == "anthropic":
            return DeepEvalAnthropicModel(
                model=mc.model_id,
                temperature=0,
            )
        if mc.provider == "openai":
            return DeepEvalGPTModel(
                model=mc.model_id,
                temperature=0,
            )

        raise ValueError(f"El modelo '{mc.provider}' no está soportado.")

    return _create

@pytest.fixture(scope="session")
def eval_model(get_eval_model):
    return get_eval_model("sonnet-default")
