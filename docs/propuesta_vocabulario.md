# Propuesta técnica — Aplicación de estudio de vocabulario

**Documento de contexto del proyecto**
Autor: Carlos Blázquez Martín · Versión 1.4 · Septiembre 2026

---

## 0. Propósito de este documento

Este documento define qué se va a construir, con qué tecnologías y en qué orden, antes de escribir código. Sirve como contexto único del proyecto: para el desarrollo, para el README del repositorio y para explicar el proyecto en una entrevista técnica.

El proyecto tiene **dos objetivos simultáneos y ambos son de primer nivel**:

1. **Objetivo de producto**: una aplicación que el autor usará a diario para aprender el vocabulario de los libros que lee.
2. **Objetivo profesional**: un proyecto demostrable que respalde un perfil de AI Engineer, construido con tecnologías que el mercado pide.

Cuando ambos objetivos entren en conflicto, las secciones correspondientes indican cuál prevalece.

---

## 1. Resumen ejecutivo

Aplicación web que importa el vocabulario que un lector ha consultado en su Kindle y genera ejercicios interactivos para aprenderlo, programados con repetición espaciada. Cada ejercicio se ancla a la frase real del libro donde apareció la palabra.

La mayor parte del sistema es determinista. Se emplean modelos de lenguaje en tres puntos concretos donde no existe alternativa determinista razonable, y cada uno lleva su justificación en la sección 5. Alrededor de esos puntos se construye una capa de validación, evaluación automática y observabilidad, que es el núcleo técnico del proyecto.

---

## 2. Objetivo práctico para el usuario

### 2.1 El problema

Un lector que lee en un idioma no nativo consulta palabras en el diccionario del Kindle mientras lee. El Kindle guarda esas consultas, pero su función de repaso es rudimentaria: muestra la palabra y su definición, sin ejercicios, sin programación de repasos y sin variedad. El resultado práctico es que el vocabulario consultado no se aprende: se consulta y se olvida.

La información valiosa que el Kindle sí guarda y no explota es **la frase concreta en la que apareció la palabra**. Esa frase es el mejor material de estudio posible, porque es contexto auténtico y ya significativo para el lector.

### 2.2 Qué hace la aplicación

1. El usuario sube su archivo de vocabulario. La aplicación lo importa, normaliza y limpia.
2. Cada día, la aplicación selecciona qué palabras toca repasar según un algoritmo de repetición espaciada.
3. Para cada palabra genera un ejercicio, anclado a la frase real del libro.
4. El usuario responde; su acierto o fallo realimenta la programación del siguiente repaso.
5. El usuario puede consultar su progreso por libro, por idioma y por palabra.

### 2.3 Tipos de ejercicio

| Código | Ejercicio | Generación | Fase |
|---|---|---|---|
| `cloze_original` | La frase real del libro con la palabra tapada. El usuario la escribe o la elige. | Determinista | v1 |
| `mcq_definition` | Se muestra la frase del libro y cuatro definiciones; una es correcta. | IA (distractores) | v1 |
| `preposition_cloze` | La frase real con la **preposición** tapada. El usuario elige entre preposiciones. | **Determinista** | v1 |
| `cloze_generated` | Una frase **nueva**, distinta de la del libro, con la palabra tapada. | IA (frase) | v1 |
| `phrasal_verb` | Hueco sobre verbo y partícula, o elección de la partícula correcta. | Determinista + IA | Abierto (§2.5) |
| `sense_discrimination` | Ejercicios sobre acepciones de la palabra que **no** aparecen en el libro. | IA | Abierto (§5.4) |

`cloze_original` y `preposition_cloze` funcionan sin ninguna llamada a un modelo. Esto es deliberado: garantiza que la aplicación sea utilizable desde el primer día y que nunca falle por una caída del proveedor de LLM.

**Sobre `preposition_cloze`.** Es el ejercicio con mejor relación entre valor y coste de todo el proyecto. La respuesta correcta ya está en la frase, y los distractores son otras preposiciones tomadas de un conjunto cerrado de unas cuarenta, ponderado por la frecuencia observada en el propio corpus del usuario. No hay nada que generar, así que no hay nada que pueda alucinar.

Pedagógicamente es de los más valiosos para un hispanohablante: las preposiciones en inglés no se deducen, se memorizan por colocación, y son un punto de fallo persistente en niveles intermedios.


### 2.5 Unidades léxicas multipalabra

**El problema.** El Kindle guarda una sola palabra, pero el significado no siempre reside en ella. Si el usuario consulta `eased` en *"electronics eased out hydraulics"*, la base de datos almacena `eased` con lema `ease`. Un ejercicio construido sobre esa palabra enseñaría *aliviar* o *facilitar*, cuando el significado real de `ease out` es *desplazar*.

**Esto no es una funcionalidad que falta: es la aplicación enseñando algo falso.** Por eso la guarda es obligatoria y no opcional.

**La guarda (obligatoria, F0).** Antes de generar cualquier ejercicio, determinar si la palabra consultada forma parte de una unidad léxica mayor en su contexto. Si es así, el ejercicio se construye sobre la unidad completa.

**El tipo de ejercicio (abierto, F7).** `phrasal_verb`: hueco que cubre verbo y partícula, o elección de la partícula correcta entre varias. Depende de disponer de una fuente léxica fiable, igual que §5.4.

**El problema difícil es la detección, no la generación.** Una regla ingenua de "palabra seguida de partícula" da un **80 % de falsos positivos** sobre el corpus real: `sojourn in`, `gravestones in`, `stake in` o `tycoons in` son sustantivo más preposición, no verbos frasales. Enfoque previsto, en este orden:

