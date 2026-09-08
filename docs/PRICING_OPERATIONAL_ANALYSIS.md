# Pricing: Módulo de Análisis Operativo

**Video de referencia**: 60 minutos · 1080p · ~1.5 GB  
**Región GCP**: us-central1  
**Precios**: USD, tarifas estándar GCP · Mayo 2026

> El módulo de Análisis Operativo **no utiliza Video Intelligence API**. El escaneo de movimiento se realiza localmente con OpenCV (incluido en el costo de Cloud Run). El costo dominante es Gemini Vision para el análisis de segmentos.

---

## Pipeline y Consumo por Video (1 h)

| Fase | Proceso | Servicio GCP |
|------|---------|-------------|
| 0 — Descarga | Video desde GCS al worker | Cloud Storage (egress intra-región: gratis) |
| 1 — Escaneo denso | OpenCV frame diff · MOG2 · contornos cada 0.5 s | Cloud Run CPU (local) |
| 2 — Análisis de segmentos | FFmpeg extrae clips → GCS → Gemini Vision por segmento | Gemini · GCS · Cloud Run |
| 3 — Cross-analysis | Consolidación de todos los resultados con Gemini + Thinking | Gemini |
| 4 — Reporte | PDF con ReportLab → GCS | Cloud Run · GCS |

---

## Costo Variable por Análisis

### Capacidad de segmentos según duración

| Duración del video | Segmentos máx. | Duración media por segmento |
|-------------------|----------------|----------------------------|
| ≤ 10 min | 30 | ~20 s |
| ≤ 30 min | 60 | ~30 s |
| **1 hora (referencia)** | **100** | **~36 s** |
| ≤ 2 h | 150 | ~48 s |

Para el cálculo se usan **3 escenarios de segmentos** que definen los tiers de volumen de análisis por pasada:

| Tier | Segmentos por análisis | Modelo Gemini | Retención GCS |
|------|----------------------|---------------|---------------|
| Básico | 30 (análisis rápido, zonas de mayor movimiento) | `gemini-2.0-flash` | 7 días |
| Medio | 80 (análisis completo estándar) | `gemini-2.0-flash` | 30 días |
| Avanzado | 100 (análisis exhaustivo con cross-analysis con Thinking) | `gemini-2.5-flash` + Thinking | 90 días |

---

### 1. Gemini Vision — Análisis de Segmentos

Cada segmento se procesa como un clip de video enviado a Gemini vía GCS URI.  
Muestreo: 1 fps. Tokens de video = frames × 258 tokens/frame.

#### Tier Básico (30 segmentos × ~20 s c/u)

| Componente | Precio | Consumo | Costo |
|------------|--------|---------|-------|
| Video input (30 seg × 20 s × 1 fps × 258 tok/frame) | $0.10 / 1 M tok | 154 800 tokens | $0.0155 |
| Prompt por segmento (contexto operativo + preguntas) | $0.10 / 1 M tok | 30 × 2 000 = 60 000 tokens | $0.0060 |
| Respuesta por segmento | $0.40 / 1 M tok | 30 × 1 000 = 30 000 tokens | $0.0120 |
| Cross-analysis (todos resultados, modelo estándar) | $0.10 / 1 M tok (input) | 40 000 tokens | $0.0040 |
| Cross-analysis (output) | $0.40 / 1 M tok | 3 000 tokens | $0.0012 |
| **Subtotal Gemini** | | | **$0.0387** |

#### Tier Medio (80 segmentos × ~36 s c/u)

| Componente | Precio | Consumo | Costo |
|------------|--------|---------|-------|
| Video input (80 seg × 36 s × 258 tok/frame) | $0.10 / 1 M tok | 742 080 tokens | $0.0742 |
| Prompt por segmento | $0.10 / 1 M tok | 80 × 2 000 = 160 000 tokens | $0.0160 |
| Respuesta por segmento | $0.40 / 1 M tok | 80 × 1 200 = 96 000 tokens | $0.0384 |
| Cross-analysis (input, chunked 30 seg/chunk) | $0.10 / 1 M tok | 80 000 tokens | $0.0080 |
| Cross-analysis (output) | $0.40 / 1 M tok | 5 000 tokens | $0.0020 |
| **Subtotal Gemini** | | | **$0.1386** |

