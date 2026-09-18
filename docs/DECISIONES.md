# Registro de decisiones

Una entrada por decisión no trivial. Formato fijo: **qué se decidió**, **qué se descartó**, **por qué**. Tres líneas bastan.

Se escribe **en el momento de decidir**, no al final de la fase. A las tres semanas ya no se recuerda por qué se hizo algo, y esa es justamente la información que vale.

Este archivo es el material de entrevista del proyecto. Cuando pregunten "¿por qué elegiste X?", la respuesta está aquí.

**Después de cada fase, subir la versión actualizada al proyecto de Claude**, o el asistente trabajará con información obsoleta.

---

## Índice

| ID | Fecha | Fase | Decisión |
|---|---|---|---|
| D-001 | 2026-09-07 | Pruebas previas | Ollama dentro de WSL2, no en Windows |
| D-002 | 2026-09-07 | Pruebas previas | Modelo local: Qwen3.5-4B |
| D-003 | 2026-09-07 | Pruebas previas | Razonamiento desactivado en generación |
| D-004 | 2026-09-07 | Pruebas previas | Endpoint `/api/chat`, no `/v1/` |
| D-005 | 2026-09-07 | Pruebas previas | Nueva métrica D7: distractores triviales |
| D-006 | 2026-09-07 | Pruebas previas | Modelos de más de 9B descartados |
| D-007 | 2026-09-07 | Diseño | El modelo es configuración por tarea, no una constante |
| D-008 | 2026-09-07 | Diseño | Guarda de unidad léxica antes de generar cualquier ejercicio |
| D-009 | 2026-09-07 | Diseño | `preposition_cloze` entra en la v1 y es 100 % determinista |
| D-010 | 2026-09-07 | Diseño | No completar frases con un modelo |
| D-011 | 2026-09-08 | F0 | Bucle de desarrollo en `.venv`, artefacto en contenedor |
| D-012 | 2026-09-09 | F0 | La reimportación es incremental y no toca el progreso |
| D-013 | 2026-09-18 | F0 | El ruido se filtra por lista cerrada, no por categoría gramatical |
| D-014 | 2026-09-18 | F0 | Estado de estudio por entrada, controlado por el usuario |
| D-015 | 2026-09-18 | F0.4 | La lematización se hace en contexto, no sobre la palabra aislada |

---

## D-001 · Ollama se ejecuta dentro de WSL2, no en Windows

**Fecha**: 2026-09-07 · **Fase**: pruebas previas

**Decisión**: instalar Ollama en Ubuntu bajo WSL2.

**Descartado**: Ollama nativo en Windows, accedido desde WSL por la IP del host.

**Por qué**: la instalación de Windows solo escucha en `127.0.0.1` y no es alcanzable desde WSL. Abrirla requiere la variable `OLLAMA_HOST=0.0.0.0`, reiniciar el servicio y una regla de cortafuegos, y aun así la IP del host cambia entre reinicios de WSL. Con Ollama en Linux, `localhost` funciona sin configuración y encaja con el resto del proyecto, que también vive en Linux.

**Coste**: descargar el modelo por duplicado hasta desinstalar el de Windows.

**Nota de instalación**: el instalador requiere `zstd` (`sudo apt install -y zstd`). No usar la versión de snap: suele dar problemas con el acceso a GPU.

**Efecto secundario a limpiar**: si se llegó a definir `OLLAMA_HOST` en Windows, hay que borrarla o el cliente de Windows intentará conectarse a `0.0.0.0` y fallará.

---

## D-002 · Modelo local: Qwen3.5-4B (Q4)

**Fecha**: 2026-09-07 · **Fase**: pruebas previas

**Decisión**: `qwen3.5:4b` como modelo local de desarrollo.

**Descartado**: Qwen3-4B (generación anterior), Qwen3.5-9B, y cualquier modelo de más de 9B.

**Por qué**, con la misma tarea y el mismo prompt:

| Modelo | Tokens por petición | Tiempo | Idioma de salida |
|---|---|---|---|
| Qwen3-4B | 2.503 | 44,5 s | Ignora el idioma del prompt |
| Qwen3.5-4B | 37 (con `think:false`) | 1,1 s | Respeta el idioma del prompt |

