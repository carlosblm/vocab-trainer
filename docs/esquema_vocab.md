# Esquema de `vocab.db` (Kindle Vocabulary Builder)

Documento de referencia sobre el formato de entrada. Todo lo que hay aquí está **verificado sobre un archivo real** (1.345 palabras, 1.511 consultas, 25 libros, julio 2024 – agosto 2026), no sacado de documentación.

Es un SQLite corriente. Se encuentra en el Kindle, por USB, en `system/vocabulary/vocab.db`.

---

## 1. Aviso previo: no hay claves foráneas

**La base de datos no declara ninguna relación.** Las tablas se relacionan por convención, no por restricción del motor. Por eso un cliente gráfico como DBeaver no dibuja ninguna conexión entre ellas y parece que las palabras y sus frases no están vinculadas.

Lo están. Estas son las relaciones reales:

```
LOOKUPS.word_key  →  WORDS.id
LOOKUPS.book_key  →  BOOK_INFO.id
LOOKUPS.dict_key  →  DICT_INFO.id
```

Verificado sobre el archivo real: **0 palabras sin consulta y 0 consultas huérfanas**. La integridad se cumple pese a no estar declarada.

---

## 2. Tablas

### `WORDS` — el vocabulario consultado

```sql
CREATE TABLE WORDS (
  id        TEXT PRIMARY KEY NOT NULL,
  word      TEXT,
  stem      TEXT,
  lang      TEXT,
  category  INTEGER DEFAULT 0,
  timestamp INTEGER DEFAULT 0,
  profileid TEXT
);
```

| Campo | Contenido | Notas |
|---|---|---|
| `id` | `es:prebenda`, `en:resilient` | **Idioma + dos puntos + palabra.** No es numérico |
| `word` | La palabra tal como aparecía en el texto | Conserva la capitalización original: `Salvo`, `Hay` |
| `stem` | Forma lematizada | Ver §4.1 |
| `lang` | `es`, `en` | Fiable. **Usar este campo, no detectar el idioma** |
| `category` | 0 o 100 | Ver §4.4 |
| `timestamp` | Epoch en **milisegundos** | Dividir entre 1000 para convertir |
| `profileid` | Vacío en el archivo analizado | Ignorable |

```
('es:prebenda', 'prebenda', 'prebenda', 'es', 0, 1722290207037, '')
('es:entereza', 'entereza', 'entereza', 'es', 0, 1722290348067, '')
```

### `LOOKUPS` — cada consulta, con su contexto

Es la tabla que importa. **Aquí vive la frase del libro.**

```sql
CREATE TABLE LOOKUPS (
  id        TEXT PRIMARY KEY NOT NULL,
  word_key  TEXT,
  book_key  TEXT,
  dict_key  TEXT,
  pos       TEXT,
  usage     TEXT,
  timestamp INTEGER DEFAULT 0
);
```

| Campo | Contenido | Notas |
|---|---|---|
| `id` | `CR!0DHF...:AQ04AACSAQAA:384195:8` | Compuesto por libro y posición |
| `word_key` | → `WORDS.id` | |
| `book_key` | → `BOOK_INFO.id` | |
| `dict_key` | → `DICT_INFO.id` | El diccionario usado |
| `pos` | `AYo4AADGBAAA:1402162` | **NO es categoría gramatical.** Ver §4.2 |
| `usage` | La frase completa del libro | El activo del proyecto. Ver §4.3 |
| `timestamp` | Epoch en milisegundos | |

Una misma palabra puede tener varias filas si se consultó en libros o pasajes distintos. En el archivo analizado: 1.212 palabras con una consulta, 109 con dos, 17 con tres, 6 con cuatro y 1 con seis.

### `BOOK_INFO` — los libros

```sql
CREATE TABLE BOOK_INFO (
  id TEXT PRIMARY KEY NOT NULL, asin TEXT, guid TEXT,
  lang TEXT, title TEXT, authors TEXT
);
```

```
('CR!475YHJ...', 'MHE7ZZC6...', 'CR!475YHJ...', 'es',
 'Churchill . La biografia', 'Andrew Roberts')
```

El `title` viene tal como estaba en el archivo del libro, con la suciedad que eso implica: espacios sobrantes, guiones bajos, sin acentos. **Hay que normalizarlo antes de mostrarlo.**

Ojo: `BOOK_INFO.lang` es el idioma del libro y `WORDS.lang` el de la palabra. Normalmente coinciden, pero no hay garantía.

### `DICT_INFO` y `METADATA`

Auxiliares. `DICT_INFO` guarda qué diccionario se usó, con idioma de entrada y salida (`es`→`es`, `en`→`en`, o sea diccionarios monolingües). `METADATA` guarda contadores internos de sincronización, sin interés para el proyecto.

---

## 3. La consulta base

```sql
SELECT
  w.id            AS word_id,
  w.word          AS palabra,
  w.stem          AS lema,
  w.lang          AS idioma,
  l.usage         AS frase,
  b.title         AS libro,
  b.lang          AS idioma_libro,
  l.timestamp     AS consultado_ms
FROM LOOKUPS l
JOIN WORDS     w ON l.word_key = w.id
JOIN BOOK_INFO b ON l.book_key = b.id
WHERE w.lang = 'en'
ORDER BY l.timestamp DESC;
```