#### Tier Avanzado (100 segmentos × ~36 s c/u · Gemini 2.5 Flash + Thinking)

| Componente | Precio | Consumo | Costo |
|------------|--------|---------|-------|
| Video input (100 seg × 36 s × 258 tok/frame) | $0.15 / 1 M tok (2.5 Flash) | 928 800 tokens | $0.1393 |
| Prompt por segmento | $0.15 / 1 M tok | 100 × 2 000 = 200 000 tokens | $0.0300 |
| Respuesta por segmento | $0.60 / 1 M tok | 100 × 1 500 = 150 000 tokens | $0.0900 |
| Cross-analysis input (chunked, Thinking activado) | $3.50 / 1 M tok (thinking) | 150 000 tokens | $0.5250 |
| Cross-analysis output (thinking) | $15.00 / 1 M tok | 8 000 tokens | $0.1200 |
| Cross-analysis output (texto final) | $0.60 / 1 M tok | 5 000 tokens | $0.0030 |
| **Subtotal Gemini** | | | **$0.9073** |

---

### 2. Cloud Storage (GCS)

#### Tier Básico

| Recurso | Precio | Consumo | Costo |
|---------|--------|---------|-------|
| Video 1.5 GB (Standard, 7 días) | $0.020 / GB·mes | 1.5 GB × 0.23 mes | $0.0069 |
| Clips temporales (30 clips × ~5 MB = 150 MB, 1 día) | $0.020 / GB·mes | 0.15 GB × 0.033 mes | $0.0001 |
| Frames capturados (~100 frames × 150 KB = 15 MB, 7 días) | $0.020 / GB·mes | 0.015 GB × 0.23 mes | $0.0001 |
| Reporte PDF (~3 MB, 7 días) | $0.020 / GB·mes | 0.003 GB × 0.23 mes | $0.0000 |
| Operaciones Class A (uploads clips, frames, report) | $0.05 / 10 000 | ~200 ops | $0.0010 |
| Operaciones Class B (lecturas Gemini, descarga video) | $0.004 / 10 000 | ~80 ops | $0.0000 |
| **Subtotal GCS** | | | **$0.0081** |

#### Tier Medio

| Recurso | Precio | Consumo | Costo |
|---------|--------|---------|-------|
| Video 1.5 GB (Standard, 30 días) | $0.020 / GB·mes | 1.5 GB × 1 mes | $0.0300 |
| Clips temporales (80 clips × ~8 MB = 640 MB, 1 día) | $0.020 / GB·mes | 0.64 GB × 0.033 mes | $0.0004 |
| Frames (~300 frames × 150 KB = 45 MB, 30 días) | $0.020 / GB·mes | 0.045 GB × 1 mes | $0.0009 |
| Reporte PDF (~5 MB, 30 días) | $0.020 / GB·mes | 0.005 GB × 1 mes | $0.0001 |
| Operaciones Class A | $0.05 / 10 000 | ~500 ops | $0.0025 |
| Operaciones Class B | $0.004 / 10 000 | ~200 ops | $0.0001 |
| **Subtotal GCS** | | | **$0.0340** |

#### Tier Avanzado

| Recurso | Precio | Consumo | Costo |
|---------|--------|---------|-------|
| Video 1.5 GB (Standard, 90 días) | $0.020 / GB·mes | 1.5 GB × 3 mes | $0.0900 |
| Clips temporales (100 clips × ~10 MB = 1 GB, 1 día) | $0.020 / GB·mes | 1 GB × 0.033 mes | $0.0007 |
| Frames (~500 frames × 150 KB = 75 MB, 90 días) | $0.020 / GB·mes | 0.075 GB × 3 mes | $0.0045 |
| Reporte PDF (~8 MB, 90 días) | $0.020 / GB·mes | 0.008 GB × 3 mes | $0.0005 |
| Operaciones Class A | $0.05 / 10 000 | ~800 ops | $0.0040 |
| Operaciones Class B | $0.004 / 10 000 | ~400 ops | $0.0002 |
| **Subtotal GCS** | | | **$0.0999** |

