"""
Motor de consultas sobre base de datos completa de eventos de seguridad
Permite hacer preguntas específicas sobre eventos ya analizados
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class SecurityQueryEngine:
    """
    Motor de consultas sobre base de datos COMPLETA de eventos
    """
    
    def __init__(self, firestore_service=None, gemini_service=None):
        """
        Args:
            firestore_service: Legacy (sin uso; los eventos viven en PostgreSQL)
            gemini_service: Gateway de IA (por defecto el local 32B)
        """
        self.firestore = firestore_service
        self.gemini = gemini_service

    def _get_repo(self):
        from infrastructure.repositories.security_video_repository import SecurityVideoRepository
        return SecurityVideoRepository()

    def _get_gemini(self):
        if self.gemini is None:
            from infrastructure.adapters.ai_gateway import get_ai_gateway
            self.gemini = get_ai_gateway()
        return self.gemini
        
    def query(self, video_id: str, pregunta: str) -> Dict[str, Any]:
        """
        Responde pregunta basándose en TODOS los eventos analizados
        
        Args:
            video_id: ID del video de seguridad
            pregunta: Pregunta en lenguaje natural
            
        Returns:
            Dict con respuesta y eventos relevantes
        """
        logger.info(f"🔍 Consultando video {video_id}: '{pregunta}'")
        
        # 1. Obtener TODOS los eventos del video
        all_events = self._get_all_events(video_id)
        
        if not all_events:
            return {
                "pregunta": pregunta,
                "eventos_encontrados": 0,
                "respuesta": "No se encontraron eventos analizados para este video.",
                "eventos_detallados": []
            }
        
        logger.info(f"📊 Analizando {len(all_events)} eventos totales")
        
        # 2. Usar Gemini para interpretar pregunta y filtrar eventos
        query_params = self._parse_query_with_gemini(pregunta, all_events)
        
        # 3. Filtrar eventos según parámetros
        relevant_events = self._filter_events(all_events, query_params)
        
        # 4. Generar respuesta contextual
        response_text = self._generate_response(pregunta, relevant_events)
        
        logger.info(f"✅ Encontrados {len(relevant_events)} eventos relevantes")
        
        return {
            "pregunta": pregunta,
            "eventos_encontrados": len(relevant_events),
            "respuesta": response_text,
            "eventos_detallados": relevant_events,
            "parametros_busqueda": query_params
        }
    
    def _get_all_events(self, video_id: str) -> List[Dict[str, Any]]:
        """Obtiene TODOS los eventos del video desde PostgreSQL"""
        try:
            repo = self._get_repo()
            eventos = repo.obtener_eventos_video(video_id)
            return [repo._evento_to_dict(e) for e in eventos]
        except Exception as e:
            logger.error(f"Error obteniendo eventos: {e}")
            return []
    
    def _parse_query_with_gemini(self, pregunta: str, all_events: List[Dict]) -> Dict[str, Any]:
        """
        Usa Gemini para interpretar la pregunta y extraer parámetros de búsqueda
        
        Returns:
            Dict con parámetros: {objects, actions, time_range, keywords}
        """
        try:
            # Crear contexto para Gemini
            summary = self._create_events_summary(all_events)
            
            prompt = f"""
Analiza esta pregunta sobre un video de seguridad y extrae los parámetros de búsqueda.

Pregunta del usuario: "{pregunta}"

Contexto del video:
- Total de eventos analizados: {len(all_events)}
- Objetos detectados en el video: {summary['objetos_unicos']}
- Acciones detectadas en el video: {summary['acciones_unicas']}
- Rango temporal: {summary['tiempo_inicio']} a {summary['tiempo_fin']}

