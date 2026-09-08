"""
Adaptador de Video Intelligence API para AccessFan
Maneja el análisis de videos usando Google Cloud Video Intelligence
"""
from typing import Optional, List, Dict, Any
from google.cloud import videointelligence_v1 as videointelligence
from google.cloud.videointelligence_v1 import Feature

from config.gcp_config import GCPConfig


import logging
logger = logging.getLogger(__name__)

class VideoIntelligenceAdapter:
    """
    Adaptador para Google Cloud Video Intelligence API
    
    Funcionalidades:
    - Detección de logos (marcas)
    - Detección de texto en video (OCR)
    - Análisis de contenido explícito
    - Detección de etiquetas
    """
    
    def __init__(self, config: GCPConfig = None):
        """
        Inicializa el adaptador de Video Intelligence
        
        Args:
            config: Configuración GCP (usa default si no se proporciona)
        """
        self.config = config or GCPConfig()
        self.client = None
        
        if self.config.is_gcp_enabled():
            self._initialize_client()
    
    def _initialize_client(self):
        """Inicializa el cliente de Video Intelligence"""
        try:
            import os
            
            self.client = videointelligence.VideoIntelligenceServiceClient()
            logger.info("Video Intelligence API inicializada")
        except Exception as e:
            logger.warning(f"Error inicializando Video Intelligence: {e}")
            self.client = None
    
    def is_available(self) -> bool:
        """Verifica si Video Intelligence está disponible"""
        return self.client is not None
    
    def analyze_video(
        self, 
        gcs_uri: str,
        features: List[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Analiza un video completo con múltiples features
        
        Args:
            gcs_uri: URI del video en Cloud Storage (gs://bucket/path)
            features: Lista de features a analizar
                     ['LOGO_RECOGNITION', 'TEXT_DETECTION', 'EXPLICIT_CONTENT_DETECTION']
            
        Returns:
            dict: Resultados del análisis o None si falla
        """
        if not self.is_available():
            logger.warning(" Video Intelligence no está disponible")
            return None
        
        try:
            # Features por defecto
            if features is None:
                features = ['LOGO_RECOGNITION', 'TEXT_DETECTION']
            
            # Convertir features a enums
            feature_enums = []
            feature_map = {
                'LOGO_RECOGNITION': Feature.LOGO_RECOGNITION,
                'TEXT_DETECTION': Feature.TEXT_DETECTION,
                'EXPLICIT_CONTENT_DETECTION': Feature.EXPLICIT_CONTENT_DETECTION,
                'LABEL_DETECTION': Feature.LABEL_DETECTION,
                'OBJECT_TRACKING': Feature.OBJECT_TRACKING,
                'SHOT_CHANGE_DETECTION': Feature.SHOT_CHANGE_DETECTION,
                'PERSON_DETECTION': Feature.PERSON_DETECTION,
                'FACE_DETECTION': Feature.FACE_DETECTION
            }
            
            for feature in features:
                if feature in feature_map:
                    feature_enums.append(feature_map[feature])
            
            logger.debug(f"Analizando video: {gcs_uri}")
            logger.info(f"   Features: {', '.join(features)}")
            
            # Iniciar análisis (operación asíncrona)
            operation = self.client.annotate_video(
                request={
                    "features": feature_enums,
                    "input_uri": gcs_uri,
                }
            )
            
            logger.debug("Esperando resultado del análisis de Video Intelligence API...")
            logger.info(f"   Esto puede tomar entre 30 segundos y varios minutos dependiendo del video.")
            logger.info(f"   Operación iniciada: {operation.operation.name}")
            
            import time
            start_time = time.time()
            try:
                result = operation.result(timeout=600)  # 10 minutos timeout
                elapsed = time.time() - start_time
                logger.info(f"Análisis completado en {elapsed:.1f} segundos")
            except Exception as timeout_error:
                elapsed = time.time() - start_time
                logger.error(f"Timeout después de {elapsed:.1f} segundos: {timeout_error}")
                raise
            
            # Procesar resultados
            analysis_result = {
                'gcs_uri': gcs_uri,
                'logos': [],
                'text': [],
                'explicit_content': None,
                'labels': [],
                'shots': [],
                'persons': {},
                'faces': {},
                'objects': []
            }
            
            # Obtener primer resultado
            annotation_result = result.annotation_results[0]
            
            # Procesar detección de logos
            if 'LOGO_RECOGNITION' in features:
                analysis_result['logos'] = self._process_logo_annotations(
                    annotation_result.logo_recognition_annotations
                )
            
            # Procesar detección de texto
            if 'TEXT_DETECTION' in features:
                analysis_result['text'] = self._process_text_annotations(
                    annotation_result.text_annotations
                )
            
            # Procesar contenido explícito
            if 'EXPLICIT_CONTENT_DETECTION' in features:
                analysis_result['explicit_content'] = self._process_explicit_content(
                    annotation_result.explicit_annotation
                )
            
            # Procesar etiquetas
            if 'LABEL_DETECTION' in features:
                analysis_result['labels'] = self._process_label_annotations(
                    annotation_result.segment_label_annotations
                )
            
            # Procesar cambios de escena (shots)
            if 'SHOT_CHANGE_DETECTION' in features:
                analysis_result['shots'] = self._process_shot_annotations(
                    annotation_result.shot_annotations
                )
            
            # Procesar detección de personas
            if 'PERSON_DETECTION' in features:
                analysis_result['persons'] = self._process_person_detection(
                    annotation_result.person_detection_annotations
                )
            
            # Procesar detección de rostros
            if 'FACE_DETECTION' in features:
                analysis_result['faces'] = self._process_face_detection(
                    annotation_result.face_detection_annotations
                )
            
            # Procesar seguimiento de objetos
            if 'OBJECT_TRACKING' in features:
                analysis_result['objects'] = self._process_object_tracking(
                    annotation_result.object_annotations
                )
            
            logger.info("Análisis completado")
            return analysis_result
            
        except Exception as e:
            logger.error(f"Error analizando video: {e}")
            return None
    
    def detect_logos(self, gcs_uri: str) -> List[Dict[str, Any]]:
        """
        Detecta logos/marcas en un video
        
        Args:
            gcs_uri: URI del video en Cloud Storage
            
        Returns:
            List[dict]: Lista de logos detectados con timestamps
        """
        if not self.is_available():
            return []
        
        try:
            operation = self.client.annotate_video(
                request={
                    "features": [Feature.LOGO_RECOGNITION],
                    "input_uri": gcs_uri,
                }
            )
            
            result = operation.result(timeout=600)
            annotation_result = result.annotation_results[0]
            
            return self._process_logo_annotations(
                annotation_result.logo_recognition_annotations
            )
            
        except Exception as e:
            logger.error(f"Error detectando logos: {e}")
            return []
    
    def detect_text(self, gcs_uri: str) -> List[str]:
        """
        Detecta texto en un video (OCR)
        
        Args:
            gcs_uri: URI del video en Cloud Storage
            
        Returns:
            List[str]: Lista de textos detectados (únicos)
        """
        if not self.is_available():
            return []
        
        try:
            operation = self.client.annotate_video(
                request={
                    "features": [Feature.TEXT_DETECTION],
                    "input_uri": gcs_uri,
                }
            )
            
            result = operation.result(timeout=600)
            annotation_result = result.annotation_results[0]
            
            text_list = self._process_text_annotations(
                annotation_result.text_annotations
            )
            
            # Retornar solo textos únicos
            return list(set(text_list))
            
        except Exception as e:
            logger.error(f"Error detectando texto: {e}")
            return []
    
    def check_explicit_content(self, gcs_uri: str) -> Optional[Dict[str, Any]]:
        """
        Verifica contenido explícito en el video
        
        Args:
            gcs_uri: URI del video en Cloud Storage
            
        Returns:
            dict: Información sobre contenido explícito
        """
        if not self.is_available():
            return None
        
        try:
            operation = self.client.annotate_video(
                request={
                    "features": [Feature.EXPLICIT_CONTENT_DETECTION],
                    "input_uri": gcs_uri,
                }
            )
            
            result = operation.result(timeout=600)
            annotation_result = result.annotation_results[0]
            
            return self._process_explicit_content(
                annotation_result.explicit_annotation
            )
            
        except Exception as e:
            logger.error(f"Error verificando contenido explícito: {e}")
            return None
    
    # ==================== PROCESADORES ====================
    
    def _process_logo_annotations(self, logo_annotations) -> List[Dict[str, Any]]:
        """Procesa anotaciones de logos con timestamps formateados"""
        logos = []
        
        for annotation in logo_annotations:
            logo_info = {
                'description': annotation.entity.description,
                'confidence': 0.0,
                'segments': [],
                'timestamps_formatted': []  # Timestamps legibles para el usuario
            }
            
            # Procesar cada aparición del logo
            for track in annotation.tracks:
                confidence = track.confidence
                logo_info['confidence'] = max(logo_info['confidence'], confidence)
                
                # Timestamps - usando timestamped_objects si segments no está disponible
                segments_list = getattr(track, 'segments', None) or getattr(track, 'timestamped_objects', [])
                for segment in segments_list:
                    segment_data = getattr(segment, 'segment', segment)
                    start_offset = getattr(segment_data, 'start_time_offset', None)
                    end_offset = getattr(segment_data, 'end_time_offset', None)
                    if not start_offset or not end_offset:
                        continue
                    start_time = start_offset.seconds + start_offset.microseconds / 1e6
                    end_time = end_offset.seconds + end_offset.microseconds / 1e6
                    
                    logo_info['segments'].append({
                        'start_time': start_time,
                        'end_time': end_time,
                        'start_formatted': self._format_timestamp(start_time),
                        'end_formatted': self._format_timestamp(end_time),
                        'confidence': confidence
                    })
                    logo_info['timestamps_formatted'].append(
                        f"{self._format_timestamp(start_time)} - {self._format_timestamp(end_time)}"
                    )
            
            logos.append(logo_info)
        
        return logos
    
    def _process_text_annotations(self, text_annotations, include_timestamps: bool = False) -> List:
        """Procesa anotaciones de texto con timestamps opcionales"""
        detected_texts = []
        
        for annotation in text_annotations:
            text = annotation.text
            if text and text.strip():
                if include_timestamps:
                    # Obtener timestamps de los segmentos
                    segments = []
                    for text_segment in annotation.segments:
                        segment = text_segment.segment
                        start_time = segment.start_time_offset.seconds + segment.start_time_offset.microseconds / 1e6
                        end_time = segment.end_time_offset.seconds + segment.end_time_offset.microseconds / 1e6
                        segments.append({
                            'start_time': start_time,
                            'end_time': end_time,
                            'start_formatted': self._format_timestamp(start_time),
                            'end_formatted': self._format_timestamp(end_time)
                        })
                    detected_texts.append({
                        'text': text.strip(),
                        'segments': segments
                    })
                else:
                    detected_texts.append(text.strip())
        
        return detected_texts
    
    def _format_timestamp(self, seconds: float) -> str:
        """Formatea segundos a MM:SS"""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins:02d}:{secs:02d}"
    
    def _process_explicit_content(self, explicit_annotation) -> Dict[str, Any]:
        """Procesa anotaciones de contenido explícito con timestamps detallados"""
        if not explicit_annotation:
            return None
        
        # Likelihood levels: UNKNOWN, VERY_UNLIKELY, UNLIKELY, POSSIBLE, LIKELY, VERY_LIKELY
        frames_data = []
        problematic_frames = []  # Frames con contenido problemático
        max_likelihood = "UNKNOWN"
        
        for frame in explicit_annotation.frames:
            likelihood = frame.pornography_likelihood.name
            time_seconds = frame.time_offset.seconds + frame.time_offset.microseconds / 1e6
            
            frame_info = {
                'time_offset': time_seconds,
                'time_formatted': self._format_timestamp(time_seconds),
                'likelihood': likelihood
            }
            frames_data.append(frame_info)
            
            # Guardar frames problemáticos (POSSIBLE o más)
            if likelihood in ["POSSIBLE", "LIKELY", "VERY_LIKELY"]:
                problematic_frames.append(frame_info)
            
            # Determinar máximo nivel
            likelihood_levels = [
                "UNKNOWN", "VERY_UNLIKELY", "UNLIKELY", 
                "POSSIBLE", "LIKELY", "VERY_LIKELY"
            ]
            if likelihood_levels.index(likelihood) > likelihood_levels.index(max_likelihood):
                max_likelihood = likelihood
        
        # Agrupar frames problemáticos en rangos de tiempo
        problematic_ranges = self._group_frames_into_ranges(problematic_frames)
        
        return {
            'max_likelihood': max_likelihood,
            'is_explicit': max_likelihood in ["LIKELY", "VERY_LIKELY"],
            'frames_analyzed': len(frames_data),
            'problematic_frames': problematic_frames[:20],
            'problematic_ranges': problematic_ranges,
            'frames': frames_data[:10]
        }
    
    def _group_frames_into_ranges(self, frames: List[Dict]) -> List[Dict]:
        """Agrupa frames consecutivos en rangos de tiempo"""
        if not frames:
            return []
        
        ranges = []
        current_range = None
        
        for frame in sorted(frames, key=lambda x: x['time_offset']):
            if current_range is None:
                current_range = {
                    'start_time': frame['time_offset'],
                    'end_time': frame['time_offset'],
                    'start_formatted': frame['time_formatted'],
                    'end_formatted': frame['time_formatted'],
                    'max_likelihood': frame['likelihood']
                }
            elif frame['time_offset'] - current_range['end_time'] <= 2.0:  # 2 segundos de tolerancia
                current_range['end_time'] = frame['time_offset']
                current_range['end_formatted'] = frame['time_formatted']
                # Actualizar likelihood máximo
                likelihood_levels = ["UNKNOWN", "VERY_UNLIKELY", "UNLIKELY", "POSSIBLE", "LIKELY", "VERY_LIKELY"]
                if likelihood_levels.index(frame['likelihood']) > likelihood_levels.index(current_range['max_likelihood']):
                    current_range['max_likelihood'] = frame['likelihood']
            else:
                ranges.append(current_range)
                current_range = {
                    'start_time': frame['time_offset'],
                    'end_time': frame['time_offset'],
                    'start_formatted': frame['time_formatted'],
                    'end_formatted': frame['time_formatted'],
                    'max_likelihood': frame['likelihood']
                }
        
        if current_range:
            ranges.append(current_range)
        
        return ranges
    
    def _process_label_annotations(self, label_annotations) -> List[Dict[str, Any]]:
        """Procesa anotaciones de etiquetas con información extendida para detección de violencia"""
        labels = []
        
        for annotation in label_annotations:
            label_info = {
                'description': annotation.entity.description,
                'entity': {
                    'description': annotation.entity.description,
                    'entity_id': annotation.entity.entity_id if hasattr(annotation.entity, 'entity_id') else None
                },
                'confidence': 0.0,
                'category': annotation.category_entities[0].description if annotation.category_entities else None,
                'segments_count': len(annotation.segments) if hasattr(annotation, 'segments') else 0
            }
            
            # Calcular confianza promedio
            confidences = [segment.confidence for segment in annotation.segments]
            if confidences:
                label_info['confidence'] = sum(confidences) / len(confidences)
                label_info['max_confidence'] = max(confidences)
                label_info['min_confidence'] = min(confidences)
            
            labels.append(label_info)
        
        # Ordenar por confianza
        labels.sort(key=lambda x: x['confidence'], reverse=True)
        
        return labels[:30]  # Top 30 etiquetas para mejor cobertura
    
    def _process_shot_annotations(self, shot_annotations) -> List[Dict[str, Any]]:
        """
        Procesa detección de cambios de escena (shots)
        
        Returns:
            Lista de escenas detectadas con timestamps
        """
        shots = []
        
        for i, shot in enumerate(shot_annotations):
            start_time = shot.start_time_offset.seconds + shot.start_time_offset.microseconds / 1e6
            end_time = shot.end_time_offset.seconds + shot.end_time_offset.microseconds / 1e6
            
            shots.append({
                'shot_number': i + 1,
                'start_time': start_time,
                'end_time': end_time,
                'duration': end_time - start_time,
                'start_formatted': self._format_timestamp(start_time),
                'end_formatted': self._format_timestamp(end_time)
            })
        
        return shots
    
    def _process_person_detection(self, person_detection_annotations) -> Dict[str, Any]:
        """
        Procesa detección de personas en el video
        
        Returns:
            Dict con información de personas detectadas
        """
        if not person_detection_annotations:
            return {
                'total_persons': 0,
                'persons': []
            }
        
        persons = []
        
        for track in person_detection_annotations:
            person_info = {
                'track_id': len(persons) + 1,
                'confidence': track.confidence if hasattr(track, 'confidence') else 0.0,
                'segments': [],
                'total_duration': 0.0
            }
            
            # Procesar segmentos temporales donde aparece la persona
            segments_list = getattr(track, 'segments', None) or getattr(track, 'timestamped_objects', [])
            for segment in segments_list:
                segment_data = getattr(segment, 'segment', segment)
                start_offset = getattr(segment_data, 'start_time_offset', None)
                end_offset = getattr(segment_data, 'end_time_offset', None)
                if not start_offset or not end_offset:
                    continue
                start_time = start_offset.seconds + start_offset.microseconds / 1e6
                end_time = end_offset.seconds + end_offset.microseconds / 1e6
                duration = end_time - start_time
                
                person_info['segments'].append({
                    'start_time': start_time,
                    'end_time': end_time,
                    'duration': duration,
                    'start_formatted': self._format_timestamp(start_time),
                    'end_formatted': self._format_timestamp(end_time)
                })
                person_info['total_duration'] += duration
            
            persons.append(person_info)
        
        return {
            'total_persons': len(persons),
            'persons': persons
        }
    
    def _process_face_detection(self, face_detection_annotations) -> Dict[str, Any]:
        """
        Procesa detección de rostros y expresiones
        
        Returns:
            Dict con información de rostros detectados
        """
        if not face_detection_annotations:
            return {
                'total_faces': 0,
                'faces': []
            }
        
        faces = []
        
        for track in face_detection_annotations:
            face_info = {
                'track_id': len(faces) + 1,
                'confidence': 0.0,
                'segments': [],
                'emotions': {
                    'joy': [],
                    'sorrow': [],
                    'anger': [],
                    'surprise': []
                },
                'attributes': {
                    'looking_at_camera': [],
                    'wearing_headwear': []
                }
            }
            
            # Procesar frames con detecciones de rostro
            timestamped_objects = getattr(track, 'timestamped_objects', [])
            for timestamped_object in timestamped_objects:
                time_seconds = timestamped_object.time_offset.seconds + timestamped_object.time_offset.microseconds / 1e6
                
                # Extraer atributos del rostro
                if hasattr(timestamped_object, 'attributes'):
                    for attribute in timestamped_object.attributes:
                        attr_name = attribute.name.lower()
                        confidence = attribute.confidence
                        
                        # Emociones
                        if 'joy' in attr_name:
                            face_info['emotions']['joy'].append({'time': time_seconds, 'confidence': confidence})
                        elif 'sorrow' in attr_name:
                            face_info['emotions']['sorrow'].append({'time': time_seconds, 'confidence': confidence})
                        elif 'anger' in attr_name:
                            face_info['emotions']['anger'].append({'time': time_seconds, 'confidence': confidence})
                        elif 'surprise' in attr_name:
                            face_info['emotions']['surprise'].append({'time': time_seconds, 'confidence': confidence})
                        
                        # Atributos
                        elif 'looking_at_camera' in attr_name:
                            face_info['attributes']['looking_at_camera'].append({'time': time_seconds, 'confidence': confidence})
                        elif 'headwear' in attr_name:
                            face_info['attributes']['wearing_headwear'].append({'time': time_seconds, 'confidence': confidence})
            
            # Procesar segmentos
            segments_list = getattr(track, 'segments', None) or getattr(track, 'timestamped_objects', [])
            for segment in segments_list:
                segment_data = getattr(segment, 'segment', segment)
                start_offset = getattr(segment_data, 'start_time_offset', None)
                end_offset = getattr(segment_data, 'end_time_offset', None)
                if not start_offset or not end_offset:
                    continue
                start_time = start_offset.seconds + start_offset.microseconds / 1e6
                end_time = end_offset.seconds + end_offset.microseconds / 1e6
                
                face_info['segments'].append({
                    'start_time': start_time,
                    'end_time': end_time,
                    'start_formatted': self._format_timestamp(start_time),
                    'end_formatted': self._format_timestamp(end_time)
                })
                
                # Calcular confianza promedio
                if hasattr(segment, 'confidence'):
                    face_info['confidence'] = max(face_info['confidence'], segment.confidence)
            
            # Calcular emoción dominante
            face_info['dominant_emotion'] = self._get_dominant_emotion(face_info['emotions'])
            
            # Verificar si tiene emociones negativas significativas
            has_anger = len(face_info['emotions']['anger']) > 0 and any(e['confidence'] > 0.5 for e in face_info['emotions']['anger'])
            has_sorrow = len(face_info['emotions']['sorrow']) > 0 and any(e['confidence'] > 0.5 for e in face_info['emotions']['sorrow'])
            face_info['has_negative_emotions'] = has_anger or has_sorrow
            face_info['has_high_anger'] = has_anger
            
            faces.append(face_info)
        
        # Calcular estadísticas de emociones negativas
        faces_with_anger = sum(1 for f in faces if f.get('has_high_anger', False))
        faces_with_negative = sum(1 for f in faces if f.get('has_negative_emotions', False))
        
        return {
            'total_faces': len(faces),
            'faces': faces,
            'summary': {
                'multiple_faces': len(faces) > 1,
                'faces_with_negative_emotions': faces_with_negative,
                'faces_with_anger': faces_with_anger,
                'high_tension_detected': faces_with_anger >= 2 or (faces_with_negative >= 2 and len(faces) > 2)
            }
        }
    
    def _process_object_tracking(self, object_tracking_annotations) -> List[Dict[str, Any]]:
        """
        Procesa seguimiento de objetos en el video
        
        Returns:
            Lista de objetos detectados y rastreados
        """
        objects = []
        
        for track in object_tracking_annotations:
            object_info = {
                'entity': track.entity.description if hasattr(track.entity, 'description') else 'Unknown',
                'entity_id': track.entity.entity_id if hasattr(track.entity, 'entity_id') else None,
                'confidence': track.confidence,
                'segments': [],
                'total_duration': 0.0
            }
            
            # Procesar segmentos temporales del objeto
            segments_list = getattr(track, 'segments', None) or getattr(track, 'timestamped_objects', [])
            for segment in segments_list:
                segment_data = getattr(segment, 'segment', segment)
                start_offset = getattr(segment_data, 'start_time_offset', None)
                end_offset = getattr(segment_data, 'end_time_offset', None)
                if not start_offset or not end_offset:
                    continue
                start_time = start_offset.seconds + start_offset.microseconds / 1e6
                end_time = end_offset.seconds + end_offset.microseconds / 1e6
                duration = end_time - start_time
                
                object_info['segments'].append({
                    'start_time': start_time,
                    'end_time': end_time,
                    'duration': duration,
                    'start_formatted': self._format_timestamp(start_time),
                    'end_formatted': self._format_timestamp(end_time)
                })
                object_info['total_duration'] += duration
            
            objects.append(object_info)
        
        # Ordenar por duración (objetos más prominentes primero)
        objects.sort(key=lambda x: x['total_duration'], reverse=True)
        
        return objects[:50]  # Top 50 objetos
    
    def _get_dominant_emotion(self, emotions: Dict[str, List]) -> str:
        """Determina la emoción dominante basada en confianza promedio"""
        emotion_scores = {}
        
        for emotion, detections in emotions.items():
            if detections:
                avg_confidence = sum(d['confidence'] for d in detections) / len(detections)
                emotion_scores[emotion] = avg_confidence
        
        if not emotion_scores:
            return 'neutral'
        
        return max(emotion_scores.items(), key=lambda x: x[1])[0]
    
    # ==================== UTILIDADES ====================
    
    def get_supported_features(self) -> List[str]:
        """Retorna las features soportadas"""
        return [
            'LOGO_RECOGNITION',
            'TEXT_DETECTION',
            'EXPLICIT_CONTENT_DETECTION',
            'LABEL_DETECTION',
            'OBJECT_TRACKING',
            'SHOT_CHANGE_DETECTION',
            'PERSON_DETECTION',
            'FACE_DETECTION'
        ]
    
    def estimate_analysis_time(self, video_duration_seconds: float) -> float:
        """
        Estima el tiempo de análisis en minutos
        
        Args:
            video_duration_seconds: Duración del video en segundos
            
        Returns:
            float: Tiempo estimado en minutos
        """
        # Aproximadamente 0.5-1 minuto por cada minuto de video
        return (video_duration_seconds / 60) * 0.75