1. **Análisis de dependencias con spaCy.** En inglés la partícula de un verbo frasal lleva una relación de dependencia distinta de la de una preposición ordinaria. Es determinista y separa `eased out` de `stake in`. *No está confirmada su precisión sobre este corpus; hay que medirla.*
2. **Lista de phrasal verbs frecuentes** como refuerzo. Muy fiable para los comunes, nula para los raros.
3. **LLM solo como último recurso.** Preguntar a un modelo si algo es un phrasal verb tiende a producir falsos positivos, así que no puede ser la primera línea.

**Relación con §5.4.** Un phrasal verb es un caso particular del problema de desambiguación de acepción: la unidad de significado no coincide con la palabra almacenada. Ambos comparten la misma dependencia de una fuente léxica.

### 2.4 Practicidad

La aplicación es útil sin conexión a ningún servicio externo: el ejercicio determinista y la programación de repasos funcionan en local con el modelo de lenguaje ejecutándose en la propia máquina. Esto no es un detalle técnico, es una decisión de producto: el usuario no depende de una cuenta ni de una factura para estudiar.

---

## 3. Alcance

### 3.1 Dentro del alcance de la v1

- Importación de `vocab.db` de Kindle.
- Normalización: lematización, categoría gramatical, limpieza de ruido, segmentación a frase completa.
- Los tres tipos de ejercicio marcados como v1 en §2.3.
- Repetición espaciada con FSRS.
- Interfaz web mínima y funcional.
- Capa de validación de las salidas del modelo, con reintento y degradación.
- Conjunto de evaluación automática y observabilidad de coste y latencia.
- Ejecución completa en local mediante contenedores.
- Despliegue en un entorno de producción.

### 3.2 Fuera del alcance de la v1

- Autenticación y gestión de usuarios (el esquema estará preparado; ver §3.3.3).
- Aplicación móvil.
- Sincronización automática con el Kindle.
- Ejercicios de audio o pronunciación.
- Gamificación (rachas, insignias, tablas de clasificación).
- Ejercicios sobre acepciones no presentes en el libro (§5.4).

**Nota sobre el conflicto de objetivos**: como usuario, el autor querrá varias de estas funciones. Como candidato, ninguna aporta. Se anotan en un archivo `IDEAS.md` y no se implementan hasta que el objetivo profesional esté cubierto.

### 3.3 Los cuatro desacoplamientos obligatorios

Estas tres decisiones son baratas ahora y caras después. Por eso están en el alcance a pesar del principio general de mantener el alcance mínimo.

#### 3.3.1 Idioma

**Decisión: el idioma es un dato, nunca una rama del código.**

- La v1 se lanza **solo con inglés** (753 de las 1.345 palabras del corpus real). Motivo doble: reduce a la mitad el trabajo de diseño de prompts y de evaluación, y el inglés es el idioma que el autor necesita reforzar.
- Toda entidad lleva su columna `lang`. Los generadores de ejercicios son agnósticos al idioma.
- Los *prompts* viven en archivos de plantilla versionados, indexados por `(tarea, idioma)`. Añadir español consiste en añadir plantillas y un modelo de spaCy, no en tocar la lógica.
- El conjunto de evaluación también se indexa por idioma: las métricas se calculan por idioma, nunca agregadas.

**Advertencia honesta**: los *prompts* no se traducen, se rediseñan. Un *prompt* afinado para inglés rendirá peor en español, y habrá que medirlo de nuevo. El desacoplamiento evita reescribir código, no evita rehacer el trabajo de *prompting*. Añadir español es aproximadamente una semana, no una tarde.

#### 3.3.2 Fuente de datos

**Decisión: patrón de puertos y adaptadores. `KindleVocabImporter` es una implementación, no el núcleo.**

Se define un modelo canónico interno (§4.3) y una interfaz de importación:

```
VocabularyImporter (puerto)
  ├── KindleVocabImporter   (v1)
  ├── CsvImporter           (futuro — estimado en < 1 día)
  └── AnkiImporter          (futuro)
```

El dominio no conoce SQLite, ni el esquema del Kindle, ni la palabra "Kindle". Todo lo específico del Kindle vive en el adaptador.

Coste de hacerlo ahora: bajo, del orden de medio día. Coste de hacerlo después: reescribir el modelo de datos y todos los generadores. Además, es continuidad directa de la arquitectura hexagonal que el autor ya ha trabajado profesionalmente, no una técnica nueva.

#### 3.3.3 Entorno

**Decisión: doce factores desde el primer commit.**

| Regla | Motivo |
|---|---|
| PostgreSQL desde el día 1, no SQLite | Migrar después cuesta más que empezar bien |
| Toda la configuración por variables de entorno | Cero rutas absolutas, cero credenciales en código |
| Todo en contenedores desde el día 1 | Lo que corre en local es la misma imagen que en producción |
| El proveedor de LLM detrás de una interfaz | Cambiar de Ollama a una API es una variable de entorno |
| Migraciones con Alembic | El esquema es código versionado |
| Almacenamiento de ficheros por interfaz | Disco en local, almacenamiento de objetos en producción |
| Sin estado en el proceso de la aplicación | Requisito para escalar horizontalmente |

**Lo que sí cambiará al desplegar, y es inevitable**: la GPU no viaja. En local el modelo corre en la RTX 4070; en producción, alquilar GPU es caro, así que se usará una API. Esto significa que el sistema desplegado **no es el mismo que el desarrollado**, y un *prompt* validado con un modelo puede fallar con otro.

