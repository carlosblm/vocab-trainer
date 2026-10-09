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
| D-016 | 2026-09-23 | F0.4 | La normalización entra por un puerto, no por tipos del adaptador |
| D-017 | 2026-09-23 | F0.4 | La dirección de las dependencias la verifica import-linter |
| D-018 | 2026-09-23 | F0.4 | El estado inicial lo decide la palabra consultada, no el conjunto de sus formas |
| D-019 | 2026-09-24 | F0.5 | `cloze_original`: palabra completa, todas las apariciones, hueco fijo |
| D-020 | 2026-09-24 | F0.5 | Cada contexto guarda la forma consultada en él |
| D-021 | 2026-09-24 | F0.5 | El modelo de spaCy es una dependencia del lock |
| D-022 | 2026-09-25 | F0.5 | Variante de elección: distractores con la misma forma gramatical |
| D-023 | 2026-09-25 | F0.5 | Un contrato de repositorio por caso de uso |
| D-024 | 2026-10-05 | F1 | Ollama se ejecuta fuera de compose |
| D-025 | 2026-10-05 | F1 | Fuente de la definición correcta y política conservadora de sentidos |
| D-026 | 2026-10-06 | F1 | Un puerto por tarea de IA, no un `run` genérico |
| D-027 | 2026-10-06 | F1 | Validadores deterministas de F1: básico, D1 y D7 |
| D-028 | 2026-10-06 | F1 | Bucle de generación: el motivo del reintento viaja como datos |
| D-029 | 2026-10-07 | F1 | Plantillas del prompt: en inglés, en TOML dentro del paquete |
| D-030 | 2026-10-07 | F1 | Adaptador de Ollama: configuración por tarea y transporte |
| D-031 | 2026-10-09 | F1 | Puerto del léxico y adaptador de OEWN |
| D-032 | 2026-10-09 | F1 | Todo contexto que marca R1 va a `cloze_original` en F1 |
| D-033 | 2026-10-09 | F1 | La definición se busca al importar y se guarda |
| D-034 | 2026-10-09 | F1 | La desambiguación de sentidos pasa a F2, como comparación medida |

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

**Actualización (2026-10-06)**: el puerto es uno por tarea (D-026). Si existe un `LLMProvider`, será interno de los adaptadores. Siguen haciendo falta los dos adaptadores reales.

---

## D-005 · Nueva métrica D7: distractores triviales

**Fecha**: 2026-09-07 · **Fase**: pruebas previas

**Decisión**: añadir al arnés de evaluación una métrica determinista que detecte distractores construidos como antónimos o negaciones de la respuesta correcta.

**Origen**: en 2 de 5 ejecuciones de prueba, el modelo generó distractores del tipo *"Incapable of withstanding damage"*, *"Prone to breaking down under pressure"*, *"Lacking the ability to adapt"*. Un usuario los descarta sin conocer la palabra, solo por la forma negativa, así que el ejercicio no evalúa nada.

**Por qué es determinista**: se detecta con patrones de negación y prefijos privativos (`in-`, `un-`, `lacking`, `unable`, `incapable`, `prone to`), sin necesidad de un LLM juez.

**Nota**: es un modo de fallo que no estaba previsto en la propuesta v1.0 y apareció en cinco ejecuciones. Refuerza el argumento de construir el arnés antes de confiar en la generación.

**Actualización (2026-10-06)**: la detección no usa prefijos ni detecta `prone to`. De los tres ejemplos de §12.4 detecta dos (D-027).

---

## D-006 · Modelos de más de 9B descartados

**Fecha**: 2026-09-07 · **Fase**: pruebas previas

**Decisión**: limitar el modelo local a 4B.

**Por qué**: la RTX 4070 Laptop tiene 8.188 MiB totales, de los que Ollama reporta **~6,9 GiB disponibles**. Un 9B en Q4 ocupa unos 6,6 GB de pesos y no deja margen para la caché de contexto, que crece con la longitud del prompt.

**Velocidad medida**: 65 tokens/s con un 4B, con las 37 capas en GPU.

**Alternativa si hiciera falta más capacidad**: comparar contra una API externa en la F6. Para el volumen del proyecto (unos 5.000 ejercicios en total) el coste de API es de pocos euros, así que no hay razón económica para forzar el hardware.

**Actualización (2026-10-07)**: las 37 capas eran de Qwen3-4B. Con
`qwen3.5:4b`, el registro de Ollama dice 34/34 (D-030).

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

**Actualización (2026-10-06)**: el `llm.run` genérico se sustituyó por un puerto por tarea (D-026). Quien llama es `application/`, y el modelo de cada tarea se resuelve en la raíz de composición. Las cuatro reglas siguen vigentes.

---

## D-008 · Guarda de unidad léxica antes de generar cualquier ejercicio

**Fecha**: 2026-09-07 · **Fase**: diseño; implementada en F0.6, se conecta en F1

**Decisión**: antes de construir un ejercicio, comprobar si la palabra consultada forma parte de una unidad léxica mayor en su contexto (phrasal verb, locución). Si es así, el ejercicio se construye sobre la unidad completa.

**Descartado**: generar siempre sobre la palabra almacenada, que era el planteamiento implícito hasta la v1.2.

**Por qué**: el Kindle guarda una sola palabra, pero el significado no siempre reside en ella. Ejemplo real del corpus: `come` en *come up with*. La aplicación enseñaría *venir*, cuando la unidad significa *idear*. **No es una funcionalidad ausente, es la aplicación enseñando algo falso.**

El caso que motivó la decisión fue `eased` en *"electronics eased out
hydraulics"*: la aplicación enseñaría *aliviar*, cuando `ease out` significa
*desplazar*. Al revisarlo en F0.6 resultó dudoso, porque *ease* también es
«mover poco a poco».

**Incidencia medida** (F0.6, 2026-10-01): de los 13 contextos que marca R1
(«Lo aprendido en F0.6») sobre las 1.024 consultas en inglés de la exportación
de septiembre de 2026, 5 son positivos claros y 3 dudosos. Los falsos negativos,
lo que R1 no marca, no se midieron. Bajo en volumen, grave en efecto.

**El problema es la detección, no la generación.** La regla ingenua, **R0** —la
palabra consultada va seguida de un token que el etiquetador de spaCy marca
como `RP` (partícula) o `IN` (preposición o conjunción subordinante), sin mirar
el análisis de dependencias—, marca **206 de las 1.024** consultas en inglés de
la exportación de septiembre de 2026 (`sojourn in`, `stake in`, `tycoons in` son
sustantivo más preposición). La cifra que había aquí, un 80 % de falsos
positivos, no se pudo reproducir: la definición de la regla no quedó escrita.

**Capas**: la implementada es R1, sobre el análisis de dependencias de spaCy
(F0.6). La opacidad de los verbos con preposición, que R1 no ve, se decide en F1
con la fuente de definiciones (punto 3 de «Pendiente en F1»). La lista de
phrasal verbs frecuentes, que era la segunda capa prevista, ya no lo es: marcaría
igual *came across a letter* y *a bridge*. El LLM sigue siendo el último
recurso, porque tiende a los falsos positivos.

**Verificado en F0.6, sin medición formal**: el análisis de dependencias separa
la partícula de la preposición cuando la diferencia es sintáctica, pero no ve la
opacidad semántica. Detalle y motivo en «Lo aprendido en F0.6».

El riesgo no viene de frases truncadas —solo el 0,7 % lo están— sino de la suciedad de maquetación: notas al pie (`[59]`, `[`) y espacios sobrantes en el 98,5 % de las frases. El análisis se ejecuta sobre la frase ya limpia, así que la limpieza es una precondición de la detección, no un paso independiente.

**Métrica asociada**: D8.

**Orden de implementación (2026-09-24)**: la guarda se implementa en F0.6.
`cloze_original` llega antes, en F0.5, como excepción explícita a «antes de
construir un ejercicio». Se acepta porque no muestra ningún significado y la
partícula queda visible en la frase («Electronics _____ out hydraulics»): no
puede enseñar un significado falso, que es el daño que esta guarda previene.

**Lo aprendido en F0.6 (2026-10-01)**:

