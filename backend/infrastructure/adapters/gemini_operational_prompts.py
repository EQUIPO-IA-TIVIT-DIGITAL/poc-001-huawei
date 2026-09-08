"""
Prompts especializados para Análisis Operativo con Gemini.

Cada tipo de análisis tiene su propio prompt que instruye a Gemini
a extraer información específica según el contexto operativo.
El prompt incluye event_type del Dense Scanner para dar más contexto.
"""


def _sanitize_prompt_input(text: str, max_len: int = 500) -> str:
    """Sanitize user-supplied text before embedding it in a prompt.

    Prevents prompt injection by normalising whitespace and removing
    characters that could break out of the quoted string context or
    inject new instructions into the model.
    """
    if not text:
        return ""
    # Collapse newlines / tabs to spaces so injected instructions can't
    # span lines inside the prompt block.
    text = " ".join(text.split())
    # Remove characters that break out of the quoted context or that could
    # inject JSON keys / f-string placeholders.
    text = (
        text
        .replace('"', "'")
        .replace('`', "'")
        .replace('\\', "")
        .replace('{', "[")
        .replace('}', "]")
    )
    return text[:max_len]


def build_segment_prompt(
    analysis_type: str,
    custom_context: str = "",
    segment_number: int = 0,
    total_segments: int = 0,
    event_type: str = "MOVEMENT",
    event_priority: str = "MEDIUM",
    time_range: str = "",
    is_frames_only: bool = False
) -> str:
    """Genera el prompt para analizar un segmento según el tipo de análisis operativo"""

    media_type = "frames de imagen" if is_frames_only else "video clip completo"
    safe_context = _sanitize_prompt_input(custom_context)
    base = f"""Eres un analista de video de seguridad profesional realizando un análisis operativo.
Contexto del usuario: "{safe_context}"
Segmento {segment_number}/{total_segments} | Rango temporal: {time_range}
Tipo de detección del escáner: {event_type} (prioridad: {event_priority})
Medio de análisis: {media_type}
"""

    if analysis_type == "ACCESS_CONTROL":
        return _prompt_access_control(base)
    elif analysis_type == "OCCUPANCY":
        return _prompt_occupancy(base)
    elif analysis_type == "PEOPLE_FLOW":
        return _prompt_people_flow(base)
    elif analysis_type == "MERCHANDISE_CONTROL":
        return _prompt_merchandise(base)
    elif analysis_type == "PARKING":
        return _prompt_parking(base)
    elif analysis_type == "WORK_SUPERVISION":
        return _prompt_work_supervision(base)
    else:
        return _prompt_generic(base)


# ═══════════════════════════════════════════════════════════════
# PROMPTS POR TIPO DE ANÁLISIS
# ═══════════════════════════════════════════════════════════════

