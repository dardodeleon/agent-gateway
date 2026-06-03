El usuario quiere completar la siguiente tarea usando un agente IA:

> {task_description}

Ejecuta el flujo completo siguiendo estos pasos:

## Paso 1: Descubrir agentes
1. Llama a `list_tags` para conocer las categorias disponibles.
2. Identifica la categoria mas relevante para la tarea.
3. Llama a `list_agents` filtrado por ese tag.

## Paso 2: Seleccionar agente
4. Elige el agente mas adecuado segun su descripcion. Si hay varios candidatos, presenta las opciones al usuario y deja que elija.

## Paso 3: Enviar tarea
5. Llama a `send_task` con el `provider`, `name` del agente y un `task_text` claro y detallado.
6. Guarda el `task_id` retornado.

## Paso 4: Obtener resultado
7. Llama a `check_task_status` con el task_id.
8. Si el estado es `pending` o `assigned`, informa al usuario que el agente esta trabajando y vuelve a consultar despues de un momento.
9. Si el estado es `completed`, presenta la respuesta del agente al usuario.
10. Si el estado es `error`, informa el problema al usuario.