Mismo tamaño en disco, generación más reciente, y es el único de los dos que acepta `think:false` correctamente (ver D-003).

**Calidad**: los distractores generados son suficientes para el caso de uso. No hace falta subir de tamaño.

**Revisión**: en la F2, comparar contra Phi-4-mini con el arnés de evaluación. La hipótesis es que un modelo más pequeño y predecible puede ser más fiable en salida estructurada que uno mayor y más creativo. Sin comprobar.

---

## D-003 · Razonamiento desactivado en la generación

**Fecha**: 2026-09-07 · **Fase**: pruebas previas

**Decisión**: `"think": false` en todas las llamadas de generación.

**Descartado**: dejar el razonamiento activado, que es el valor por defecto en Ollama.

**Por qué**: medido con el mismo prompt.

| Configuración | Tokens | Tiempo |
|---|---|---|
| Razonamiento activado | 1.246 | 25,6 s |
| Razonamiento desactivado | 37 | 1,1 s |

Con Qwen3-4B la diferencia era aún mayor: 2.503 tokens y 44,5 s. El 97 % de los tokens generados se descartaba.

**Impacto en el proyecto**: una vuelta del arnés de evaluación con 100 casos pasa de unos 51 minutos a unos 2. Es el factor que más determina cuántas veces se puede iterar sobre un prompt.

**Pendiente de revisar en la F2**: medir si el razonamiento mejora el **juez semántico** (métricas J1–J3). Hipótesis: el razonamiento ayuda a quien juzga, no a quien genera, porque juzgar es una comparación en varios pasos y generar una definición no lo es. **No comprobado.**

---

## D-004 · Endpoint `/api/chat` nativo, no `/v1/chat/completions`

**Fecha**: 2026-09-07 · **Fase**: pruebas previas

**Decisión**: usar el endpoint nativo de Ollama con el esquema en el campo `format`.

**Descartado**: el endpoint compatible con OpenAI con `response_format`, que era el plan original de la propuesta v1.0.

**Por qué**: el endpoint `/v1/` no propaga el parámetro `think`. Y, más grave, con Qwen3 el intento de desactivarlo **no suprime el razonamiento: deja de separarlo en el campo `thinking` y lo vuelca dentro de `content`**.

Es un fallo silencioso. La respuesta parece correcta a nivel de HTTP y rompería el parseo en producción. Se detectó únicamente porque se comprobó el contenido del campo, no solo el código de estado.

**Consecuencia de diseño**: los dos endpoints no son intercambiables, así que la interfaz `LLMProvider` no es opcional. Necesita dos adaptadores reales: uno nativo de Ollama para local y uno OpenAI para producción.

---

## D-005 · Nueva métrica D7: distractores triviales

**Fecha**: 2026-09-07 · **Fase**: pruebas previas

**Decisión**: añadir al arnés de evaluación una métrica determinista que detecte distractores construidos como antónimos o negaciones de la respuesta correcta.

**Origen**: en 2 de 5 ejecuciones de prueba, el modelo generó distractores del tipo *"Incapable of withstanding damage"*, *"Prone to breaking down under pressure"*, *"Lacking the ability to adapt"*. Un usuario los descarta sin conocer la palabra, solo por la forma negativa, así que el ejercicio no evalúa nada.

**Por qué es determinista**: se detecta con patrones de negación y prefijos privativos (`in-`, `un-`, `lacking`, `unable`, `incapable`, `prone to`), sin necesidad de un LLM juez.

**Nota**: es un modo de fallo que no estaba previsto en la propuesta v1.0 y apareció en cinco ejecuciones. Refuerza el argumento de construir el arnés antes de confiar en la generación.

---

## D-006 · Modelos de más de 9B descartados

**Fecha**: 2026-09-07 · **Fase**: pruebas previas

**Decisión**: limitar el modelo local a 4B.

**Por qué**: la RTX 4070 Laptop tiene 8.188 MiB totales, de los que Ollama reporta **~6,9 GiB disponibles**. Un 9B en Q4 ocupa unos 6,6 GB de pesos y no deja margen para la caché de contexto, que crece con la longitud del prompt.