def _prompt_access_control(base: str) -> str:
    return f"""{base}

OBJETIVO: Análisis de CONTROL DE ACCESO. Identifica y documenta CADA persona que aparece.

INSTRUCCIONES:

1. IDENTIFICACIÓN DE PERSONAS — Para CADA persona visible:
   - Descripción física: género aparente, ropa (color, tipo), accesorios
   - Estatura aproximada (alta, media, baja)
   - Elementos identificativos: uniforme, credencial visible, mochila, etc.

2. DIRECCIÓN DE MOVIMIENTO:
   - ENTRY: La persona se mueve HACIA el interior del espacio
   - EXIT: La persona se mueve HACIA el exterior
   - STATIONARY: La persona está quieta
   - PASSING: La persona pasa sin entrar/salir

3. USO DE FOTCHECK / CONTROL DE ACCESO:
   - FOTCHECK_USED: La persona usa el sistema de control (tarjeta, biométrico, etc.)
   - FOTCHECK_SKIPPED: La persona pasa SIN usar el sistema
   - FOTCHECK_NOT_VISIBLE: No se ve dispositivo de control en escena

4. OBJETOS TRANSPORTADOS:
   - Describir todo lo que la persona carga (mochila, bolso, caja, equipo, etc.)

5. COMPORTAMIENTO:
   - ¿Paso normal? ¿Hesitación? ¿Interacción con otros?

RESPONDE EXCLUSIVAMENTE en JSON válido (sin comentarios, sin markdown):
{{
    "persons_detected": [
        {{
            "person_id": "P1",
            "description": "Hombre, ~35 años, camisa azul, pantalón gris, estatura media",
            "direction": "ENTRY",
            "fotcheck_status": "FOTCHECK_USED",
            "fotcheck_detail": "Acerca tarjeta al lector junto a la puerta",
            "carried_objects": "Mochila negra, carpeta en mano derecha",
            "behavior": "Paso normal, entra directamente",
            "confidence": "HIGH",
            "approximate_time_in_segment": "inicio del clip"
        }}
    ],
    "access_device_visible": true,
    "access_device_description": "Lector de tarjeta en pared derecha",
    "scene_description": "Puerta de acceso a oficina, pasillo interior",
    "total_entries_in_segment": 1,
    "total_exits_in_segment": 0,
    "alerts": [],
    "notes": ""
}}

IMPORTANTE:
- Si NO hay personas, responder persons_detected: [] y describir la escena
- Si hay múltiples personas, documentar CADA UNA por separado
- Sé preciso: NO inventes personas que no están visibles
"""


def _prompt_occupancy(base: str) -> str:
    return f"""{base}

OBJETIVO: Análisis de AFORO. Contar personas presentes simultáneamente en el espacio.

INSTRUCCIONES:
1. Cuenta EXACTAMENTE cuántas personas son visibles en cada momento
2. Si hay variación, indica mínimo y máximo
3. Distingue entre personas que ESTÁN vs personas que solo PASAN
4. Describe distribución espacial y tipo de ocupación

RESPONDE EXCLUSIVAMENTE en JSON válido (sin comentarios, sin markdown):
{{
    "persons_count_start": 3,
    "persons_count_end": 4,
    "persons_count_max": 4,
    "persons_count_min": 3,
    "spatial_distribution": "3 personas sentadas al fondo, 1 de pie cerca de la entrada",
    "occupation_type": "Personas trabajando sentadas y una en tránsito",
    "congestion_level": "LOW",
    "scene_description": "Oficina de planta abierta con escritorios",
    "alerts": [],
    "notes": ""
}}
"""


def _prompt_people_flow(base: str) -> str:
    return f"""{base}

OBJETIVO: Análisis de FLUJO DE PERSONAS. Documentar tráfico y patrones de movimiento.

INSTRUCCIONES:
1. Cuántas personas pasan por el espacio
2. Dirección predominante del flujo
3. Velocidad: rápido, normal, lento/congestionado
4. Patrones: todos misma dirección, contra-flujo, personas detenidas

RESPONDE EXCLUSIVAMENTE en JSON válido (sin comentarios, sin markdown):
{{
    "persons_passing": 3,
    "flow_direction": "Predominantemente de izquierda a derecha",
    "flow_speed": "NORMAL",
    "movement_patterns": "Flujo constante en una dirección",
    "counter_flow": false,
    "stopped_persons": 0,
    "interactions": "Sin interacciones significativas",
    "scene_description": "Pasillo principal de acceso",
    "notes": ""
}}
"""


def _prompt_merchandise(base: str) -> str:
    return f"""{base}

OBJETIVO: Análisis de CONTROL DE MERCANCÍA. Documentar objetos que entran/salen.

INSTRUCCIONES:
1. Objetos que entran/salen: tamaño, color, tipo
2. Quién transporta cada objeto y cómo
3. Actividad de carga/descarga
4. Objetos sin supervisión

RESPONDE EXCLUSIVAMENTE en JSON válido (sin comentarios, sin markdown):
{{
    "objects_in": [
        {{
            "description": "Caja de cartón mediana, marrón",
            "carrier": "Hombre con uniforme azul",
            "method": "En manos"
        }}
    ],
    "objects_out": [],
    "loading_activity": false,
    "unattended_objects": [],
    "scene_description": "Zona de recepción de mercancía",
    "alerts": [],
    "notes": ""
}}
"""