---

## 4. Trampas conocidas

Cinco cosas que hay que resolver en la ingesta. Ninguna es opcional.

### 4.1 `stem` es una lematización parcial y ruidosa

Solo 825 de 1.345 registros tienen `stem` idéntico a `word`. En el resto, la lematización a veces es correcta y a veces no:

| `word` | `stem` | Valoración |
|---|---|---|
| `tribulaciones` | `tribulación` | Correcto |
| `abluciones` | `ablución` | Correcto |
| `Hay` | `haber` | Correcto |
| `Vidas` | `vida` | Correcto |
| `Salvo` | `salvo` | Solo baja la capitalización |
| `fiat` | `fíat` | **Añade una tilde que no estaba** |

**Decisión de diseño**: usar `stem` como pista, pero **derivar el lema con spaCy** para tener consistencia y control. No fiarse del campo para deduplicar.

### 4.2 `pos` no es *part of speech*

Es el error más fácil de cometer, porque el nombre lo sugiere. El contenido real es `AYo4AADGBAAA:1402162`: un identificador de posición dentro del libro.

**La categoría gramatical no está en la base de datos.** Hay que derivarla con spaCy analizando la palabra dentro de su frase de contexto, que además es más fiable que una etiqueta aislada porque desambigua por contexto.

Es un requisito de la métrica D2 (homogeneidad gramatical de los distractores).

### 4.3 `usage`: el activo del proyecto

Lo bueno, verificado sobre el archivo real:

- **1.511 de 1.511 consultas tienen frase.** Cobertura del 100 %.
- **La palabra aparece literalmente en su frase el 100 % de las veces.** Esto hace que el ejercicio de hueco (`cloze_original`) sea una sustitución de cadena trivial y perfectamente fiable, sin necesidad de ningún modelo.
- Longitud media: 178 caracteres. Máxima: 1.003.
- **1.421 de 1.511 terminan en punto.** El contexto llega completo.

**Truncamiento: marginal.** El Kindle guarda la frase completa, no un recorte por longitud.

| Terminación de la frase | Casos |
|---|---|
| Punto | 1.421 |
| Interrogación o exclamación | 32 |
| Comillas de cierre (`”`, `’`, `»`) | 27 |
| Sin puntuación reconocible | 28 (1,9 %) |

De esas 28, la mayoría terminan en `[`, que es el inicio de una llamada a nota al pie del libro. **Frases realmente cortadas: unas 5 o 6 de 1.511.**

Se recorta a frase completa con el segmentador de spaCy por higiene, pero no es un riesgo del proyecto. **Nunca completar el texto que falta con un modelo**: no existe en la base de datos, así que solo se puede fabricar.

**Espacios sobrantes.** 1.485 de 1.511 frases empiezan o terminan con espacio. Un `trim()` obligatorio.

**Llamadas a notas al pie.** Algunas frases terminan con `[` o contienen `[59]`: son referencias del libro que se han colado en el recorte. Hay que limpiarlas antes de mostrarlas.

### 4.4 `category`: interpretación no confirmada

Toma el valor 0 en 1.344 registros y 100 en uno solo. La interpretación probable es *en aprendizaje* frente a *dominada*, marcada desde el propio Kindle.

**No está confirmado** y, con un solo caso, tampoco se puede inferir del archivo. **No usar este campo hasta verificarlo.** El estado de aprendizaje lo gestiona FSRS dentro de la aplicación, así que no es bloqueante.

### 4.5 Ruido por toques accidentales

Entre las palabras consultadas aparecen `En` y `Salvo`: pulsaciones involuntarias sobre palabras funcionales mientras se pasaba página.

Hay que filtrarlas con listas de palabras vacías por idioma. Sin ese filtro, la aplicación pedirá estudiar preposiciones que el usuario ya conoce, y el usuario abandonará.

---

## 5. Perfil del archivo de referencia

| Métrica | Valor |
|---|---|
| Palabras únicas | 1.345 |
| Consultas totales | 1.511 |
| Libros | 25 |
| Inglés / español | 753 / 592 |
| Rango temporal | jul. 2024 – ago. 2026 |
| Consultas con contexto | 1.511 (100 %) |
| Longitud media del contexto | 178 caracteres |
| Palabras con una sola consulta | 1.212 |

**Volumen**: suficiente de sobra para la aplicación, del todo insuficiente para entrenar nada. Confirma que el proyecto es de inferencia, orquestación y evaluación.

**Historial de repaso**: 1.212 de 1.345 palabras tienen una sola consulta, así que la curva de repetición espaciada arranca casi de cero y se construye con el uso.

---

## 6. Nota sobre el desacoplamiento

Todo lo descrito aquí vive **exclusivamente** dentro del adaptador `KindleVocabImporter`. El dominio de la aplicación no conoce estas tablas, ni el formato de los identificadores, ni la palabra «Kindle».

Un importador de CSV tendría que producir el mismo modelo canónico (§4.3 de la propuesta) y nada más cambiaría.