**Velocidad medida**: 65 tokens/s con un 4B, con las 37 capas en GPU.

**Alternativa si hiciera falta más capacidad**: comparar contra una API externa en la F6. Para el volumen del proyecto (unos 5.000 ejercicios en total) el coste de API es de pocos euros, así que no hay razón económica para forzar el hardware.

---

## D-007 · El modelo es configuración por tarea, no una constante del código

**Fecha**: 2026-09-07 · **Fase**: diseño (previa a la F0)

**Decisión**: la elección de proveedor, modelo, parámetros y versión de *prompt* se resuelve por **tarea** (`distractores`, `frases`, `juez`) mediante variables de entorno. El dominio invoca `llm.run("distractores", entrada)` sin conocer qué hay detrás.

**Descartado**: una única variable global de modelo, que era el planteamiento implícito de la propuesta v1.1. Permitía cambiar de proveedor, pero no usar modelos distintos para tareas distintas.

**Por qué**: las tres tareas con IA tienen requisitos opuestos. Los distractores priorizan velocidad y coste; el juez semántico prioriza precisión y probablemente se beneficie del razonamiento, que en generación está desactivado (D-003). Con una configuración global habría que elegir un compromiso malo para las tres.

**Reglas derivadas**:

- Ningún nombre de modelo escrito en código Python.
- `think`, temperatura y `num_predict` son configuración de tarea, no lógica. Un `think=False` en el código acoplaría la aplicación a Qwen3.5.
- Los *prompts* viven en archivos versionados indexados por `(tarea, idioma, versión)`.
- Cada ejercicio guarda `model` y `prompt_version` en la tabla `exercises`. Sin eso, comparar configuraciones es imposible.

**Límite reconocido**: cambiar de modelo no será gratis. Los *prompts* no son portables entre modelos. Lo que se garantiza es que cambiar de modelo sea **modificar configuración y volver a medir**, no refactorizar.

**Dependencia**: este desacoplamiento carece de valor sin el arnés de evaluación de la F2. Sin él, permitiría cambiar de modelo a ciegas, que es peor que no poder cambiarlo.

---

## D-008 · Guarda de unidad léxica antes de generar cualquier ejercicio

**Fecha**: 2026-09-07 · **Fase**: diseño (implementación en F0)

**Decisión**: antes de construir un ejercicio, comprobar si la palabra consultada forma parte de una unidad léxica mayor en su contexto (phrasal verb, locución). Si es así, el ejercicio se construye sobre la unidad completa.

**Descartado**: generar siempre sobre la palabra almacenada, que era el planteamiento implícito hasta la v1.2.

**Por qué**: el Kindle guarda una sola palabra, pero el significado no siempre reside en ella. Ejemplo real del corpus: `eased` en *"electronics eased out hydraulics"*. La aplicación enseñaría *aliviar*, cuando `ease out` significa *desplazar*. **No es una funcionalidad ausente, es la aplicación enseñando algo falso.**

**Incidencia medida**: 5 o 6 casos reales sobre las 845 consultas en inglés del corpus de agosto de 2026 (menos del 1 %). Bajo en volumen, grave en efecto.

**El problema es la detección, no la generación.** Una regla de "palabra seguida de partícula" da **80 % de falsos positivos** sobre el corpus real (`sojourn in`, `stake in`, `tycoons in` son sustantivo más preposición). Orden previsto: dependencias de spaCy, después lista de phrasal verbs frecuentes, y LLM solo como último recurso porque tiende a los falsos positivos.

**Sin verificar**: la precisión del análisis de dependencias sobre este corpus. Es el primer número a medir en la F0.

El riesgo no viene de frases truncadas —solo el 0,7 % lo están— sino de la suciedad de maquetación: notas al pie (`[59]`, `[`) y espacios sobrantes en el 98,5 % de las frases. El análisis se ejecuta sobre la frase ya limpia, así que la limpieza es una precondición de la detección, no un paso independiente.

**Métrica asociada**: D8.

---

## D-009 · `preposition_cloze` entra en la v1 y no usa IA

**Fecha**: 2026-09-07 · **Fase**: diseño (implementación en F0)