- **La regla, R1**: la palabra consultada tiene un dependiente con la relación
  `prt`, pegado a ella o separado por el objeto («eased the hydraulics out»). Se
  mira la primera aparición, con la misma función que usa el normalizador, así
  que la guarda habla del mismo token del que salen `pos` y `morph`. Vive en
  `adapters/nlp/lexical_unit.py` porque `prt` es una etiqueta del esquema de
  `en_core_web_sm`: un núcleo privado sobre el `Token` y un envoltorio por lotes
  sobre `list[CleanedLookup]`, emparejado por `external_id`, que devuelve la
  partícula o `None`.
- **Resultado**: R1 marca **13 de las 1.024** consultas en inglés, frente a las
  206 de R0. Revisados a mano con la pregunta «¿enseñar la palabra sola daría un
  significado falso en esta frase?»:

  | Revisión | Contextos | Casos |
  |---|---|---|
  | Sí | 5 | `perked up`, `come up (with)`, `hung up`, `stamp out`, `belly-up` |
  | Duda | 3 | `eased out`, `lever up`, `patch up` |
  | No | 5 | `chewed up`, `spit out`, `sponged up`, `gulped down`, `slinking up` |

  Los negativos son sobre todo partículas aspectuales o de dirección: el
  significado sigue en el verbo. `slinking up` es un error del analizador: en
  *up the staircase*, `up` es preposición de lugar.
- **Por qué ese nivel de falsos positivos es aceptable**: los composicionales
  son la mitad de los casos decididos (5 de 10; contando los dudosos, entre 5 y
  8 de 13). Un falso positivo hace buscar la definición de la unidad (`gulp
  down` en vez de `gulp`), que sigue siendo correcta. El daño grave es el falso
  negativo: enseñar la palabra sola con un significado falso.
- **Lo que la sintaxis no ve**: el analizador no distingue la opacidad
  semántica. *came across an old letter* (encontrar) y *came across an old
  bridge* (cruzar) reciben el mismo análisis, con `across` como preposición, y
  ninguno se marca. *carried out the experiment* (realizar) y *carried out the
  boxes* (sacar) reciben también el mismo, con `out` como partícula, y se
  marcan los dos.
- **Por qué no se midió formalmente**: el problema afecta a unos 5 o 6 casos
  reales del corpus. Con tan pocos positivos, cualquier métrica tendría un
  intervalo tan ancho que no permitiría elegir entre reglas: un solo caso mueve
  la exhaustividad entre 17 y 20 puntos. Lo útil de la medición —que la sintaxis
  no cubre la opacidad semántica— salió de inspeccionar cuatro casos reales y
  pares mínimos inventados. Lo que R1 no marca no se revisó, así que los falsos
  negativos quedan sin medir.
- **La guarda no se conecta ni se persiste en F0.6.** Su consumidor es
  `mcq_definition`, en F1, y la forma del dato se decide con él delante, como en
  D-020.

**Pendiente en F1**:

1. `mcq_definition` consume la guarda: si hay partícula, busca la definición de
   la unidad completa. Si la unidad no está en la fuente de definiciones, vuelve
   a la palabra sola; si no, el falso positivo deja de ser barato.
2. La unidad puede tener más de dos piezas: *come up with*.
3. La opacidad de los verbos con preposición (*came across a letter* frente a
   *a bridge*) **no** la resuelve una lista: la marcaría igual en los dos casos,
   y ahí el falso positivo sí enseña un significado falso. Requiere desambiguar
   por contexto, comparte la dependencia de una fuente léxica de §5.4 y §11
   (pregunta 5), y se decide en F1 junto con la fuente de definiciones.
4. La métrica D8 del arnés de F2 mide el daño residual sobre ejercicios reales.

**Actualización (2026-10-05)**, sobre «Pendiente en F1»:

- El punto 1 cambia: si la unidad no está en la fuente, `cloze_original`, no
  la palabra sola. Prueba: `belly-up` es un positivo claro, su unidad no está
  en el léxico, y volver a la palabra sola enseñaría «vientre».
- Medido: de los 13 contextos de R1, la unidad está en el léxico en 8 y no en
  5 (`ease out`; `belly up`, que el léxico escribe con guion; `lever up`;
  `slink up`; `gulp down`).
- Puntos 2 y 3: con la política de D-025 no producen ejercicios con un
  significado falso en F1 (`come up` tiene 12 sentidos, así que va a
  `cloze_original`). Se revisan en F4.

**Actualización (2026-10-09)**: todo contexto que marca R1 va a
`cloze_original` en F1 (D-032). La frase de que la definición de la unidad
«sigue siendo correcta» queda refutada por `chewed up`.

---

## D-009 · `preposition_cloze` entra en la v1 y no usa IA

**Fecha**: 2026-09-07 · **Fase**: diseño (implementación tras F2; ver «Aplazamiento»)

**Decisión**: añadir un tipo de ejercicio que tapa la preposición que sigue a la palabra consultada, con distractores tomados de un conjunto cerrado de preposiciones. **Sin ninguna llamada a un modelo.**

**Descartado**: generar los distractores con un LLM. Innecesario: el espacio de candidatos es cerrado (unas cuarenta preposiciones) y se pondera por la frecuencia observada en el propio corpus del usuario.

**Por qué entra en la v1**:

- **Cobertura**: con la regla R0 de D-008, 206 de las 1.024 consultas en inglés
  de la exportación de septiembre de 2026 (**20 %**) tienen la palabra seguida
  de un token `IN` o `RP`. Es una cota superior: 182 son preposiciones, 15
  conjunciones subordinantes (`IN` con categoría `SCONJ`) y 9 partículas.
  Frente a los phrasal verbs —al menos 5 casos claros en 1.024, con los falsos
  negativos sin medir (D-008)—, hay volumen de sobra. La cifra que había aquí, 178 de 845 sobre agosto, no se reproduce: ninguna de tres definiciones
  probadas la da (166, 152 y 186).
- **Coste**: horas de trabajo. Es sustitución de cadena, igual que `cloze_original`.
- **Fiabilidad**: la respuesta correcta está literalmente en la frase. No hay nada que alucinar.
- **Valor pedagógico**: las preposiciones en inglés no se deducen, se memorizan por colocación, y son un fallo persistente en hispanohablantes de nivel intermedio.

**Efecto lateral interesante**: los casos que la detección de phrasal verbs descartaba como falsos positivos (`stake in`, `moats around`, `scattered across`) son verdaderos positivos para este ejercicio. La misma detección sirve para las dos cosas con criterios opuestos.

**Riesgo conocido**: no toda preposición que sigue a una palabra es una colocación. En *"proved resilient after the flood"*, `after` pertenece a la estructura de la oración y no a `resilient`; un ejercicio ahí enseñaría una asociación falsa. Se distingue con análisis de dependencias de spaCy y se mide con **D9**.

**Consecuencia sobre el proyecto**: la proporción de la aplicación que no requiere modelos sube por encima del 70 %. Refuerza el argumento central de §5: la decisión por defecto es no usar un LLM.

**Aplazamiento (2026-10-01)**: se implementa después de F2, no en F0. Motivo:
calendario y dependencias. F0 estaba planificada en una semana y ha llevado
casi tres, y §9 sitúa en F0–F2 en torno al 70 % del valor profesional del
proyecto. `preposition_cloze` no es requisito de nada: no lo necesita ningún
ejercicio de F1 ni el arnés de F2. Y la promesa de §2.3 —que la aplicación sea
utilizable sin modelo desde el primer día— ya la cumple `cloze_original`, en sus
dos variantes. Se retoma tras F2; el patrón de la guarda de D-008 (núcleo sobre
`Token` y envoltorio por lotes) sirve de base para detectar la preposición que
depende de la palabra.

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

**Verificado (2026-09-25)**: el riesgo se materializó. La imagen no tenía el
modelo de spaCy: el `Dockerfile` lo descargaba con `spacy download` y el
`uv sync --frozen` de la capa de código lo borraba a continuación (D-021).
Construida la imagen del commit `cc75041`, `spacy.load("en_core_web_sm")`
falla con `E050`. Se detectó a mano, no por CI, que todavía no existe: un
`uv sync` borró el modelo del `.venv`, y al revisar el `Dockerfile` se vio que
la imagen caía en lo mismo. Tras la corrección, importar el `vocab.db` de
septiembre de 2026 sobre una base vacía da 860 entradas y 1.024 contextos
tanto en la imagen como en el `.venv`.


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

**Fecha**: 2026-09-18 · **Fase**: F0

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

