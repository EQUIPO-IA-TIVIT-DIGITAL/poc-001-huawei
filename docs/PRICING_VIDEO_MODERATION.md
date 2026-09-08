# Pricing: Módulo de Moderación de Video (Socio)

**Video de referencia**: 60 segundos · 1080p · ~100 MB  
**Región GCP**: us-central1  
**Precios**: USD, tarifas estándar GCP · Mayo 2026

---

## Costo Variable por Video (1 video de 60 s)

### 1. Google Cloud Video Intelligence API

| Feature | Precio unitario | Consumo | Costo |
|---------|----------------|---------|-------|
| Label Detection | $0.10 / min | 1 min | $0.1000 |
| Shot Change Detection | $0.10 / min | 1 min | $0.1000 |
| Explicit Content Detection | $0.10 / min | 1 min | $0.1000 |
| Object Tracking | $0.15 / min | 1 min | $0.1500 |
| Text Detection (OCR) | $0.15 / min | 1 min | $0.1500 |
| Logo Recognition | $0.15 / min | 1 min | $0.1500 |
| **Subtotal** | | | **$0.7500** |

> **Free tier**: 1 000 min/mes gratis por feature. Para ≤ 1 000 videos de 60 s/mes el costo de Video Intelligence es **$0.00**.

---

### 2. Gemini Vision (`gemini-2.0-flash`)

| Componente | Precio unitario | Consumo | Costo |
|------------|----------------|---------|-------|
| Video input (60 frames × 258 tokens/frame) | $0.10 / 1 M tokens | 15 480 tokens | $0.0015 |
| Prompt de análisis (contexto + reglas) | $0.10 / 1 M tokens | 2 000 tokens | $0.0002 |
| Respuesta (resultado de análisis) | $0.40 / 1 M tokens | 1 500 tokens | $0.0006 |
| **Subtotal** | | | **$0.0023** |

---

### 3. Cloud Storage (GCS)

| Recurso | Precio unitario | Consumo | Costo |
|---------|----------------|---------|-------|
| Almacenamiento video (Standard, 30 días) | $0.020 / GB·mes | 0.10 GB | $0.0020 |
| Almacenamiento thumbnail (30 días) | $0.020 / GB·mes | 0.005 GB | $0.0001 |
| Operaciones Class A (upload, thumbnail write) | $0.05 / 10 000 ops | 25 ops | $0.0001 |
| Operaciones Class B (lecturas en análisis) | $0.004 / 10 000 ops | 30 ops | $0.0000 |
| Egreso de red (worker → GCS, misma región) | Gratis | — | $0.0000 |
| **Subtotal** | | | **$0.0022** |

---

### 4. Cloud Firestore

| Recurso | Precio unitario | Consumo | Costo |
|---------|----------------|---------|-------|
| Escrituras (metadatos, estado, resultado IA) | $0.18 / 100 000 | 15 writes | $0.0000 |
| Lecturas (consultas de estado) | $0.06 / 100 000 | 10 reads | $0.0000 |
| Almacenamiento documento (~4 KB) | $0.06 / GB·mes | 0.000004 GB | $0.0000 |
| **Subtotal** | | | **$0.0000** |

---

### 5. Cloud Run — Worker (procesamiento asíncrono RQ)

| Recurso | Precio unitario | Consumo | Costo |
|---------|----------------|---------|-------|
| CPU (2 vCPU × 45 s de procesamiento) | $0.000024 / vCPU·s | 90 vCPU·s | $0.0022 |
| Memoria (2 GiB × 45 s) | $0.0000025 / GiB·s | 90 GiB·s | $0.0002 |
| Invocaciones de contenedor | $0.40 / 1 M reqs | 1 req | $0.0000 |
| **Subtotal** | | | **$0.0024** |

---

### 6. Cloud Tasks

| Recurso | Precio unitario | Consumo | Costo |
|---------|----------------|---------|-------|
| Dispatch de tarea (enqueue + execute) | $0.40 / 1 M ops | 2 ops | $0.0000 |
| **Subtotal** | | | **$0.0000** |

---

### Resumen: Costo Variable por Video

| Servicio | Costo por video |
|---------|----------------|
| Video Intelligence API | $0.7500 |
| Gemini Vision | $0.0023 |
| Cloud Storage | $0.0022 |
| Cloud Firestore | $0.0000 |
| Cloud Run (worker) | $0.0024 |
| Cloud Tasks | $0.0000 |
| **Total variable** | **$0.7569** |

---

## Infraestructura Fija Mensual (compartida)

Estos costos existen independientemente del volumen de videos procesados.