Responde SOLO con un JSON válido con este formato:
{{
  "objects": ["persona", "vehiculo"],  // Objetos mencionados o relacionados
  "actions": ["caminar", "correr"],     // Acciones mencionadas o relacionadas
  "time_range": {{"start": 14.0, "end": 16.0}},  // Rango horario si se menciona
  "keywords": ["robo", "intrusion"],    // Palabras clave relevantes
  "context": "Buscar eventos de robo o intrusión"  // Resumen de lo que busca
}}
"""
            
            response = self._get_gemini().chat(
                [{"role": "user", "content": prompt}],
                json_mode=True,
                temperature=0,
                max_tokens=1024,
            )
            
            # Parsear respuesta JSON
            import json
            import re
            
            # Extraer JSON de la respuesta
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                params = json.loads(json_match.group())
                return params
            else:
                logger.warning("No se pudo parsear respuesta de Gemini, usando búsqueda genérica")
                return self._create_generic_query_params(pregunta)
                
        except Exception as e:
            logger.error(f"Error parseando query con Gemini: {e}")
            return self._create_generic_query_params(pregunta)
    
    def _create_events_summary(self, events: List[Dict]) -> Dict[str, Any]:
        """Crea un resumen de los eventos para contexto"""
        if not events:
            return {
                'objetos_unicos': [],
                'acciones_unicas': [],
                'tiempo_inicio': 0,
                'tiempo_fin': 0
            }
        
        objetos = set()
        acciones = set()
        
        for event in events:
            objetos.update(event.get('objetos_detectados', []))
            acciones.update(event.get('acciones_detectadas', []))
        
        return {
            'objetos_unicos': list(objetos),
            'acciones_unicas': list(acciones),
            'tiempo_inicio': events[0].get('timestamp_inicio', 0),
            'tiempo_fin': events[-1].get('timestamp_fin', 0)
        }
    
    def _create_generic_query_params(self, pregunta: str) -> Dict[str, Any]:
        """Crea parámetros genéricos basados en palabras clave simples"""
        pregunta_lower = pregunta.lower()
        
        # Objetos comunes
        objects = []
        if any(word in pregunta_lower for word in ['persona', 'personas', 'gente']):
            objects.append('persona')
        if any(word in pregunta_lower for word in ['vehiculo', 'auto', 'carro', 'camion']):
            objects.append('vehiculo')
        
        # Acciones comunes
        actions = []
        if any(word in pregunta_lower for word in ['caminar', 'caminando']):
            actions.append('caminar')
        if any(word in pregunta_lower for word in ['correr', 'corriendo']):
            actions.append('correr')
        if any(word in pregunta_lower for word in ['entrar', 'entrando', 'entrada']):
            actions.append('entrar')
        
        return {
            'objects': objects,
            'actions': actions,
            'time_range': None,
            'keywords': pregunta_lower.split(),
            'context': pregunta
        }
    
    def _filter_events(self, events: List[Dict], params: Dict[str, Any]) -> List[Dict]:
        """Filtra eventos según parámetros de búsqueda"""
        filtered = events
        
        # Filtrar por objetos
        if params.get('objects'):
            filtered = [
                e for e in filtered
                if any(obj in e.get('objetos_detectados', []) for obj in params['objects'])
            ]
        
        # Filtrar por acciones
        if params.get('actions'):
            filtered = [
                e for e in filtered
                if any(act in e.get('acciones_detectadas', []) for act in params['actions'])
            ]
        
        # Filtrar por tiempo
        time_range = params.get('time_range')
        if time_range:
            start = time_range.get('start', 0)
            end = time_range.get('end', float('inf'))
            filtered = [
                e for e in filtered
                if start <= e.get('timestamp_inicio', 0) <= end
            ]
        
        # Filtrar por keywords en descripción
        keywords = params.get('keywords', [])
        if keywords and not params.get('objects') and not params.get('actions'):
            # Solo aplicar si no hay otros filtros
            filtered = [
                e for e in filtered
                if any(kw.lower() in e.get('descripcion', '').lower() for kw in keywords)
            ]
        
        return filtered
    
    def _generate_response(self, pregunta: str, events: List[Dict]) -> str:
        """Genera respuesta en lenguaje natural usando Gemini"""
        try:
            if not events:
                return "No se encontraron eventos que coincidan con tu consulta."
            
            # Crear resumen de eventos encontrados
            events_summary = []
            for event in events[:10]:  # Máximo 10 eventos en el resumen
                events_summary.append({
                    'timestamp': f"{event['timestamp_inicio']:.1f}s - {event['timestamp_fin']:.1f}s",
                    'descripcion': event.get('descripcion', ''),
                    'objetos': event.get('objetos_detectados', []),
                    'acciones': event.get('acciones_detectadas', []),
                    'personas': event.get('personas_count', 0),
                    'vehiculos': event.get('vehiculos_count', 0)
                })
            
            prompt = f"""
Genera una respuesta clara y concisa para esta pregunta del usuario sobre un video de seguridad.

Pregunta: "{pregunta}"

Eventos encontrados (mostrando {len(events_summary)} de {len(events)} total):
{events_summary}

Instrucciones:
- Responde directamente la pregunta
- Sé específico con timestamps si es relevante
- Menciona detalles importantes (cantidad de personas, objetos, acciones)
- Máximo 3-4 oraciones
- Si hay muchos eventos, haz un resumen general

Respuesta:
"""
            
            response = self._get_gemini().chat(
                [{"role": "user", "content": prompt}],
                json_mode=False,
                temperature=0.4,
                max_tokens=1024,
            )
            return response.strip()
            
        except Exception as e:
            logger.error(f"Error generando respuesta: {e}")
            return f"Se encontraron {len(events)} eventos relacionados con tu consulta."