**Actualización (2026-10-05)**, sobre la incidencia: el control de lema de
D-025 marca 27 de los 999 contextos. Según una lectura manual hecha en la
revisión con el asistente:

- 11 son errores de spaCy que cambian el significado: `odds` (3), `waned`,
  `waning`, `primes`, `means`, `summons`, `logistics`, `hermeneutics`, `omen`.
- 9 son lemas alternativos reales y spaCy acierta: `bore`, `sands`, `trunks`,
  `deeds` (2), `waters`, `sales`, `liabilities`, `best`.
- 7 son variantes inofensivas: `lambasted` (2), `enthralled`, `swinging`,
  `corps`, `hypochondria`, `Wounded`.

Hay una familia nueva de error: sustantivos acabados en -s que no son el plural
de otra palabra. Es una cota inferior: solo ve los casos en que el léxico
discrepa de spaCy. En F1, esos contextos van a `cloze_original`.

---


## D-016 · La normalización entra por un puerto, no por tipos del adaptador

**Fecha**: 2026-09-23 · **Fase**: F0.4

**Decisión**: un tercer puerto en `ports/normalizer.py`, con sus dos objetos de
transferencia —`CleanedLookup` a la entrada, `NormalizedWord` a la salida— y un
contrato `Callable`. El adaptador de spaCy lo implementa; el caso de uso solo
conoce el puerto.

**Descartado**: dejar el alias `Normalizer` en `application/`, escrito con tipos
que pertenecían al adaptador de spaCy. Era lo que había.

**Por qué**: la capa de aplicación importaba de `adapters/nlp/`, así que
importar el caso de uso arrastraba `import spacy`. El test unitario del caso de
uso —cuyo docstring prometía «sin base de datos y sin spaCy»— tardaba **0,47 s**
frente a los **0,01 s** de los demás tests unitarios. La violación de la
arquitectura no era una objeción de estilo: tenía un coste medible, y el
docstring era falso a medias. Tras el cambio ese test tarda 0,01 s y no carga un
solo módulo de spaCy.

**Tres decisiones derivadas**:

- **`Callable` y no `Protocol`.** Una normalización no tiene estado que
  inyectar, a diferencia de `VocabularyImporter` (ruta, idiomas) y
  `VocabularyRepository` (sesión). Exigir una clase obligaría al adaptador a
  envolver una función en un objeto vacío.
- **Un tipo reducido en lugar de `RawLookup`.** El puerto declara lo que
  consume: palabra, idioma, frase limpia y una clave de correlación. Ni el libro
  ni la fecha, que no usa. **Coste aceptado**: el caso de uso tiene que
  correlacionar los resultados por `external_id` en vez de recibir de vuelta la
  consulta entera.
- **`pos: str | None` en lugar de `"X"`.** `X` es una etiqueta legítima de
  Universal POS —«otro»: extranjerismos, erratas, símbolos—, así que usar un
  valor posible como marca de ausencia confunde «no encontré la palabra en la
  frase» con «la encontré y es de categoría desconocida». Medido sobre las 1.024
  consultas en inglés de la exportación de septiembre de 2026: el recuento de no
  resueltos no se mueve —2 con cualquiera de los dos criterios— porque en este
  corpus ningún token localizado recibe `X`. **El número no cambia; el
  significado sí.** Era un falso positivo latente que el corpus no llega a
  disparar.

**Amplía la arquitectura descrita**: §3.3.2 de la propuesta solo contempla
`VocabularyImporter` como puerto. Con este son tres.

**Actualización (2026-09-25)**: el repositorio se separó en dos contratos, uno
por caso de uso, así que ahora son cuatro puertos: importador, normalizador,
`ImportRepository` y `StudyRepository` (D-023).

**Actualización (2026-10-06)**: ahora son cinco puertos, con
`DistractorGenerator` (D-026).

**Actualización (2026-10-09)**: ahora son seis puertos, con `Lexicon` (D-031).

**Revisión**: el contrato tiene una sola implementación, así que su capacidad
real de abstraer está sin verificar. El primer examen llega con un segundo
normalizador: el español en F7, o cualquier sustituto de spaCy.

---

## D-017 · La dirección de las dependencias la verifica import-linter, no mi memoria

**Fecha**: 2026-09-23 · **Fase**: F0.4

**Decisión**: declarar las capas como un contrato de `import-linter` en
`pyproject.toml` y ejecutarlo junto a `ruff` y `mypy`.

**Descartado**: un test propio que recorriera las importaciones con `ast`, y
confiar en la revisión manual.

**Por qué**: mypy en modo estricto y ruff con `E, F, I, B, UP` pasaban los **24
archivos** con la violación dentro: `application/import_vocabulary.py` importaba
de `adapters/nlp/` en tres líneas. Ninguna de las dos herramientas mira la
dirección de las importaciones, así que la tabla de capas se sostenía únicamente
sobre que yo me acordara de leerla.

**El delimitador es lo que más vale de la configuración**:

| Sintaxis | Significado |
|---|---|
| `a : b` | hermanos que **pueden** importarse entre sí |
| `a \| b` | hermanos **independientes**: ninguno puede importar al otro |

`adapters` y `application` necesitan `|`. Con `:` el contrato permitiría
`adapters → application`, que es una arquitectura en capas y no hexagonal. La
diferencia entre las dos cabe en un solo carácter del fichero de configuración.

**El método importa tanto como el resultado**: el guardián se configuró **antes**
de arreglar nada y se comprobó que fallaba señalando las tres líneas exactas.
Después se inyectó a propósito la violación contraria —un import de
`adapters` hacia `application`— para verificar que vigilaba los dos sentidos y
no solo uno. Un guardián al que no se ha visto fallar no es un guardián.

**Segundo contrato**, de tipo `forbidden`: recoge la primera fila de la tabla,
`domain/` no importa nada de terceros.

**Estado de la verificación**: hoy se ejecuta a mano junto a `ruff` y `mypy`.
Entra en la CI con el resto, con el mismo riesgo asumido que D-011: mientras la
CI no esté operativa, la garantía depende de acordarse de ejecutarlo.

**Arreglo incluido en el mismo cambio, sin entrada propia**: se borró
`adapters/postgres/session.py`, que construía el motor de SQLAlchemy al
importarse y contradecía la regla de que las dependencias entran por parámetro.
No lo usaba nadie —los tests de integración ya construían su propio motor—, así
que el borrado no obligó a tocar ninguna otra cosa.

---

## D-018 · El estado inicial lo decide la palabra consultada, no el conjunto de sus formas

**Fecha**: 2026-09-23 · **Fase**: F0.4

**Decisión**: la regla de ruido completa vive en el dominio. `Entry.new` recibe
un `LookedUpWord` —la palabra tal como se consultó y su idioma— y decide con qué
estado nace la entrada. La regla es a nivel de palabra: no mira las demás formas
que comparten lema.

**Descartado**:

- **Dejar la agregación en la capa de aplicación.** Era lo que había: una
  función que marcaba `noise` solo si **todas** las consultas del grupo lo eran.
  La mitad de la regla de D-013 y D-014 vivía fuera del dominio, donde ningún
  test podía alcanzarla sin montar el caso de uso entero.
- **Hacer del estado una propiedad calculada de `Entry`.** Choca de frente con
  D-014: el estado lo controla el usuario y una propiedad no se puede
  sobrescribir. El estado se calcula **al nacer** y nunca más. El constructor
  normal sigue aceptando cualquier valor, que es como el repositorio reconstruye
  una entrada guardada con el `known` que puso el usuario.
- **Guardar la forma consultada en cada contexto.** Con la regla a nivel de
  palabra no hacía falta, y se aplazó hasta tener consumidor. Lo tuvo en F0.5:
  ver D-020.

**Por qué a nivel de palabra**: dentro de un grupo el idioma es constante —la
identidad de una entrada es `(lemma, lang)`— y la lista de D-013 se consulta
sobre la forma consultada, no sobre el lema.

**Qué cambia, medido sobre las dos exportaciones**:

| Exportación | Entradas | Con más de una forma | `noise` con la regla vieja | `noise` con la nueva |
|---|---|---|---|---|
| agosto 2026 | 716 | 35 | 13 | 13 |
| septiembre 2026 | 860 | 51 | 14 | 14 |

