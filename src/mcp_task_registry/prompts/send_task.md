El usuario quiere enviar la siguiente tarea a un agente IA:

> {task_description}

Sigue estos pasos:

1. Llama a `list_tags` para ver las categorias de agentes disponibles.
2. Identifica la categoria mas relevante para la tarea descrita.
3. Llama a `list_agents` con el tag de esa categoria.
4. Selecciona el agente mas adecuado segun su descripcion y la tarea solicitada. Si hay varios candidatos, presenta las opciones al usuario y deja que elija.
5. Llama a `send_task` con el `provider`, `name` del agente elegido y un `task_text` claro y detallado basado en la descripcion del usuario.
6. Guarda el `task_id` de la respuesta e informalo al usuario.
7. Indica al usuario que puede consultar el estado de la tarea con el task_id proporcionado.
