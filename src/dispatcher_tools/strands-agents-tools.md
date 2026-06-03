# Proveedores personalizados

Las tools se organizan bajo proveedores, crear la estructura `/tools/{proveedor}/{nombre}/tool.py` y referenciar como `"proveedor:nombre"`:

```yaml
# agent.yml
tools:
  - "mi-empresa:mi_tool"    # Busca en /tools/mi-empresa/mi_tool/tool.py
```

# Tools de Strands disponibles

```yaml
# agent.yml
tools:
  - "strands:file_read"    
```

| Tool          | Import                          | Descripción                                              |
|---------------|---------------------------------|----------------------------------------------------------|
| `file_read`   | `from strands_tools import file_read`   | Lee archivos con múltiples modos                  |
| `file_write`  | `from strands_tools import file_write`  | Crea y escribe contenido en archivos              |
| `editor`      | `from strands_tools import editor`      | Edición avanzada con syntax highlighting          |

## Sistema y Ejecución

| Tool          | Import                          | Descripción                                              |
|---------------|---------------------------------|----------------------------------------------------------|
| `shell`       | `from strands_tools import shell`       | Ejecuta comandos de shell                         |
| `python_repl` | `from strands_tools import python_repl` | Ejecuta snippets de Python                        |
| `calculator`  | `from strands_tools import calculator`  | Operaciones matemáticas                           |
| `cron`        | `from strands_tools import cron`        | Programa tareas recurrentes                       |

## Web y Búsqueda

| Tool             | Import                                            | Descripción                              |
|------------------|---------------------------------------------------|------------------------------------------|
| `http_request`   | `from strands_tools import http_request`           | Llamadas HTTP/API con autenticación      |
| `tavily_search`  | `from strands_tools.tavily import tavily_search`   | Búsqueda web en tiempo real              |
| `tavily_extract` | `from strands_tools.tavily import tavily_extract`  | Extrae contenido de URLs                 |
| `tavily_crawl`   | `from strands_tools.tavily import tavily_crawl`    | Crawling inteligente de sitios web       |
| `tavily_map`     | `from strands_tools.tavily import tavily_map`      | Mapea estructura de sitios web           |
| `exa_search`     | `from strands_tools.exa import exa_search`         | Búsqueda neural y por keywords           |
| `exa_get_contents` | `from strands_tools.exa import exa_get_contents` | Extrae contenido completo de URLs        |
| `bright_data`    | `from strands_tools import bright_data`            | Web scraping y extracción de datos       |

## Memoria y Conocimiento

| Tool                 | Import                                    | Descripción                                   |
|----------------------|-------------------------------------------|-----------------------------------------------|
| `memory`             | `from strands_tools import memory`             | Almacena documentos en bases de conocimiento |
| `retrieve`           | `from strands_tools import retrieve`           | Consulta bases de conocimiento               |
| `mem0_memory`        | `from strands_tools import mem0_memory`        | Memorias de usuario/agente persistentes      |
| `agent_core_memory`  | `from strands_tools import agent_core_memory`  | Servicio de memoria Amazon Bedrock           |
| `mongodb_memory`     | `from strands_tools import mongodb_memory`     | Memoria basada en MongoDB Atlas              |
| `elasticsearch_memory` | `from strands_tools import elasticsearch_memory` | Memoria vectorial con Elasticsearch     |

## AWS y Cloud

| Tool                        | Import                                              | Descripción                              |
|-----------------------------|-----------------------------------------------------|------------------------------------------|
| `use_aws`                   | `from strands_tools import use_aws`                  | Acceso a servicios AWS                   |
| `code_interpreter`          | `from strands_tools import code_interpreter`         | Ejecución de código en sandbox           |
| `nova_reels`                | `from strands_tools import nova_reels`               | Generación de video vía Bedrock          |
| `generate_image`            | `from strands_tools import generate_image`           | Generación de imágenes con IA            |
| `generate_image_stability`  | `from strands_tools import generate_image_stability` | Generación de imágenes con Stability AI  |

#### Coordinación de Agentes

| Tool          | Import                                  | Descripción                                        |
|---------------|-----------------------------------------|----------------------------------------------------|
| `swarm`       | `from strands_tools import swarm`       | Coordina múltiples agentes                         |
| `a2a_client`  | `from strands_tools import a2a_client`  | Descubre y comunica agentes entre sí               |
| `mcp_client`  | `from strands_tools import mcp_client`  | Conecta con servidores MCP externos                |
| `batch`       | `from strands_tools import batch`       | Ejecuta múltiples tools en paralelo                |
| `use_llm`     | `from strands_tools import use_llm`     | Crea loops anidados de IA                          |

## Automatización

| Tool            | Import                                    | Descripción                                      |
|-----------------|-------------------------------------------|--------------------------------------------------|
| `browser`       | `from strands_tools import browser`       | Automatización de navegador (Chromium)            |
| `use_computer`  | `from strands_tools import use_computer`  | Automatización de escritorio (mouse, teclado)     |
| `slack`         | `from strands_tools import slack`         | Interacción con workspaces de Slack               |

## Utilidades

| Tool              | Import                                      | Descripción                                    |
|-------------------|---------------------------------------------|------------------------------------------------|
| `current_time`    | `from strands_tools import current_time`    | Obtiene la fecha/hora actual                   |
| `environment`     | `from strands_tools import environment`     | Gestión de variables de entorno                |
| `sleep`           | `from strands_tools import sleep`           | Pausa la ejecución                             |
| `think`           | `from strands_tools import think`           | Razonamiento avanzado                          |
| `journal`         | `from strands_tools import journal`         | Logs estructurados                             |
| `diagram`         | `from strands_tools import diagram`         | Crea diagramas de arquitectura/UML             |
| `rss`             | `from strands_tools import rss`             | Gestión de feeds RSS                           |
| `speak`           | `from strands_tools import speak`           | Salida de texto a voz                          |
| `image_reader`    | `from strands_tools import image_reader`    | Procesamiento de archivos de imagen            |
| `load_tool`       | `from strands_tools import load_tool`       | Carga dinámica de tools personalizadas         |
| `agent_graph`     | `from strands_tools import agent_graph`     | Visualización de relaciones entre agentes      |
| `workflow`        | `from strands_tools import workflow`        | Define procesos multi-paso                     |
| `handoff_to_user` | `from strands_tools import handoff_to_user` | Transfiere control al usuario                  |
| `stop`            | `from strands_tools import stop`            | Termina la ejecución del agente                |

> **Nota**: Algunas tools de strands requieren credenciales o servicios adicionales (ej: Tavily API key, AWS credentials, Slack tokens). Consultar la documentación de cada tool para requisitos específicos.

---

# Referencias

- [strands-agents-tools en PyPI](https://pypi.org/project/strands-agents-tools/)
- [Repositorio GitHub](https://github.com/strands-agents/tools)
- [Documentación de Strands Agents](https://strandsagents.com)