**Ninguna entrada cambia de estado.** Pero las dos reglas no son equivalentes, y
conviene dejar escrito qué se perdió.

**Límite reconocido: desaparece el rescate por consulta deliberada.** Antes,
una sola consulta de vocabulario real entre varias accidentales bastaba para que
la entrada naciera `learning`. Ahora decide la consulta más antigua. El caso
donde difiere es alcanzable, comprobado con el modelo real:

```
doing    lema=do      en la lista de ruido: False
do       lema=do      en la lista de ruido: True
having   lema=have    en la lista de ruido: False
have     lema=have    en la lista de ruido: True
```

`do` y `doing` caen en la misma entrada. Si `do` se consultó antes, la entrada
nace `noise` y la consulta deliberada de `doing` deja de verse. Ocurre porque la
lista de D-013 es cerrada y contiene formas base, mientras que la agrupación es
por lema (D-015): una flexión que no está en la lista puede compartir lema con
una que sí está. No ocurre en el corpus actual; puede ocurrir.

**La dependencia circular y cómo se evitó**: `domain/noise.py` no importa
`domain/models.py`. Para eso, `is_noise` devuelve `bool` y no `EntryStatus`, y
`LookedUpWord` vive en `noise.py`. El mapeo a `EntryStatus` lo hace `Entry.new`.
El ciclo lo cerraban las dos direcciones, no solo el tipo de retorno: si el
objeto de valor hubiera vivido en `models.py`, la regla habría tenido que
importarlo para recibirlo.

**Revisión**: cuando la interfaz de F3 permita cambiar el estado a mano. Si
rescatar entradas resulta frecuente, el rescate automático vuelve a la mesa con
datos de uso en lugar de con un caso construido.

---

## D-019 · `cloze_original`: palabra completa, todas las apariciones, hueco fijo

**Fecha**: 2026-09-24 · **Fase**: F0.5

**Decisión**: el ejercicio es un objeto del dominio, `ClozeOriginal`, definido
por dos campos: la frase limpia del contexto y la forma consultada en él
(D-020). La palabra se localiza sin distinguir mayúsculas y como palabra
completa; se tapan **todas** sus apariciones con un hueco de longitud fija; la
respuesta esperada es la forma flexionada que aparece en la frase, no el lema;
la corrección compara con `lower()` y `strip()`, nada más. Tras un fallo se
muestran la palabra y la frase limpia.

**Descartado**:

- **Una función que devuelva el texto tapado.** La tabla `exercises` de §4.3
  persistirá los ejercicios en F1, y lo que se persiste es un objeto.
- **Buscar por subcadena.** La subcadena puede caer antes dentro de otra
  palabra: `straw` en «…clutch at straws, and the anchor is a plausible straw.»
  taparía `_____s` y dejaría la respuesta a la vista.
- **Tapar solo una aparición.** En una frase que repite la palabra, las demás
  apariciones dan la respuesta.
- **Un hueco del tamaño de la palabra.** Revela cuántas letras tiene.

**Medido** sobre los 999 contextos utilizables de las entradas `learning` de la
exportación de septiembre de 2026, que son los que usa `study`:

| Caso | Contextos |
|---|---|
| Repiten la palabra | 27 |
| … con mayúsculas distintas (`Biases … biases`) | 2 |
| La subcadena cae antes dentro de otra palabra | 1 |
| La palabra va pegada a un guion (`tech-savvy`) | 9 |

Sobre las 1.024 consultas en inglés, ruido incluido, son 36 repeticiones y 4
subcadenas: las otras 3 subcadenas están en entradas `noise`.

**Derivadas**:

- **Determinista.** Tapar todas las apariciones elimina la posición como dato:
  el ejercicio queda definido por la frase y la palabra, sin azar que guardar.
  El texto tapado y la respuesta son propiedades derivadas, así que no se puede
  construir un ejercicio cuyo hueco no corresponda a su frase.
- **Invariante, no decisión al nacer.** Que la palabra aparezca como palabra
  completa se comprueba en `__post_init__` y lanza `ValueError`, porque tiene
  que cumplirse también al reconstruir el ejercicio en F1. Es lo contrario de
  `Entry.new` (D-018), que decide el estado una sola vez. Una palabra vacía
  también se rechaza: el patrón vacío encaja al final de la frase y aceptaría
  `""` como respuesta correcta.
- **El caso de uso no se cae por un contexto roto.** Si `ClozeOriginal` lanza,
  avisa, prueba otro contexto y luego otra entrada, recorriendo permutaciones
  aleatorias para no perder la uniformidad. Con la palabra de cada contexto
  ocurre en 0 de los 999: es una red de seguridad.
- **El guion cuenta como borde.** `savvy` en `tech-savvy` queda
  `tech-_____`: el Kindle guardó `savvy`, no el compuesto. Entre esos 9 casos
  están `gone belly-up` y `roll-up`, que son terreno de D-008.

**Variante de elección (2026-09-25)**: `ClozeOriginal` sigue siendo la variante
de escritura, determinista y de dos campos. La de elección es un tipo nuevo que
lo contiene y fija sus opciones al crearse (D-022).

---

## D-020 · Cada contexto guarda la forma consultada en él

**Fecha**: 2026-09-24 · **Fase**: F0.5

**Decisión**: `Context.term` y la columna `contexts.term` (`NOT NULL`) guardan
la palabra que se consultó en esa frase, tal como la guardó la fuente.
`Entry.term` sigue siendo la de la consulta más antigua. El nombre es el mismo
porque el dato es el mismo: `entries.term` es el `term` de su primer contexto.

**Descartado**: buscar `Entry.term` en todos los contextos de la entrada y
descartar aquellos donde no aparece. No cambiaba el esquema, pero perdía
contextos en silencio y hacía que «utilizable» significara dos cosas distintas.

**Historia**: la opción se consideró en F0.4, al decidir D-018, y se aplazó por
tres motivos: con la regla de ruido a nivel de palabra no hacía falta; la forma
del campo no se sabría hasta tener su consumidor, `cloze_original`; y añadirla
después costaba una columna. Ahora hay consumidor y forma conocida.

**Por qué ahora**, medido sobre los 999 contextos utilizables de las entradas
`learning` de la exportación de septiembre de 2026 (los que usa `study`):

| Palabra que se busca en la frase | No aparece como palabra completa |
|---|---|
| `Entry.term` | 49 contextos |
| `Context.term` | 0 contextos |

Los 49 son contextos de entradas con varias formas: `crave` no está en «…his
sequestered spirit craved.». En este corpus ninguna entrada se quedaba sin
ejercicio (medido: 0), pero se perdían esos 49 contextos sin aviso.

**La migración se niega a ejecutarse sobre una tabla con filas.** La forma
consultada no se puede reconstruir desde la base: solo está en la fuente.
Rellenarla con `entries.term` habría puesto una forma falsa en 58 de los 1.024
contextos de septiembre (7 de ellos solo por mayúsculas), sin aviso, en una
columna que promete «tal como la guardó la fuente». La migración `fee3d3fffef4`
aborta si `contexts` tiene filas y explica qué hacer: `alembic downgrade base`,
`upgrade head` y reimportar. Hasta F3 no hay progreso que perder. Verificado en
un Postgres desechable: con una fila aborta y la base queda en la revisión
anterior, porque el DDL es transaccional; sin filas, añade la columna.

**Consecuencia sobre §4.2 de la propuesta**: «si tras el recorte la palabra
objetivo no sobrevive en un contexto utilizable» solo se puede evaluar si el
contexto conoce su palabra. Ahora la conoce.

---

## D-021 · El modelo de spaCy es una dependencia del lock

**Fecha**: 2026-09-24 · **Fase**: F0.5

**Decisión**: `en_core_web_sm` 3.8.0 se declara en `pyproject.toml` con URL
directa a su release de GitHub (`explosion/spacy-models`) y queda en `uv.lock`
con su hash. spaCy se acota a `>=3.8,<3.9`.

**Descartado**: descargarlo a mano con `spacy download`, que era lo que había,
en local y en el `Dockerfile`.

**Por qué**: `uv sync` deja el entorno exactamente como el lock, y el modelo no
estaba en él, así que cada sincronización lo borraba. Por la misma razón la
imagen no lo tenía: el `Dockerfile` lo descargaba y el `uv sync --frozen` de la
capa de código lo eliminaba a continuación (D-011, «Verificado»). Ahora `uv
sync` lo conserva y, si falta, lo reinstala.

