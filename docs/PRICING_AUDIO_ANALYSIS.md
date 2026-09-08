# Pricing: Módulo de Análisis de Audio

**Video de referencia**: 60 minutos · 1080p · ~1.5 GB (audio extraído: ~350 MB FLAC)  
**Región GCP**: us-central1  
**Precios**: USD, tarifas estándar GCP · Mayo 2026

---

## Pipeline y Consumo por Análisis (1 h)

| Fase | Proceso | Servicio GCP |
|------|---------|-------------|
| 1 — Descarga y validación | Video desde GCS + `ffprobe` duración | Cloud Storage · Cloud Run |
| 1.5 — Deduplicación | SHA-256 → lookup en Redis | Cloud Run (Redis en memoria) |
| 2 — Pre-check de calidad | `ffmpeg` volumedetect + detección de voz | Cloud Run CPU |
| 3 — Extracción de audio | `ffmpeg` mono · 16 kHz · FLAC → GCS | Cloud Run · Cloud Storage |
| 4 — Transcripción | Gemini Vision (primario) · STT V2 Chirp 2 (fallback 1) · STT V1 (fallback 2) | Gemini o Speech-to-Text |
| 5 — Embeddings | `text-embedding-004` por segmento | Vertex AI Embeddings |
| 6 — Resumen IA | Gemini: tópicos · key points · sentimiento · action items | Gemini |
| 7 — Almacenamiento | Transcripción larga → GCS (.txt) · metadatos → Firestore | Cloud Storage · Firestore |

---

## Tiers por Método de Transcripción y Volumen

Los tres tiers reflejan **el camino de transcripción utilizado** (de menor a mayor costo y calidad) más la **retención de almacenamiento**.

| Tier | Transcripción | Embeddings | Resumen | Retención GCS | Capacidad Q&A |
|------|--------------|------------|---------|---------------|--------------|
| Básico | Gemini Vision (path primario, sin fallback) | No | Básico | 7 días | No |
| Medio | Gemini Vision + STT V2 Chirp 2 si falla | Sí | Completo | 30 días | Sí |
| Avanzado | Gemini 2.5 Flash + STT V2 + STT V1 · word-level timestamps | Sí | Completo + Q&A semántico | 90 días | Sí |

---

## Costo Variable por Análisis

### 1. Transcripción

#### Opción A — Gemini Vision (path primario · Básico y Medio)

Audio de 60 minutos extraído como FLAC (~350 MB) y enviado a Gemini vía Files API.  
Gemini procesa audio a ~32 tokens por segundo de audio.

| Componente | Precio | Consumo | Costo |
|------------|--------|---------|-------|
| Audio input (60 min × 60 s × 32 tok/s) | $0.10 / 1 M tok (`gemini-2.0-flash`) | 115 200 tokens | $0.0115 |
| Prompt de transcripción (instrucciones + diarización) | $0.10 / 1 M tok | 1 500 tokens | $0.0002 |
| Transcripción output (1 h ≈ ~10 000 palabras ≈ 15 000 tokens) | $0.40 / 1 M tok | 15 000 tokens | $0.0060 |
| **Subtotal Gemini (transcripción)** | | | **$0.0177** |

#### Opción B — STT V2 Chirp 2 (fallback 1 · si Gemini falla)

Batch recognize sobre archivo FLAC en GCS.

| Componente | Precio | Consumo | Costo |
|------------|--------|---------|-------|
| Chirp 2 batch recognize | $0.016 / min | 60 min | $0.9600 |
| Gemini speaker enrichment (post-STT) | $0.10 / 1 M tok (input) | 20 000 tokens | $0.0020 |
| Gemini speaker enrichment (output) | $0.40 / 1 M tok | 5 000 tokens | $0.0020 |
| **Subtotal STT V2** | | | **$0.9640** |

#### Opción C — STT V1 long_running_recognize (fallback 2 · chunks paralelos)

Chunks de 5 min en thread pool para audio > 15 min.

| Componente | Precio | Consumo | Costo |
|------------|--------|---------|-------|
| STT V1 long audio (12 chunks × 5 min) | $0.004 / min | 60 min | $0.2400 |
| Gemini speaker enrichment (post-STT) | $0.10 / 1 M tok | 20 000 tokens | $0.0020 |
| Gemini speaker enrichment (output) | $0.40 / 1 M tok | 5 000 tokens | $0.0020 |
| **Subtotal STT V1** | | | **$0.2440** |

---

### 2. Embeddings — Vertex AI (`text-embedding-004`)

Solo habilitado en Tier Medio y Avanzado. Cada segmento de speaker turn se vectoriza para búsqueda semántica.

