# Esquema de `vocab.db` (Kindle Vocabulary Builder)

Documento de referencia sobre el formato de entrada. Todo lo que hay aquí está **verificado sobre archivos reales** —dos exportaciones del mismo Kindle, de agosto y septiembre de 2026—, no sacado de documentación.

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

Verificado sobre los archivos reales: **0 palabras sin consulta y 0 consultas huérfanas**. La integridad se cumple pese a no estar declarada.

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
| `timestamp` | Epoch en **milisegundos** | Es la **última** consulta, no la primera. Ver §5.1 |
| `profileid` | Vacío en los archivos analizados | Ignorable |

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
| `id` | `CR!0DHF...:AQ04AACSAQAA:384195:8` | Compuesto por libro y posición. Estable entre exportaciones (§5.2) |
| `word_key` | → `WORDS.id` | |
| `book_key` | → `BOOK_INFO.id` | |
| `dict_key` | → `DICT_INFO.id` | El diccionario usado |
| `pos` | `AYo4AADGBAAA:1402162` | **NO es categoría gramatical.** Ver §4.2 |
| `usage` | La frase completa del libro | El activo del proyecto. Ver §4.3 |
| `timestamp` | Epoch en milisegundos | Inmutable. Es el momento de esa consulta concreta |

Una misma palabra puede tener varias filas si se consultó en libros o pasajes distintos. En el archivo de septiembre de 2026: 1.357 palabras con una consulta, 121 con dos, 19 con tres, 7 con cuatro y 1 con seis.

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
  l.id            AS lookup_id,
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

Solo 921 de 1.505 registros tienen `stem` idéntico a `word`. En el resto, la lematización a veces es correcta y a veces no:

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

Lo bueno, verificado sobre 1.690 consultas:

- **1.690 de 1.690 consultas tienen frase.** Cobertura del 100 %.
- **La palabra aparece literalmente en su frase el 100 % de las veces.** Comprobado en las dos exportaciones. Esto hace que el ejercicio de hueco (`cloze_original`) sea una sustitución de cadena trivial y perfectamente fiable, sin necesidad de ningún modelo.
- Longitud media: 172 caracteres. Máxima: 1.003.

**El problema no es el truncamiento, es la suciedad.** El Kindle guarda la frase completa, no un recorte por longitud.

| Terminación de la frase | Casos |
|---|---|
| Punto | 1.584 |
| Interrogación o exclamación | 36 |
| Comillas de cierre (`”`, `’`, `»`) | 39 |
| Sin puntuación reconocible | 31 (1,8 %) |

De esas 31, 17 terminan en `[`: la frase está completa y lo que sobra es el inicio de una llamada a nota al pie del libro. **Frases realmente cortadas a mitad: unas 11 de 1.690** (0,7 %).

El trabajo de ingesta que esto exige es **limpieza de sufijo, no rescate de frases rotas**. El segmentador de spaCy queda como salvaguarda para esa decena de casos. **Nunca completar el texto que falta con un modelo**: no existe en la base de datos, así que solo se puede fabricar.

**Espacios sobrantes.** 1.665 de 1.690 frases (98,5 %) empiezan o terminan con espacio. Un `trim()` obligatorio.

**Llamadas a notas al pie.** Algunas frases terminan con `[` o contienen `[59]`: son referencias del libro que se han colado en el recorte. Hay que limpiarlas antes de mostrarlas.

### 4.4 `category`: no se usa

Toma el valor 0 en 1.504 registros y 100 en uno solo (`en:managed`). La interpretación probable es *en aprendizaje* frente a *dominada*, marcada desde el propio Kindle.

Sigue habiendo un único caso en las dos exportaciones, y no cambia entre ellas, así que no se puede inferir del archivo. **No se usa este campo.** El estado de aprendizaje lo gestiona FSRS dentro de la aplicación, así que la columna es prescindible y la cuestión queda cerrada.

### 4.5 Ruido por toques accidentales

Entre las palabras consultadas aparecen `En` y `Salvo`: pulsaciones involuntarias sobre palabras funcionales mientras se pasaba página.

Hay que filtrarlas con listas de palabras vacías por idioma. Sin ese filtro, la aplicación pedirá estudiar preposiciones que el usuario ya conoce, y el usuario abandonará.

---

## 5. Comportamiento entre exportaciones

El Kindle acumula: cada exportación contiene todo lo anterior más lo nuevo. Este apartado es la base sobre la que se apoya la ingesta incremental (D-012).

### 5.1 `WORDS.timestamp` es la última consulta, no la primera

De las 1.345 palabras comunes a las dos exportaciones, 16 cambiaron de `timestamp`, y las 16 eran palabras vueltas a consultar en el intervalo. Ningún otro campo de `WORDS` cambia.

**Consecuencia**: `entries.first_seen_at` se deriva de `MIN(LOOKUPS.timestamp)` de las consultas de esa palabra. **Nunca de `WORDS.timestamp`**, que daría la fecha más reciente bajo un nombre que promete lo contrario.

### 5.2 Los identificadores son estables

Comparadas dos exportaciones del mismo Kindle con tres días de diferencia (1.511 → 1.690 consultas):

| Tabla | En ambas | Desaparecidas | Añadidas |
|---|---|---|---|
| `LOOKUPS` | 1.511 | 0 | 179 |
| `WORDS` | 1.345 | 0 | 160 |
| `BOOK_INFO` | 25 | 0 | 0 |

Las filas comunes de `LOOKUPS` y `BOOK_INFO` son **idénticas campo a campo**, incluida `usage`. El Kindle nunca reescribe ni elimina consultas pasadas.

`LOOKUPS.id` y `WORDS.id` sirven, por tanto, como `external_id` para deduplicar sin perder el progreso del usuario.

---

## 6. Perfil de los archivos de referencia

| Métrica | ago. 2026 | sept. 2026 |
|---|---|---|
| Palabras únicas | 1.345 | 1.505 |
| Consultas totales | 1.511 | 1.690 |
| Libros | 25 | 25 |
| Inglés / español (palabras) | 753 / 592 | 913 / 592 |
| Consultas en inglés | 845 | 1.024 |
| Consultas con contexto | 1.511 (100 %) | 1.690 (100 %) |
| Longitud media del contexto | 178 caracteres | 172 caracteres |
| Palabras con una sola consulta | 1.212 | 1.357 |

Rango temporal: julio 2024 – septiembre 2026.

**Volumen**: suficiente de sobra para la aplicación, del todo insuficiente para entrenar nada. Confirma que el proyecto es de inferencia, orquestación y evaluación.

**Crecimiento**: 160 palabras nuevas en tres días, **todas en inglés**. La reimportación no es un caso excepcional, es el flujo normal de uso.

**Historial de repaso**: 1.357 de 1.505 palabras tienen una sola consulta, así que la curva de repetición espaciada arranca casi de cero y se construye con el uso.

---

## 7. Nota sobre el desacoplamiento

Todo lo descrito aquí vive **exclusivamente** dentro del adaptador `KindleVocabImporter`. El dominio de la aplicación no conoce estas tablas, ni el formato de los identificadores, ni la palabra «Kindle».

Un importador de CSV tendría que producir el mismo modelo canónico (§4.3 de la propuesta) y nada más cambiaría.