**El rango existe porque el wheel del modelo no declara su dependencia de
spaCy.** `spacy validate` exige `>=3.8.0,<3.9.0` para el modelo 3.8.0, pero el
wheel no tiene `Requires-Dist` y el lock no le registra ninguna dependencia.
Sin el rango, un `uv lock --upgrade` podría subir spaCy a 3.9 y dejar el modelo
incompatible sin avisar. Modelo y spaCy se actualizan juntos.

**Coste**: `allow-direct-references` en la configuración de hatchling, que por
defecto rechaza URLs directas en las dependencias. PyPI tampoco las admite, lo
que no importa en una aplicación que no se publica ahí.

**Revisión**: al subir a spaCy 3.9, cambiar a la vez la URL del modelo y el
rango, y comprobarlo con `spacy validate`.

---

## D-022 · Variante de elección: distractores con la misma forma gramatical

**Fecha**: 2026-09-25 · **Fase**: F0.5

**Decisión**: `cloze_original` tiene las dos variantes que prevé §2.3 («la
escribe o la elige»). La de elección es la predeterminada en la CLI y `--write`
activa la de escritura; cuándo pasar de una a otra es F3. Cuatro opciones: la
respuesta y tres distractores tomados de las palabras que el propio lector
consultó, con la misma categoría y los mismos rasgos morfológicos
(`Context.pos` y `Context.morph`), de otro lema, del mismo idioma, nunca
`noise` y sin formas repetidas. Las opciones y su orden se fijan al crear el
ejercicio, con el azar por parámetro.

Es un tipo nuevo, `ClozeOriginalChoice`, que contiene un `ClozeOriginal`: la
variante de escritura no cambia y D-019 sigue siendo cierta. La regla es una
función pura del dominio, `choose_options`: candidatos y azar de entrada,
opciones o `None` de salida.

**Por qué la misma forma gramatical**: sin ella, el ejercicio se resuelve por
gramática. En «She _____ on the maps» solo encaja un verbo en pasado: un
sustantivo o un gerundio se descartan sin conocer la palabra.

**Por qué otro lema**: dos formas del mismo lema serían dos respuestas
correctas. `learned` y `learnt` comparten lema y rasgos (`VERB`,
`Tense=Past|VerbForm=Fin`): sin el filtro, las dos aparecerían entre las
opciones. Por lo mismo, una forma idéntica a la respuesta que venga de otro
lema tampoco vale.

**Medido** sobre los 999 contextos de `study` de la exportación de septiembre
de 2026, con los 1.000 contextos de las entradas no `noise` como candidatos:

| | Contextos |
|---|---|
| Con al menos tres distractores | 986 |
| Sin ellos | 13 |

Los 13 son clases cerradas o raras: conjunciones subordinantes (`although`
dos veces, `after`, `whence`), superlativos (`best`, `widest`), modales
(`shall`, `ought`, `might`), `neither`, `three`, `thy` y `Woes`, que es un
error del etiquetador (`NNS` con categoría AUX).

**Repliegue**: un contexto sin tres distractores se presenta en la variante de
escritura, con un aviso que dice por qué: cuántas palabras consultadas comparten
su forma gramatical, cuál es esa forma y que hacen falta tres para que la
gramática no delate la respuesta. No se busca otro contexto que sí los tenga:
sesgaría la selección hacia las palabras con muchas formas parecidas.

**Descartado**, medido sobre los 13:

| Alternativa | Siguen sin 3 | Por qué no |
|---|---|---|
| Misma categoría, sin rasgos | 7 | Vuelve la pista gramatical |
| Completar con cualquier palabra de las frases | 4 | Exige guardar el análisis de cada token, y mete fragmentos de contracción (`ca`, `wo` de `can't`, `won't`) |
| Menos de cuatro opciones | 0 | Acertar al azar deja de ser un 25 % y los resultados dejan de ser comparables |

**`token.morph` y no `tag_`**: FEATS de Universal Dependencies es el mismo
formato en inglés y en español (§3.3.1); las etiquetas Penn Treebank de `tag_`
son propias del inglés.
El matiz medido: `en_core_web_sm` no tiene morfologizador, y los rasgos los pone
`attribute_ruler` a partir de la etiqueta Penn y de reglas por palabra. En
inglés, por tanto, `morph` no aporta nada que `tag_` no tenga —ninguna
combinación de categoría y rasgos corresponde a dos etiquetas— y a veces es más
fino de lo que pide la gramática: la etiqueta `MD` se parte en `VerbType=Mod`
(`shall`, `ought`) y `VerbForm=Fin` (`might`, `would`, `could`), y `thy` no
comparte rasgos con `my`. Se acepta por la coherencia entre idiomas.

Se guarda en `contexts.morph`, con los rasgos en orden alfabético. De las 1.024
consultas inglesas, 966 tienen rasgos; 56 son tokens localizados sin rasgos
(`""`, sobre todo adverbios) y 2 no se localizaron (`None`). Confundir esos dos
casos es el error que D-016 evitó con `pos`. La migración `7a2292119592` se
niega a ejecutarse con filas, con el mismo criterio que D-020.

**Mayúsculas: las opciones adoptan el patrón de la respuesta.** Si la respuesta
va capitalizada, se capitalizan las cuatro; si va en mayúsculas, las cuatro en
mayúsculas; si no, las cuatro en minúscula, también la escritura mixta (`PhD`).
En los 999 contextos hay 973 respuestas en minúscula, 22 capitalizadas, 3 en
mayúsculas y 1 mixta. La corrección sigue comparando en minúscula.

Esto hace innecesario cruzar PROPN con mayúsculas: la regla no mira la
categoría, así que no depende de que spaCy acierte con los nombres propios, y
no acierta en ninguna de las dos direcciones. De las 26 respuestas con
mayúscula solo 12 son PROPN; las otras 14 no lo son para spaCy, y casi todas
abren frase o titular (`Biases`, `Hence`, `VACUUM`). Y otras 12 PROPN son
palabras comunes en minúscula (`geese`, `inn`, `kin`). La alternativa
considerada, «minúscula salvo PROPN», dejaba expuestos los 24 ejercicios con
respuesta PROPN: en los 24 hay distractores posibles escritos de otra forma que
la respuesta, porque salen de un grupo PROPN mitad en minúscula, y que se
notara dependía del sorteo. Con el patrón de la respuesta, las cuatro opciones
se escriben igual por construcción: 0 de los 986 ejercicios mezclan
escrituras.

**El corpus se lee en cada llamada**, no una vez por sesión. El caso de uso no
guarda estado, como exigirá la API sin estado de F3 (§3.3.3), y lo que lee está
siempre al día cuando responder cambie el estado de repaso. Medido sobre
Postgres local con el corpus de septiembre: unos 50 ms de mediana por ejercicio
de elección y 23 ms por uno de escritura. No hay nada que optimizar.

**Revisión**: en F3, cuándo pasar de elección a escritura según el progreso de
cada palabra. Si los 13 contextos sin opciones molestan en el uso diario, el
repliegue con palabras de las frases está medido: rescata 9.

---

## D-023 · Un contrato de repositorio por caso de uso

**Fecha**: 2026-09-25 · **Fase**: F0.5

**Decisión**: el puerto de persistencia se separa en dos `Protocol`, cada uno
con lo que necesita su caso de uso: `ImportRepository` (`ensure_user`,
`register_source`, `upsert_entries`) para `import_vocabulary`, y
`StudyRepository` (`ensure_user` y las lecturas de estudio) para
`next_exercise`. `ensure_user` se repite en los dos. La lectura de candidatos
de la variante de elección irá a `StudyRepository`.

**Descartado**: completar los dobles de prueba con los métodos que les
faltaban, como stubs que lanzan `NotImplementedError`. Arreglaba el síntoma y
había que repetirlo con cada método nuevo del puerto.

**Por qué**: al añadir la lectura de `study` al único `VocabularyRepository`,
tres dobles dejaron de cumplir el `Protocol`, cada uno por el lado contrario:

| Doble | Caso de uso | Le faltaba |
|---|---|---|
| `FakeRepository` de `test_import_vocabulary.py` | `import_vocabulary` | la lectura de `study` |
| `FakeRepository` de `test_next_exercise.py` | `next_exercise` | `register_source` y `upsert_entries` |
| `CapturingRepository` de `scripts/profile_normalization.py` | `import_vocabulary` | la lectura de `study` |

