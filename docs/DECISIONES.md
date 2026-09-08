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

**Incidencia medida**: 5 o 6 casos reales en 845 consultas en inglés (menos del 1 %). Bajo en volumen, grave en efecto.

**El problema es la detección, no la generación.** Una regla de "palabra seguida de partícula" da **80 % de falsos positivos** sobre el corpus real (`sojourn in`, `stake in`, `tycoons in` son sustantivo más preposición). Orden previsto: dependencias de spaCy, después lista de phrasal verbs frecuentes, y LLM solo como último recurso porque tiende a los falsos positivos.

**Sin verificar**: la precisión del análisis de dependencias sobre frases truncadas (el 40 % aproximado del corpus). Es el primer número a medir en la F0.

**Métrica asociada**: D8.

---

## D-009 · `preposition_cloze` entra en la v1 y no usa IA

**Fecha**: 2026-09-07 · **Fase**: diseño (implementación en F0)

**Decisión**: añadir un tipo de ejercicio que tapa la preposición que sigue a la palabra consultada, con distractores tomados de un conjunto cerrado de preposiciones. **Sin ninguna llamada a un modelo.**

**Descartado**: generar los distractores con un LLM. Innecesario: el espacio de candidatos es cerrado (unas cuarenta preposiciones) y se pondera por la frecuencia observada en el propio corpus del usuario.

**Por qué entra en la v1**:

- **Cobertura**: 178 de 845 consultas en inglés (**21 %**) tienen la palabra seguida de preposición. Frente al <1 % de los phrasal verbs, hay volumen de sobra.
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

## Plantilla para nuevas entradas

```markdown
## D-0XX · Título en una línea

**Fecha**: AAAA-MM-DD · **Fase**: FX

**Decisión**: qué se hace.

**Descartado**: qué alternativa se consideró y no se eligió.

**Por qué**: el motivo, con números si los hay.

**Revisión**: en qué momento y con qué criterio se reevaluaría. Omitir si es definitiva.
```