**Decisión**: añadir un tipo de ejercicio que tapa la preposición que sigue a la palabra consultada, con distractores tomados de un conjunto cerrado de preposiciones. **Sin ninguna llamada a un modelo.**

**Descartado**: generar los distractores con un LLM. Innecesario: el espacio de candidatos es cerrado (unas cuarenta preposiciones) y se pondera por la frecuencia observada en el propio corpus del usuario.

**Por qué entra en la v1**:

- **Cobertura**: 178 de 845 consultas en inglés (**21 %**) tienen la palabra seguida de preposición, medido sobre el corpus de agosto de 2026. Frente al <1 % de los phrasal verbs, hay volumen de sobra.
- **Coste**: horas de trabajo. Es sustitución de cadena, igual que `cloze_original`.
- **Fiabilidad**: la respuesta correcta está literalmente en la frase. No hay nada que alucinar.
- **Valor pedagógico**: las preposiciones en inglés no se deducen, se memorizan por colocación, y son un fallo persistente en hispanohablantes de nivel intermedio.

**Efecto lateral interesante**: los casos que la detección de phrasal verbs descartaba como falsos positivos (`stake in`, `moats around`, `scattered across`) son verdaderos positivos para este ejercicio. La misma detección sirve para las dos cosas con criterios opuestos.

**Riesgo conocido**: no toda preposición que sigue a una palabra es una colocación. En *"proved resilient after the flood"*, `after` pertenece a la estructura de la oración y no a `resilient`; un ejercicio ahí enseñaría una asociación falsa. Se distingue con análisis de dependencias de spaCy y se mide con **D9**.

**Consecuencia sobre el proyecto**: la proporción de la aplicación que no requiere modelos sube por encima del 70 %. Refuerza el argumento central de §5: la decisión por defecto es no usar un LLM.

---

## D-010 · No completar frases truncadas con un modelo

**Fecha**: 2026-09-07 · **Fase**: diseño

**Decisión**: cuando el contexto de una palabra no sea utilizable, no se reconstruye. La entrada se marca como sin contexto y solo admite ejercicios de tipo `cloze_generated`, que se presentan explícitamente como frases nuevas de práctica.

**Descartado**: usar un LLM para completar la frase del libro y así no dejar ninguna palabra sin ejercicio.

**Por qué**: el texto que falta existe en el libro pero no en la base de datos. Un modelo no puede recuperarlo, solo fabricar algo verosímil. La aplicación estaría presentando como *"la frase de tu libro"* algo que el autor nunca escribió, que es exactamente la alucinación que el proyecto se propone medir y evitar.

**Por qué el coste no es el argumento**: el problema afecta a unas 5 o 6 frases de 1.511. Generar esas seis costaría céntimos. La objeción es de integridad del producto, no económica.

**Alternativa ya prevista en el diseño**: `cloze_generated` cubre estos casos sin inventar nada, porque la frase se presenta como generada y no como auténtica. Ninguna palabra se queda sin ejercicio.

---

## D-011 · Bucle de desarrollo en `.venv`, artefacto oficial en contenedor

**Fecha**: 2026-09-08 · **Fase**: F0

**Decisión**: los tests y la CLI se ejecutan en local con `uv run` sobre un
`.venv`. La imagen Docker es el artefacto desplegable y la CI ejecuta los
tests dentro de ella.

**Descartado**: ejecutar absolutamente todo dentro del contenedor, que es la
lectura literal de §3.3.3 ("todo en contenedores desde el día 1").

**Por qué**: con spaCy y su modelo dentro de la imagen, cada ciclo de prueba
implicaría reconstruir. El principio de los doce factores exige que el
artefacto desplegable sea único y versionado, no que se prohíba ejecutar un
test fuera de él. La divergencia entre `.venv` e imagen la detecta la CI en
el siguiente push, no dos semanas después.

**Riesgo asumido**: si la CI no está operativa, la divergencia pasa
desapercibida. Por eso la ejecución de tests en contenedor entra en la CI
en F6 como muy tarde.


---

## D-012 · La reimportación es incremental y no toca el progreso

**Fecha**: 2026-09-09 · **Fase**: F0