Cada uno tenía que implementar métodos que su caso de uso nunca llama, y el
problema crecía con cada método nuevo: la lectura de candidatos habría sido el
siguiente.

**La separación es gratuita para el adaptador.** Un `Protocol` se cumple por
forma, no por herencia: `PostgresVocabularyRepository` satisface los dos
contratos sin declararlo y sin cambiar una línea. Lo comprueba mypy en la raíz
de composición, al pasarlo a cada caso de uso. Verificado quitándole a
propósito la lectura de `study`: el error aparece en `cli/main.py`.

**El fallo lo vio el editor, no la verificación.** Los tests pasaban —Python no
comprueba un `Protocol` en tiempo de ejecución— y mypy solo revisaba el paquete
`vocab`, no `tests/` ni `scripts/`. Lo marcó Pylance al abrir un test. Ahora
mypy revisa también esos dos directorios con una configuración más laxa: no
exige anotar, pero revisa el cuerpo de las funciones sin anotar y obliga a
completar las que se anotan a medias. Destapó además 9 errores de anotación en
5 funciones auxiliares de los tests, ya corregidos. Es la lección de D-017 otra
vez: una regla que solo se comprueba si alguien se acuerda no está comprobada.

**Coste**: dos contratos en vez de uno y `ensure_user` declarado dos veces.

---

## D-024 · Ollama se ejecuta fuera de compose

**Fecha**: 2026-10-05 · **Fase**: F1

**Decisión**: Ollama sigue nativo en WSL2 (D-001) y la aplicación lo localiza
por variable de entorno.

**Descartado**: el servicio `ollama` de §8.1, en compose y con GPU.

**Por qué**:

- §3.3.3 protege el artefacto desplegable, y Ollama no forma parte de él: en
  producción se sustituye por una API (§8.2). Es un servicio de respaldo.
- Los tests no lo necesitan, porque usan un doble.
- La CI no tendría GPU.
- Contenerizarlo con GPU en WSL2 sería infraestructura sin validar: §12.1
  validó la instalación nativa.

Las versiones del servidor y del modelo se registrarán con el arnés de F2.

**Revisión**: en F3, cuando `api` corra en compose y tenga que alcanzar Ollama,
que por defecto solo escucha en `127.0.0.1`. Dato para esa revisión: Docker
funciona con Docker Desktop y su integración con WSL, no con Docker Engine
dentro de Ubuntu.

---

## D-025 · Fuente de la definición correcta y política conservadora de sentidos

**Fecha**: 2026-10-05 · **Fase**: F1

**Decisión**:

- Fuente: Open English WordNet, edición `oewn:2025`, con el paquete `wn` 1.1.1.
- `mcq_definition` solo en los contextos cuyo (lema, categoría) tiene un único
  sentido en el léxico y cuyo lema coincide con el que el léxico deduce de la
  forma consultada. El resto, `cloze_original`.

**Descartado**:

- Una API externa en ejecución: rompe §2.4, y el arnés necesita que la
  respuesta correcta no cambie entre ejecuciones.
- Una definición generada por un LLM: la clave del ejercicio sería fabricada
  (D-010).
- Princeton WordNet: OEWN es su continuación mantenida.
- Wiktionary: no se midió. La regla, fijada antes de medir, era medirlo solo si
  OEWN perdía cobertura por formas no encontradas, y la pérdida venía de la
  polisemia.
- `oewn:2025+`: sus nombres propios sumarían sentidos a palabras comunes al
  comparar en minúsculas.

**Medido** con `scripts/measure_definition_source.py` (commit `c67f305`) sobre
los 999 contextos utilizables de entradas `learning` de la exportación de
septiembre de 2026. Repetida, la salida es idéntica byte a byte.

| Categoría | Contextos |
|---|---|
| `pos_unmapped` | 40 (PROPN 24, ADP 5, AUX 4, SCONJ 4, CCONJ 1, NUM 1, PRON 1) |
| `form_not_found` | 44 |
| `lemma_disagrees` | 27 (7 con el lema ausente, 20 con el lema acompañado de otros) |
| `monosemous` | 274 |
| `polysemous` | 614 |

**Por qué la política conservadora**:

- Elegir mal el sentido enseña un significado falso, el daño de D-008.
- Ninguna palabra se queda sin ejercicio, porque `cloze_original` siempre está
  disponible.
- Saca la desambiguación de F1, y es determinista.
- 274 contextos bastan para construir y demostrar el bucle de A1 (§10: hasta F3
  manda el objetivo profesional).

**Control de lema**: los 27 contextos de `lemma_disagrees` van a
`cloze_original` (ver D-015).

**Medición de la primera acepción, preparada y no ejecutada**:

- Script: `scripts/sample_first_sense.py` (commit `c67f305`).
- Población: los 605 contextos `polysemous` sin los marcados por R1. Muestra de
  50, semilla 20261005.
- Criterio de etiquetado: «¿enseñar esta definición daría un significado falso
  en esta frase?». Las dudas cuentan como daño.
- Umbral del 10 %, fijado antes de etiquetar, con intervalo de Wilson al 95 %:
  0 casos dañinos → primera acepción; de 1 a 9 → no concluyente, política
  conservadora; 10 o más → selector con LLM justificado.
- No se ejecutó porque exige etiquetado humano, y con etiquetas de un LLM
  ningún resultado cambiaba la decisión de F1.
- El orden de sentidos de `wn` se verificó contra el XML: el primer sentido de
  `bank` es la orilla, como en Princeton 3.0.
- Lemas en varias entradas (7 de los 605): primero la escritura exacta, después
  `a` antes que `s`, después el orden del léxico.

**Licencia**: CC BY 4.0. No se contempla la comercialización (§11, pregunta 4).
Los datos no se commitean: se descargan.

**Revisión**:

- En F4, la selección de sentido, cuando §6.4 ya exija etiquetado humano.
  - R1 detecta unidades de dos piezas, y *come up with* tiene tres.
    Comprobado en `oewn:2025`: `come up with` no es un lema propio, y su uso
    cae en un sentido de `come up` («bring forth», con el ejemplo «came up with
    some recommendations»). En este caso, un selector tendría una opción
    válida.
  - Que un selector con LLM pueda responder «ninguno» sigue siendo un
    requisito por principio: el léxico puede no tener el sentido del contexto.
    Todavía no hay un caso del corpus que lo demuestre.
- Al hacer el adaptador: `wn` pasa a dependencia principal y el léxico se
  provisiona en la imagen (lección de D-021).

**Actualización (2026-10-09)**:

- `chewed up` es el caso del corpus que faltaba (D-032).
- La seguridad de la política conservadora era una suposición: un único
  sentido en el léxico no garantiza que sea el sentido del contexto.
- El riesgo entre los 270 contextos `eligible` está sin medir, y se medirá
  con el etiquetado de F2 (D-034).
- Con R1 son 270, no 274.
- La selección de sentido pasa de F4 a F2 (D-034).
- Del punto «Al hacer el adaptador», `wn` ya es dependencia principal
  (D-031); falta el léxico en la imagen.

---

## D-026 · Un puerto por tarea de IA, no un `run` genérico

**Fecha**: 2026-10-06 · **Fase**: F1

**Decisión**: un `Protocol` en `ports/`,
`DistractorGenerator.generate(DistractorRequest) -> GeneratedDistractors`. Dos
excepciones: `GeneratorUnavailable` (degradar) y `MalformedOutput` (reintentar
con el motivo). El modelo de cada tarea se elige en la raíz de composición.

**Descartado**: el `llm.run(task, input)` genérico de D-007 y §3.3.4.

**Por qué**:

- Tipos exactos con mypy estricto.
- En F1 hay una sola tarea, así que la generalidad sería abstracción sin uso.
- El objetivo de D-007 se mantiene: ningún modelo en el código y configuración
  por tarea.

**Detalles**:

- `Protocol` y no `Callable`, porque un generador tiene estado que inyectar
  (criterio de D-016).
- Tipos de la biblioteca estándar; Pydantic irá en el adaptador.
- `tuple[str, str, str]`, para que mypy compruebe que son tres.
- `model` y `prompt_version` vuelven en el resultado.
- Forma (exactamente tres cadenas) frente a contenido (vacías o repetidas): lo
  segundo es de los validadores.

