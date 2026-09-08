"""
Sistema de Control de Costos para IA (Gemini)
Rastrea y limita el uso de APIs de IA para prevenir gastos excesivos
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from google.cloud import firestore
import hashlib

logger = logging.getLogger(__name__)

# Límites de costo
MAX_TOKENS_PER_USER_DAY = 100_000  # 100k tokens por día por usuario
MAX_REQUESTS_PER_USER_DAY = 50  # 50 requests de IA por día
MAX_TOKENS_PER_REQUEST = 8_000  # Máximo 8k tokens por request (input + output)
MAX_INPUT_LENGTH = 5_000  # Máximo 5k caracteres en input

# Costos aproximados Gemini Pro
COST_PER_1K_INPUT_TOKENS = 0.00025  # $0.25 por 1M tokens input
COST_PER_1K_OUTPUT_TOKENS = 0.00050  # $0.50 por 1M tokens output


class AIUsageTracker:
    """
    Rastrea el uso de APIs de IA por usuario y fecha
    
    Almacena en Firestore colección 'ai_usage_logs':
    {
        'id': str,
        'usuario': str,
        'fecha': str (YYYY-MM-DD),
        'timestamp': str (ISO 8601),
        'endpoint': str (validate|improve|conversation),
        'workspace_id': str,
        'workspace_nombre': str,
        'input_tokens': int,
        'output_tokens': int,
        'total_tokens': int,
        'estimated_cost_usd': float,
        'latency_ms': int,
        'success': bool,
        'error_message': str (opcional),
        'model': str,
        'prompt_hash': str (para cache)
    }
    """
    
    COLLECTION_NAME = 'ai_usage_logs'
    DAILY_LIMITS_COLLECTION = 'ai_daily_limits'
    RESPONSE_CACHE_COLLECTION = 'ai_response_cache'
    
    @staticmethod
    def _get_db() -> Optional[firestore.Client]:
        """Obtiene cliente de Firestore"""
        try:
            from config.gcp_config import GCPConfig
            from infrastructure.adapters.gcp_firestore import FirestoreAdapter
            
            adapter = FirestoreAdapter(GCPConfig())
            if adapter.is_available():
                return adapter.db
        except Exception as e:
            logger.error(f"Error obteniendo Firestore para AI tracking: {e}")
        return None
    
    @staticmethod
    def check_user_limits(usuario: str) -> Tuple[bool, Optional[str]]:
        """
        Verifica si el usuario puede hacer más requests de IA hoy
        
        Args:
            usuario: Username del usuario
            
        Returns:
            Tupla (allowed, error_message)
        """
        try:
            db = AIUsageTracker._get_db()
            if not db:
                # Si no hay DB, permitir (fail open)
                logger.warning("Firestore no disponible - permitiendo request de IA")
                return (True, None)
            
            today = datetime.now().strftime('%Y-%m-%d')
            limit_doc_id = f"{usuario}_{today}"
            
            # Obtener límites del día
            limit_ref = db.collection(AIUsageTracker.DAILY_LIMITS_COLLECTION).document(limit_doc_id)
            limit_doc = limit_ref.get()
            
            if not limit_doc.exists:
                # Primera request del día - permitir
                return (True, None)
            
            usage = limit_doc.to_dict()
            requests_today = usage.get('requests_count', 0)
            tokens_today = usage.get('tokens_count', 0)
            
            # Verificar límite de requests
            if requests_today >= MAX_REQUESTS_PER_USER_DAY:
                return (False, f"Has alcanzado el límite diario de {MAX_REQUESTS_PER_USER_DAY} consultas de IA. Intenta mañana.")
            
            # Verificar límite de tokens
            if tokens_today >= MAX_TOKENS_PER_USER_DAY:
                return (False, f"Has alcanzado el límite diario de {MAX_TOKENS_PER_USER_DAY} tokens. Intenta mañana.")
            
            return (True, None)
            
        except Exception as e:
            logger.error(f"Error verificando límites de IA: {e}", exc_info=True)
            # En caso de error, permitir (fail open)
            return (True, None)
    
    @staticmethod
    def validate_input_size(input_text: str) -> Tuple[bool, Optional[str]]:
        """
        Valida que el input no sea excesivamente largo
        
        Args:
            input_text: Texto de entrada
            
        Returns:
            Tupla (valid, error_message)
        """
        if len(input_text) > MAX_INPUT_LENGTH:
            return (False, f"El contexto es demasiado largo. Máximo {MAX_INPUT_LENGTH} caracteres (actual: {len(input_text)})")
        return (True, None)
    
    @staticmethod
    def get_cached_response(prompt: str, model: str = "gemini-pro") -> Optional[Dict[str, Any]]:
        """
        Busca una respuesta cacheada para el mismo prompt
        
        Args:
            prompt: Texto del prompt
            model: Modelo usado
            
        Returns:
            Respuesta cacheada o None
        """
        try:
            db = AIUsageTracker._get_db()
            if not db:
                return None
            
            # Hash del prompt para buscar en cache
            prompt_hash = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
            
            # Buscar en cache (últimas 24 horas)
            yesterday = (datetime.now() - timedelta(days=1)).isoformat()
            
            query = (
                db.collection(AIUsageTracker.RESPONSE_CACHE_COLLECTION)
                .where(filter=firestore.FieldFilter('prompt_hash', '==', prompt_hash))
                .where(filter=firestore.FieldFilter('model', '==', model))
                .where(filter=firestore.FieldFilter('timestamp', '>=', yesterday))
                .limit(1)
            )
            
            docs = list(query.stream())
            if docs:
                cached = docs[0].to_dict()
                logger.info(f"✅ Cache hit para prompt de IA (hash: {prompt_hash[:8]})")
                return cached.get('response')
            
            return None
            
        except Exception as e:
            logger.error(f"Error buscando en cache de IA: {e}")
            return None
    
    @staticmethod
    def cache_response(prompt: str, response: Dict[str, Any], model: str = "gemini-pro") -> bool:
        """
        Cachea una respuesta de IA para reutilización
        
        Args:
            prompt: Texto del prompt
            response: Respuesta de la IA
            model: Modelo usado
            
        Returns:
            True si se cacheó correctamente
        """
        try:
            db = AIUsageTracker._get_db()
            if not db:
                return False
            
            prompt_hash = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
            
            cache_entry = {
                'prompt_hash': prompt_hash,
                'model': model,
                'response': response,
                'timestamp': datetime.now().isoformat(),
                'expires_at': (datetime.now() + timedelta(days=1)).isoformat()
            }
            
            db.collection(AIUsageTracker.RESPONSE_CACHE_COLLECTION).add(cache_entry)
            logger.debug(f"✅ Respuesta de IA cacheada (hash: {prompt_hash[:8]})")
            return True
            
        except Exception as e:
            logger.error(f"Error cacheando respuesta de IA: {e}")
            return False
    
    @staticmethod
    def log_usage(
        usuario: str,
        endpoint: str,
        workspace_id: str,
        workspace_nombre: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        model: str = "gemini-pro",
        success: bool = True,
        error_message: Optional[str] = None,
        prompt: Optional[str] = None
    ) -> bool:
        """
        Registra el uso de IA en Firestore
        
        Args:
            usuario: Username del usuario
            endpoint: Endpoint usado (validate|improve|conversation)
            workspace_id: ID del workspace
            workspace_nombre: Nombre del workspace
            input_tokens: Tokens de entrada
            output_tokens: Tokens de salida
            latency_ms: Latencia en milisegundos
            model: Modelo usado
            success: Si la llamada fue exitosa
            error_message: Mensaje de error si falló
            prompt: Texto del prompt (opcional, para hash)
            
        Returns:
            True si se registró correctamente
        """
        try:
            db = AIUsageTracker._get_db()
            if not db:
                logger.warning("Firestore no disponible - uso de IA no registrado")
                return False
            
            total_tokens = input_tokens + output_tokens
            
            # Calcular costo estimado
            input_cost = (input_tokens / 1000) * COST_PER_1K_INPUT_TOKENS
            output_cost = (output_tokens / 1000) * COST_PER_1K_OUTPUT_TOKENS
            estimated_cost = input_cost + output_cost
            
            # Crear log de uso
            usage_log = {
                'usuario': usuario,
                'fecha': datetime.now().strftime('%Y-%m-%d'),
                'timestamp': datetime.now().isoformat(),
                'endpoint': endpoint,
                'workspace_id': workspace_id,
                'workspace_nombre': workspace_nombre,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': total_tokens,
                'estimated_cost_usd': round(estimated_cost, 6),
                'latency_ms': latency_ms,
                'model': model,
                'success': success
            }
            
            if error_message:
                usage_log['error_message'] = error_message
            
            if prompt:
                usage_log['prompt_hash'] = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
            
            # Guardar log
            db.collection(AIUsageTracker.COLLECTION_NAME).add(usage_log)
            
            # Actualizar contador diario
            if success:
                today = datetime.now().strftime('%Y-%m-%d')
                limit_doc_id = f"{usuario}_{today}"
                limit_ref = db.collection(AIUsageTracker.DAILY_LIMITS_COLLECTION).document(limit_doc_id)
                
                limit_ref.set({
                    'usuario': usuario,
                    'fecha': today,
                    'requests_count': firestore.Increment(1),
                    'tokens_count': firestore.Increment(total_tokens),
                    'total_cost_usd': firestore.Increment(estimated_cost),
                    'last_updated': datetime.now().isoformat()
                }, merge=True)
            
            logger.info(f"📊 Uso de IA registrado: {usuario} - {endpoint} - {total_tokens} tokens (${estimated_cost:.4f})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error registrando uso de IA: {e}", exc_info=True)
            return False
    
    @staticmethod
    def get_user_usage_today(usuario: str) -> Dict[str, Any]:
        """
        Obtiene el uso de IA del usuario hoy
        
        Args:
            usuario: Username del usuario
            
        Returns:
            Diccionario con estadísticas de uso
        """
        try:
            db = AIUsageTracker._get_db()
            if not db:
                return {
                    'requests_count': 0,
                    'tokens_count': 0,
                    'total_cost_usd': 0.0,
                    'requests_remaining': MAX_REQUESTS_PER_USER_DAY,
                    'tokens_remaining': MAX_TOKENS_PER_USER_DAY
                }
            
            today = datetime.now().strftime('%Y-%m-%d')
            limit_doc_id = f"{usuario}_{today}"
            
            limit_ref = db.collection(AIUsageTracker.DAILY_LIMITS_COLLECTION).document(limit_doc_id)
            limit_doc = limit_ref.get()
            
            if not limit_doc.exists:
                return {
                    'requests_count': 0,
                    'tokens_count': 0,
                    'total_cost_usd': 0.0,
                    'requests_remaining': MAX_REQUESTS_PER_USER_DAY,
                    'tokens_remaining': MAX_TOKENS_PER_USER_DAY
                }
            
            usage = limit_doc.to_dict()
            requests = usage.get('requests_count', 0)
            tokens = usage.get('tokens_count', 0)
            
            return {
                'requests_count': requests,
                'tokens_count': tokens,
                'total_cost_usd': usage.get('total_cost_usd', 0.0),
                'requests_remaining': max(0, MAX_REQUESTS_PER_USER_DAY - requests),
                'tokens_remaining': max(0, MAX_TOKENS_PER_USER_DAY - tokens)
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo uso de IA: {e}")
            return {
                'requests_count': 0,
                'tokens_count': 0,
                'total_cost_usd': 0.0,
                'requests_remaining': MAX_REQUESTS_PER_USER_DAY,
                'tokens_remaining': MAX_TOKENS_PER_USER_DAY
            }
