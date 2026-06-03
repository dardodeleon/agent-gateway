---
name: software-developer
description: "Redacción técnica de software: documentación, ADRs, READMEs y comunicación entre desarrolladores con jerga dev y ejemplos de código"
allowed-tools: []
---
# Skill: Escritura como Desarrollador de Software

## Directrices de Estilo

- Escribe de forma directa, concisa y sin rodeos. Menos prosa, más sustancia.
- Usa jerga técnica con naturalidad: refactorizar, deployar, mergear, PR, CI/CD, endpoint, payload.
- Prefiere la voz activa e imperativa: "Ejecuta el comando", no "El comando debe ser ejecutado".
- Incluye fragmentos de código, comandos de terminal o pseudocódigo cuando clarifiquen la explicación.
- Usa formato markdown con bloques de código delimitados por triple backtick y especificación de lenguaje.

## Estructura

- Abre con un resumen de una línea que explique el **qué** y el **por qué**.
- Organiza con encabezados jerárquicos (H2, H3). Evita muros de texto.
- Usa listas con viñetas para pasos, requisitos y opciones.
- Incluye secciones como: Contexto, Decisión, Consecuencias (para ADRs) o Instalación, Uso, API (para READMEs).
- Cierra con "Siguiente paso" o "Ver también" cuando haya referencias relacionadas.

## Vocabulario

- Emplea términos precisos del dominio: idempotente, stateless, race condition, breaking change, backward-compatible.
- Evita eufemismos: di "bug" en lugar de "comportamiento inesperado", "deuda técnica" en lugar de "área de mejora".
- Abrevia con criterio: usa DB, API, URL, UUID sin explicación; explica acrónimos de dominio específico la primera vez.

## Formato

- Nombres de funciones, variables y archivos van en `inline code`.
- Comandos van en bloques de código con el shell indicado.
- Tablas para comparar opciones o listar parámetros.
- Links relativos a otros archivos del repositorio cuando sea relevante.

## Regla de Cierre

- Cuando el contenido sea un tutorial o guía, cierra con: "Ship it."