**Verificado**: al renombrar `generate` en una copia del doble, mypy falla en la
asignación tipada.

**Revisión**: en F4, con las otras dos tareas.

---

## D-027 · Validadores deterministas de F1: básico, D1 y D7

**Fecha**: 2026-10-06 · **Fase**: F1

**Decisión**: funciones puras del dominio que devuelven códigos e índices, no
texto.

- Básico: `EMPTY` y `DUPLICATE`.
- D1 (`OVERLAPS_CORRECT`): la definición correcta está contenida en un
  distractor, o al revés. Se compara por secuencias de palabras, no por
  subcadenas (la trampa de D-019).
- D7 (`NEGATION`): lista cerrada de marcadores, indexada por idioma y sin
  prefijos. Solo marca si la definición correcta no niega.
- Un idioma sin lista provoca `ValueError`, al revés que D-013: sin
  marcadores, D7 daría por bueno cualquier distractor negativo y nadie lo
  notaría.
- La tokenización no depende del alfabeto inglés y normaliza a NFC.

**Descartado**:

- D2: necesita spaCy, que no puede entrar en el dominio; exigiría otro puerto,
  y el arnés de F2 lo mide igualmente.
- D3: la v1 es solo inglés, y el fallo de idioma solo se vio con Qwen3 (D-002).
- D4: es de frases generadas (A2, F4).
- D5 y D6: no son de generación.
- Los prefijos de D-005: marcarían `interesting`, `under` o `uniform`.

**Por qué códigos**: el informe se guarda y se cuenta, y el texto que lee el
modelo depende del idioma del prompt.

**Límites**:

- D7 no ve antónimos léxicos: «Prone to breaking down under pressure» (§12.4)
  pasa. Lo cubre J2.
- D1 no ve paráfrasis. Lo cubre J1.

**Revisión**: en F2 (arnés) y en F4 (juez).

**Actualización (2026-10-07)**: evidencia con el modelo real, sin medición
formal:

- En 2 de los 3 ejemplos de integración, un distractor era un antónimo
  léxico de la correcta: «capable of being broken easily» para `resilient`,
  y «want to avoid something» para `craved`.
- En otra ejecución salió una paráfrasis de la correcta para `craved`
  («feel a strong urge for»).
- D7 marcó las negaciones de §12.4, y D1, la definición correcta copiada
  como distractor.

---

## D-028 · Bucle de generación: el motivo del reintento viaja como datos

**Fecha**: 2026-10-06 · **Fase**: F1

**Decisión**: un intento inicial y, como máximo, dos reintentos. Así se leen
juntos «máximo 2» y «si falla 2 veces» de §7.3.

- El reintento lleva `RejectedDistractors` (los distractores anteriores y sus
  violaciones) o `MalformedAnswer` (el motivo), siempre solo del último fallo.
- El texto que lee el modelo lo escribe el adaptador con las plantillas del
  prompt.

**Descartado**: traducir los códigos a frases en la aplicación.

**Por qué**:

- Cómo se explica el fallo cambia lo que responde el modelo. Si esa frase vive
  en Python, cambiarla no cambia `prompt_version` y el arnés no puede atribuir
  el resultado (D-007, regla 3).
- Una frase en inglés en la aplicación sería una rama de idioma en el código
  (§3.3.1).
- Los distractores anteriores viajan porque cada llamada al modelo es
  independiente.

**Proveedor no disponible**: se degrada al momento, sin reintentar, y se
conserva el motivo para avisar. Sin aviso, un nombre de modelo mal escrito
degradaría en silencio. Los reintentos de errores de transporte pasajeros,
incluida la carga del modelo en Ollama, son del adaptador.

El `ValueError` del validador no se captura. La función no imprime nada:
devuelve la causa.

**Historial**: registra cada intento: aceptado; rechazado, con los distractores
y las violaciones; mal formado; o no disponible.

**Actualización (2026-10-07)**: la carga del modelo ya no la cubre un
reintento, sino el tiempo de espera. Un tiempo agotado no se reintenta; solo
los 5xx (D-030).

---

## D-029 · Plantillas del prompt: en inglés, en TOML dentro del paquete

**Fecha**: 2026-10-07 · **Fase**: F1

**Decisión**:

- Un archivo TOML por (tarea, idioma, versión), dentro del paquete, leído con
  `importlib.resources` y `tomllib`: `prompts/distractors/en/v1.toml`.
- Contiene el mensaje de sistema, el de usuario, el reintento por rechazo
  (`[retry_rejected]`, con las plantillas de línea `kept` y `rejected`), el
  reintento por salida mal formada (`[retry_malformed]`), una frase por
  `ViolationCode` (`[violations]`) y una por cada forma de salida mal formada
  (`[malformed]`).
- Plantillas con `string.Template`, porque el prompt contiene JSON con llaves.
- Se valida al cargar: una clave desconocida o un `ViolationCode` sin frase
  fallan al construir el adaptador, no en la primera llamada.
- El reintento va como un segundo mensaje `user`.

**El prompt está en inglés.** Se aparta de la configuración de referencia de
§12.5, con el prompt en español y «Responde únicamente en inglés». Qwen3.5
responde en el idioma del prompt, así que escribirlo en inglés elimina ese modo
de fallo en vez de parchearlo. Encaja con §3.3.1: el prompt de `en` se escribe
en inglés, y el de `es`, en F7, en español.

**Idioma de los motivos**: los de `MalformedOutput` están en inglés y en el
TOML, porque vuelven al modelo (D-028). Los de `GeneratorUnavailable` están en
español, porque los lee el usuario.

**Descartado**:

- El prompt en el código: cambiarlo no cambiaría `prompt_version`, y el arnés
  no podría atribuir los resultados (D-007, regla 3).
- El prompt en una carpeta fuera del paquete: habría que copiarla a la imagen
  y configurar su ruta (lección de D-021).

**Observado con el modelo real, sin medición formal**: en un reintento, el
modelo conservó el distractor que se le pidió sustituir y escribió la
definición correcta como distractor. D1 lo marcó, y se aceptó al tercer
intento.

**Revisión**: en F2, como primer experimento del arnés, `v1` frente a una `v2`
con ejemplos (*few-shot*). Riesgos a medir:

- que el modelo copie los ejemplos;
- que los ejemplos negativos empujen hacia ese patrón;
- la fuga de datos si los ejemplos salen del conjunto de evaluación.

---

## D-030 · Adaptador de Ollama: configuración por tarea y transporte

**Fecha**: 2026-10-07 · **Fase**: F1

**Configuración**, con pydantic-settings y el delimitador anidado `__`:

- Por tarea: `LLM_TASK__DISTRACTORS__PROVIDER`, `__MODEL` y
  `__PROMPT_VERSION`. Opcionales: `__THINK` y `__TEMPERATURE`; si no se
  definen, no se envían.
- Por proveedor: `OLLAMA_BASE_URL` y `OLLAMA_TIMEOUT_SECONDS`.
- Los nombres van en inglés por la regla de `CLAUDE.md`; el ejemplo de §3.3.4
  los tenía en español.
- La sección es opcional, para que `import` y `study` arranquen sin ella.
- Un `PROVIDER` distinto de `ollama` falla al cargar la configuración: en F1
  es el único adaptador.
- El modelo solo aparece en `.env` y `.env.example` (D-007).

**Petición**:

- `POST /api/chat`, con `stream: false`, `think` según la tarea y `format` con
  el esquema JSON del modelo Pydantic de salida (D-004).
- Se valida `message.content` con Pydantic: exactamente tres cadenas, sin
  campos extra. JSON inválido, otro número de distractores o una respuesta
  cortada por longitud (`done_reason`) → `MalformedOutput`.
- Un 2xx sin `message.content` → `GeneratorUnavailable`: quien responde no es
  `/api/chat`.

**Transporte**:

- Un único reintento, tras 1 s, solo para respuestas 5xx.
- Conexión rechazada, 4xx o tiempo agotado → `GeneratorUnavailable` al
  momento, con la URL y el modelo en el motivo.
- La política es de este adaptador y supone un Ollama local. Un adaptador de
  API decidirá la suya con sus propias mediciones (F6).