Esto no es un problema del diseño: es la razón principal por la que el conjunto de evaluación (§6) debe existir **antes** del primer cambio de proveedor. Sin él, el cambio es a ciegas.

#### 3.3.4 Modelo

**Decisión: el modelo es configuración por tarea, no una constante del código.**

El desacoplamiento del §3.3.3 permite cambiar de proveedor. Este permite algo distinto y más útil: **usar modelos diferentes para tareas diferentes, y cambiarlos sin tocar código**.

Es previsible que haga falta. Los tres usos de IA (§5.2) tienen requisitos opuestos:

| Tarea | Prioriza | Perfil de modelo probable |
|---|---|---|
| A1 · Distractores | Velocidad y coste | Pequeño, sin razonamiento |
| A2 · Frases nuevas | Calidad de redacción | Intermedio |
| A3 · Juez semántico | Precisión de juicio | Mayor, posiblemente con razonamiento |

Forzar el mismo modelo en las tres es una decisión que no se querrá mantener.

**Implementación.** Una tabla de configuración indexada por tarea, resuelta por variables de entorno:

```
# Modelos orientativos (pueden cambiarse en el futuro para utilizar el más 
# adecuado para cada tarea)
LLM_TASK__DISTRACTORES__PROVIDER=ollama
LLM_TASK__DISTRACTORES__MODEL=qwen3.5:4b
LLM_TASK__DISTRACTORES__THINK=false
LLM_TASK__DISTRACTORES__PROMPT_VERSION=v3

LLM_TASK__JUEZ__PROVIDER=openai
LLM_TASK__JUEZ__MODEL=<modelo comercial>
LLM_TASK__JUEZ__THINK=true
LLM_TASK__JUEZ__PROMPT_VERSION=v2
```

El dominio invoca `llm.run("distractores", entrada)` y no conoce el modelo, el proveedor ni el endpoint.

**Cuatro reglas que lo hacen efectivo:**

1. **Ningún nombre de modelo en el código.** Si aparece `qwen3.5:4b` en un `.py`, el desacoplamiento ha fallado.
2. **Los parámetros específicos de proveedor viven en la configuración de la tarea**, no en la lógica. `think`, temperatura y `num_predict` son configuración. Un `think=False` escrito en el código acopla la aplicación a Qwen3.5.
3. **Los prompts fuera del código**, en archivos versionados indexados por `(tarea, idioma, versión)`. Cambiar un prompt no debe ser un commit de código. Esto ya era necesario para el desacoplamiento por idioma (§3.3.1); aquí se refuerza.
4. **Cada ejercicio generado registra qué configuración lo produjo.** La tabla `exercises` ya guarda `generator`, `model` y `prompt_version` (§4.3). Sin eso, comparar configuraciones es imposible.

**Consecuencia sobre la evaluación.** Si las configuraciones son intercambiables, el arnés (§6) debe poder ejecutar el mismo conjunto de casos bajo varias y comparar los resultados. Eso convierte el desacoplamiento en algo medible en lugar de teórico, y hace que la comparativa local frente a API de la F6 sea una ejecución más del arnés en vez de un trabajo aparte.

**El límite, dicho con claridad.** Cambiar de modelo **no** va a ser gratis, y este documento no lo promete. Los *prompts* no son portables: uno afinado para Qwen3.5 puede rendir peor con un modelo comercial, y algunos parámetros solo existen en un proveedor. Lo que sí se garantiza es que **cambiar de modelo sea modificar configuración y volver a medir**, en lugar de refactorizar. Sin el arnés de evaluación, este desacoplamiento no sirve de nada: permitiría cambiar de modelo a ciegas.

---

## 4. Datos de partida

### 4.1 Contenido real del corpus

Análisis del archivo `vocab.db` del autor (agosto 2026):

| Métrica | Valor |
|---|---|
| Palabras únicas | 1.345 |
| Consultas totales | 1.511 |
| Libros distintos | 25 |
| Reparto por idioma | 753 inglés · 592 español |
| Rango temporal | julio 2024 → agosto 2026 |
| Consultas con frase de contexto | 1.511 de 1.511 (100 %) |
| Longitud media de la frase | 178 caracteres |
| Palabras con una sola consulta | 1.212 de 1.345 |

**Dato crítico para el diseño**: la palabra consultada aparece **literalmente** dentro de su frase de contexto en el 100 % de los casos. Esto hace que el ejercicio de hueco (`cloze_original`) sea una sustitución de cadena trivial y perfectamente fiable, sin ninguna necesidad de modelo de lenguaje.

**Volumen**: 1.345 palabras son suficientes de sobra para la aplicación y del todo insuficientes para entrenar nada. Queda confirmado que este es un proyecto de **inferencia, orquestación y evaluación**, no de entrenamiento.

### 4.2 Problemas de calidad detectados

Estos tres problemas son reales, están medidos sobre el corpus del autor y requieren trabajo explícito en la fase de ingesta.

**1. La columna `pos` no es la categoría gramatical.** Contiene identificadores de posición dentro del libro, con valores del tipo `AfyTAABqAAAA:3573613`. La categoría gramatical debe derivarse con spaCy analizando la palabra en su frase. Es un error fácil de cometer por el nombre de la columna.

**2. Frases truncadas: caso marginal.** El Kindle guarda la frase completa. 1.421 de 1.511 contextos terminan en punto, y solo 28 (1,9 %) no acaban en puntuación reconocible, la mayoría porque terminan con el corchete de una nota al pie. Frases realmente cortadas a mitad: unas 5 o 6 de 1.511.

