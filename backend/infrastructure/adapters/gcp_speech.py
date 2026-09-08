"""
Adaptador para Google Cloud Speech-to-Text y Natural Language API
Transcripción y análisis de audio de videos
"""
import os
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional
from google.cloud import speech_v1
from google.cloud import language_v1
from google.cloud import storage

logger = logging.getLogger(__name__)


class GCPSpeechAdapter:
    """
    Adaptador para Google Cloud Speech-to-Text y Natural Language API
    
    Proporciona:
    - Transcripción de audio de videos
    - Análisis de sentimiento
    - Detección de entidades
    - Detección de palabras prohibidas y patrones sospechosos
    """
    
    def __init__(self, gcp_config=None):
        """
        Inicializa el adaptador de Speech-to-Text
        
        Args:
            gcp_config: Configuración de GCP (opcional)
        """
        self.gcp_config = gcp_config
        self.available = False
        
        try:
            self.speech_client = speech_v1.SpeechClient()
            self.language_client = language_v1.LanguageServiceClient()
            self.storage_client = storage.Client()
            self.available = True
            logger.info("✅ GCP Speech-to-Text y Natural Language API inicializados")
        except Exception as e:
            logger.warning(f"⚠️ No se pudo inicializar Speech API: {str(e)}")
            self.speech_client = None
            self.language_client = None
            self.storage_client = None
    
    def is_available(self) -> bool:
        """Verifica si el servicio está disponible"""
        return self.available
    
    def _video_tiene_audio(self, video_path: str) -> bool:
        """
        Verifica si el video tiene pista de audio
        
        Args:
            video_path: Ruta del video
            
        Returns:
            True si el video tiene audio
        """
        try:
            comando = [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'a:0',
                '-show_entries', 'stream=codec_type',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ]
            
            resultado = subprocess.run(
                comando,
                capture_output=True,
                timeout=10
            )
            
            # Si hay output, significa que hay stream de audio
            return bool(resultado.stdout.strip())
            
        except Exception as e:
            logger.warning(f"⚠️ No se pudo verificar audio: {str(e)}")
            return False  # Asumir que no tiene audio si falla la verificación
    
    def _extraer_audio_de_video(self, video_path: str) -> Optional[str]:
        """
        Extrae el audio del video usando FFmpeg
        
        Args:
            video_path: Ruta del video
            
        Returns:
            Ruta del archivo de audio extraído (.flac) o None si falla
        """
        try:
            # PRIMERO: Verificar si el video tiene audio
            if not self._video_tiene_audio(video_path):
                logger.info("ℹ️  Video sin pista de audio - Saltando transcripción")
                return None
            
            # Crear archivo temporal para el audio
            temp_audio = tempfile.NamedTemporaryFile(suffix='.flac', delete=False)
            audio_path = temp_audio.name
            temp_audio.close()
            
            # Extraer audio con FFmpeg en formato FLAC (mejor para Speech-to-Text)
            comando = [
                'ffmpeg',
                '-v', 'error',  # Solo mostrar errores
                '-i', video_path,
                '-vn',  # Sin video
                '-acodec', 'flac',  # Codec FLAC
                '-ar', '16000',  # Sample rate 16kHz
                '-ac', '1',  # Mono
                '-y',  # Sobrescribir si existe
                audio_path
            ]
            
            resultado = subprocess.run(
                comando, 
                check=True, 
                capture_output=True,
                timeout=300  # OPT-07: 5 min (era 60s, insuficiente para archivos grandes)
            )
            
            # Verificar que el archivo existe y tiene contenido
            if os.path.exists(audio_path) and os.path.getsize(audio_path) > 0:
                logger.info(f"✅ Audio extraído: {os.path.getsize(audio_path)} bytes")
                return audio_path
            else:
                logger.warning("⚠️ El archivo de audio está vacío")
                return None
                
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            # Solo logear la línea del error real, no todo el output de FFmpeg
            if 'does not contain any stream' in error_msg:
                logger.info("ℹ️  Video sin pista de audio válida")
            else:
                logger.error(f"❌ Error extrayendo audio: {error_msg.split('Error')[0] if 'Error' in error_msg else error_msg[:200]}")
            return None
        except subprocess.TimeoutExpired:
            logger.error("❌ Timeout extrayendo audio del video")
            return None
        except Exception as e:
            logger.error(f"❌ Error inesperado extrayendo audio: {str(e)}")
            return None
    
    def _subir_audio_a_gcs(self, audio_path: str, video_id: str) -> Optional[str]:
        """
        Sube el audio a GCS para procesamiento
        
        Args:
            audio_path: Ruta local del audio
            video_id: ID único del video
            
        Returns:
            URI de GCS del audio o None si falla
        """
        try:
            bucket_name = os.getenv('GCP_BUCKET_NAME')
            if not bucket_name:
                logger.error("GCP_BUCKET_NAME no configurado")
                return None
            
            bucket = self.storage_client.bucket(bucket_name)
            blob_name = f"audio/{video_id}/audio.flac"
            blob = bucket.blob(blob_name)
            
            blob.upload_from_filename(audio_path)
            gcs_uri = f"gs://{bucket_name}/{blob_name}"
            
            logger.info(f"✅ Audio subido a GCS: {gcs_uri}")
            return gcs_uri
            
        except Exception as e:
            logger.error(f"❌ Error subiendo audio a GCS: {str(e)}")
            return None
    
    def transcribe_video(self, video_path: str, video_id: str, duration_hint: float = 0) -> Dict:
        """
        Transcribe el audio de un video completo
        
        Args:
            video_path: Ruta local del video
            video_id: ID único del video
            duration_hint: Duración del video en segundos (para calcular timeout dinámico)
            
        Returns:
            Dict con transcripción, sentimiento, entidades y análisis
        """
        if not self.available:
            return {
                'success': False,
                'error': 'Speech-to-Text no está disponible',
                'tiene_audio': None
            }
        
        audio_path = None
        try:
            # 1. Extraer audio del video
            logger.info(f"🎤 Extrayendo audio del video {video_id}")
            audio_path = self._extraer_audio_de_video(video_path)
            
            if not audio_path or not os.path.exists(audio_path):
                return {
                    'success': False,
                    'error': 'No se pudo extraer el audio del video',
                    'tiene_audio': False
                }
            
            # 2. Subir audio a GCS
            audio_gcs_uri = self._subir_audio_a_gcs(audio_path, video_id)
            if not audio_gcs_uri:
                return {
                    'success': False,
                    'error': 'No se pudo subir el audio a GCS',
                    'tiene_audio': True
                }
            
            # 3. Configurar Speech-to-Text
            audio = speech_v1.RecognitionAudio(uri=audio_gcs_uri)
            config = speech_v1.RecognitionConfig(
                encoding=speech_v1.RecognitionConfig.AudioEncoding.FLAC,
                sample_rate_hertz=16000,
                language_code="es-ES",
                enable_automatic_punctuation=True,
                enable_word_time_offsets=True,
                enable_word_confidence=True,
                profanity_filter=False,  # Queremos detectar groserías
                model="default",  # Modelo por defecto (compatible con todas las opciones)
                use_enhanced=True  # Mejor calidad
            )
            
            # OPT-08: timeout dinámico proporcional a la duración — mínimo 600s (10 min)
            # Regla: max(600, duration_hint × 0.17) — coherente con audio_analyzer.py
            timeout_seconds = max(600, int(duration_hint * 0.17)) if duration_hint > 0 else 600

            # 4. Transcripción (asíncrona para videos largos)
            logger.info(f"🎤 Iniciando transcripción de audio para video {video_id} (timeout: {timeout_seconds}s)")
            operation = self.speech_client.long_running_recognize(
                config=config,
                audio=audio
            )
            response = operation.result(timeout=timeout_seconds)  # OPT-08: era fijo 300s
            
            # 5. Procesar resultados
            transcripcion_completa = ""
            palabras_temporales = []
            idiomas_detectados = set()
            confianza_promedio = 0
            total_palabras = 0
            
            for result in response.results:
                alternativa = result.alternatives[0]
                transcripcion_completa += alternativa.transcript + " "
                confianza_promedio += alternativa.confidence
                
                if hasattr(result, 'language_code'):
                    idiomas_detectados.add(result.language_code)
                
                for word_info in alternativa.words:
                    palabras_temporales.append({
                        "palabra": word_info.word,
                        "inicio": word_info.start_time.total_seconds(),
                        "fin": word_info.end_time.total_seconds(),
                        "confianza": word_info.confidence
                    })
                    total_palabras += 1
            
            confianza_promedio = confianza_promedio / len(response.results) if response.results else 0
            transcripcion_completa = transcripcion_completa.strip()
            
            if not transcripcion_completa:
                logger.info("⚠️ El video tiene audio pero no se detectó voz humana")
                return {
                    'success': True,
                    'tiene_audio': True,
                    'tiene_voz': False,
                    'transcripcion': '',
                    'mensaje': 'El video tiene audio pero no se detectó voz humana'
                }
            
            # 6. Análisis de Sentimiento
            document = language_v1.Document(
                content=transcripcion_completa,
                type_=language_v1.Document.Type.PLAIN_TEXT,
                language="es"
            )
            
            sentiment_response = self.language_client.analyze_sentiment(
                request={"document": document}
            )
            sentiment = sentiment_response.document_sentiment
            
            # 7. Detección de Entidades
            entities_response = self.language_client.analyze_entities(
                request={"document": document}
            )
            
            entidades = []
            for entity in entities_response.entities[:20]:  # Top 20 entidades
                try:
                    # entity.type_ puede ser un enum o un int
                    tipo = entity.type_.name if hasattr(entity.type_, 'name') else str(entity.type_)
                    entidades.append({
                        "nombre": entity.name,
                        "tipo": tipo,
                        "relevancia": entity.salience,
                        "menciones": len(entity.mentions)
                    })
                except Exception as e:
                    logger.warning(f"Error procesando entidad: {e}")
                    continue
            
            # 8. Detectar palabras prohibidas y patrones sospechosos
            palabras_prohibidas = self._detectar_palabras_prohibidas(transcripcion_completa)
            patrones_sospechosos = self._detectar_patrones_sospechosos(transcripcion_completa)
            
            resultado = {
                'success': True,
                'tiene_audio': True,
                'tiene_voz': True,
                'transcripcion': transcripcion_completa,
                'palabras_totales': total_palabras,
                'duracion_audio': palabras_temporales[-1]['fin'] if palabras_temporales else 0,
                'idiomas_detectados': list(idiomas_detectados),
                'confianza_transcripcion': float(confianza_promedio),
                'palabras_temporales': palabras_temporales[:100],  # Primeras 100 para no saturar
                'sentimiento': {
                    'score': float(sentiment.score),  # -1.0 (negativo) a 1.0 (positivo)
                    'magnitud': float(sentiment.magnitude),  # Intensidad emocional
                    'interpretacion': self._interpretar_sentimiento(sentiment.score, sentiment.magnitude)
                },
                'entidades': entidades,
                'palabras_prohibidas': palabras_prohibidas,
                'patrones_sospechosos': patrones_sospechosos,
                'alertas': self._generar_alertas_audio(
                    transcripcion_completa, 
                    sentiment, 
                    palabras_prohibidas,
                    patrones_sospechosos
                )
            }
            
            logger.info(f"✅ Transcripción completada: {total_palabras} palabras, sentimiento: {resultado['sentimiento']['interpretacion']}")
            
            return resultado
            
        except Exception as e:
            logger.error(f"❌ Error en transcripción: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'tiene_audio': None
            }
        finally:
            # Limpiar archivo temporal
            if audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                    logger.debug(f"🗑️ Archivo temporal eliminado: {audio_path}")
                except Exception as e:
                    logger.warning(f"No se pudo eliminar archivo temporal: {str(e)}")
    
    def _detectar_palabras_prohibidas(self, texto: str) -> List[Dict]:
        """Detecta palabras prohibidas en el texto usando word boundaries para evitar falsos positivos"""
        import re

        palabras_prohibidas_lista = [
            'puta', 'puto', 'mierda', 'joder', 'coño',
            'cabrón', 'cabron', 'gilipollas', 'hijo de puta',
            'marica', 'maricón', 'maricon', 'pendejo', 'culero',
            'verga', 'chingar', 'pinche', 'mamada'
        ]

        texto_lower = texto.lower()
        encontradas = []

        for palabra in palabras_prohibidas_lista:
            # Usar \b para word boundaries; palabras multi-termino con espacio se tratan literalmente
            if ' ' in palabra:
                pattern = re.compile(re.escape(palabra), re.IGNORECASE)
            else:
                pattern = re.compile(r'\b' + re.escape(palabra) + r'\b', re.IGNORECASE)
            matches = pattern.findall(texto_lower)
            if matches:
                encontradas.append({
                    'palabra': palabra,
                    'ocurrencias': len(matches)
                })

        return encontradas
    
    def _detectar_patrones_sospechosos(self, texto: str) -> List[Dict]:
        """Detecta patrones sospechosos como URLs, emails, teléfonos"""
        import re
        
        patrones = {
            'urls': r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
            'emails': r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            'telefonos': r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}',
            'menciones_dinero': r'\$\d+|\d+\s*(dolares|dólares|euros|pesos|USD|EUR)',
            'palabras_spam': r'\b(compra|vende|gratis|descuento|oferta|promoción|promocion|gana dinero|haz clic|suscríbete|suscribete)\b'
        }
        
        detectados = []
        
        for tipo, patron in patrones.items():
            matches = re.findall(patron, texto, re.IGNORECASE)
            if matches:
                detectados.append({
                    'tipo': tipo,
                    'coincidencias': matches[:5]  # Máximo 5 ejemplos
                })
        
        return detectados
    
    def _interpretar_sentimiento(self, score: float, magnitud: float) -> str:
        """Interpreta el sentimiento del texto"""
        if magnitud < 0.5:
            return "neutral"
        elif score > 0.25:
            return "positivo" if magnitud > 2.0 else "ligeramente_positivo"
        elif score < -0.25:
            return "negativo" if magnitud > 2.0 else "ligeramente_negativo"
        else:
            return "mixto"
    
    def _generar_alertas_audio(self, transcripcion: str, sentiment, 
                               palabras_prohibidas: List[Dict], 
                               patrones_sospechosos: List[Dict]) -> List[Dict]:
        """Genera alertas basadas en el análisis de audio"""
        alertas = []
        
        # Alertas por palabras prohibidas
        if palabras_prohibidas:
            total_groserias = sum(p['ocurrencias'] for p in palabras_prohibidas)
            if total_groserias > 5:
                alertas.append({
                    'nivel': 'critico',
                    'tipo': 'lenguaje_ofensivo',
                    'mensaje': f'Se detectaron {total_groserias} palabras ofensivas'
                })
            elif total_groserias > 0:
                alertas.append({
                    'nivel': 'medio',
                    'tipo': 'lenguaje_inapropiado',
                    'mensaje': f'Se detectaron {total_groserias} palabras inapropiadas'
                })
        
        # Alertas por sentimiento muy negativo
        if sentiment.score < -0.5 and sentiment.magnitude > 2.0:
            alertas.append({
                'nivel': 'medio',
                'tipo': 'sentimiento_negativo',
                'mensaje': 'El contenido tiene un tono muy negativo o agresivo'
            })
        
        # Alertas por patrones sospechosos
        for patron in patrones_sospechosos:
            if patron['tipo'] == 'urls':
                alertas.append({
                    'nivel': 'alto',
                    'tipo': 'enlaces_externos',
                    'mensaje': f"Se detectaron {len(patron['coincidencias'])} URLs en el audio"
                })
            elif patron['tipo'] == 'telefonos' or patron['tipo'] == 'emails':
                alertas.append({
                    'nivel': 'alto',
                    'tipo': 'informacion_contacto',
                    'mensaje': f"Se mencionó información de contacto ({patron['tipo']})"
                })
            elif patron['tipo'] == 'menciones_dinero':
                alertas.append({
                    'nivel': 'medio',
                    'tipo': 'contenido_comercial',
                    'mensaje': 'Se detectaron menciones de dinero/precios'
                })
            elif patron['tipo'] == 'palabras_spam':
                alertas.append({
                    'nivel': 'alto',
                    'tipo': 'posible_spam',
                    'mensaje': 'Se detectaron palabras típicas de contenido spam'
                })
        
        return alertas