---

### 3. Cloud Run — Worker (procesamiento)

El worker realiza el escaneo denso (CPU intensivo) y los 3 workers paralelos de Gemini.

#### Tier Básico (tiempo total ~20 min = 1 200 s · 2 vCPU · 4 GiB)

| Recurso | Precio | Consumo | Costo |
|---------|--------|---------|-------|
| CPU | $0.000024 / vCPU·s | 2 × 1 200 = 2 400 vCPU·s | $0.0576 |
| Memoria | $0.0000025 / GiB·s | 4 × 1 200 = 4 800 GiB·s | $0.0120 |
| **Subtotal Cloud Run** | | | **$0.0696** |

#### Tier Medio (tiempo total ~35 min = 2 100 s · 2 vCPU · 4 GiB)

| Recurso | Precio | Consumo | Costo |
|---------|--------|---------|-------|
| CPU | $0.000024 / vCPU·s | 2 × 2 100 = 4 200 vCPU·s | $0.1008 |
| Memoria | $0.0000025 / GiB·s | 4 × 2 100 = 8 400 GiB·s | $0.0210 |
| **Subtotal Cloud Run** | | | **$0.1218** |

#### Tier Avanzado (tiempo total ~55 min = 3 300 s · 4 vCPU · 8 GiB)

| Recurso | Precio | Consumo | Costo |
|---------|--------|---------|-------|
| CPU | $0.000024 / vCPU·s | 4 × 3 300 = 13 200 vCPU·s | $0.3168 |
| Memoria | $0.0000025 / GiB·s | 8 × 3 300 = 26 400 GiB·s | $0.0660 |
| **Subtotal Cloud Run** | | | **$0.3828** |

---

### 4. Cloud Firestore

| Recurso | Precio | Consumo | Costo |
|---------|--------|---------|-------|
| Escrituras (análisis doc + N eventos) | $0.18 / 100 000 | ~200 writes (Básico) / ~400 (Avanzado) | $0.0004 – $0.0007 |
| Lecturas (consultas de progreso) | $0.06 / 100 000 | ~30 reads | $0.0000 |
| Almacenamiento (docs de análisis y eventos) | $0.06 / GB·mes | ~0.01 GB | $0.0006 |
| **Subtotal Firestore (estimado)** | | | **$0.0010** |

---

### 5. Cloud Tasks

| Recurso | Precio | Consumo | Costo |
|---------|--------|---------|-------|
| Dispatch de tarea | $0.40 / 1 M ops | 2 ops | $0.0000 |

---

### Resumen: Costo Variable por Análisis de 1 hora

| Servicio | Básico (30 seg) | Medio (80 seg) | Avanzado (100 seg + Thinking) |
|---------|----------------|----------------|-------------------------------|
| Gemini Vision | $0.0387 | $0.1386 | $0.9073 |
| Cloud Storage | $0.0081 | $0.0340 | $0.0999 |
| Cloud Run (worker) | $0.0696 | $0.1218 | $0.3828 |
| Cloud Firestore | $0.0010 | $0.0010 | $0.0010 |
| Cloud Tasks | $0.0000 | $0.0000 | $0.0000 |
| **Total por análisis** | **$0.1174** | **$0.2954** | **$1.3910** |

---

## Infraestructura Fija Mensual (compartida)

Idéntica a la del módulo de Moderación de Video (se comparten los mismos contenedores backend y worker).

| Servicio | Costo/mes |
|---------|-----------|
| Cloud Run — Backend (1 instancia activa) | $68.69 |
| Cloud Run — Redis (job queue) | $15.55 |
| Firestore base | $0.01 |
| GCS (bucket ops base) | $0.10 |
| **Total fijo** | **~$84.35 / mes** |