| Componente | Precio | Consumo | Costo |
|------------|--------|---------|-------|
| Input tokens (1 h ≈ 200 segmentos × ~50 tokens c/u) | $0.000025 / 1 000 tokens | 10 000 tokens | $0.0003 |
| **Subtotal Embeddings** | | | **$0.0003** |

---

### 3. Resumen IA — Gemini

| Componente | Precio | Consumo (Básico) | Costo |
|------------|--------|-----------------|-------|
| Input (transcripción completa + prompt) | $0.10 / 1 M tok | 16 500 tokens | $0.0017 |
| Output (tópicos, key points, sentimiento, action items) | $0.40 / 1 M tok | 2 000 tokens | $0.0008 |
| **Subtotal Resumen** | | | **$0.0025** |

> Tier Avanzado usa `gemini-2.5-flash`: input $0.15/1M · output $0.60/1M → ~$0.0037.

---

### 4. Q&A Semántico (Tier Medio y Avanzado · por consulta)

Cada pregunta del usuario genera una llamada adicional a Gemini.

| Componente | Precio | Consumo | Costo |
|------------|--------|---------|-------|
| Input (pregunta + fragmentos relevantes del transcript) | $0.10 / 1 M tok | ~8 000 tokens | $0.0008 |
| Output (respuesta + timestamps) | $0.40 / 1 M tok | 500 tokens | $0.0002 |
| **Costo por consulta Q&A** | | | **$0.0010** |

---

### 5. Cloud Storage (GCS)

#### Tier Básico (7 días retención)

| Recurso | Precio | Consumo | Costo |
|---------|--------|---------|-------|
| Video original 1.5 GB (Standard, 7 días) | $0.020 / GB·mes | 1.5 × 0.23 mes | $0.0069 |
| Audio FLAC 350 MB (Standard, 7 días) | $0.020 / GB·mes | 0.35 × 0.23 mes | $0.0016 |
| Transcripción .txt (~60 KB, si > 100 KB omitido) | $0.020 / GB·mes | ~0 GB | $0.0000 |
| Operaciones Class A (upload video, FLAC) | $0.05 / 10 000 | ~15 ops | $0.0001 |
| Operaciones Class B (lecturas en procesamiento) | $0.004 / 10 000 | ~20 ops | $0.0000 |
| **Subtotal GCS** | | | **$0.0086** |

#### Tier Medio (30 días retención)

| Recurso | Precio | Consumo | Costo |
|---------|--------|---------|-------|
| Video original 1.5 GB (Standard, 30 días) | $0.020 / GB·mes | 1.5 × 1 mes | $0.0300 |
| Audio FLAC 350 MB (Standard, 30 días) | $0.020 / GB·mes | 0.35 × 1 mes | $0.0070 |
| Transcripción .txt (~400 KB, > 100 KB → GCS) | $0.020 / GB·mes | 0.0004 × 1 mes | $0.0000 |
| Operaciones Class A | $0.05 / 10 000 | ~20 ops | $0.0001 |
| Operaciones Class B | $0.004 / 10 000 | ~40 ops | $0.0000 |
| **Subtotal GCS** | | | **$0.0371** |

#### Tier Avanzado (90 días retención · con transición Nearline a 30d)

| Recurso | Precio | Consumo | Costo |
|---------|--------|---------|-------|
| Video original 1.5 GB (Standard 0–30 d) | $0.020 / GB·mes | 1.5 × 1 mes | $0.0300 |
| Video original 1.5 GB (Nearline 30–90 d) | $0.010 / GB·mes | 1.5 × 2 mes | $0.0300 |
| Audio FLAC 350 MB (Standard 0–30 d) | $0.020 / GB·mes | 0.35 × 1 mes | $0.0070 |
| Audio FLAC 350 MB (Nearline 30–90 d) | $0.010 / GB·mes | 0.35 × 2 mes | $0.0070 |
| Transcripción .txt larga + segmentos (~1 MB) | $0.020 / GB·mes | 0.001 × 3 mes | $0.0001 |
| Operaciones Class A + B | $0.05–0.004 / 10 000 | ~60 ops | $0.0003 |
| Early deletion fee Nearline (< 30 d min) | N/A (retención ≥ 30 d) | — | $0.0000 |
| **Subtotal GCS** | | | **$0.0744** |

---

### 6. Cloud Run — Worker

#### Tier Básico (~15 min total = 900 s · 2 vCPU · 4 GiB)

| Recurso | Precio | Consumo | Costo |
|---------|--------|---------|-------|
| CPU | $0.000024 / vCPU·s | 2 × 900 = 1 800 vCPU·s | $0.0432 |
| Memoria | $0.0000025 / GiB·s | 4 × 900 = 3 600 GiB·s | $0.0090 |
| **Subtotal Cloud Run** | | | **$0.0522** |