**Decisión**: la ingesta inserta solo lo que no existe. Las palabras y
contextos ya presentes se dejan intactos. Nunca se borra nada, ni siquiera
si desaparece del `vocab.db` de origen.

**Descartado**: (a) rechazar archivos ya importados por `checksum`, que
impediría reimportar un archivo que ha crecido; (b) borrar e insertar,
que destruiría el estado de repetición espaciada.

**Por qué**: el Kindle acumula. Cada subida contiene casi todo lo anterior
más lo nuevo. Sin idempotencia, el usuario tendría palabras duplicadas y
volvería a repasar desde cero vocabulario que ya domina.

**Cómo se garantiza**:
- `entries` única por `(user_id, lemma, lang)`.
- `contexts` única por `(entry_id, external_id)`, donde `external_id` es
  el `LOOKUPS.id` del Kindle (libro + posición), estable entre exportaciones.
- `INSERT ... ON CONFLICT DO NOTHING`, atómico, no `SELECT` previo.
- El progreso vive en `scheduling_state` y `reviews`, que la ingesta no toca.

**Nota**: el `checksum` de `sources` registra qué archivo se subió, no sirve
como criterio de "ya importado". Un archivo con una palabra más tiene otro
checksum y debe aceptarse.

**Verificado (2026-09-09)**: comparadas dos exportaciones reales del mismo
Kindle (1.511 → 1.690 consultas). Los 1.511 `LOOKUPS.id` antiguos siguen
presentes y con **todos** sus campos idénticos, incluido `usage`. Ninguna
fila desaparece ni muta. `BOOK_INFO` tampoco cambia.

**Excepción encontrada**: `WORDS.timestamp` sí cambia (16 casos), y siempre
en palabras vueltas a consultar. Es la fecha de la **última** consulta, no
de la primera. Por tanto `entries.first_seen_at` se deriva de
`MIN(LOOKUPS.timestamp)`, nunca de `WORDS.timestamp`.


---

## D-013 · El ruido se filtra por lista cerrada, no por categoría gramatical

**Fecha**: 2026-09-XX · **Fase**: F0

**Decisión**: descartar una consulta si la palabra está en una lista corta de
palabras funcionales por idioma, o si tiene menos de dos caracteres.

**Descartado**: filtrar por la categoría gramatical que devuelve spaCy en
contexto (`ADP`, `DET`, `PRON`...), que era la opción más potente.

**Por qué**: el sentido del error. El filtro por categoría descarta en
silencio vocabulario que el modelo etiquetó mal, y spaCy se equivoca más en
frases cortas o mal puntuadas. La lista solo descarta lo que está escrito en
ella y se audita abriendo el archivo.

**Medición que corrigió la lista**: una primera versión con las palabras
funcionales habituales descartaba 24 entradas, y al revisarlas una a una
cuatro eran vocabulario legítimo: `beneath` (2 consultas), `neither`, `shall`
y `although` (2). Son funcionales gramaticalmente, pero un hispanohablante de
nivel intermedio las consulta a propósito. La lista se redujo al núcleo básico.

También quedan fuera las funcionales con acepción de contenido: `even` aparece
en el corpus dentro de «Never give roses in even numbers», donde significa
*par*.

**Resultado**: 17 palabras filtradas de 913; 24 consultas de 1.024 (2,3 %).

**Revisión**: al añadir español (F7). `salvo` es preposición y verbo con la
misma grafía, así que una lista no los distingue. Ahí puede hacer falta
combinar lista con confirmación por categoría gramatical.

---

## D-014 · Estado de estudio por entrada, controlado por el usuario

**Decisión**: `entries.status` con tres valores — `learning` (por defecto),
`known` y `noise`. El selector de FSRS solo considera `learning`.

**Descartado**: descartar el ruido en la ingesta, y confiar únicamente en FSRS
para las palabras ya sabidas.

**Por qué**: FSRS resuelve "ya la he aprendido" subiendo el intervalo tras
varios aciertos, pero no resuelve "ya la sabía antes de empezar". 1.357 de
1.505 palabras tienen una sola consulta, así que la curva arranca de cero para
casi todo el corpus y el usuario tendría que fallar o acertar repetidamente
para que el algoritmo se entere. Con 913 palabras en inglés, eso es fricción
suficiente para abandonar.