def _prompt_parking(base: str) -> str:
    return f"""{base}

OBJETIVO: Análisis de ESTACIONAMIENTO. Documentar movimiento de vehículos.

INSTRUCCIONES:
1. Vehículos visibles: tipo, color, placa si es legible
2. Entran o salen del estacionamiento
3. Ocupación: espacios ocupados vs disponibles
4. Personas que suben/bajan de vehículos

RESPONDE EXCLUSIVAMENTE en JSON válido (sin comentarios, sin markdown):
{{
    "vehicles_entering": [],
    "vehicles_exiting": [],
    "vehicles_parked_count": 5,
    "spaces_available_count": 3,
    "occupancy_pct": 62.5,
    "persons_from_vehicles": 0,
    "scene_description": "Estacionamiento subterráneo nivel -1",
    "alerts": [],
    "notes": ""
}}
"""


def _prompt_work_supervision(base: str) -> str:
    return f"""{base}

OBJETIVO: Análisis de SUPERVISIÓN DE TRABAJO. Documentar actividad laboral y seguridad.

INSTRUCCIONES:
1. Trabajadores presentes: cuántos y qué actividad realizan
2. EPP: casco, chaleco, guantes, gafas de seguridad
3. Período activo vs inactivo
4. Violaciones de seguridad visibles

RESPONDE EXCLUSIVAMENTE en JSON válido (sin comentarios, sin markdown):
{{
    "workers_count": 3,
    "workers": [
        {{
            "description": "Trabajador con camiseta amarilla",
            "activity": "Soldando estructura metálica",
            "ppe": {{"helmet": true, "vest": true, "gloves": true, "goggles": false}},
            "ppe_compliant": false,
            "violation": "Sin gafas de seguridad mientras suelda"
        }}
    ],
    "activity_status": "ACTIVE",
    "safety_violations": ["Trabajador soldando sin gafas protectoras"],
    "scene_description": "Zona de construcción",
    "alerts": [],
    "notes": ""
}}
"""


def _prompt_generic(base: str) -> str:
    return f"""{base}

OBJETIVO: Análisis operativo general del video.

Analiza el segmento con el máximo detalle posible.

RESPONDE EXCLUSIVAMENTE en JSON válido (sin comentarios, sin markdown):
{{
    "persons_count": 0,
    "description": "Descripción detallada",
    "activities": [],
    "objects": [],
    "scene_description": "",
    "alerts": [],
    "notes": ""
}}
"""


# ═══════════════════════════════════════════════════════════════
# PROMPTS DE ANÁLISIS CRUZADO (CONSOLIDACIÓN FINAL)
# ═══════════════════════════════════════════════════════════════