#### Tier Medio (~22 min = 1 320 s · 2 vCPU · 4 GiB)

| Recurso | Precio | Consumo | Costo |
|---------|--------|---------|-------|
| CPU | $0.000024 / vCPU·s | 2 × 1 320 = 2 640 vCPU·s | $0.0634 |
| Memoria | $0.0000025 / GiB·s | 4 × 1 320 = 5 280 GiB·s | $0.0132 |
| **Subtotal Cloud Run** | | | **$0.0766** |

#### Tier Avanzado (~32 min = 1 920 s · 4 vCPU · 8 GiB)

| Recurso | Precio | Consumo | Costo |
|---------|--------|---------|-------|
| CPU | $0.000024 / vCPU·s | 4 × 1 920 = 7 680 vCPU·s | $0.1843 |
| Memoria | $0.0000025 / GiB·s | 8 × 1 920 = 15 360 GiB·s | $0.0384 |
| **Subtotal Cloud Run** | | | **$0.2227** |

---

### 7. Cloud Firestore

| Recurso | Precio | Consumo (Medio) | Costo |
|---------|--------|----------------|-------|
| Escrituras (análisis doc + ~200 segmentos + embeddings) | $0.18 / 100 000 | ~420 writes | $0.0008 |
| Lecturas (Q&A: buscar segmentos relevantes) | $0.06 / 100 000 | ~50 reads | $0.0000 |
| Almacenamiento (análisis + segmentos ~500 KB) | $0.06 / GB·mes | 0.0005 GB | $0.0000 |
| **Subtotal Firestore** | | | **$0.0008** |

---

### Resumen: Costo Variable por Análisis (1 hora)

#### Ruta principal (Gemini como transcriptor primario)

| Servicio | Básico | Medio | Avanzado |
|---------|--------|-------|----------|
| Gemini (transcripción) | $0.0177 | $0.0177 | $0.0266¹ |
| STT V2 / V1 (si aplica fallback) | $0.00 | Presupuestado $0.096² | $0.2928³ |
| Embeddings | $0.00 | $0.0003 | $0.0003 |
| Resumen IA | $0.0025 | $0.0025 | $0.0037 |
| Cloud Storage | $0.0086 | $0.0371 | $0.0744 |
| Cloud Run (worker) | $0.0522 | $0.0766 | $0.2227 |
| Cloud Firestore | $0.0005 | $0.0008 | $0.0010 |
| Cloud Tasks | $0.0000 | $0.0000 | $0.0000 |
| **Total por análisis** | **$0.0815** | **$0.2350** | **$0.6215** |

¹ Gemini 2.5 Flash · ² 10% de probabilidad de fallback a STT V2: 0.10 × $0.9640 = $0.0964 esperado  
³ Tier Avanzado incluye STT V1 como backup adicional al STT V2: ($0.2440 + $0.9640) / 2 si ambos se usan parcialmente → costo total budgetado $0.29

---

## Infraestructura Fija Mensual (compartida)

| Servicio | Costo/mes |
|---------|-----------|
| Cloud Run — Backend (1 instancia activa · 1 vCPU · 1 GiB) | $68.69 |
| Cloud Run — Redis (job queue) | $15.55 |
| Firestore base (usuarios, workspaces, índices) | $0.01 |
| GCS (bucket, ops base) | $0.10 |
| **Total fijo** | **~$84.35 / mes** |

---

## Tiers por Volumen Mensual

### Tier Básico — 20 análisis/mes (Gemini primario · 7 días retención)

| Servicio | Costo variable |
|---------|---------------|
| Gemini (transcripción + resumen) | 20 × $0.0202 = $0.40 |
| Cloud Storage | 20 × $0.0086 = $0.17 |
| Cloud Run (worker) | 20 × $0.0522 = $1.04 |
| Firestore | $0.01 |
| **Total variable** | **$1.62** |
| Infraestructura fija | $84.35 |
| **Total mensual** | **$85.97** |
| **Costo por análisis** *(incl. infra fija)* | **$4.30** |
| **Costo marginal** *(solo variable)* | **$0.081** |

---

### Tier Medio — 100 análisis/mes (Gemini + embeddings + Q&A · 30 días)

| Servicio | Costo variable |
|---------|---------------|
| Gemini (transcripción + resumen) | 100 × $0.0202 = $2.02 |
| STT V2 (10% fallback esperado) | 10 × $0.9640 = $9.64 |
| Embeddings | 100 × $0.0003 = $0.03 |
| Cloud Storage | 100 × $0.0371 = $3.71 |
| Cloud Run (worker) | 100 × $0.0766 = $7.66 |
| Firestore | $0.08 |
| Q&A semántico (estimado 5 consultas/análisis) | 500 × $0.001 = $0.50 |
| **Total variable** | **$23.64** |
| Infraestructura fija | $84.35 |
| **Total mensual** | **$107.99** |
| **Costo por análisis** *(incl. infra fija)* | **$1.08** |
| **Costo marginal** *(solo variable)* | **$0.24** |