**Efecto sobre D-013**: el filtrado de ruido pasa de descartar a marcar.
Equivocarse en la lista deja de ser destructivo: la entrada sigue ahí y el
usuario puede rescatarla. Es el mismo principio de D-010 — no se destruye el
dato de partida.

**Alcance**: en F0 solo entra la columna. La interfaz para cambiar el estado
es F3, con el resto de la interfaz.

---

## D-015 · La lematización se hace en contexto, no sobre la palabra aislada

**Fase**: F0.4

**Decisión**: el lema de cada entrada lo deriva spaCy analizando la palabra
dentro de su frase de contexto, no la palabra por sí sola ni el campo `stem`
del Kindle.

**Descartado**: agrupar por la palabra en minúsculas (`word.lower()`), que era
el lema provisional de F0.3, y fiarse de `WORDS.stem` (§4.1 del esquema: solo
921 de 1.505 coinciden con `word`, y algunos añaden tildes inexistentes).

**Medido sobre las 845 consultas en inglés de la exportación de agosto de
2026**: el lema de spaCy fusiona 30 grupos de formas flexionadas que el
dedupe por minúsculas mantenía separadas (`enquiries`/`enquiry`,
`crave`/`craved`, `eased`/`ease`), y **divide** un caso que el dedupe unía:
`strained` recibe lema `strain` en una frase y `strained` en otra, verbo y
adjetivo. Neto: 745 → 716 entradas.

Sobre las 1.024 consultas en inglés de la exportación de septiembre de 2026,
el mismo efecto neto: 904 → 860 entradas. Son las cifras que usan los tests
de integración.

La división es el argumento a favor de lematizar en contexto: la palabra
aislada no permite distinguir esos dos casos.

**Primer límite: la fusión es morfológica, no semántica.** `bearing` y `bore`
comparten lema y no significado. Es §5.4 apareciendo en la ingesta; no afecta
a `cloze_original`, sí afectará a los distractores de A1 en F1.

**Segundo límite: el lematizador se equivoca.** `en_core_web_sm` usa reglas de
sufijo y falla con verbos cuyo infinitivo termina en `-e`. En el corpus,
`waned` y `waning` reciben lema `wan` (pálido) en lugar de `wane` (menguar),
con `pos_ = VERB` correcto en ambos: el fallo es del lematizador, no del
etiquetador.

La agrupación sigue siendo correcta —las dos formas caen en la misma entrada—,
pero la **etiqueta** es errónea, y esa etiqueta es la que ve el usuario y la
que irá al prompt de A1 en F1. No afecta a `cloze_original`, que tapa la
palabra en su propia frase.

**Incidencia sin acotar.** Se intentó medir cuántos casos como `wan` hay en el
corpus y no se consiguió: la heurística probada (lemas cuya forma con `-e`
aparece en el corpus) devolvió cinco candidatos, cuatro de ellos coincidencias
ortográficas legítimas —`dim`/`dime`, `fin`/`fine`, `prim`/`prime`—, y dejó
fuera el propio `wan`, porque `wane` nunca aparece suelto en el corpus. Sin un
diccionario inglés disponible en el entorno no se pudo separar la señal del
ruido. **Se sabe que ocurre; no se sabe con qué frecuencia.**

**No se corrige en F0.** Un diccionario de excepciones a mano es mantenimiento
sin fin, `en_core_web_lg` usa el mismo lematizador de reglas, y un LLM para
lematizar contradice el principio por defecto (§5). Se revisa en F1 si los
distractores se degradan por esto.

**Revisión**: en F1, al medir la calidad de los distractores. Si el arnés
detecta fallos atribuibles al lema, el número sale de ahí en lugar de una
heurística sobre el corpus.

---


## Plantilla para nuevas entradas

```markdown
## D-0XX · Título en una línea

**Fecha**: AAAA-MM-DD · **Fase**: FX

**Decisión**: qué se hace.

**Descartado**: qué alternativa se consideró y no se eligió.

**Por qué**: el motivo, con números si los hay.

**Revisión**: en qué momento y con qué criterio se reevaluaría. Omitir si es definitiva.
```