def build_cross_analysis_prompt(
    analysis_type: str,
    custom_context: str = "",
    total_events: int = 0,
    video_duration: float = 0
) -> str:
    """Prompt para el meta-análisis cruzado que consolida todos los segmentos"""

    dur_str = f"{video_duration/3600:.1f} horas" if video_duration > 3600 else f"{video_duration/60:.1f} minutos"
    safe_context = _sanitize_prompt_input(custom_context)

    if analysis_type == "ACCESS_CONTROL":
        return f"""Eres un analista de seguridad profesional. Acabas de analizar {total_events} segmentos
de un video de {dur_str} de una cámara de seguridad.
Contexto: "{safe_context}"

Se te proporcionan los resultados individuales de cada segmento. CONSOLIDA toda la información:

1. CONTEO TOTAL:
   - Entradas únicas (NO duplicar la misma persona en segmentos consecutivos)
   - Salidas únicas
   - Personas actualmente dentro (entradas - salidas)

2. CUMPLIMIENTO DE FOTCHECK:
   - Cuántos usaron fotcheck vs cuántos no
   - Porcentaje de cumplimiento
   - Lista detallada de accesos sin fotcheck (timestamp + descripción)

3. FLUJO POR HORA:
   - Desglose hora por hora de entradas/salidas
   - Hora pico

4. ALERTAS:
   - Accesos sin fotcheck
   - Patrones inusuales
   - Personas que entran sin salir (o viceversa)

5. PERSONAS ÚNICAS:
   - Lista de cada persona identificada con hora de entrada/salida y fotcheck

RESPONDE EXCLUSIVAMENTE en JSON válido (sin comentarios, sin markdown):
{{
    "total_unique_entries": 0,
    "total_unique_exits": 0,
    "currently_inside": 0,
    "fotcheck_used_count": 0,
    "fotcheck_skipped_count": 0,
    "fotcheck_compliance_pct": 0.0,
    "hourly_breakdown": {{
        "08:00-09:00": {{"entries": 0, "exits": 0}}
    }},
    "peak_hour": "08:00-09:00",
    "peak_hour_count": 0,
    "unique_persons": [
        {{
            "person_id": "P1",
            "description": "Descripción",
            "entry_time_s": 120,
            "exit_time_s": 3600,
            "fotcheck_used": true
        }}
    ],
    "unauthorized_access": [
        {{
            "time_s": 560,
            "description": "Persona sin usar fotcheck",
            "severity": "HIGH"
        }}
    ],
    "alerts": [],
    "overall_assessment": "Resumen general",
    "recommendations": []
}}

IMPORTANTE:
- Si la misma persona aparece en segmentos consecutivos, es UNA sola entrada
- Estima timestamps basándote en la posición temporal de cada segmento
- Sé conservador: si no es claro, cuenta como personas diferentes
"""

    elif analysis_type == "OCCUPANCY":
        return f"""Eres un analista de aforo profesional. Acabas de analizar {total_events} segmentos
de un video de {dur_str}.
Contexto: "{safe_context}"

Se te proporcionan los resultados individuales de cada segmento. CONSOLIDA toda la información:

1. OCUPACIÓN MÁXIMA Y PROMEDIO:
   - Máximo de personas simultáneas en cualquier momento del video
   - Promedio de personas por intervalo de tiempo
   - Momentos por encima del límite de aforo (si el contexto lo indica)

2. LÍNEA TEMPORAL DE OCUPACIÓN:
   - Desglose por intervalos de tiempo del conteo de personas
   - Identifica períodos de alta y baja ocupación

3. MOMENTOS PICO:
   - Hora/instante con mayor ocupación
   - Duración de la ocupación máxima

4. ALERTAS:
   - Superación de aforo si aplica
   - Concentraciones inusuales de personas
   - Zonas de congestión

RESPONDE EXCLUSIVAMENTE en JSON válido (sin comentarios, sin markdown):
{{
    "max_occupancy": 0,
    "max_occupancy_time_s": 0,
    "avg_occupancy": 0.0,
    "occupancy_timeline": [
        {{"time_s": 0, "time_label": "00:00", "count": 0}}
    ],
    "peak_moment": "00:00",
    "peak_duration_s": 0,
    "congestion_alerts": [
        {{
            "time_s": 0,
            "count": 0,
            "description": "Descripción del evento de congestión"
        }}
    ],
    "overall_assessment": "Resumen general del aforo",
    "recommendations": []
}}
"""

    elif analysis_type == "PEOPLE_FLOW":
        return f"""Eres un analista de flujo de personas profesional. Acabas de analizar {total_events} segmentos
de un video de {dur_str}.
Contexto: "{safe_context}"

Se te proporcionan los resultados individuales de cada segmento. CONSOLIDA toda la información:

1. CONTEO TOTAL DE PERSONAS:
   - Total de personas que pasaron por la escena (sin duplicar personas consecutivas)
   - Dirección dominante del flujo (entrada, salida, bidireccional)

2. FLUJO POR HORA:
   - Desglose hora a hora (o por intervalos) del número de personas
   - Hora pico de flujo

3. PATRONES DE FLUJO:
   - Agrupaciones, formación de colas, aglomeraciones
   - Velocidad general del flujo (rápido, normal, lento)

4. CUELLOS DE BOTELLA:
   - Zonas o momentos donde el flujo se reduce significativamente
   - Causa aparente si es visible

5. ALERTAS:
   - Congestión, contraflujo, incidentes

RESPONDE EXCLUSIVAMENTE en JSON válido (sin comentarios, sin markdown):
{{
    "total_persons_passed": 0,
    "direction_breakdown": {{"entering": 0, "exiting": 0, "undefined": 0}},
    "hourly_flow": {{
        "00:00-01:00": 0
    }},
    "peak_hour": "00:00-01:00",
    "peak_hour_count": 0,
    "flow_patterns": [
        {{"time_s": 0, "description": "Descripción del patrón", "severity": "LOW"}}
    ],
    "bottleneck_areas": [
        {{"time_s": 0, "description": "Descripción del cuello de botella"}}
    ],
    "overall_assessment": "Resumen general del flujo",
    "recommendations": []
}}
"""

    elif analysis_type == "MERCHANDISE_CONTROL":
        return f"""Eres un analista de control de mercancía profesional. Acabas de analizar {total_events} segmentos
de un video de {dur_str}.
Contexto: "{safe_context}"

Se te proporcionan los resultados individuales de cada segmento. CONSOLIDA toda la información:

1. CONTEO DE OBJETOS/MERCANCÍA:
   - Total de objetos o bultos que entraron
   - Total de objetos o bultos que salieron
   - Balance neto (diferencia entre entradas y salidas)

2. INVENTARIO DE OBJETOS:
   - Lista de cada tipo de objeto observado con descripción y cantidad
   - Estimación de tamaño/volumen cuando sea posible

3. EVENTOS DE CARGA/DESCARGA:
   - Actividades de carga, descarga o movimiento de mercancía
   - Personas involucradas en cada evento

4. OBJETOS DESATENDIDOS:
   - Objetos dejados sin custodia por más de un intervalo de tiempo
   - Ubicación aproximada y duración

5. ALERTAS:
   - Discrepancias entre entradas y salidas
   - Objetos sospechosos o no identificados
   - Movimientos sin supervisión

RESPONDE EXCLUSIVAMENTE en JSON válido (sin comentarios, sin markdown):
{{
    "total_objects_in": 0,
    "total_objects_out": 0,
    "net_balance": 0,
    "object_inventory": [
        {{
            "type": "Tipo de objeto",
            "count": 0,
            "description": "Descripción detallada"
        }}
    ],
    "loading_events": [
        {{
            "time_s": 0,
            "type": "LOADING",
            "description": "Descripción del evento",
            "persons_involved": 0
        }}
    ],
    "unattended_objects": [
        {{
            "time_s": 0,
            "duration_s": 0,
            "description": "Descripción del objeto desatendido",
            "severity": "MEDIUM"
        }}
    ],
    "alerts": [],
    "overall_assessment": "Resumen general del control de mercancía",
    "recommendations": []
}}
"""

    elif analysis_type == "PARKING":
        return f"""Eres un analista de estacionamiento profesional. Acabas de analizar {total_events} segmentos
de un video de {dur_str}.
Contexto: "{safe_context}"

Se te proporcionan los resultados individuales de cada segmento. CONSOLIDA toda la información:

1. CONTEO DE VEHÍCULOS:
   - Total de vehículos que entraron
   - Total de vehículos que salieron
   - Vehículos que permanecieron durante todo el período

2. OCUPACIÓN DEL ESTACIONAMIENTO:
   - Máxima ocupación simultánea
   - Promedio de ocupación
   - Hora pico de ocupación

3. LISTA DE VEHÍCULOS:
   - Tipo (automóvil, camioneta, moto, camión, etc.)
   - Color y características visibles
   - Hora de entrada y salida cuando sea determinable

4. ALERTAS:
   - Vehículos mal estacionados
   - Exceso de tiempo de permanencia (si el contexto lo indica)
   - Vehículos no identificados o sospechosos

RESPONDE EXCLUSIVAMENTE en JSON válido (sin comentarios, sin markdown):
{{
    "total_vehicles_entered": 0,
    "total_vehicles_exited": 0,
    "vehicles_remaining": 0,
    "max_occupancy": 0,
    "max_occupancy_time_s": 0,
    "avg_occupancy": 0.0,
    "peak_hour": "00:00-01:00",
    "hourly_flow": {{
        "00:00-01:00": {{"entered": 0, "exited": 0}}
    }},
    "vehicle_list": [
        {{
            "type": "Tipo de vehículo",
            "description": "Color y características",
            "entry_time_s": 0,
            "exit_time_s": null,
            "duration_s": 0
        }}
    ],
    "alerts": [],
    "overall_assessment": "Resumen general del estacionamiento",
    "recommendations": []
}}
"""

    elif analysis_type == "WORK_SUPERVISION":
        return f"""Eres un analista de supervisión de trabajo y seguridad laboral profesional.
Acabas de analizar {total_events} segmentos de un video de {dur_str}.
Contexto: "{safe_context}"

Se te proporcionan los resultados individuales de cada segmento. CONSOLIDA toda la información:

1. IDENTIFICACIÓN DE TRABAJADORES:
   - Total de trabajadores únicos identificados (NO duplicar la misma persona en segmentos consecutivos)
   - Actividades realizadas por cada trabajador

2. CUMPLIMIENTO DE EPP (Equipos de Protección Personal):
   - Porcentaje de cumplimiento general
   - Desglose por tipo de EPP: casco, chaleco, guantes, gafas
   - Lista de trabajadores con EPP incompleto

3. ACTIVIDAD LABORAL:
   - Porcentaje de tiempo activo vs inactivo
   - Tipos de actividades observadas
   - Productividad general

4. VIOLACIONES DE SEGURIDAD:
   - Lista detallada de violaciones con timestamp y descripción
   - Severidad de cada violación
   - Trabajador involucrado cuando sea identificable

5. ALERTAS:
   - Situaciones de riesgo inmediato
   - Patrones recurrentes de incumplimiento

RESPONDE EXCLUSIVAMENTE en JSON válido (sin comentarios, sin markdown):
{{
    "total_workers_identified": 0,
    "ppe_compliance_pct": 0.0,
    "ppe_breakdown": {{
        "helmet_compliance_pct": 0.0,
        "vest_compliance_pct": 0.0,
        "gloves_compliance_pct": 0.0,
        "goggles_compliance_pct": 0.0
    }},
    "active_vs_idle_pct": {{"active": 0.0, "idle": 0.0}},
    "worker_list": [
        {{
            "worker_id": "W1",
            "description": "Descripción del trabajador",
            "activity": "Actividad principal",
            "ppe": {{"helmet": true, "vest": true, "gloves": false, "goggles": false}},
            "ppe_compliant": false,
            "violations": ["Descripción de la violación"]
        }}
    ],
    "safety_violations": [
        {{
            "time_s": 0,
            "worker_id": "W1",
            "description": "Descripción de la violación",
            "severity": "HIGH"
        }}
    ],
    "alerts": [],
    "overall_assessment": "Resumen general de la supervisión de trabajo",
    "recommendations": []
}}
"""

    else:
        return f"""Consolida {total_events} segmentos de un video de {dur_str}.
Contexto: "{safe_context}".

Produce un JSON consolidado con resumen, conteos, alertas, recomendaciones.
RESPONDE EXCLUSIVAMENTE en JSON válido (sin comentarios, sin markdown).
"""
