# vocab-trainer

vocab-trainer convierte las palabras que consultas en el diccionario del Kindle en ejercicios anclados a la frase del libro donde aparecieron.
Importa el `vocab.db` del Kindle a PostgreSQL, limpia cada frase, la analiza con spaCy y le asigna la definición de Open English WordNet cuando el sentido no es ambiguo.
Los ejercicios se hacen desde la línea de comandos, y un modelo local en Ollama genera las opciones falsas de los de definición.

## Qué hay en el repo

El backend es el paquete Python `vocab`, con arquitectura hexagonal: las dependencias apuntan siempre hacia el dominio, y lo comprueban los contratos de `import-linter` de [`backend/pyproject.toml`](backend/pyproject.toml).

- [`backend/src/vocab/domain/`](backend/src/vocab/domain): entidades, limpieza de frases y ejercicios, solo con la biblioteca estándar.
- [`backend/src/vocab/ports/`](backend/src/vocab/ports): los contratos que los casos de uso piden a los adaptadores.
- [`backend/src/vocab/application/`](backend/src/vocab/application): los casos de uso, que orquestan dominio y puertos.
- [`backend/src/vocab/adapters/`](backend/src/vocab/adapters): las implementaciones para Kindle, PostgreSQL, spaCy, Open English WordNet y Ollama.
- [`backend/src/vocab/cli/main.py`](backend/src/vocab/cli/main.py): los comandos `vocab import` y `vocab study`, y el único sitio donde se construyen los adaptadores.
- [`backend/migrations/`](backend/migrations): las migraciones de Alembic del esquema.
- [`backend/tests/`](backend/tests): tests unitarios con un doble por puerto y tests de integración contra PostgreSQL, con un `vocab.db` mínimo en [`backend/tests/fixtures/`](backend/tests/fixtures).
- [`backend/scripts/`](backend/scripts): mediciones sobre el corpus que justificaron decisiones, fuera del código de producción.
- [`notebooks/`](notebooks): el perfilado de los datos del Kindle previo a la ingesta.
- [`docs/propuesta_vocabulario.md`](docs/propuesta_vocabulario.md): el diseño, el alcance y las fases del proyecto.
- [`docs/DECISIONES.md`](docs/DECISIONES.md): cada decisión tomada, con lo descartado y por qué.
- [`docs/esquema_vocab.md`](docs/esquema_vocab.md): el formato del `vocab.db` y sus trampas.
- [`compose.yaml`](compose.yaml): PostgreSQL y el servicio `app`, que ejecuta la CLI dentro de la imagen de [`backend/Dockerfile`](backend/Dockerfile).
- [`.env.example`](.env.example): todas las variables de entorno, cada una con su explicación.

## Uso

Copia la plantilla de configuración y rellena `.env`.

```bash
cp .env.example .env
```

Levanta PostgreSQL, instala las dependencias y crea el esquema.
Ejecuta los comandos de `uv` desde `backend/`.

```bash
docker compose up -d --wait db
cd backend
uv sync
uv run alembic upgrade head
```

`vocab import` necesita el léxico Open English WordNet en el directorio que indica `WN_DATA_DIR`.
Descárgalo con el comando que acompaña a esa variable en `.env.example`.

Importa tu `vocab.db` y estudia:

```bash
uv run vocab import ruta/a/tu/vocab.db
uv run vocab study
```

La importación solo añade lo nuevo, así que puedes repetirla con cada exportación sin tocar lo que ya tienes.
`study` te propone ejercicios hasta que cierras la entrada con Ctrl+D.
Respondes con el número de la opción, o escribes la palabra si añades `--write`.
Tras un ejercicio de definición, `x` marca que la definición no encaja en la frase, y ese contexto deja de darla.

### Distractores con Ollama

Sin más configuración, las opciones falsas de los ejercicios de definición salen de las definiciones de tus otras palabras.
Para que las genere un modelo, define en `.env` las variables `LLM_TASK__DISTRACTORS__*` y `OLLAMA_BASE_URL`.
Si el modelo falla o no responde, `study` vuelve a las definiciones de tus palabras y te avisa.

### Tests y comprobaciones

```bash
uv run pytest
uv run ruff check
uv run mypy
uv run lint-imports
```

Los tests de integración levantan su propio PostgreSQL en un contenedor.
Los que necesitan un `vocab.db` real, el léxico u Ollama se saltan si falta `VOCAB_TEST_DATA`, `WN_DATA_DIR` u `OLLAMA_BASE_URL`.

## Requisitos

- [uv](https://docs.astral.sh/uv/), que instala Python y las dependencias de `backend/`.
- Docker con Compose, para PostgreSQL y para los tests de integración.
- Un `vocab.db` de tu Kindle, que está en `system/vocabulary/vocab.db` al conectarlo por USB.
- Ollama fuera de compose, solo si quieres que un modelo genere los distractores.
