"""
Adaptador para Google Gemini 3 AI - TIVIT Video
Proporciona capacidades de IA generativa como servicio principal.
NUEVO: Usa google-genai SDK v1.51+ con Gemini 3 Flash/Pro via Vertex AI.
"""
import os
import json
import re
import logging
import base64
import time
from typing import Optional, Dict, Any, List, Callable

logger = logging.getLogger(__name__)

# Configuración de reintentos
MAX_RETRIES = 3
INITIAL_BACKOFF = 2  # segundos
MAX_BACKOFF = 30     # segundos


class GeminiAdapter:
    """
    Adaptador para Google Gemini 3 AI via GenAI SDK.
    Usado como servicio principal de IA.
    Usa ADC (Application Default Credentials) para autenticación con Vertex AI.
    """
    
    def __init__(self):
        self.client = None
        self._initialized = False
        # Modelos Gemini estables (GA) — sin riesgo de deprecación
        self._model_name = 'gemini-2.5-flash'   # Sucesor de 2.0-flash, más capaz y disponible
        self._model_pro = 'gemini-2.5-flash'      # Mismo modelo — suficiente para análisis operativo
        self.project_id = os.getenv('GCP_PROJECT_ID') or os.getenv('GOOGLE_CLOUD_PROJECT')
        self.region = os.getenv('GOOGLE_CLOUD_LOCATION', 'us-central1')  # us-central1 es la región estándar de Gemini en Vertex AI
        
        if not self.project_id:
            logger.warning("⚠️ GCP_PROJECT_ID no configurado para Gemini")
            return
        
        try:
            from google import genai
            from google.genai import types
            
            # Crear cliente GenAI explícitamente forzando Vertex AI si está configurado
            _use_vertex = os.getenv('GOOGLE_GENAI_USE_VERTEXAI', 'True').lower() in ('true', '1', 'yes')
            if _use_vertex:
                self.client = genai.Client(vertexai=True, project=self.project_id, location=self.region)
            else:
                self.client = genai.Client()
            self.types = types
            self._initialized = True
            logger.info(f"✅ Gemini 3 inicializado ({self._model_name}, proyecto={self.project_id}, región={self.region})")
            
        except ImportError as e:
            logger.warning(f"⚠️ google-genai SDK no instalado: {e}")
        except Exception as e:
            logger.error(f"❌ Error inicializando Gemini 3: {e}")
    
    @property
    def disponible(self) -> bool:
        """Verifica si el servicio está disponible"""
        return self._initialized and self.client is not None
    
    def is_available(self) -> bool:
        """Alias para disponible (compatibilidad)"""
        return self.disponible
    
    def _classify_gemini_error(self, e: Exception) -> dict:
        """
        Clasifica una excepción de la API Gemini en un error tipificado.
        """
        error_str = str(e).lower()
        if any(k in error_str for k in ('429', 'resource_exhausted', 'quota', 'rate limit', 'rate_limit')):
            error_type = 'rate_limit'
            message = 'Cuota de Gemini agotada. Intente más tarde.'
        elif any(k in error_str for k in ('context', 'token', 'too long', 'maximum context', 'input too long')):
            error_type = 'context_too_long'
            message = 'El contenido enviado supera el límite del modelo.'
        elif any(k in error_str for k in ('timeout', 'deadline', 'timed out', 'connection', 'network')):
            error_type = 'network'
            message = 'Error de red o timeout al contactar Gemini.'
        elif any(k in error_str for k in ('api_key', 'api key', 'authentication', 'permission', 'unauthenticated', '401', '403')):
            error_type = 'auth'
            message = 'Credenciales de Gemini inválidas o sin permisos.'
        elif any(k in error_str for k in ('safety', 'blocked', 'harm', 'finish_reason: safety')):
            error_type = 'content_blocked'
            message = 'Respuesta bloqueada por filtros de seguridad del modelo.'
        elif any(k in error_str for k in ('503', 'unavailable', 'overloaded', 'service unavailable')):
            error_type = 'unavailable'
            message = 'Servicio Gemini temporalmente no disponible.'
        else:
            error_type = 'unknown'
            message = 'Error inesperado en Gemini.'
        logger.error("Gemini 3 error [%s]: %s", error_type, e)
        return {'success': False, 'error': message, 'error_type': error_type}

    def _retry_with_backoff(self, func: Callable, *args, **kwargs) -> Any:
        """
        Ejecuta una función con reintentos exponenciales
        """
        last_exception = None
        backoff = INITIAL_BACKOFF
        
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
                
            except Exception as e:
                last_exception = e
                error_str = str(e).lower()
                
                # Identificar errores que ameritan reintento
                is_retryable = any([
                    '429' in error_str,
                    '500' in error_str,
                    '503' in error_str,
                    'timeout' in error_str,
                    'deadline' in error_str,
                    'temporarily unavailable' in error_str,
                    'resource exhausted' in error_str
                ])
                
                if not is_retryable:
                    logger.warning(f"❌ Error no recuperable en Gemini 3: {e}")
                    raise
                
                if attempt < MAX_RETRIES - 1:
                    wait_time = min(backoff, MAX_BACKOFF)
                    logger.warning(
                        f"⚠️ Error Gemini 3 (intento {attempt + 1}/{MAX_RETRIES}): {e}. "
                        f"Reintentando en {wait_time}s..."
                    )
                    time.sleep(wait_time)
                    backoff *= 2
                else:
                    logger.error(f"❌ Fallo definitivo en Gemini 3 después de {MAX_RETRIES} intentos: {e}")
        
        raise last_exception

    def _validate_gemini_response(self, response: dict) -> dict:
        """
        Valida y normaliza respuesta de Gemini
        """
        required_fields = {
            'descripcion_escena': 'Sin descripción disponible',
            'nivel_riesgo': 'BAJO',
            'confianza': 50,
            'personas_estimadas': 0,
            'vehiculos_estimados': 0
        }
        
        for field, default in required_fields.items():
            if field not in response or response[field] is None:
                response[field] = default
                logger.warning(f"⚠️ Campo '{field}' faltante, usando default: {default}")
        
        # Normalizar nivel_riesgo
        valid_risks = ['BAJO', 'MEDIO', 'ALTO', 'CRITICO']
        if response.get('nivel_riesgo') not in valid_risks:
            logger.warning(f"⚠️ Nivel de riesgo inválido: {response.get('nivel_riesgo')}, usando MEDIO")
            response['nivel_riesgo'] = 'MEDIO'
        
        # Asegurar que confianza esté en rango válido
        if not isinstance(response.get('confianza'), (int, float)):
            response['confianza'] = 50
        else:
            response['confianza'] = max(0, min(100, int(response['confianza'])))
        
        # Asegurar que contadores sean enteros positivos
        for counter in ['personas_estimadas', 'vehiculos_estimados']:
            if not isinstance(response.get(counter), int) or response[counter] < 0:
                response[counter] = 0
        
        return response
    
    def generar_titulo(
        self, 
        nombre_archivo: str, 
        etiquetas: List[str] = None,
        duracion_segundos: int = None
    ) -> str:
        """
        Genera un título creativo para el video.
        """
        if not self.disponible:
            return self._titulo_fallback(nombre_archivo)
        
        etiquetas = etiquetas or []
        
        prompt = f"""Genera un título corto y atractivo para un video corporativo.

INFORMACIÓN DEL VIDEO:
- Nombre del archivo: {nombre_archivo}
- Etiquetas detectadas: {', '.join(etiquetas[:8]) if etiquetas else 'ninguna'}
- Duración: {duracion_segundos or 'desconocida'} segundos

REGLAS:
1. Máximo 50 caracteres
2. En español
3. Atractivo y profesional
4. Sin comillas, puntos suspensivos ni emojis
5. Debe reflejar el contenido

Responde SOLO con el título, nada más."""

        try:
            response = self._retry_with_backoff(
                self.client.models.generate_content,
                model=self._model_name,
                contents=prompt,
                config=self.types.GenerateContentConfig(
                    # thinking_config removido por incompatibilidad con Vertex AI 2.5-flash
                )
            )
            titulo = response.text.strip().strip('"\'').strip()
            
            # Limpiar caracteres no deseados
            titulo = re.sub(r'["\'\n\r]', '', titulo)
            titulo = titulo[:50] if len(titulo) > 50 else titulo
            
            logger.debug(f"Título generado por Gemini 3: {titulo}")
            return titulo
            
        except Exception as e:
            logger.error(f"Error generando título con Gemini 3: {e}")
            return self._titulo_fallback(nombre_archivo)
    
    def decidir_moderacion(
        self, 
        analisis: Dict[str, Any],
        blacklist: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Decide si aprobar o rechazar un video basado en el análisis.
        """
        if not self.disponible:
            return {
                'aprobado': False,
                'razon': 'Servicio de IA no disponible',
                'confianza': 0.0,
                'requiere_revision': True,
                'modelo': 'ninguno'
            }
        
        blacklist = blacklist or {}
        logos_prohibidos = blacklist.get('logos_competidores', [])
        palabras_prohibidas = blacklist.get('palabras_prohibidas', [])
        categorias_prohibidas = blacklist.get('categorias_prohibidas', [])
        
        prompt = f"""Eres un moderador de contenido para TIVIT Video, una plataforma corporativa de videos.

ANÁLISIS DEL VIDEO:
- Logos detectados: {json.dumps(analisis.get('logos', []), ensure_ascii=False)}
- Texto OCR detectado: {json.dumps(analisis.get('textos', [])[:15], ensure_ascii=False)}
- Nivel de contenido explícito: {json.dumps(analisis.get('contenido_explicito', {}), ensure_ascii=False)}
- Etiquetas/Categorías: {json.dumps(analisis.get('etiquetas', [])[:20], ensure_ascii=False)}
- Duración: {analisis.get('duracion_segundos', 'N/A')} segundos

REGLAS DE MODERACIÓN (RECHAZAR si se cumple alguna):
1. Logos de competidores prohibidos: {logos_prohibidos[:10]}
2. Palabras/frases prohibidas: {palabras_prohibidas[:15]}
3. Categorías de contenido prohibidas: {categorias_prohibidas[:10]}
4. Contenido explícito (adulto, violencia gráfica, drogas)
5. Contenido ofensivo, discriminatorio o inapropiado para entorno corporativo
6. Spam o contenido promocional no autorizado

APROBAR si:
- El contenido es seguro para audiencia corporativa general
- No viola ninguna de las reglas anteriores

Analiza cuidadosamente y responde SOLO con este JSON (sin markdown):
{{"aprobado": true/false, "razon": "explicación breve en 1-2 oraciones", "confianza": 0.0-1.0, "categorias_detectadas": ["lista", "categorias"]}}"""

        try:
            response = self._retry_with_backoff(
                self.client.models.generate_content,
                model=self._model_name,
                contents=prompt,
                config=self.types.GenerateContentConfig(
                    # thinking_config removido por incompatibilidad
                )
            )
            text = response.text.strip()
            
            # Limpiar markdown si existe
            if '```' in text:
                match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
                if match:
                    text = match.group(1).strip()
            
            # Buscar JSON en la respuesta
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                text = json_match.group(0)
            
            result = json.loads(text)
            result['modelo'] = self._model_name
            
            logger.info(f"Moderación Gemini 3: aprobado={result.get('aprobado')}, confianza={result.get('confianza')}")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Error parseando respuesta de Gemini 3: {e}")
            return {
                'aprobado': False,
                'razon': 'Error al procesar respuesta de IA',
                'confianza': 0.0,
                'requiere_revision': True,
                'modelo': self._model_name
            }
        except Exception as e:
            logger.error(f"Error en moderación Gemini 3: {e}")
            return {
                'aprobado': False,
                'razon': f'Error de IA: {str(e)[:100]}',
                'confianza': 0.0,
                'requiere_revision': True,
                'modelo': self._model_name
            }
    
    def analizar_sentimiento(self, textos: List[str]) -> Dict[str, Any]:
        """
        Analiza el sentimiento de textos detectados en el video.
        """
        if not self.disponible or not textos:
            return {'sentimiento': 'neutral', 'confianza': 0.0}
        
        prompt = f"""Analiza el sentimiento de estos textos encontrados en un video:

{json.dumps(textos[:20], ensure_ascii=False, indent=2)}

Responde SOLO con JSON:
{{"sentimiento": "positivo/neutral/negativo", "confianza": 0.0-1.0, "palabras_clave": ["lista", "palabras"]}}"""

        try:
            response = self._retry_with_backoff(
                self.client.models.generate_content,
                model=self._model_name,
                contents=prompt,
                config=self.types.GenerateContentConfig(
                    # thinking_config removido
                )
            )
            text = response.text.strip()
            
            # Limpiar y parsear
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            
            return {'sentimiento': 'neutral', 'confianza': 0.5}
            
        except Exception as e:
            logger.error(f"Error en análisis de sentimiento: {e}")
            return {'sentimiento': 'neutral', 'confianza': 0.0}
    
    def _titulo_fallback(self, nombre_archivo: str) -> str:
        """Genera título simple sin IA"""
        nombre = os.path.splitext(nombre_archivo)[0]
        nombre = re.sub(r'[_\-\.]+', ' ', nombre)
        nombre = re.sub(r'\s+', ' ', nombre).strip()
        return nombre.title()[:50] if nombre else "Video sin título"
    
    def analyze_video_clip(self, clip_path: str, prompt: str, frames_base64: List[str] = None) -> Dict:
        """
        Analiza un video completo con Gemini 3.
        Para Vertex AI, el video debe estar en GCS.
        """
        if not self.disponible:
            return {'success': False, 'error': 'Gemini 3 no está disponible'}
        
        try:
            gcs_uri = None
            if clip_path.startswith('gs://'):
                gcs_uri = clip_path
                logger.info(f"🎬 Usando video de GCS: {gcs_uri}")
            else:
                logger.warning(f"⚠️ Video en ruta local: {clip_path}. Vertex AI requiere GCS URI.")
                if frames_base64:
                    return self.analyze_frames(prompt, frames_base64)
                auto_frames = self._extract_frames_from_clip(clip_path)
                if auto_frames:
                    logger.info(f"🔄 Extrayendo {len(auto_frames)} frames del video para análisis")
                    return self.analyze_frames(prompt, auto_frames)
                return {'success': False, 'error': 'Video debe estar en GCS para análisis con Vertex AI'}
            
            logger.info(f"🧠 Analizando video con Gemini 3...")
            analysis_start = time.time()
            
            # Crear Part para el video desde GCS
            video_part = self.types.Part.from_uri(
                file_uri=gcs_uri,
                mime_type="video/mp4"
            )
            
            # Construir contenido
            contents = [video_part, prompt]
            
            # Agregar frames HD si se proporcionaron
            if frames_base64:
                logger.info(f"   🖼️ Añadiendo {len(frames_base64[:3])} frames HD como complemento")
                contents.append("\n\nAdemás del video, aquí tienes frames de alta resolución para analizar detalles estáticos:")
                for frame_b64 in frames_base64[:3]:
                    image_data = base64.b64decode(frame_b64)
                    contents.append(self.types.Part.from_bytes(data=image_data, mime_type='image/jpeg'))
            
            # Generar análisis — sin ThinkingConfig en Fase 2.
            # ThinkingConfig solo se usa en Fase 3 (cross-analysis) donde la
            # consolidación entre segmentos requiere razonamiento profundo.
            response = self._retry_with_backoff(
                self.client.models.generate_content,
                model=self._model_name,
                contents=contents,
                config=self.types.GenerateContentConfig(
                    media_resolution=self.types.MediaResolution.MEDIA_RESOLUTION_MEDIUM,  # Balance calidad/costo
                )
            )
            
            # Parsear respuesta JSON
            texto_respuesta = response.text.strip()
            resultado = self._parse_gemini_json_response(texto_respuesta)
            resultado = self._validate_gemini_response(resultado)
            
            # Obtener métricas de uso
            tokens_used = None
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                tokens_used = getattr(response.usage_metadata, 'total_token_count', 0)
            
            analysis_elapsed = time.time() - analysis_start
            logger.info(f"✅ Análisis de video completado en {analysis_elapsed:.1f}s (tokens: {tokens_used})")
            
            return {
                'success': True,
                'analisis': resultado,
                'tipo_analisis': 'video_clip',
                'tokens_usados': tokens_used
            }
            
        except Exception as e:
            logger.error(f"❌ Error en análisis de video clip: {e}")
            # Fallback a frames
            if frames_base64:
                logger.info("🔄 Fallback: analizando frames en lugar de video clip")
                return self.analyze_frames(prompt, frames_base64)
            if not clip_path.startswith('gs://'):
                auto_frames = self._extract_frames_from_clip(clip_path)
                if auto_frames:
                    logger.info(f"🔄 Fallback automático: extrayendo {len(auto_frames)} frames")
                    return self.analyze_frames(prompt, auto_frames)
            return self._classify_gemini_error(e)
    
    def _extract_frames_from_clip(self, clip_path: str, n_frames: int = 4) -> List[str]:
        """Extrae N frames de un clip como base64 JPEG."""
        frames_b64 = []
        if not clip_path or not os.path.exists(clip_path):
            return frames_b64
        try:
            import cv2
            cap = cv2.VideoCapture(clip_path)
            if not cap.isOpened():
                return frames_b64
            total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total <= 0:
                cap.release()
                return frames_b64
            indices = [int(total * (i + 1) / (n_frames + 1)) for i in range(n_frames)]
            for idx in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()
                if not ret:
                    continue
                h, w = frame.shape[:2]
                if w > 1280:
                    frame = cv2.resize(frame, (1280, int(h * 1280 / w)), interpolation=cv2.INTER_AREA)
                _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                frames_b64.append(base64.b64encode(buf.tobytes()).decode('utf-8'))
            cap.release()
        except Exception as e:
            logger.debug(f"Error extrayendo frames: {e}")
        return frames_b64

    def analyze_text_with_thinking(self, prompt: str) -> str:
        """
        Genera una respuesta de texto usando ThinkingConfig MEDIUM.
        Diseñado exclusivamente para Fase 3 (cross-analysis / meta-consolidación)
        donde el modelo debe razonar en profundidad sobre múltiples segmentos.

        Returns:
            str: Texto generado por el modelo, o cadena vacía si falla.
        """
        if not self.disponible:
            return ""
        try:
            response = self._retry_with_backoff(
                self.client.models.generate_content,
                model=self._model_name,
                contents=prompt,
                config=self.types.GenerateContentConfig(
                    # thinking_config removido
                    max_output_tokens=32768,
                    temperature=0.1,
                )
            )
            return response.text
        except Exception as e:
            logger.error(f"❌ Error en analyze_text_with_thinking: {e}")
            return ""

    def analyze_multiple_clips_summary(self, all_events_analysis: List[Dict], video_metadata: Dict) -> Dict:
        """
        Análisis cruzado de TODOS los eventos detectados.
        """
        if not self.disponible:
            return {'success': False, 'error': 'Gemini 3 no disponible'}
        
        try:
            cross_start = time.time()
            
            events_summary = []
            for i, ev in enumerate(all_events_analysis):
                events_summary.append({
                    'evento': i + 1,
                    'timestamp': f"{ev.get('timestamp_inicio', 0):.0f}s - {ev.get('timestamp_fin', 0):.0f}s",
                    'descripcion': ev.get('descripcion', '')[:200],
                    'personas': ev.get('personas_count', 0),
                    'vehiculos': ev.get('vehiculos_count', 0),
                    'objetos': ev.get('objetos_detectados', [])[:10],
                    'nivel_riesgo': ev.get('nivel_riesgo', 'bajo'),
                    'acciones': ev.get('acciones_detectadas', [])[:5]
                })
            
            if len(events_summary) > 40:
                return self._chunked_cross_analysis(events_summary, video_metadata, cross_start)
            
            prompt = self._build_cross_analysis_prompt(events_summary, video_metadata)
            logger.info(f"🧠 Enviando {len(events_summary)} eventos a Gemini 3 para correlación cruzada...")
            
            response = self._retry_with_backoff(
                self.client.models.generate_content,
                model=self._model_pro,  # Usar Pro para razonamiento complejo
                contents=prompt,
                config=self.types.GenerateContentConfig(
                    # thinking_config removido
                )
            )
            
            texto_respuesta = response.text.strip()
            resultado = self._parse_gemini_json_response(texto_respuesta)
            
            cross_elapsed = time.time() - cross_start
            tokens_cross = None
            if hasattr(response, 'usage_metadata') and response.usage_metadata:
                tokens_cross = getattr(response.usage_metadata, 'total_token_count', 0)
            logger.info(f"✅ Análisis cruzado completado en {cross_elapsed:.1f}s (tokens: {tokens_cross})")
            
            return {
                'success': True,
                'analisis_cruzado': resultado
            }
            
        except Exception as e:
            return self._classify_gemini_error(e)

    def _build_cross_analysis_prompt(self, events_summary: list, video_metadata: Dict) -> str:
        """Construye el prompt para análisis cruzado"""
        return f"""Eres un analista experto de seguridad. Analiza TODOS estos eventos detectados en un video de cámara de seguridad y genera un reporte de correlación cruzada.

INFORMACIÓN DEL VIDEO:
- Cámara: {video_metadata.get('nombre_camara', 'Desconocida')}
- Ubicación: {video_metadata.get('ubicacion', 'Desconocida')}
- Duración total: {video_metadata.get('duracion_segundos', 0):.0f} segundos
- Total eventos: {len(events_summary)}

EVENTOS DETECTADOS:
{json.dumps(events_summary, ensure_ascii=False, indent=2)}

ANALIZA Y RESPONDE EN JSON:
{{
    "resumen_ejecutivo": "Resumen de 2-3 párrafos de todo lo ocurrido en el video",
    "nivel_riesgo_global": "BAJO/MEDIO/ALTO/CRITICO",
    "razon_nivel_riesgo": "Explicación del nivel de riesgo asignado",
    "patrones_detectados": [
        {{
            "patron": "Descripción del patrón",
            "eventos_involucrados": [1, 3, 5],
            "relevancia": "alta/media/baja"
        }}
    ],
    "cronologia": "Narrativa cronológica de los eventos más relevantes",
    "anomalias": ["Lista de comportamientos anómalos detectados"],
    "recomendaciones_seguridad": ["Recomendación 1", "Recomendación 2"],
    "zonas_mayor_actividad": ["Descripción de zonas con más actividad"],
    "horarios_criticos": ["Rangos de tiempo con mayor actividad"],
    "personas_total_estimado": 0,
    "vehiculos_total_estimado": 0,
    "clasificacion_general": "Descripción general de qué tipo de día/actividad se registró"
}}"""
    
    def _chunked_cross_analysis(self, events_summary: list, video_metadata: Dict, cross_start: float) -> Dict:
        """Análisis cruzado por chunks para manejar muchos eventos (>40)."""
        CHUNK_SIZE = 30
        chunk_results = []
        total_chunks = (len(events_summary) + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        logger.info(f"🧠 Análisis cruzado por chunks: {len(events_summary)} eventos → {total_chunks} grupos")
        
        for i in range(0, len(events_summary), CHUNK_SIZE):
            chunk = events_summary[i:i + CHUNK_SIZE]
            chunk_num = i // CHUNK_SIZE + 1
            logger.info(f"   🧠 Grupo {chunk_num}/{total_chunks}")
            
            prompt = self._build_cross_analysis_prompt(chunk, video_metadata)
            
            try:
                response = self._retry_with_backoff(
                    self.client.models.generate_content,
                    model=self._model_name,
                    contents=prompt,
                    config=self.types.GenerateContentConfig(
                    # thinking_config removido
                    )
                )
                resultado = self._parse_gemini_json_response(response.text.strip())
                chunk_results.append(resultado)
                logger.info(f"   ✅ Grupo {chunk_num} analizado")
            except Exception as e:
                logger.warning(f"   ⚠️ Error en grupo {chunk_num}: {e}")
                chunk_results.append({'resumen_ejecutivo': f'Error grupo {chunk_num}', 'nivel_riesgo_global': 'BAJO'})
            
            if i + CHUNK_SIZE < len(events_summary):
                time.sleep(2)
        
        # Meta-análisis
        logger.info(f"🧠 Meta-análisis: consolidando {len(chunk_results)} grupos...")
        
        meta_prompt = f"""Consolida estos análisis por grupos en un reporte ÚNICO:

INFORMACIÓN: {video_metadata.get('duracion_segundos', 0):.0f}s, {len(events_summary)} eventos

RESULTADOS POR GRUPO:
{json.dumps(chunk_results, ensure_ascii=False, indent=2)}

Responde con JSON consolidado (mismo formato anterior)."""
        
        try:
            response = self._retry_with_backoff(
                self.client.models.generate_content,
                model=self._model_pro,
                contents=meta_prompt,
                config=self.types.GenerateContentConfig(
                    # thinking_config removido
                )
            )
            resultado_final = self._parse_gemini_json_response(response.text.strip())
            
            cross_elapsed = time.time() - cross_start
            logger.info(f"✅ Meta-análisis completado en {cross_elapsed:.1f}s")
            
            return {'success': True, 'analisis_cruzado': resultado_final}
        except Exception as e:
            logger.error(f"❌ Error en meta-análisis: {e}")
            return {'success': True, 'analisis_cruzado': chunk_results[0] if chunk_results else {'nivel_riesgo_global': 'BAJO'}}
    
    def _parse_gemini_json_response(self, texto_respuesta: str) -> Dict:
        """Parsea y limpia respuesta JSON de Gemini con manejo robusto de errores"""
        # Limpiar markdown
        if '```json' in texto_respuesta:
            texto_respuesta = texto_respuesta.split('```json')[1]
        if '```' in texto_respuesta:
            match = re.search(r'```(?:json)?\s*(.*?)\s*```', texto_respuesta, re.DOTALL)
            if match:
                texto_respuesta = match.group(1)
        
        # Buscar JSON válido
        json_match = re.search(r'\{.*\}', texto_respuesta, re.DOTALL)
        if json_match:
            texto_respuesta = json_match.group(0)
        
        # Limpiar caracteres problemáticos
        texto_respuesta = re.sub(r',\s*([\]}])', r'\1', texto_respuesta)
        texto_respuesta = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', texto_respuesta)
        
        try:
            return json.loads(texto_respuesta.strip())
        except json.JSONDecodeError:
            # Intentar reparar JSON truncado
            texto_limpio = texto_respuesta.strip()
            if texto_limpio.count('"') % 2 != 0:
                texto_limpio += '"'
            open_braces = texto_limpio.count('{') - texto_limpio.count('}')
            open_brackets = texto_limpio.count('[') - texto_limpio.count(']')
            texto_limpio += ']' * max(0, open_brackets)
            texto_limpio += '}' * max(0, open_braces)
            texto_limpio = re.sub(r',\s*([\]}])', r'\1', texto_limpio)
            try:
                return json.loads(texto_limpio)
            except json.JSONDecodeError:
                return self._extraer_campos_json_parcial(texto_respuesta)
    
    def analyze_frames(self, prompt: str, frames_base64: List[str]) -> Dict:
        """
        Analiza múltiples frames de video con Gemini 3 Vision
        """
        if not self.disponible:
            return {'success': False, 'error': 'Gemini 3 no está disponible'}
        
        try:
            logger.info(f"🎬 Analizando {len(frames_base64)} frames con Gemini 3 Vision")
            
            # Preparar contenido multimodal
            contents = [prompt]
            
            for frame_b64 in frames_base64:
                image_data = base64.b64decode(frame_b64)
                contents.append(self.types.Part.from_bytes(data=image_data, mime_type='image/jpeg'))
            
            response = self._retry_with_backoff(
                self.client.models.generate_content,
                model=self._model_name,
                contents=contents,
                config=self.types.GenerateContentConfig(
                    # thinking_config removido
                    media_resolution=self.types.MediaResolution.MEDIA_RESOLUTION_HIGH,  # Alta resolución
                )
            )
            
            texto_respuesta = response.text.strip()
            resultado = self._parse_gemini_json_response(texto_respuesta)
            resultado = self._validate_gemini_response(resultado)
            
            logger.info(f"✅ Análisis Gemini 3 Vision completado")
            
            return {
                'success': True,
                'analisis': resultado,
                'frames_analizados': len(frames_base64),
                'tokens_usados': getattr(response.usage_metadata, 'total_token_count', 0) if hasattr(response, 'usage_metadata') and response.usage_metadata else None
            }
            
        except Exception as e:
            return self._classify_gemini_error(e)

    def _extraer_campos_json_parcial(self, texto: str) -> Dict:
        """Extrae campos clave de un JSON truncado usando regex"""
        resultado = {
            'contenido_apropiado': False,
            'recomendacion': 'rechazar',
            'razon_recomendacion': 'Análisis visual incompleto',
            'confianza': 30,
            'descripcion_contenido': '',
            'nivel_riesgo': 'BAJO',
        }
        
        try:
            # Extraer campos individuales
            match = re.search(r'"contenido_apropiado"\s*:\s*(true|false)', texto, re.IGNORECASE)
            if match:
                resultado['contenido_apropiado'] = match.group(1).lower() == 'true'
            
            match = re.search(r'"recomendacion"\s*:\s*"([^"]*)"', texto, re.IGNORECASE)
            if match:
                resultado['recomendacion'] = match.group(1).lower()
            
            match = re.search(r'"confianza"\s*:\s*(\d+)', texto)
            if match:
                resultado['confianza'] = int(match.group(1))
            
            match = re.search(r'"descripcion_contenido"\s*:\s*"([^"]*)', texto)
            if match:
                resultado['descripcion_contenido'] = match.group(1)
            
            logger.info(f"✅ Campos extraídos manualmente")
            
        except Exception as e:
            logger.warning(f"Error extrayendo campos: {e}")
        
        return resultado
    
    def analyze_video_clip_safety(self, gcs_uri: str, descripcion: str,
                                  duracion: float = 0,
                                  contexto_workspace: str = "", metadata_workspace: dict = None) -> Dict:
        """
        Análisis de seguridad de contenido usando el video completo desde GCS.
        Gemini procesa audio + video nativamente — no requiere Speech-to-Text.
        Fallback automático a frames si el URI no está disponible.
        """
        if not self.disponible:
            return {'success': False, 'error': 'Gemini 3 no está disponible'}

        metadata_workspace = metadata_workspace or {}

        workspace_info = ""
        if contexto_workspace:
            categoria = metadata_workspace.get('categoria', 'general')
            tolerancia = metadata_workspace.get('nivel_tolerancia', 'medio')
            tipo = metadata_workspace.get('tipo_contenido', '')
            tolerancia_nota = (
                "\n⚡ TOLERANCIA ALTA: contenido intenso, deportivo o de acción es NORMAL y ESPERADO. "
                "No rechazar por contacto deportivo, esfuerzo físico o escenas de juego/competencia."
                if tolerancia == 'alto' else ""
            )
            workspace_info = f"""
CONTEXTO DEL WORKSPACE (CRÍTICO para tu decisión):
- Descripción: {contexto_workspace}
- Categoría: {categoria.upper()}
- Tolerancia de contenido: {tolerancia.upper()}
- Tipo de contenido esperado: {tipo or 'general'}{tolerancia_nota}

INSTRUCCIÓN: Si el video es RELEVANTE y APROPIADO para este workspace, apruébalo."""

        prompt = f"""Eres un moderador de contenido experto para una plataforma corporativa de videos.
Analiza COMPLETAMENTE este video — tanto su contenido visual como el audio/diálogos.

Descripción del usuario: "{descripcion[:200] if descripcion else 'Sin descripción'}"
Duración: {duracion:.0f} segundos
{workspace_info}

CRITERIOS DE RECHAZO (cualquiera es suficiente para rechazar):
1. Contenido explícito: pornografía, violencia extrema real, armas ilegales, drogas, gore, discurso de odio
2. Protección infantil: menores en contexto inapropiado
3. Irrelevancia al workspace: si hay contexto de workspace definido y el video NO TIENE RELACIÓN con ese dominio → RECHAZAR con razon "Contenido no relevante al contexto del workspace"

Responde SOLO con este JSON (sin markdown ni texto adicional):
{{
  "contenido_apropiado": true,
  "relevante_al_workspace": true,
  "recomendacion": "aprobar",
  "confianza": 85,
  "descripcion_contenido": "Descripción objetiva de lo que se ve y escucha en el video",
  "nivel_riesgo": "BAJO",
  "razon_recomendacion": "Explicación concisa de la decisión",
  "calidad_visual": "alta",
  "autenticidad": 90,
  "coherencia_narrativa": 85,
  "elementos_comerciales": ["logos o marcas visibles"],
  "banderas_rojas": ["elementos preocupantes si los hay"],
  "alertas_criticas": ["solo si requiere rechazo inmediato"],
  "audio_analizado": true,
  "resumen_audio": "Breve descripción de lo que se dice/escucha"
}}"""

        try:
            logger.info(f"🎬 Análisis de seguridad con video completo GCS: {gcs_uri}")
            video_part = self.types.Part.from_uri(file_uri=gcs_uri, mime_type="video/mp4")
            contents = [video_part, prompt]

            response = self._retry_with_backoff(
                self.client.models.generate_content,
                model=self._model_name,
                contents=contents,
                config=self.types.GenerateContentConfig(
                    media_resolution=self.types.MediaResolution.MEDIA_RESOLUTION_MEDIUM,
                )
            )

            text = response.text
            if not text and response.candidates:
                for part in response.candidates[0].content.parts:
                    part_text = getattr(part, 'text', None)
                    if part_text:
                        text = part_text
                        break

            if not text:
                logger.warning("analyze_video_clip_safety: respuesta vacía, fallback a frames")
                return {'success': False, 'error': 'empty_response'}

            resultado = self._parse_gemini_json_response(text.strip())
            tokens = getattr(response.usage_metadata, 'total_token_count', 0) if hasattr(response, 'usage_metadata') and response.usage_metadata else None
            logger.info(f"✅ Análisis de video completo completado (tokens: {tokens})")
            return {'success': True, 'analisis': resultado, 'tipo_analisis': 'video_completo', 'tokens_usados': tokens}

        except Exception as e:
            logger.warning(f"⚠️ Error en analyze_video_clip_safety: {e}, fallback a frames")
            return {'success': False, 'error': str(e)}

    def analyze_content_safety(self, frames_base64: List[str], descripcion: str,
                               transcripcion: str = "", duracion: float = 0,
                               contexto_workspace: str = "", metadata_workspace: dict = None) -> Dict:
        """Análisis específico de seguridad de contenido"""
        metadata_workspace = metadata_workspace or {}

        workspace_info = ""
        if contexto_workspace:
            categoria = metadata_workspace.get('categoria', 'general')
            tolerancia = metadata_workspace.get('nivel_tolerancia', 'medio')
            tipo = metadata_workspace.get('tipo_contenido', '')
            tolerancia_nota = (
                "\n⚡ TOLERANCIA ALTA: contenido intenso, deportivo o de acción es NORMAL y ESPERADO. "
                "No rechazar por contacto deportivo, esfuerzo físico o escenas de juego/competencia."
                if tolerancia == 'alto' else ""
            )
            workspace_info = f"""
CONTEXTO DEL WORKSPACE (CRÍTICO para tu decisión):
- Descripción: {contexto_workspace}
- Categoría: {categoria.upper()}
- Tolerancia de contenido: {tolerancia.upper()}
- Tipo de contenido esperado: {tipo or 'general'}{tolerancia_nota}

INSTRUCCIÓN: Si el video es RELEVANTE y APROPIADO para este workspace, apruébalo.
Ejemplo: video de fútbol en workspace de fútbol → APROBAR. Video irrelevante al contexto → considerar rechazo."""

        transcripcion_info = f'\nTranscripción de audio: "{transcripcion[:400]}"' if transcripcion else ""

        prompt = f"""Eres un moderador de contenido experto para una plataforma corporativa de videos.
Analiza estos {len(frames_base64)} frames del video y evalúa si es apropiado para publicación.

Descripción del usuario: "{descripcion[:200] if descripcion else 'Sin descripción'}"
Duración: {duracion:.0f} segundos{transcripcion_info}
{workspace_info}

Responde SOLO con este JSON (sin markdown ni texto adicional):
{{
  "contenido_apropiado": true,
  "recomendacion": "aprobar",
  "confianza": 85,
  "descripcion_contenido": "Descripción objetiva de lo que se ve en el video",
  "nivel_riesgo": "BAJO",
  "razon_recomendacion": "Explicación concisa de la decisión",
  "calidad_visual": "alta",
  "autenticidad": 90,
  "coherencia_narrativa": 85,
  "elementos_comerciales": ["logos o marcas visibles"],
  "banderas_rojas": ["elementos preocupantes si los hay"],
  "alertas_criticas": ["solo si requiere rechazo inmediato"]
}}

RECHAZA SOLO si detectas: pornografía, violencia extrema real (no deportiva), armas ilegales,
drogas ilegales, gore, discurso de odio, o menores en contexto inapropiado."""

        return self.analyze_frames(prompt, frames_base64)
    
    def validar_contexto(self, frames_base64: List[str], contexto_usuario: str) -> Dict[str, Any]:
        """Valida si un clip de video es relevante para el contexto del usuario"""
        if not self.disponible:
            return {'es_relevante': True, 'confianza': 0.0}
        
        prompt = f"""Determina si estos frames son RELEVANTES para: "{contexto_usuario}"

Responde ÚNICAMENTE con JSON:
{{
    "es_relevante": true/false,
    "confianza": 0-100,
    "razon": "Explicación breve"
}}"""

        try:
            result = self.analyze_frames(prompt, frames_base64)
            if result.get('success') and result.get('analisis'):
                analisis = result['analisis']
                return {
                    'es_relevante': analisis.get('es_relevante', True),
                    'confianza': analisis.get('confianza', 50),
                    'razon': analisis.get('razon', '')
                }
            return {'es_relevante': True, 'confianza': 30}
        except Exception as e:
            logger.error(f"Error validando contexto: {e}")
            return {'es_relevante': True, 'confianza': 0}
    
    def analizar_escena_detallada(self, frames_base64: List[str], contexto_usuario: str) -> Dict[str, Any]:
        """Analiza una escena en detalle enfocándose en el contexto del usuario"""
        if not self.disponible:
            return {'success': False, 'error': 'Gemini 3 no disponible'}
        
        prompt = f"""Analiza estos frames en DETALLE considerando: "{contexto_usuario}"

Responde con JSON detallado incluyendo:
- descripcion_detallada
- personas_detectadas
- objetos_relevantes
- acciones_observadas
- nivel_relevancia"""

        return self.analyze_frames(prompt, frames_base64)