**Tiempo de espera**: 150 s por defecto. Medido con GPU (34/34 capas), con el
prompt `v1` (358 tokens de entrada), `think: false` y el ejemplo `craved`:

| Llamada | `load_duration` | `total_duration` |
|---|---|---|
| Frío 1 | 41,902 s | 71,201 s |
| Frío 2 | 5,643 s | 6,579 s |
| Frío 3 | 5,398 s | 6,170 s |
| Caliente 1 | 0,002 s | 0,583 s |
| Caliente 2 | 0,001 s | 0,518 s |
| Caliente 3 | 0,002 s | 0,524 s |

Frío 1 fue la primera carga tras arrancar Ollama. Es una sola muestra, y su
causa no se conoce. Con 30 s, esa primera petición degradaría siempre.

**Dependencias**: `httpx` y `pydantic` pasan a ser directas; `httpx` queda
prohibido en el dominio en import-linter.

**Descartado**: reintentar un tiempo agotado. Con un tiempo de espera que ya
cubre la carga del modelo, solo duplica la espera antes de degradar.

**Revisión**: en la pieza de la CLI.

- Precalentamiento al empezar la sesión: si el modelo no está cargado,
  cargarlo con un tiempo de espera largo y avisar al usuario.
- Durante la sesión, un tiempo de espera corto para generar.
- Dos tiempos de espera configurables.

---

## D-031 · Puerto del léxico y adaptador de OEWN

**Fecha**: 2026-10-09 · **Fase**: F1

**Decisión**:

- Un `Protocol` `Lexicon` en `ports/`, porque el adaptador tiene estado
  (criterio de D-016): `facts(list[LexiconQuery]) -> dict[str, LexiconFacts]`,
  con `LexiconQuery(external_id, term, lemma, pos, lang)`.
- Los hechos (`Sense` y `LexiconFacts`) son tipos del dominio.
- La política de D-025 es una función pura del dominio:
  `decide_definition(lemma, particle, facts) -> DefinitionDecision`.
- `DefinitionStatus` tiene valores escritos a mano: `eligible`,
  `pos_unmapped`, `form_not_found`, `lemma_disagrees`, `lexical_unit` y
  `polysemous`.
- `DefinitionDecision` exige que la definición y el sentido vayan juntos, y
  solo con `eligible`.

**El adaptador solo devuelve hechos**:

- Los lemas a los que Morphy lleva la forma consultada.
- Los sentidos del lema, sin lematizar y con `search_all_forms=False`.
- `ADJ` cubre `a` y `s`, y todo se compara en minúsculas.
- `LEXICON = "oewn:2025"`, como constante: cambiarlo exige volver a medir.
- Solo inglés: cualquier otro idioma da `ValueError` antes de consultar nada
  (§3.3.1).

**Descartado**: que el adaptador aplique la política de D-025. La regla solo
se podría probar con el diccionario delante, y cambiar de diccionario
obligaría a reescribirla. Por eso el adaptador solo devuelve hechos y la
política es una función pura del dominio.

**Dependencias y arranque**:

- `wn` pasa a dependencia principal (`>=1.1.1,<1.2`; la versión medida).
- Un override de mypy `implicit_reexport`, solo para el módulo `wn`, permite
  usar `wn.config` sin tocar el módulo privado `wn._config`.
- `wn` queda prohibido en el dominio.
- Si el léxico no está descargado en `WN_DATA_DIR`, el adaptador falla al
  construirse con el comando de descarga; `wn` crearía una base vacía.

**Verificado**: sin partícula, el test sobre la exportación de septiembre
reproduce exactamente la tabla de D-025.

**Pendiente**: el léxico en la imagen Docker (lección de D-021), con la pieza
que guarda la definición al importar.

---

## D-032 · Todo contexto que marca R1 va a `cloze_original` en F1

**Fecha**: 2026-10-09 · **Fase**: F1

**Decisión**: si R1 marca la palabra, el estado es `lexical_unit` y el
ejercicio es `cloze_original`, se encuentre o no la unidad en el léxico. El
adaptador deja de buscar la unidad.

**Descartado**: buscar la definición de la unidad (D-008, «Pendiente en F1»,
punto 1).

**Por qué**: `chewed up`. En «…have our money chewed up and spit out», la
unidad `chew up` tiene un único sentido en `oewn:2025`, «censure severely or
angrily», que en esa frase es falso. De las 3 unidades con un solo sentido, 1
lo es; `sponged up` y `stamp out` encajan. Un falso positivo de R1 no es
barato, al contrario de lo que suponía D-008.

**Resultado** sobre los 999 contextos utilizables de entradas `learning` de la
exportación de septiembre de 2026:

| Estado | Contextos |
|---|---|
| `pos_unmapped` | 40 |
| `form_not_found` | 44 |
| `lemma_disagrees` | 27 |
| `lexical_unit` | 13 |
| `eligible` | 270 |
| `polysemous` | 605 |

Sin partícula, los 13 contextos de R1 eran 4 `eligible` y 9 `polysemous`.

**Revisión**: la búsqueda de la unidad vuelve con la selección de sentido
(D-034, F2).

---

## D-033 · La definición se busca al importar y se guarda

**Fecha**: 2026-10-09 · **Fase**: F1

**Decisión**: al importar, cada contexto nuevo consulta el léxico y guarda en
Postgres su estado, y la definición y el sentido si es `eligible`. `study` lee
de la base, y no carga ni spaCy ni el léxico.

**Descartado**: buscar la definición al estudiar.

**Por qué**:

- Es el mismo patrón que `pos`, `morph` y `term` (D-020, D-022).
- La respuesta correcta de cada ejercicio queda como un dato fijo y auditable,
  que es lo que exige el arnés (D-025).
- `study`, y la API de F3, siguen siendo ligeros.
- La plantilla de degradación se reduce a una consulta a la base.

**El léxico** ocupa unos 104 MB en `WN_DATA_DIR`, la base SQLite y la
descarga. Cada búsqueda es una consulta; no se carga entero en memoria. Solo
se usa al importar, y solo para los contextos nuevos (D-012).

**Coste**:

- Una migración y reimportar, sin progreso que perder hasta F3.
- Si cambian el léxico o la política (D-034), hay que recalcular los
  contextos existentes, porque la reimportación no los toca.

**Estado**: decidida, sin implementar.

---

## D-034 · La desambiguación de sentidos pasa a F2, como comparación medida

**Fecha**: 2026-10-09 · **Fase**: F1

**Decisión**: en F2 se comparan métodos para elegir el sentido del contexto:

- la primera acepción, como referencia;
- Lesk;
- embeddings;
- modelos de desambiguación entrenados sobre WordNet;
- un selector con LLM, Qwen3.5 local o una API;
- Jev, el clasificador alojado de TypeSafe, cuyas probabilidades calibradas
  permiten abstenerse con un umbral.

Cada método es un adaptador del mismo puerto.

**La comparación incluye resolver el lema**: cuando el léxico da varios lemas
(20 de los 27 `lemma_disagrees`), el selector recibe los sentidos de todos los
candidatos; cuando da uno solo (los otros 7), se usa ese.

**Requisito**: el selector puede responder «ninguno». Con «ninguno», o con
poca confianza, `cloze_original`.

**Etiquetado de referencia**:

- Dos modelos de otra familia que los candidatos etiquetan por separado, en un
  chat y una sola vez: el sentido correcto o «ninguno».
- Se registra qué modelo, cuándo y con qué instrucción.
- Las coincidencias se aceptan; las discrepancias las decide Carlos.
- Revisión manual de unas 20 coincidencias al azar.
- Los resultados se dan sobre la referencia completa y sobre la parte
  revisada a mano.

**Descartado**:

- Mantener la política conservadora hasta F4 (D-025): solo 270 de 999
  contextos tienen opción múltiple, y 605 de los que no la tienen son
  polisémicos.
- Un único etiquetador sin validar: sería circular y de precisión desconocida.
- Etiquetarlo todo a mano.

**Por qué**: es el cuello de botella de cobertura de `mcq_definition`, y
comparar métodos con una referencia validada es material central del perfil.

**Mientras tanto**, F1 cierra con la política conservadora: 270 de 999
contextos.

**A investigar en F2**: el precio de Jev, y la licencia y la calidad de
Nimble, Laya y los modelos de desambiguación.

**Revisión**: al cerrar F2, con los números.

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