Se necesita igualmente una etapa de recorte a frase completa con el segmentador de spaCy, pero es una salvaguarda, no trabajo mayoritario. Si tras el recorte la palabra objetivo no sobrevive en un contexto utilizable, la entrada se marca como sin contexto y solo admite ejercicios de tipo `cloze_generated`.

**3. Ruido por toques accidentales.** Entre las palabras del corpus aparecen "En" y "Salvo", que son pulsaciones involuntarias sobre palabras funcionales. Filtrarlas mediante listas de palabras vacías por idioma es trabajo obligatorio; sin él, la aplicación pedirá al usuario que estudie preposiciones que ya conoce.

**4. La columna `category`.** Toma el valor 0 en 1.344 registros y 100 en uno. La interpretación probable es "en aprendizaje" frente a "dominada", pero *no estoy seguro* y conviene verificarlo antes de darle uso.

### 4.3 Modelo de datos canónico

Independiente de la fuente. Nombres orientativos.

```
users            (id, created_at)
sources          (id, user_id, kind, filename, checksum, imported_at)
entries          (id, user_id, source_id, term, lemma, lang, pos, first_seen_at)
                 UNIQUE (user_id, lemma, lang)
contexts         (id, entry_id, raw_sentence, clean_sentence, is_truncated,
                  book_title, book_lang, captured_at)
exercises        (id, entry_id, context_id, kind, lang, payload,
                  generator, model, prompt_version, validation_report, created_at)
reviews          (id, entry_id, exercise_id, rating, answered_at)
scheduling_state (entry_id, stability, difficulty, due_at, reps, lapses)
eval_runs        (id, dataset_version, model, prompt_version, metrics, created_at)
```

Notas de diseño:

- `user_id` está presente desde el principio aunque la v1 sea monousuario. Añadir autenticación después será una migración, no una reescritura.
- `exercises` guarda `model` y `prompt_version` junto al ejercicio. Sin eso es imposible saber después qué configuración produjo qué resultado, y la evaluación pierde sentido.
- `contexts` conserva la frase original **y** la limpia. Nunca se destruye el dato de partida.

---

## 5. Dónde se usa IA y dónde no

Esta es la sección central del documento. La decisión por defecto es **no usar un modelo de lenguaje**; cada uso debe justificarse individualmente.

### 5.1 Tabla de decisión

| Componente | ¿IA? | Implementación | Razón |
|---|---|---|---|
| Lectura e importación del archivo | **No** | SQL | Es un parseo. |
| Detección de idioma | **No** | Columna `lang` del origen | El dato ya viene. |
| Lematización y categoría gramatical | **No** | spaCy | Herramienta especializada, determinista y más barata. |
| Filtrado de ruido | **No** | Listas de palabras vacías | Un `if` resuelve el problema. |
| Segmentación a frase completa | **No** | Segmentador de spaCy | Problema resuelto por herramientas existentes. |
| Qué palabras repasar hoy | **No** | FSRS | Algoritmo publicado y validado empíricamente. Un LLM sería más lento, más caro y peor. |
| Ejercicio de hueco original | **No** | Sustitución de cadena | La palabra está en la frase el 100 % de las veces (§4.1). |
| Corrección de la respuesta del usuario | **No** | Comparación de cadenas | Determinista por definición. |
| Traducción de la palabra | **No** | API de diccionario | Más barato, más rápido y más fiable que un LLM. |
| **Distractores plausibles** | **Sí** | LLM + validación | §5.2 |
| **Frases nuevas de práctica** | **Sí** | LLM + validación | §5.2 |
| **Validador semántico (juez)** | **Sí** | LLM | §5.2 |
| Acepciones no presentes en el libro | **Sí** | LLM | §5.4 — punto abierto |

Estimación: entre el 60 % y el 70 % del sistema no ejecuta ninguna llamada a un modelo de lenguaje. **Esto es una característica del diseño, no una carencia**, y es el argumento técnico más fuerte del proyecto en una entrevista.

### 5.2 Justificación de cada uso de IA

#### A1 — Generación de distractores plausibles

**Qué hace.** Dada una palabra, su frase de contexto y su definición correcta, genera tres definiciones falsas que sean verosímiles pero inequívocamente incorrectas.

**Por qué aporta valor al producto.** Un test de opción múltiple solo evalúa algo si los distractores son difíciles. Con distractores obvios, el usuario acierta sin saber la palabra y el ejercicio no enseña nada.

**Alternativa determinista y por qué no basta.** Se pueden tomar definiciones de otras palabras del propio vocabulario del usuario. Funciona, y de hecho **es el mecanismo de degradación** cuando el modelo falla (§7.3). Pero produce distractores de dificultad irregular, a menudo de categoría gramatical distinta, lo que los delata.

**Honestidad sobre esta decisión**: *no estoy seguro de que el LLM gane a un enfoque con embeddings más filtro por categoría gramatical*. Podría ser comparable y mucho más barato. Esto es una virtud del proyecto, no un problema: da una comparativa real que medir con el conjunto de evaluación, y "probé las dos y estos son los números" es una respuesta mucho mejor que "usé un LLM".

**Dependencia importante.** Para generar buenos distractores hay que saber en qué acepción se usa la palabra en esa frase. En el corpus real aparece «Salvo los internados en un manicomio», donde "salvo" es preposición y no el verbo salvar. Los distractores de una acepción no sirven para la otra. Por tanto, **una desambiguación mínima de acepción es un requisito implícito de A1**, aunque no figure como funcionalidad visible.

#### A2 — Generación de frases nuevas de práctica

