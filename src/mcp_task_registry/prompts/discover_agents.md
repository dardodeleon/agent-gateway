Necesito descubrir los agentes IA disponibles en el sistema.

Sigue estos pasos:

1. Llama a `list_tags` para obtener las categorias disponibles y la cantidad de agentes en cada una.
2. Presenta las categorias al usuario en formato de lista clara.
3. Pregunta al usuario que tipo de agente necesita (o si quiere ver todos).
4. Llama a `list_agents` con el tag seleccionado (o sin filtro si quiere ver todos).
5. Presenta los agentes encontrados mostrando: nombre, descripcion y tags de cada uno.
6. Si el usuario quiere enviar una tarea a uno de los agentes, necesitara el `provider` y `name` del agente elegido.
