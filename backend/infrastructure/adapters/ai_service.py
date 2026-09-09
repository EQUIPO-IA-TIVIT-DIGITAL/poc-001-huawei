"""
Servicio de IA Unificado - TIVIT Video
Maneja el gateway local como servicio principal de IA.
Proporciona una interfaz única para todas las operaciones de IA.
"""
import os
import json
import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class AIService:
    """
    Servicio de IA basado en el gateway local.

    Este servicio actúa como wrapper del gateway,
    proporcionando una interfaz unificada para el resto de la aplicación.
    """
    
    def __init__(self):
        # Gateway local (servicio principal)
        self._gateway = None
        try:
            from infrastructure.adapters.ai_gateway import get_ai_gateway
            self._gateway = get_ai_gateway()
        except Exception as e:
            logger.warning(f"No se pudo cargar AI Gateway: {e}")
        
        # Estado
        self._gateway_available = self._gateway and self._gateway.disponible
        
        logger.info(
            f"🤖 AI Service inicializado: "
            f"Gateway={'✅' if self._gateway_available else '❌'}"
        )
    
    @property
    def disponible(self) -> bool:
        """Verifica si el servicio de IA está disponible"""
        return bool(self._gateway_available)
    
    def get_status(self) -> Dict[str, Any]:
        """Retorna el estado del servicio de IA"""
        from config.app_config import AppConfig

        return {
            'ai': {
                'available': self._gateway_available,
                'provider': AppConfig.AI_PROVIDER
            },
            'any_available': self.disponible
        }
    
    def generar_titulo(
        self, 
        nombre_archivo: str, 
        etiquetas: List[str] = None,
        duracion_segundos: int = None
    ) -> str:
        """
        Genera un título para el video usando IA.
        
        Args:
            nombre_archivo: Nombre original del archivo
            etiquetas: Etiquetas detectadas
            duracion_segundos: Duración del video
            
        Returns:
            Título generado (máximo 50 caracteres)
        """
        etiquetas = etiquetas or []
        
        if self._gateway_available:
            titulo = self._gateway.generar_titulo(nombre_archivo, etiquetas, duracion_segundos)
            logger.info(f"📝 Título (IA): {titulo}")
            return titulo
        
        # Fallback sin IA
        titulo = self._titulo_simple(nombre_archivo)
        logger.info(f"📝 Título (fallback): {titulo}")
        return titulo
    
    def decidir_moderacion(
        self, 
        analisis: Dict[str, Any],
        blacklist: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Decide si aprobar o rechazar un video usando IA.
        
        Args:
            analisis: Resultados del análisis visual
            blacklist: Configuración de elementos prohibidos
            
        Returns:
            Dict con: aprobado, razon, confianza, modelo
        """
        if self._gateway_available:
            resultado = self._gateway.decidir_moderacion(analisis, blacklist)
            logger.info(f"🔍 Moderación (IA): aprobado={resultado.get('aprobado')}")
            return resultado
        
        # Sin IA disponible
        logger.warning("⚠️ Sin IA disponible para moderación")
        return {
            'aprobado': False,
            'razon': 'Requiere revisión manual (IA no disponible)',
            'confianza': 0.0,
            'requiere_revision': True,
            'modelo': 'ninguno'
        }
    
    def analizar_sentimiento(self, textos: List[str]) -> Dict[str, Any]:
        """
        Análisis de sentimiento usando IA.
        
        Args:
            textos: Textos detectados por OCR
            
        Returns:
            Dict con análisis de sentimiento
        """
        if self._gateway_available:
            return self._gateway.analizar_sentimiento(textos)
        
        return {'sentimiento': 'neutral', 'confianza': 0.0}
    
    def _titulo_simple(self, nombre_archivo: str) -> str:
        """Genera título sin IA"""
        nombre = os.path.splitext(nombre_archivo)[0]
        nombre = re.sub(r'[_\-\.]+', ' ', nombre)
        nombre = re.sub(r'\s+', ' ', nombre).strip()
        return nombre.title()[:50] if nombre else "Video sin título"


# ============================================
# Singleton
# ============================================
_instance: Optional[AIService] = None


def get_ai_service() -> AIService:
    """Obtiene la instancia singleton del servicio de IA"""
    global _instance
    if _instance is None:
        _instance = AIService()
    return _instance