**Qué hace.** Genera una frase nueva, distinta de la del libro, que use la palabra en la misma acepción y a un nivel de dificultad similar.

**Por qué aporta valor al producto.** Si el usuario ve siempre la misma frase, acaba memorizando la frase y no la palabra. La variación de contexto es lo que produce aprendizaje transferible.

**Alternativa determinista.** No existe. No hay forma de producir contextos nuevos y correctos sin un modelo generativo.

**Riesgo principal.** Es el punto donde una alucinación llega directamente al usuario: una frase que use la palabra en una acepción equivocada le enseña algo falso. De ahí que A2 no pueda existir sin A3.

#### A3 — Validador semántico (juez)

**Qué hace.** Verifica lo que el código no puede: que exactamente una opción sea correcta, que los distractores sean falsos sin ambigüedad, y que la frase generada use la palabra en la acepción del libro.

**Por qué es obligatorio.** Los validadores deterministas (§6.1) detectan filtraciones léxicas, idioma incorrecto o categoría gramatical inconsistente, pero no pueden juzgar si una definición es semánticamente correcta.

**Nota metodológica.** Un juez basado en LLM tiene sus propios sesgos y no es un oráculo. Se usa como una señal más dentro del conjunto de métricas, nunca como criterio único, y su acuerdo con el juicio humano debe medirse sobre una muestra etiquetada a mano.

### 5.3 Dónde la IA estaría metida con calzador

Se documenta explícitamente para no caer en ello:

- **Un chatbot tutor conversacional.** Suena bien en un README, no aporta nada al objetivo de aprender vocabulario y multiplica coste y superficie de fallo.
- **Un sistema multiagente con roles** (agente profesor, agente evaluador, agente motivador). El problema no lo requiere. Ante un entrevistador competente, resta.
- **Un LLM decidiendo qué repasar.** FSRS lo hace mejor, gratis y en milisegundos.
- **Un LLM traduciendo.** Un diccionario es superior en las tres dimensiones que importan.

### 5.4 Punto abierto: ejercicios sobre acepciones no consultadas

**Qué sería.** Dada una palabra que el usuario consultó en una acepción concreta, enumerar sus otras acepciones habituales y generar ejercicios sobre ellas, aunque no aparezcan en ningún libro leído.

**Por qué es atractivo.** Es la funcionalidad que más se aleja de lo que ya existe en el mercado y la que mejor aprovecha lo que un LLM sabe y una base de datos de vocabulario no.

**Por qué no entra en la v1.** Tiene tres dependencias que no son triviales:

1. Requiere desambiguación explícita de acepción, que en la v1 solo existe de forma implícita dentro de A1.
2. Requiere una fuente de acepciones fiable. Un LLM enumerando acepciones alucina; probablemente haga falta un diccionario estructurado como referencia. *No estoy seguro de qué diccionario libre y con licencia adecuada existe para inglés con la calidad necesaria*; es algo que hay que investigar antes de comprometerse.
3. Requiere métricas de evaluación propias: cobertura de acepciones, y ausencia de acepciones inventadas.

**Decisión.** Queda registrada como evolución prioritaria post-v1. El modelo de datos la contempla: `exercises` ya admite un `kind` nuevo y `contexts` permite contextos no procedentes de un libro (`book_title` nulo). Esa previsión cuesta cero ahora.

---

## 6. Evaluación y observabilidad

Esta capa es el núcleo diferenciador del proyecto y la continuación directa de la metodología del TFM del autor.

### 6.1 Métricas deterministas

Se calculan con código, sin llamar a ningún modelo. Son el equivalente a la métrica de Exactitud de Entidades del TFM: deterministas, independientes del estilo del generador.

| ID | Métrica | Qué detecta |
|---|---|---|
| D1 | Filtración léxica | La respuesta correcta aparece dentro de algún distractor |
| D2 | Homogeneidad gramatical | Distractores con categoría gramatical distinta de la respuesta (spaCy) |
| D3 | Idioma correcto | Alguna opción o frase generada no está en el idioma objetivo |
| D4 | Presencia del término | En frases generadas, el término aparece con una flexión válida |
| D5 | Fidelidad al contexto | En `cloze_original`, la frase coincide carácter a carácter con la del libro |
| D6 | No repetición | El ejercicio no duplica uno mostrado en los últimos N días |
| D7 | Distractores no triviales | Distractores que son antónimos o negaciones de la respuesta correcta y se descartan sin conocer la palabra (detectado en §12.4) |
| D8 | Unidad léxica correcta | Ejercicios generados sobre una palabra que en su contexto formaba parte de una unidad mayor (phrasal verb, locución). Error grave: enseña un significado falso |
| D9 | Colocación real | En `preposition_cloze`, ejercicios donde la preposición no depende sintácticamente de la palabra objetivo, sino de la estructura de la frase |

### 6.2 Métricas con juez

| ID | Métrica | Qué detecta |
|---|---|---|
| J1 | Unicidad de la respuesta | Más de una opción es defendible como correcta |
| J2 | Plausibilidad de distractores | Distractores obvios que no evalúan nada |
| J3 | Fidelidad de acepción | La frase generada usa el término en otra acepción |

### 6.3 Métricas operativas

| ID | Métrica |
|---|---|
| O1 | Coste por ejercicio generado |
| O2 | Latencia p50 y p95 |
| O3 | Tasa de reintento y tasa de degradación a plantilla |

### 6.4 Conjunto de evaluación