---

## Tiers por Volumen Mensual

### Tier Básico — 10 análisis/mes (30 segmentos c/u)

| Servicio | Costo variable |
|---------|---------------|
| Gemini Vision | 10 × $0.0387 = $0.39 |
| Cloud Storage | 10 × $0.0081 = $0.08 |
| Cloud Run (worker) | 10 × $0.0696 = $0.70 |
| Firestore | $0.01 |
| **Total variable** | **$1.18** |
| Infraestructura fija | $84.35 |
| **Total mensual** | **$85.53** |
| **Costo por análisis** *(incl. infra fija)* | **$8.55** |
| **Costo marginal** *(solo variable)* | **$0.12** |

---

### Tier Medio — 50 análisis/mes (80 segmentos c/u)

| Servicio | Costo variable |
|---------|---------------|
| Gemini Vision | 50 × $0.1386 = $6.93 |
| Cloud Storage | 50 × $0.0340 = $1.70 |
| Cloud Run (worker) | 50 × $0.1218 = $6.09 |
| Firestore | $0.05 |
| **Total variable** | **$14.77** |
| Infraestructura fija | $84.35 |
| **Total mensual** | **$99.12** |
| **Costo por análisis** *(incl. infra fija)* | **$1.98** |
| **Costo marginal** *(solo variable)* | **$0.30** |

---

### Tier Avanzado — 200 análisis/mes (100 segmentos + Thinking)

| Servicio | Costo variable |
|---------|---------------|
| Gemini Vision | 200 × $0.9073 = $181.46 |
| Cloud Storage | 200 × $0.0999 = $19.98 |
| Cloud Run (worker) | 200 × $0.3828 = $76.56 + instancias adicionales ~$20 |
| Firestore | $0.50 |
| **Total variable** | **$298.50** |
| Infraestructura fija | $84.35 |
| **Total mensual** | **$382.85** |
| **Costo por análisis** *(incl. infra fija)* | **$1.91** |
| **Costo marginal** *(solo variable)* | **$1.49** |

---

## Optimización de Costos

| Escenario | Optimización | Ahorro estimado |
|-----------|-------------|----------------|
| Reducir costo Gemini | Usar Thinking solo en cross-analysis (ya implementado por defecto). Reducir segmentos máx. para videos cortos | 30–60% en Gemini |
| Cross-analysis sin Thinking | Deshabilitar `ThinkingConfig` en `cross_analyzer.py` (`MEDIUM` → `NONE`) | $0.35–$0.65 por análisis avanzado |
| Cache de contenido | Videos idénticos (mismo SHA-256 y tipo) reutilizan resultado en Redis (sin re-procesamiento) | 100% del costo variable |
| Clips temporales | El sistema ya los elimina tras la llamada a Gemini. Verificar TTL GCS: `tmp_clips/` | Negligible (< $0.01) |
| Escala horizontal | Aumentar workers paralelos (`GEMINI_MAX_WORKERS=5`) para reducir tiempo de Cloud Run sin afectar costo Gemini | Reduce costo Cloud Run por menor tiempo de procesamiento |

---

## Supuestos

- Video de referencia: 60 minutos, 1080p, H.264, ~1.5 GB.
- No se usa Video Intelligence API en este módulo (OpenCV corre localmente en Cloud Run).
- Gemini: muestreo 1 fps para clips de análisis.
- Clips temporales eliminados de GCS tras cada llamada a Gemini (lifecycle existente).
- Cloud Run: us-central1, 2nd gen. Worker escalado a 2 vCPU/4 GiB (Básico/Medio) y 4 vCPU/8 GiB (Avanzado).
- Precios en USD, tarifa estándar GCP, us-central1, Mayo 2026. Impuestos no incluidos.
- Egreso de red intra-región (Cloud Run ↔ GCS): sin costo adicional.
- Thinking tokens en `gemini-2.5-flash`: $3.50/1M input thinking + $15.00/1M output thinking.

---

**Last Updated**: May 15, 2026  
**Version**: 1.0.0
