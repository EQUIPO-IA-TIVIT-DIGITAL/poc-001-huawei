import json
import logging
import re
from pathlib import Path
from typing import Dict, Any

from domain.entities import Video, EstadoVideo

logger = logging.getLogger(__name__)

class VideoDecider:
    """Paso 5: Decisión Final + Título Generado + Guardar"""

    def __init__(self, gemini_adapter, blacklist_config: Dict[str, Any], umbral_confianza: float = 0.65):
        self.gemini = gemini_adapter
        self.blacklist_config = blacklist_config
        self.umbral_confianza = umbral_confianza

    def decide(self, video: Video, contexto_analisis: Dict[str, Any]) -> Dict[str, Any]:
        """Toma la decisión final basada en el análisis previo."""
        
        metadata_workspace = contexto_analisis.get("metadata_workspace", {})
        es_exhaustivo = metadata_workspace.get("es_exhaustivo", False)
        
        # Obtener GCS URI del video (necesario para Vertex AI)
        storage_uri = video.metadatos_ia.get("storage_uri")
        video_path = storage_uri if storage_uri else video.ruta_archivo
        
        decision_final = None
        if es_exhaustivo:
            logger.info("🛡️ MODO EXHAUSTIVO ACTIVO: Escalando Nivel 2 directo (File API)...")
            decision_final = self._analizar_con_file_api(video_path, contexto_analisis)
            if decision_final is None or decision_final.get("confianza", 0) <= 0.5:
                logger.warning("⚠️ Nivel 2 exhaustivo falló, aplicando Nivel 1.")
                decision_final = self._tomar_decision_con_gemini(contexto_analisis)
        else:
            decision_final = self._tomar_decision_con_gemini(contexto_analisis)
            
            confianza_decisor = decision_final.get("confianza", 0.5)
            parsed_from_freetext = "parsed_from_freetext" in decision_final.get("factores_decision", [])
            
            if confianza_decisor < 0.70 or parsed_from_freetext:
                logger.warning(f"⚠️ Decisor Nivel 1 con confianza media/baja ({confianza_decisor:.0%}) o freetext. Escalando a Nivel 2 (File API)...")
                decision_file_api = self._analizar_con_file_api(video_path, contexto_analisis)
                if decision_file_api and decision_file_api.get("confianza", 0) > confianza_decisor:
                    decision_final = decision_file_api
                    logger.info(f"✅ Usando Nivel 2 File API como decisión final (confianza: {decision_final.get('confianza'):.0%})")
                elif confianza_decisor <= 0.5 or parsed_from_freetext:
                    logger.warning("⚠️ Nivel 2 falló o no mejoró, usando fallback vision")
                    vision_decision = self._analisis_fallback_vision(contexto_analisis)
                    if vision_decision.get("confianza", 0) > confianza_decisor:
                        decision_final = vision_decision
                        logger.info(f"✅ Usando Vision como decisión final (confianza: {decision_final.get('confianza'):.0%})")

        video.agregar_metadatos("decision_gemini", decision_final)
        video.agregar_metadatos("analisis_ia", decision_final.get("analisis", ""))
        video.agregar_metadatos("razon_decision", decision_final.get("razon", ""))

        titulo_generado = self._generar_titulo_automatico(video, contexto_analisis, decision_final)
        video.agregar_metadatos("titulo", titulo_generado)
        video.descripcion = titulo_generado

        confianza = decision_final.get("confianza", 0.5)
        video.agregar_metadatos("confianza_ia", confianza)

        if confianza >= self.umbral_confianza:
            if decision_final.get("aprobado"):
                video.agregar_metadatos("resultado_ia", "APROBADO")
                if video.estado not in [EstadoVideo.APROBADO, EstadoVideo.RECHAZADO, EstadoVideo.COMPLETADO]:
                    video.actualizar_estado(EstadoVideo.APROBADO)
            else:
                video.agregar_metadatos("resultado_ia", "RECHAZADO")
                if video.estado not in [EstadoVideo.APROBADO, EstadoVideo.RECHAZADO, EstadoVideo.COMPLETADO]:
                    video.actualizar_estado(EstadoVideo.RECHAZADO)
                razon = decision_final.get("razon", "Rechazado por IA")
                video.agregar_metadatos("razon_rechazo", razon)
        else:
            video.agregar_metadatos("resultado_ia", "REQUIERE_REVISION")
            if video.estado not in [EstadoVideo.EN_REVISION, EstadoVideo.APROBADO, EstadoVideo.RECHAZADO, EstadoVideo.COMPLETADO]:
                video.actualizar_estado(EstadoVideo.EN_REVISION)

        return {
            "decision_final": decision_final,
            "confianza": confianza,
            "titulo": titulo_generado
        }

    def _tomar_decision_con_gemini(self, contexto: Dict[str, Any]) -> Dict[str, Any]:
        try:
            logos_prohibidos = self.blacklist_config.get("logos_competidores", [])
            palabras_prohibidas = self.blacklist_config.get("palabras_prohibidas", [])
            categorias_prohibidas = self.blacklist_config.get("categorias_prohibidas", {})

            prompt = self._construir_prompt_decisor(
                contexto=contexto,
                logos_prohibidos=logos_prohibidos,
                palabras_prohibidas=palabras_prohibidas,
                categorias_prohibidas=categorias_prohibidas
            )

            if not self.gemini or not self.gemini.is_available():
                return self._analisis_fallback_vision(contexto)

            system_prompt = """Eres el moderador de contenido de AccessFan, plataforma de videos UGC para TIVIT Latam.

Tu rol es tomar la DECISIÓN FINAL sobre si un video debe ser aprobado o rechazado. Reponde EXCLUSIVAMENTE en JSON puro con las siguientes claves requeridas: aprobado (boolean), razon (string), confianza (number 0.0 a 1.0), analisis (string), factores_decision (array string), relevante_al_workspace (boolean).

FUENTES DE ANÁLISIS:
1. **Gemini Vision** (FUENTE PRINCIPAL - analiza frames reales con IA multimodal)
2. **Speech-to-Text + NLP** (análisis de audio, sentimiento, lenguaje)
3. **Contexto del Workspace** (categoría, tolerancia, tipo de contenido esperado)

REGLAS CRÍTICAS DE DECISIÓN:
- ⚡ El CONTEXTO DEL WORKSPACE es OBLIGATORIO para decidir. Si el workspace define un dominio (ej: fútbol) y el video es de ESE dominio → APROBAR con alta confianza
- ⚡ Si el workspace tiene TOLERANCIA ALTA y el video muestra contenido intenso pero DENTRO del dominio → APROBAR
- ⚡ Un video de fútbol en un workspace de fútbol SIEMPRE debe ser APROBADO (contacto deportivo normal)
- Gemini Vision es la fuente MÁS CONFIABLE para contenido visual
- Si detecta contenido explícito OBVIO (pornografía, violencia extrema real) → RECHAZAR independiente del contexto
- La descripción del usuario NO ES CONFIABLE, verificar con análisis técnicos
- Logos solo rechazar si están en la blacklist exacta
- PROTECCIÓN INFANTIL: Cualquier indicio de menores en contexto inapropiado = RECHAZO AUTOMÁTICO
- Si el video NO TIENE RELACIÓN con el workspace → RECHAZAR por "contenido fuera de contexto"

FLUJO DE DECISIÓN:
1. ¿El video contiene contenido explícito REAL (no deportivo/contextual)? → RECHAZAR
2. ¿El video es RELEVANTE al contexto del workspace? → Si NO → RECHAZAR
3. ¿El contenido es apropiado DENTRO del contexto? → Evaluar con tolerancia del workspace
4. Si hay duda → Mantener baja confianza para revisión manual
"""

            full_prompt = f"{system_prompt}\\n\\n{prompt}"

            text = self.gemini.chat(
                [{"role": "user", "content": full_prompt}],
                json_mode=True,
                temperature=0.1,
                max_tokens=2048,
            )
            if not text:
                logger.warning("Decisor Gemini devolvió respuesta vacía, usando fallback")
                return self._analisis_fallback_vision(contexto)
            return self._parsear_respuesta_gemini(text)

        except Exception as e:
            logger.warning(f"Error en Gemini decisor: {e}")
            logger.info("🔄 Usando fallback inteligente basado en Gemini Vision")
            return self._analisis_fallback_vision(contexto)

    def _analizar_con_file_api(self, video_path: str, contexto: Dict[str, Any]) -> Dict[str, Any]:
        """Nivel 2: Sube el video completo a Gemini File API"""
        try:
            logos_prohibidos = self.blacklist_config.get("logos_competidores", [])
            palabras_prohibidas = self.blacklist_config.get("palabras_prohibidas", [])
            categorias_prohibidas = self.blacklist_config.get("categorias_prohibidas", {})
            
            prompt = self._construir_prompt_decisor(
                contexto=contexto,
                logos_prohibidos=logos_prohibidos,
                palabras_prohibidas=palabras_prohibidas,
                categorias_prohibidas=categorias_prohibidas
            )
            
            system_prompt = "Eres el moderador de contenido de AccessFan, plataforma de videos UGC para TIVIT Latam. Tu rol es tomar la DECISIÓN FINAL sobre si un video debe ser aprobado o rechazado. Reponde EXCLUSIVAMENTE en JSON puro con las siguientes claves requeridas: aprobado (boolean), razon (string), confianza (number 0.0 a 1.0), analisis (string), factores_decision (array string), relevante_al_workspace (boolean)."
            
            full_prompt = f"{system_prompt}\n\n{prompt}"
            
            if not self.gemini or not hasattr(self.gemini, 'analyze_video_clip'):
                return None
                
            logger.info("🎬 Iniciando subida de video a Gemini File API para Análisis Nivel 2...")
            result = self.gemini.analyze_video_clip(video_path, full_prompt)
            
            if result and result.get("success"):
                analisis_ia = result.get("analisis", {})
                return {
                    "aprobado": analisis_ia.get("aprobado", False),
                    "razon": analisis_ia.get("razon", "Análisis File API completado"),
                    "analisis": analisis_ia.get("analisis", "Análisis File API completado"),
                    "confianza": float(analisis_ia.get("confianza", 0.9)),
                    "factores_decision": analisis_ia.get("factores_decision", ["file_api_nivel_2"]),
                    "relevante_al_workspace": analisis_ia.get("relevante_al_workspace", True)
                }
            
            return None
        except Exception as e:
            logger.error(f"Error en Nivel 2 File API: {e}")
            return None

    def _analisis_fallback_vision(self, contexto: Dict[str, Any]) -> Dict[str, Any]:
        gemini_vision = contexto.get("gemini_vision")
        
        if gemini_vision:
            recomendacion = str(gemini_vision.get("recomendacion", "")).lower().strip()
            confianza_vision = gemini_vision.get("confianza", 50)
            contenido_apropiado = gemini_vision.get("contenido_apropiado", None)
            razon = gemini_vision.get("razon_recomendacion", "Decisión basada en análisis visual")
            descripcion = gemini_vision.get("descripcion_contenido", "")
            banderas = gemini_vision.get("banderas_rojas", [])
            alertas = gemini_vision.get("alertas_criticas", [])
            relevante_al_workspace = gemini_vision.get("relevante_al_workspace", None)

            confianza_normalizada = confianza_vision / 100.0 if confianza_vision > 1 else confianza_vision

            # Si Gemini Vision determinó que el video no es relevante al workspace → rechazar
            if relevante_al_workspace is False:
                logger.info("🚫 Fallback Vision: video no relevante al workspace → RECHAZAR")
                return {
                    "aprobado": False,
                    "razon": razon or "Contenido no relevante al contexto del workspace",
                    "analisis": f"Fallback Vision. {descripcion}",
                    "confianza": max(confianza_normalizada, 0.75),
                    "factores_decision": ["fallback_vision", "workspace_irrelevante"],
                }

            if alertas:
                return {
                    "aprobado": False,
                    "razon": f"Alertas críticas: {', '.join(alertas[:3])}",
                    "analisis": f"Fallback Vision. {descripcion}",
                    "confianza": max(confianza_normalizada, 0.85),
                    "factores_decision": ["alertas_criticas", "fallback_vision"] + alertas[:3],
                }
            
            if recomendacion in ("aprobar", "aprobado", "approve"):
                aprobado = True
            elif recomendacion in ("rechazar", "rechazado", "reject"):
                aprobado = False
            elif contenido_apropiado is not None:
                aprobado = bool(contenido_apropiado)
            else:
                aprobado = confianza_normalizada >= 0.6
            
            if banderas:
                confianza_normalizada = min(confianza_normalizada, 0.70)
            
            if confianza_normalizada >= 0.75:
                confianza_final = confianza_normalizada
            elif recomendacion in ("aprobar", "aprobado", "rechazar", "rechazado"):
                confianza_final = max(confianza_normalizada, 0.80)
            else:
                confianza_final = max(confianza_normalizada, 0.65)
            
            return {
                "aprobado": aprobado,
                "razon": razon,
                "analisis": f"Fallback Vision (decisor no disponible). {descripcion}",
                "confianza": confianza_final,
                "factores_decision": ["fallback_vision", f"vision_{recomendacion}", f"confianza_{confianza_vision}%"],
            }
        
        return self._analisis_fallback_local(contexto)

    def _analisis_fallback_local(self, contexto: Dict[str, Any]) -> Dict[str, Any]:
        razones_rechazo = []
        palabras_prohibidas = self.blacklist_config.get("palabras_prohibidas", [])
        texto = contexto.get("descripcion_usuario", "").lower()
        for palabra in palabras_prohibidas:
            if palabra.lower() in texto:
                razones_rechazo.append(f"Palabra prohibida: {palabra}")
                break
        if razones_rechazo:
            return {
                "aprobado": False,
                "razon": razones_rechazo[0],
                "analisis": f"Fallback local. Problemas: {'; '.join(razones_rechazo)}",
                "confianza": 0.7,
                "factores_decision": razones_rechazo,
            }
        return {
            "aprobado": True,
            "razon": "Contenido apropiado (análisis local)",
            "analisis": "Fallback local, sin problemas detectados.",
            "confianza": 0.6,
            "factores_decision": ["sin_problemas"],
        }

    def _construir_prompt_decisor(self, contexto, logos_prohibidos, palabras_prohibidas, categorias_prohibidas):
        gemini_info = "No disponible"
        if contexto.get("gemini_vision"):
            gv = contexto["gemini_vision"]
            gemini_info = f"""
🎨 ANÁLISIS VISUAL (Gemini Vision - FUENTE PRINCIPAL):
- Contenido apropiado: {gv.get("contenido_apropiado", "N/A")}
- Calidad visual: {gv.get("calidad_visual", "N/A")}
- Autenticidad: {gv.get("autenticidad", "N/A")}%
- Coherencia narrativa: {gv.get("coherencia_narrativa", "N/A")}%
- Descripción: {gv.get("descripcion_contenido", "N/A")}
- Elementos comerciales: {", ".join(gv.get("elementos_comerciales", [])) or "Ninguno"}
- Banderas rojas: {", ".join(gv.get("banderas_rojas", [])) or "Ninguna"}
- Alertas críticas: {", ".join(gv.get("alertas_criticas", [])) or "Ninguna"}
- Recomendación: {gv.get("recomendacion", "N/A")}
- Razón: {gv.get("razon_recomendacion", "N/A")}
- Confianza visual: {gv.get("confianza", "N/A")}%"""

        speech_info = "No disponible"
        if contexto.get("speech_analysis"):
            sp = contexto["speech_analysis"]
            if sp.get("tiene_voz"):
                transcripcion = sp.get("transcripcion", "")[:500]
                sentimiento = sp.get("sentimiento", {})
                alertas = sp.get("alertas", [])
                speech_info = f"""
🎤 ANÁLISIS DE AUDIO:
- Transcripción: "{transcripcion}{'...' if len(sp.get('transcripcion', '')) > 500 else ''}"
- Sentimiento: {sentimiento.get("interpretacion", "N/A")}
- Palabras ofensivas: {len(sp.get("palabras_prohibidas", []))}
- Alertas: {len(alertas)} ({", ".join([a.get("tipo", "?") for a in alertas[:3]]) if alertas else "ninguna"})"""
            elif sp.get("skip_reason"):
                speech_info = f"🎤 AUDIO: {sp['skip_reason']}"
            else:
                speech_info = "🎤 AUDIO: Sin voz humana detectada"

        contexto_enfasis = ""
        if contexto.get("contexto_usuario"):
            metadata_ws = contexto.get("metadata_workspace", {})
            cat = metadata_ws.get('categoria', 'general')
            tol = metadata_ws.get('nivel_tolerancia', 'medio')
            contexto_enfasis = f"""
🎯 ATENCIÓN: Considerar contexto del workspace MUY FUERTEMENTE.
Categoría: {cat.upper()} | Tolerancia: {tol.upper()}
{"TOLERANCIA ALTA: contenido intenso/deportivo esperado, NO ser excesivamente estricto falso-positivo." if tol == 'alto' else ""}
"""

        return f"""Analiza este video y toma la DECISIÓN FINAL:
{contexto_enfasis}
📁 ARCHIVO: {contexto.get("nombre_archivo", "video")}
👤 USUARIO: {contexto.get("usuario", "Desconocido")}
📝 DESCRIPCIÓN DEL USUARIO: "{contexto.get("descripcion_usuario", "Sin descripción")}"
⏱️ DURACIÓN: {contexto.get("duracion_segundos", "N/A")}s

🎯🎯🎯 CONTEXTO DEL WORKSPACE (OBLIGATORIO PARA LA DECISIÓN):
"{contexto.get("contexto_usuario", "No proporcionado")}"
- Categoría: {contexto.get("metadata_workspace", {}).get("categoria", "N/A")}
- Tolerancia: {contexto.get("metadata_workspace", {}).get("nivel_tolerancia", "N/A")}
- Tipo contenido esperado: {contexto.get("metadata_workspace", {}).get("tipo_contenido", "N/A")}

⚠️ INSTRUCCIÓN CRÍTICA: Tu decisión DEBE basarse en si el video es RELEVANTE y APROPIADO 
para este workspace. Si el video muestra contenido que COINCIDE con el contexto del workspace 
(ej: videos de fútbol en un workspace de fútbol), debe ser APROBADO con alta confianza.
Solo rechazar si: (1) contenido explícito real, (2) no tiene relación con el workspace, 
(3) protección infantil.

{gemini_info}

{speech_info}

📛 LOGOS PROHIBIDOS: {", ".join(logos_prohibidos[:15]) or "Ninguno"}
📛 PALABRAS PROHIBIDAS: {", ".join(palabras_prohibidas[:20]) or "Ninguna"}

CONSIDERACIONES FINALES:
- Gemini Vision es la fuente PRINCIPAL y MÁS CONFIABLE
- Contexto del workspace DEFINE la tolerancia y relevancia
- Eventos sociales, deportivos y corporativos son contenido VÁLIDO si coinciden con el workspace
- Si el análisis visual indica "aprobar" con alta confianza Y el contenido es relevante al workspace → APROBAR con confianza >= 0.85
"""

    def _parsear_respuesta_gemini(self, content: str) -> Dict[str, Any]:
        """Extrae el JSON de la respuesta de Gemini."""
        if not content:
            return {
                "aprobado": False,
                "razon": "Respuesta vacía del modelo",
                "analisis": "Sin análisis disponible",
                "confianza": 0.0,
                "factores_decision": ["empty_response"],
                "relevante_al_workspace": False
            }
        try:
            # Limpiar markdown si existe (por si el modelo lo añade)
            content = content.strip()
            if content.startswith('```'):
                match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
                if match:
                    content = match.group(1).strip()
            # Buscar primer objeto JSON válido
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group(0)

            resultado = json.loads(content)
            
            if resultado.get("needs_clarification"):
                return {
                    "needs_clarification": True,
                    "aprobado": None,
                    "razon": "Se requiere clarificación",
                    "analisis": "Esperando respuestas",
                    "confianza": 0.0,
                    "factores_decision": [],
                    "relevante_al_workspace": False
                }
            
            return {
                "aprobado": resultado.get("aprobado", False),
                "razon": resultado.get("razon", "Análisis completado"),
                "analisis": resultado.get("analisis", "Análisis completado"),
                "confianza": float(resultado.get("confianza", 0.8)),
                "factores_decision": resultado.get("factores_decision", []),
                "relevante_al_workspace": resultado.get("relevante_al_workspace", True)
            }
            
        except json.JSONDecodeError as e:
            logger.error(f"Error decodificando Structured Output JSON de Gemini: {e}")
            logger.error(f"Contenido problemático: {content}")
            return {
                "aprobado": False,
                "razon": "Error en parseo de respuesta IA",
                "analisis": "El modelo no respetó el esquema JSON.",
                "confianza": 0.0,
                "factores_decision": ["json_decode_error"],
                "relevante_al_workspace": False
            }

    def _generar_titulo_automatico(self, video, contexto, decision):
        try:
            nombre_archivo = contexto.get("nombre_archivo", "video")
            nombre_base = Path(nombre_archivo).stem
            nombre_limpio = re.sub(r"^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\.?", "", nombre_base)
            if not nombre_limpio:
                nombre_limpio = nombre_base
            etiquetas = contexto.get("etiquetas", [])[:5]
            if not self.gemini or not self.gemini.is_available():
                return self._generar_titulo_fallback(nombre_limpio, etiquetas)
            prompt = f"""Genera un título corto y descriptivo (máx 60 chars) para un video.
Nombre: {nombre_limpio} | Etiquetas: {', '.join(etiquetas) or 'N/A'} | Duración: {contexto.get('duracion_segundos', 'N/A')}s
Reglas: conciso, sin emojis, en español, sin extensión. Responde SOLO el título."""
            try:
                titulo = self.gemini.chat(
                    [{"role": "user", "content": prompt}],
                    temperature=0.2,
                    max_tokens=256,
                ).strip().strip("\"'")
                return titulo[:80] if len(titulo) > 80 else titulo
            except Exception:
                return self._generar_titulo_fallback(nombre_limpio, etiquetas)
        except Exception:
            return self._generar_titulo_fallback("video", [])

    def _generar_titulo_fallback(self, nombre_archivo, etiquetas):
        if not re.match(r"^[a-f0-9]{8}-[a-f0-9]{4}-", nombre_archivo):
            titulo = nombre_archivo.replace("_", " ").replace("-", " ")
            titulo = " ".join(word.capitalize() for word in titulo.split())
            return titulo[:60]
        if etiquetas:
            return f"Video: {', '.join(etiquetas[:3])}"
        from datetime import datetime
        return f"Video {datetime.now().strftime('%d/%m/%Y %H:%M')}"