- **Tamaño objetivo**: 100 casos congelados, muestreados del corpus real, cubriendo distintos libros, longitudes de frase y categorías gramaticales.
- **Versionado**: el conjunto se versiona en el repositorio. Cambiar el conjunto invalida las comparaciones anteriores.
- **Etiquetado humano**: un subconjunto de unos 30 casos se etiqueta a mano para medir el acuerdo del juez.
- **Ejecución**: mediante `pytest`, en local y en integración continua.
- **Informe**: cada ejecución genera un informe con las métricas por idioma, por modelo y por versión de *prompt*.

---

## 7. Stack tecnológico

### 7.1 Decisiones

Cada elección lleva su justificación. La columna "Demanda" refleja el número de ofertas, sobre 29 analizadas en el mercado español de IA, que mencionan esa tecnología o categoría.

| Capa | Elección | Demanda | Justificación |
|---|---|---|---|
| Lenguaje del backend | **Python 3.12** | 25/29 | Estándar absoluto en IA. Es donde está el ecosistema y el mercado. |
| Framework del backend | **FastAPI** | — | Estándar de facto para servicios de IA. Tipado, validación con Pydantic y OpenAPI automático. |
| Validación y esquemas | **Pydantic v2** | — | Base de las salidas estructuradas. Un modelo que no puede rellenar el esquema es un fallo detectado antes de mirar el contenido. |
| Base de datos | **PostgreSQL 16** | 10/29 | Desde el día 1. La extensión `pgvector` queda disponible por si A2 o §5.4 requieren búsqueda semántica. |
| ORM y migraciones | **SQLAlchemy 2 + Alembic** | — | Estándar del ecosistema Python. |
| Frontend | **Angular + TypeScript** | 7/29 (TS) | El autor ya lo domina: coste de aprendizaje cero. La interfaz no es donde está el valor del proyecto. |
| Modelo local | **Qwen3.5-4B (Q4) sobre Ollama** | — | Validado en §12. Frente a Qwen3-4B: la mitad de tokens, respeta el idioma del prompt y acepta `think:false` de verdad. |
| Endpoint local | **`/api/chat` nativo con `format`** | — | **No** el endpoint `/v1/` compatible con OpenAI: no propaga `think` y, con Qwen3, `think:false` mueve el razonamiento al campo `content` en lugar de suprimirlo (§12.3). |
| Cliente de LLM | Interfaz propia `LLMProvider` + registro de tareas | — | Adaptador nativo de Ollama y adaptador OpenAI. La configuración se resuelve por tarea (§3.3.4), no globalmente. Es obligatoria porque los dos endpoints no son intercambiables. |
| NLP | **spaCy** | 6/29 (NLP) | Lematización, categoría gramatical y segmentación de frases. Ya figura en el CV del autor. |
| Repetición espaciada | **`fsrs`** (PyPI, v6.3.2) | — | Algoritmo publicado y mantenido. Reimplementarlo sería tiempo perdido. |
| Observabilidad | **Langfuse** (autohospedado) | 10/29 | Trazas, coste y latencia por petición. Open source, se levanta en el mismo `compose`. |
| Orquestación | **LangGraph** | 7/29 | **Solo** en el bucle de generación (§7.3), a partir de la fase F5. Nunca en un flujo lineal. |
| Evaluación | **pytest** + arnés propio | 6/29 (evals) | El arnés propio traslada la metodología del TFM y es más defendible que una herramienta genérica. |
| Contenedores | **Docker + Compose** | 9/29 | Todo, desde el primer commit. |
| Integración continua | **GitHub Actions** | 7/29 | Tests, linter y ejecución del arnés de evaluación en cada PR. |
| Producción | **Azure Container Apps** | 11/29 (Azure) | Azure es el proveedor más pedido en la muestra analizada. Alternativas equivalentes: Railway, Fly.io, Hetzner. |

### 7.2 Descartados y por qué

| Descartado | Motivo |
|---|---|
| SQLite en producción | Migrar después es más caro que empezar con Postgres. Se usa solo como formato de **entrada** (el `vocab.db`). |
| `instructor` (PyPI, v1.16.0) | Buena librería, pero oculta exactamente el bucle de validación y reintento que constituye el aprendizaje central del proyecto. Se usa Pydantic y se implementa el bucle a mano. |
| CrewAI / AutoGen | El problema no requiere autonomía multiagente. Sería complejidad injustificada. |
| Kubernetes | Sobredimensionado para una aplicación de un contenedor. |
| Vanilla JS o backend sin framework | No aporta aprendizaje de valor y cuesta tiempo. |
| Frameworks de agentes en la v1 | Introducirlos antes de tener un flujo que lo justifique es exactamente la señal negativa que se quiere evitar. |

### 7.3 El bucle de generación

Es el único componente con estado y control de flujo no lineal, y por tanto el único que justifica LangGraph.

```
Selector FSRS (código)
      ↓
Recuperación de contexto (SQL)
      ↓
Generador (LLM, salida Pydantic)  ←──────┐
      ↓                                   │
Validadores deterministas (D1–D6)         │ reintento con el motivo
      ↓                                   │ del fallo inyectado
Validador semántico (juez, J1–J3)  ───────┘  (máximo 2)
      ↓ si pasa            ↓ si falla 2 veces
  Ejercicio          Plantilla determinista
   al usuario        (distractores del propio vocabulario)
```

**El camino de degradación no es opcional.** El usuario nunca ve un error: si el modelo falla dos veces, recibe un ejercicio de plantilla, peor pedagógicamente pero siempre funcional. Diseñar la degradación es lo que separa un sistema de una demo.

---

## 8. Local y producción

### 8.1 Composición local

Un único `docker compose up` levanta:

| Servicio | Rol |
|---|---|
| `api` | FastAPI |
| `web` | Angular |
| `db` | PostgreSQL |
| `langfuse` + su base de datos | Observabilidad |
| `ollama` | Modelo local sobre WSL2 con acceso a la GPU (validado, §12.1) |

El servicio `ollama` es el único que se sustituye en producción por una variable de entorno apuntando a un proveedor externo. Los demás son idénticos.

### 8.2 Qué cambia al desplegar

Solo esto:

1. `LLM_BASE_URL` y `LLM_API_KEY` apuntan a un proveedor comercial en lugar de a Ollama.
2. `DATABASE_URL` apunta a un Postgres gestionado.
3. El almacenamiento de archivos subidos pasa de disco a almacenamiento de objetos, a través de la interfaz ya existente.
4. Se activan límites de gasto y de peticiones por IP.

Si alguna de estas cuatro cosas exige tocar código de dominio, el desacoplamiento ha fallado y hay que corregirlo, no parchearlo.

### 8.3 Riesgo asumido

Cambiar de modelo cambia el comportamiento del sistema. Un *prompt* validado con Qwen3 en local puede degradarse con un proveedor comercial. **Por eso el conjunto de evaluación (§6) debe estar operativo antes del primer despliegue**, y la comparativa entre modelo local y API es un entregable del proyecto (fase F6), no un extra.

---

## 9. Planificación

Ritmo asumido: 10–20 h semanales, en paralelo a la búsqueda activa de empleo. La ordenación prioriza **llegar cuanto antes a las partes que dan material de entrevista**, sacrificando la interfaz web hasta que el núcleo esté hecho.

| Fase | Semanas | Entregable | Material de entrevista que desbloquea |
|---|---|---|---|
| **F0 · Cimientos** | 1 | Ingesta a Postgres, normalización con spaCy, limpieza, recorte de frases. `compose` completo. CLI que muestra `cloze_original`. | Ingesta y calidad de datos sobre datos reales y sucios. |
| **F1 · Primera IA** | 2–3 | Generación de distractores (A1) con salida Pydantic, validadores D1–D4, bucle de reintento y degradación. Sigue siendo CLI. | Salidas estructuradas, validación, reintento con feedback, diseño de la degradación. |
| **F2 · Medición** | 3–4 | Langfuse integrado. Arnés de evaluación con 100 casos y métricas deterministas. Informe versionado. | Evaluación de LLMs, coste y latencia por petición, metodología propia. **El diferenciador.** |
| **F3 · Producto** | 4–5 | API FastAPI, interfaz Angular mínima, FSRS conectado. **La aplicación pasa a ser usable a diario.** | Sistema completo de extremo a extremo. |
| **F4 · Segunda IA** | 5–6 | Frases nuevas de práctica (A2) y juez semántico (A3, métricas J1–J3). Acuerdo del juez con etiquetado humano. | Generación anclada a contexto, LLM como juez y sus límites. |
| **F5 · Orquestación** | 6–7 | El bucle migrado a LangGraph, con justificación documentada de por qué solo ahí. | LangGraph, grafos con estado, criterio sobre cuándo no usarlos. |
| **F6 · Producción** | 7–8 | Despliegue en Azure, CI/CD, comparativa local frente a API con números. | Despliegue real, CI/CD, comparativa de coste y calidad entre modelos. |
| **F7 · Abierto** | — | Acepciones no consultadas (§5.4), importador CSV, español, servidor MCP. | Según lo que se implemente. |

**Puntos de parada.** Cada fase deja algo defendible. Si en la semana 4 aparece una oferta, se acepta y el proyecto continúa a menor ritmo sin haber perdido nada. Las fases F0–F2 concentran aproximadamente el 70 % del valor profesional del proyecto.

**Sobre la ausencia de interfaz hasta F3**: es deliberado. Una CLI es perfectamente utilizable para estudiar y evita gastar en la capa donde el autor no aprende nada nuevo.

---

## 10. Riesgos

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Ampliación del alcance por el objetivo de producto | Alto | `IDEAS.md`. El objetivo profesional manda hasta F3. |
| Tiempo desviado a la interfaz | Alto | Interfaz aplazada a F3 y presupuestada en menos del 15 % del total. |
| El *prompt* no transfiere entre modelos | Medio | Arnés de evaluación operativo antes del cambio (F2 antes de F6). |
| El juez basado en LLM no es fiable | Medio | Medir su acuerdo con etiquetado humano; nunca usarlo como criterio único. |
| Coste de API descontrolado en producción | Medio | Tope duro de gasto, cuota por IP, caché de ejercicios generados. |
| Demo pública caída o lenta | Medio | Si no se puede garantizar disponibilidad, publicar solo el repositorio. |

### 10.1 Consideraciones legales

**Datos personales.** Si terceros suben su propio archivo de vocabulario, se están tratando datos personales y aplica el RGPD. Para la v1 monousuario en local no aplica. Para una demo pública, la vía simple es un modo de demostración con datos de ejemplo y sin persistencia para visitantes.

**Contenido de terceros.** Las frases de contexto son fragmentos literales de libros con derechos de autor. Para uso personal el riesgo es despreciable. Para un servicio comercial que almacene y muestre esos fragmentos, la situación no es evidente. **No soy abogado y no puedo valorar este punto**; si se plantea la comercialización, hay que consultarlo con un profesional antes de invertir en esa dirección.

---

## 11. Supuestos y preguntas abiertas

### Supuestos asumidos en este documento