| Servicio | Recurso | Precio | Consumo mensual | Costo/mes |
|---------|---------|--------|----------------|-----------|
| Cloud Run — Backend | 1 instancia activa · 1 vCPU | $0.000024 / vCPU·s | 2 592 000 s | $62.21 |
| Cloud Run — Backend | Memoria · 1 GiB | $0.0000025 / GiB·s | 2 592 000 s | $6.48 |
| Cloud Run — Redis | 0.5 vCPU · 0.5 GiB (job queue) | $0.000024 / vCPU·s | ~1 296 000 s | $15.55 |
| Firestore | Almacenamiento base (usuarios, workspaces, índices) | $0.06 / GB·mes | ~0.1 GB | $0.01 |
| Cloud Storage | Bucket · operaciones base | — | Mínimo | $0.10 |
| **Total fijo estimado** | | | | **~$84.35 / mes** |

> Con Cloud Run mínimo de instancias = 0 (cold start) el costo fijo se reduce a **~$22/mes**. No recomendado para producción con SLA.

---

## Tiers por Volumen Mensual

### Tier Básico — 50 videos/mes

| Servicio | Detalle | Costo variable |
|---------|---------|---------------|
| Video Intelligence | 50 min totales · **dentro del free tier (1 000 min/feature)** | $0.00 |
| Gemini Vision | 50 × $0.0023 | $0.12 |
| Cloud Storage | 50 × 100 MB = 5 GB almacenados | $0.11 |
| Cloud Run (worker) | 50 × $0.0024 | $0.12 |
| Cloud Tasks | 50 × $0.0000 | $0.00 |
| **Total variable** | | **$0.35** |
| Infraestructura fija | | $84.35 |
| **Total mensual** | | **$84.70** |
| **Costo por video** | *(incluye infra fija)* | **$1.69** |
| **Costo marginal por video** | *(solo costo variable)* | **$0.007** |

---

### Tier Medio — 500 videos/mes

| Servicio | Detalle | Costo variable |
|---------|---------|---------------|
| Video Intelligence | 500 min totales · **dentro del free tier** | $0.00 |
| Gemini Vision | 500 × $0.0023 | $1.15 |
| Cloud Storage | 500 × 100 MB = 50 GB almacenados | $1.00 |
| Cloud Run (worker) | 500 × $0.0024 | $1.20 |
| Cloud Tasks | 500 × $0.0000 | $0.00 |
| **Total variable** | | **$3.35** |
| Infraestructura fija | | $84.35 |
| **Total mensual** | | **$87.70** |
| **Costo por video** | *(incluye infra fija)* | **$0.18** |
| **Costo marginal por video** | *(solo costo variable)* | **$0.007** |

---

### Tier Avanzado — 5 000 videos/mes

| Servicio | Detalle | Costo variable |
|---------|---------|---------------|
| Video Intelligence | 5 000 min − 1 000 min free = **4 000 min pagados × 6 features × $0.125/min** | $3 000.00 |
| *(optimizado: solo 2 features críticas)* | *4 000 min × 2 features × $0.10/min* | *$800.00* |
| Gemini Vision | 5 000 × $0.0023 | $11.50 |
| Cloud Storage | 5 000 × 100 MB = 500 GB | $10.00 |
| Cloud Run (worker) | 5 000 × $0.0024 (+ instancias adicionales) | $14.00 |
| Cloud Tasks | 5 000 × $0.0000 | $0.00 |
| **Total variable (suite completa)** | | **$3 035.50** |
| **Total variable (2 features)** | | **$835.50** |
| Infraestructura fija | | $84.35 |
| **Total mensual (suite completa)** | | **$3 119.85** |
| **Total mensual (optimizado)** | | **$919.85** |
| **Costo por video (suite completa)** | | **$0.62** |
| **Costo por video (optimizado)** | | **$0.18** |

---

## Optimización de Costos

| Escenario | Optimización | Ahorro estimado |
|-----------|-------------|----------------|
| Solo moderación de contenido | Habilitar únicamente Explicit Content Detection ($0.10/min) en vez de las 6 features | Hasta **87%** en Video Intelligence |
| Alto volumen (>1 000 videos/mes) | Committed Use Discount 1 año (Cloud Run) | Hasta **57%** en Cloud Run |
| Retención de almacenamiento | Lifecycle: Standard → Nearline (30 d) → Coldline (90 d) | **50–80%** en GCS después de 30 días |
| Modelo Gemini | Usar `gemini-2.0-flash` (ya configurado por defecto) vs. `gemini-2.5-pro` | **10× menos** en costo Gemini |

---

## Supuestos

- Video de referencia: 60 segundos, 1080p, H.264, ~100 MB.
- Gemini: muestreo a 1 fps = 60 frames = 15 480 tokens de video.
- Video Intelligence: 6 features habilitadas (suite completa). La optimización mínima usa solo Explicit Content + Label Detection.
- Cloud Run: región us-central1, 2nd gen, mínimo 1 instancia activa (backend siempre disponible).
- Precios en USD, tarifa estándar GCP, us-central1, Mayo 2026. Impuestos no incluidos.
- Free tier de Video Intelligence: 1 000 min/mes por feature (primeras 6 features).
- Egreso de red intra-región (Cloud Run ↔ GCS ↔ Firestore): sin costo adicional.

---

**Last Updated**: May 15, 2026  
**Version**: 1.0.0
