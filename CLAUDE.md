# Contexto del proyecto

Aplicación de estudio de vocabulario a partir del `vocab.db` de Kindle.

**Antes de proponer o escribir nada, lee:**
- `docs/propuesta_vocabulario.md` — fuente de verdad del diseño
- `docs/esquema_vocab.md` — formato del archivo de entrada
- `DECISIONES.md` — decisiones ya tomadas y por qué

Si te pido algo que contradice esos documentos, **dímelo antes de hacerlo**.

## Fase actual: F0

Entregable de F0: ingesta a Postgres, normalización con spaCy, limpieza,
recorte de frases, `compose` funcionando, CLI que muestra `cloze_original`.

**Fuera de F0**: FastAPI, Angular, cualquier llamada a un LLM, Langfuse,
LangGraph, FSRS, autenticación. No los introduzcas ni los prepares.

## Reglas duras

- `src/vocab/domain/` no importa nada de terceros. Ni SQLAlchemy, ni spaCy,
  ni Pydantic. Solo biblioteca estándar.
- Entidad de dominio y tabla de SQLAlchemy son clases distintas, con una
  función de traducción entre ellas. Nunca una sola clase con anotaciones.
- Ningún nombre de modelo LLM escrito en Python (D-007).
- Código, nombres de tabla y columnas en **inglés**.
  Documentación, comentarios y mensajes de commit en **español**.
- Toda configuración por variables de entorno. Cero rutas absolutas.
- Decisión por defecto: **no usar un LLM**. Cada uso debe justificarse.
- `vocab.db` real no se commitea nunca.
- **Todo identificador en inglés**: variables, constantes, funciones, clases,
  argumentos, nombres de test, tablas y columnas.

## Gestión de dependencias

`uv` con `pyproject.toml` (PEP 621) y `uv.lock`. No generes `requirements.txt`
ni uses `pip install` directamente.

## Cómo trabajar conmigo

- Explica el porqué de cada decisión, no solo el cómo.
- Si no estás seguro de algo, dilo explícitamente. No inventes.
- No amplíes el alcance. Si detectas que yo lo estoy ampliando, señálalo.
- Un cambio por vez. No refactorices archivos que no te he pedido tocar.