1. La v1 es monousuario y sin autenticación, con el esquema preparado para multiusuario.
2. El desarrollo es 100 % local con Ollama dentro de WSL2 sobre la GPU del portátil; el despliegue usa una API comercial.
3. La v1 cubre solo inglés; el español entra en F7.
4. El autor dispone de 10–20 h semanales.

### Preguntas que deben resolverse antes de F0

1. ~~¿Cuánta VRAM tiene la RTX 4070?~~ **Resuelto (§12.1)**: 8.188 MiB totales, ~6,9 GiB disponibles. Descarta modelos de más de 9B.
2. **¿Hay cuenta o crédito de Azure disponible?** Si no, conviene decidir el destino de despliegue ahora, porque afecta al `compose` y a la configuración.
3. **¿Qué presupuesto hay para llamadas a API** en la fase de comparativa (F6)? Determina el tamaño del conjunto de evaluación y el número de configuraciones comparables.
4. **¿Se contempla realmente la comercialización?** Si sí, la autenticación y el RGPD suben de prioridad y conviene decidir la licencia del repositorio desde el principio.

### Preguntas que pueden resolverse durante el desarrollo

5. ¿Qué fuente de definiciones y acepciones usar para inglés, con licencia compatible? (bloqueante solo para §5.4)
6. ¿Los distractores generados por LLM superan a un enfoque con embeddings más filtro gramatical? Se responde con el arnés en F2.
7. ¿Qué significa exactamente la columna `category` del `vocab.db`?

---

## 12. Resultados de las pruebas previas de entorno

Ejecutadas antes de la F0 sobre el equipo real. Todo lo de esta sección está **medido**, no estimado.

### 12.1 Hardware y paso de GPU

| Dato | Valor |
|---|---|
| GPU | NVIDIA RTX 4070 Laptop |
| VRAM total | 8.188 MiB |
| VRAM disponible para el modelo | ~6,9 GiB |
| Driver / CUDA | 566.07 / 12.7 |
| Entorno | WSL2 con Ubuntu 24.04, GPU accesible |

Ollama carga las 37 capas del modelo de 4B en GPU (`offloaded 37/37`). Velocidad medida con Qwen3-4B: **65 tokens/s**.

**Consecuencia**: quedan descartados los modelos de más de 9B. Un 9B en Q4 ocuparía unos 6,6 GB de los 6,9 disponibles y no dejaría margen para la caché de contexto.

**Nota de instalación**: Ollama debe ir **dentro de WSL2**, no en Windows. La instalación en Windows solo escucha en `127.0.0.1` y no es accesible desde WSL sin abrir la red y el cortafuegos. La instalación en Linux requiere el paquete `zstd` como dependencia previa.

### 12.2 Salidas estructuradas: fiables

Cinco ejecuciones consecutivas con un esquema JSON: **5 de 5 válidas**, con la forma exacta y siempre tres distractores. El diseño de validación de §7.3 se mantiene sin cambios.

### 12.3 Razonamiento: la decisión con más impacto medido

| Configuración | Tokens | Tiempo | Campo `content` |
|---|---|---|---|
| Qwen3-4B, razonamiento por defecto | 2.503 | 44,5 s | Limpio |
| Qwen3-4B con `think:false` vía `/api/chat` | 2.384 | 36,0 s | **Contaminado** |
| Qwen3-4B con `reasoning_effort:none` vía `/v1/` | 2.384 | 36,0 s | **Contaminado** |
| Qwen3.5-4B, razonamiento por defecto | 1.246 | 25,6 s | Limpio |
| **Qwen3.5-4B con `think:false`** | **37** | **1,1 s** | **Limpio** |

Dos conclusiones:

**El razonamiento se desactiva y sale gratis.** Factor 68 en tokens y 40 en tiempo. Traducido al arnés de evaluación: una vuelta de 100 casos pasa de unos 51 minutos a unos 2. Esa diferencia determina cuántas veces se puede iterar sobre un prompt en una tarde.

**Con Qwen3, `think:false` es peligroso.** No suprime el razonamiento: deja de separarlo en el campo `thinking` y lo vuelca dentro de `content`. Una configuración que parece correcta y rompería el parseo en producción. Es el motivo por el que el endpoint elegido es `/api/chat` con Qwen3.5 y no `/v1/`.

**Revisión pendiente**: en la F2 hay que medir si el razonamiento mejora el juez semántico (J1–J3). La hipótesis es que ayuda al que juzga y no al que genera, pero no está comprobada.

### 12.4 Hallazgo: distractores triviales

En 2 de 5 ejecuciones, el modelo generó distractores que eran **antónimos o negaciones** de la respuesta correcta:

> "Incapable of withstanding damage or adversity" · "Prone to breaking down under pressure" · "Lacking the ability to adapt to changing environments"

Un usuario los descarta sin saber qué significa la palabra, solo por la forma negativa. El ejercicio deja de evaluar nada.

Es un modo de fallo no previsto en la v1.0 de este documento, detectado en cinco ejecuciones. Se incorpora como **métrica D7** (§6.1) y es detectable de forma determinista mediante patrones de negación y prefijos privativos.

### 12.5 Configuración de referencia

```json
{
  "model": "qwen3.5:4b",
  "think": false,
  "stream": false,
  "format": { "...": "esquema JSON del ejercicio" },
  "messages": [
    {"role": "system", "content": "Responde unicamente en ingles. Devuelve solo JSON valido."},
    {"role": "user", "content": "..."}
  ]
}
```

Endpoint: `POST http://localhost:11434/api/chat`

**Nota sobre el idioma**: Qwen3.5 detecta el idioma del prompt y responde en él. Con los prompts escritos en español, hay que instruir explícitamente el idioma de salida.
