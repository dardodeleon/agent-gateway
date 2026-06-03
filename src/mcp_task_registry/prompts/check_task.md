Consulta el estado de la tarea con ID: `{task_id}`

Sigue estos pasos:

1. Llama a `check_task_status` con el task_id indicado.
2. Interpreta el resultado segun el estado:
   - **pending**: La tarea esta en cola. Informa al usuario que aun no ha sido tomada por un agente.
   - **assigned**: Un agente esta procesando la tarea. Informa al usuario que esta en progreso.
   - **completed**: El agente termino. Presenta el contenido del campo `response` al usuario de forma clara y formateada.
   - **error**: Hubo un problema. Presenta el campo `error_message` al usuario.
3. Si el estado es `pending` o `assigned`, sugiere al usuario esperar un momento y volver a consultar.