---

### Tier Avanzado — 500 análisis/mes (suite completa · 90 días retención)

| Servicio | Costo variable |
|---------|---------------|
| Gemini 2.5 Flash (transcripción + resumen) | 500 × $0.0303 = $15.15 |
| STT V2 (20% fallback) | 100 × $0.9640 = $96.40 |
| STT V1 (5% doble fallback) | 25 × $0.2440 = $6.10 |
| Embeddings | 500 × $0.0003 = $0.15 |
| Cloud Storage | 500 × $0.0744 = $37.20 |
| Cloud Run (worker · instancias adicionales) | 500 × $0.2227 + $30 escala = $141.35 |
| Firestore | $0.40 |
| Q&A semántico (estimado 8 consultas/análisis) | 4 000 × $0.001 = $4.00 |
| **Total variable** | **$300.75** |
| Infraestructura fija | $84.35 |
| **Total mensual** | **$385.10** |
| **Costo por análisis** *(incl. infra fija)* | **$0.77** |
| **Costo marginal** *(solo variable)* | **$0.60** |

---

## Escenarios de Fallback: Impacto en Costo por Análisis (1 hora)

| Camino de transcripción | Probabilidad estimada | Costo transcripción | Costo total análisis |
|------------------------|----------------------|--------------------|--------------------|
| Gemini Vision (primario) | ~85% | $0.0177 | **$0.0815** |
| STT V2 Chirp 2 (fallback 1) | ~10% | $0.9640 | **$1.0393** |
| STT V1 (fallback 2) | ~5% | $0.2440 | **$0.3193** |
| **Costo esperado ponderado** | 100% | $0.1190 | **$0.1573** |

> El sistema intenta siempre Gemini primero (menor costo). STT V2 se usa solo si Gemini rechaza el archivo o excede el timeout. El costo esperado ponderado es **$0.16/análisis** para 1 h de video.

---

## Deduplicación: Ahorro Real por Cache

El sistema calcula SHA-256 del video antes de procesar. Si el mismo video ya fue analizado con el mismo tipo:

- **Cache hit**: resultado copiado de Redis/Firestore en < 2 s. Costo: **$0.0001** (solo Firestore reads + Cloud Run mínimo).
- **Ahorro**: hasta **99.9%** del costo de un análisis completo.
- El cache tiene TTL de 7 días (Redis) y persiste en Firestore sin límite hasta borrado explícito.

---

## Optimización de Costos

| Escenario | Optimización | Ahorro estimado |
|-----------|-------------|----------------|
| Reducir uso de STT V2 | Mejorar timeout y retry en Gemini antes de escalar a STT | 60% en fallback costs |
| Videos largos (> 30 min) | Aumentar chunk size de STT V1 (actualmente 5 min) para reducir overhead de API calls | ~10% en STT V1 |
| Almacenamiento de audio | FLAC → MP3 128 kbps reduce ~70% el tamaño → menor costo GCS y egress | ~70% en GCS audio |
| Transcripciones largas | Textos > 100 KB ya se almacenan en GCS (implementado). Para textos < 100 KB en Firestore, evaluar si el costo de Firestore storage es mayor que GCS | Depende del volumen |
| Committed Use Discount | 1-year CUD en Cloud Run | Hasta 57% en compute |

---

## Supuestos

- Video de referencia: 60 minutos, 1080p, H.264, ~1.5 GB.
- Audio extraído: FLAC mono 16 kHz, ~350 MB.
- Gemini tokenización de audio: 32 tokens/s (estimado para audio FLAC).
- STT V1: `long_running_recognize` en paralelo, 12 chunks de 5 min con thread pool.
- Embeddings: `text-embedding-004` por segmento de speaker turn (~200 segmentos por 1 h).
- Q&A: búsqueda vectorial en Firestore + Gemini para generar respuesta.
- Cloud Run: us-central1, 2nd gen. Worker 2 vCPU/4 GiB (Básico/Medio), 4 vCPU/8 GiB (Avanzado).
- Precios en USD, tarifa estándar GCP, us-central1, Mayo 2026. Impuestos no incluidos.
- Gemini 2.0 Flash: $0.10/1M input · $0.40/1M output. Gemini 2.5 Flash: $0.15/1M input · $0.60/1M output.
- STT V2 Chirp 2 (batch): $0.016/min. STT V1 standard: $0.004/min.
- text-embedding-004: $0.000025/1K tokens.

---

**Last Updated**: May 15, 2026  
**Version**: 1.0.0
