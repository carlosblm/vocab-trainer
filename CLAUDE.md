# Contexto del proyecto

Aplicación de estudio de vocabulario a partir del `vocab.db` de Kindle.

**Antes de proponer o escribir nada, lee:**
- `docs/propuesta_vocabulario.md` — fuente de verdad del diseño
- `docs/esquema_vocab.md` — formato del archivo de entrada y cifras del corpus
- `docs/DECISIONES.md` — decisiones ya tomadas y por qué

Si te pido algo que contradice esos documentos, **dímelo antes de hacerlo**.

## Estructura

Monorepo. El backend vive en `backend/`, con `src-layout`: el paquete es
`vocab` y su raíz es `backend/src/vocab/`. Las rutas de las reglas duras se
entienden desde ahí. `frontend/` está vacío hasta F3.

## Arquitectura

Hexagonal. Las dependencias apuntan siempre hacia el dominio.

| Capa | Qué contiene | Puede importar de |
|---|---|---|
| `domain/` | Entidades y reglas de negocio | Solo biblioteca estándar |
| `ports/` | Contratos (`Protocol`) y objetos de transferencia | `domain/` |
| `application/` | Casos de uso: orquestan dominio y puertos | `domain/`, `ports/` |
| `adapters/` | Implementaciones de los puertos (Kindle, Postgres, spaCy) | `domain/`, `ports/` |
| `cli/` | Adaptador de entrada y raíz de composición | Todas |

`cli/` es el único sitio donde se instancian los adaptadores concretos y se
inyectan en los casos de uso. Si un cambio obliga a romper una de estas
reglas, dímelo antes de hacerlo.

## Modo de aprendizaje

Uso este proyecto para aprender. Cada tarea viene marcada:

- **[aprender]**: no escribas el código. Explícame qué hay que hacer, qué
  archivos tocar y qué preguntas tengo que resolver, sin darme las respuestas.
  Yo lo escribo y tú lo revisas con crítica: dime qué está mal y por qué, sin
  darme la versión corregida salvo que te la pida.
- **[delegar]**: escríbelo tú, y explícame paso a paso qué hace y por qué
  está así.

En ambos casos, al empezar y al terminar, explícame el flujo completo de la
funcionalidad a través de las capas: por dónde entra, qué capa llama a cuál y
qué tipo cruza cada frontera, citando archivo y función reales del
repositorio. Si una tarea no viene marcada, pregunta.

## Alcance

El proyecto avanza por fases (§9 de la propuesta). Antes de escribir nada,
comprueba en qué fase estamos y qué queda fuera de ella. Si no está claro en
el prompt, pregunta.

No introduzcas ni prepares tecnologías de fases posteriores: cualquier llamada
a un LLM es F1, Langfuse es F2, FastAPI y Angular son F3, LangGraph es F5.

## Reglas duras

- `backend/src/vocab/domain/` no importa nada de terceros. Ni SQLAlchemy, ni
  spaCy, ni Pydantic. Solo biblioteca estándar.
- Entidad de dominio y tabla de SQLAlchemy son clases distintas, con una
  función de traducción entre ellas. Nunca una sola clase con anotaciones.
- Las dependencias entran por parámetro, no se instancian dentro de quien las
  usa. Es lo que permite probar el caso de uso sin base de datos ni spaCy.
- Ningún nombre de modelo LLM escrito en Python (D-007).
- **Todo identificador en inglés**: variables, constantes, funciones, clases,
  argumentos, nombres de test, tablas y columnas.
  Documentación, docstrings, comentarios y mensajes de commit en **español**.
- Toda configuración por variables de entorno. Cero rutas absolutas.
- Decisión por defecto: **no usar un LLM**. Cada uso debe justificarse.
- El `vocab.db` real no se commitea nunca. Los tests que lo necesitan leen la
  ruta de `VOCAB_TEST_DATA` y se saltan si no existe.
- Nada de `# type: ignore` ni `# noqa` sin un comentario que justifique por qué
  no se puede arreglar la causa.

## Números medidos

No los inventes ni los deduzcas. Si un test falla por un número, ejecútalo y
usa el valor real; si no puedes ejecutarlo, dímelo en vez de estimar. Las
cifras del corpus están en `docs/esquema_vocab.md`.

## Gestión de dependencias

`uv` con `pyproject.toml` (PEP 621) y `uv.lock`. No generes `requirements.txt`
ni uses `pip install` directamente.

## Cómo trabajar conmigo

- Explica el porqué de cada decisión, no solo el cómo.
- Si no estás seguro de algo, dilo explícitamente. No inventes.
- No amplíes el alcance. Si detectas que yo lo estoy ampliando, señálalo.
- Un cambio por vez. No refactorices archivos que no te he pedido tocar.
- Al terminar una tarea, muéstrame el resultado y para. No encadenes.
- No edites nada de `docs/`, `DECISIONES.md` incluido, salvo que te lo pida
  explícitamente.
  Son material de entrevista y van en mi voz.
- Sí avísame cuando un cambio los deje desactualizados: una cifra que ya no
  cuadra, una decisión nueva sin entrada, un campo del modelo de datos que
  cambió. Dime qué archivo y qué apartado, y sigue con la tarea.
