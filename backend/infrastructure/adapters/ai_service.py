"""
Servicio de IA Unificado - TIVIT Video
Maneja Gemini como servicio principal de IA.
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
    Servicio de IA basado en Gemini.
    
    Este servicio actúa como wrapper del GeminiAdapter,
    proporcionando una interfaz unificada para el resto de la aplicación.
    """
    
    def __init__(self):
        # Gemini (servicio principal)
        self._gemini = None
        if os.getenv('GEMINI_API_KEY'):
            try:
                from infrastructure.adapters.gemini_adapter import get_gemini_adapter
                self._gemini = get_gemini_adapter()
            except Exception as e:
                logger.warning(f"No se pudo cargar Gemini: {e}")
        
        # Estado
        self._gemini_available = self._gemini and self._gemini.disponible
        
        logger.info(
            f"🤖 AI Service inicializado: "
            f"Gemini={'✅' if self._gemini_available else '❌'}"
        )
    
    @property
    def disponible(self) -> bool:
        """Verifica si el servicio de IA está disponible"""
        return self._gemini_available
    
    def get_status(self) -> Dict[str, Any]:
        """Retorna el estado del servicio de IA"""
        return {
            'gemini': {
                'available': self._gemini_available,
                'model': 'gemini-2.0-flash' if self._gemini_available else None
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
        Genera un título para el video usando Gemini.
        
        Args:
            nombre_archivo: Nombre original del archivo
            etiquetas: Etiquetas detectadas
            duracion_segundos: Duración del video
            
        Returns:
            Título generado (máximo 50 caracteres)
        """
        etiquetas = etiquetas or []
        
        if self._gemini_available:
            titulo = self._gemini.generar_titulo(nombre_archivo, etiquetas, duracion_segundos)
            logger.info(f"📝 Título (Gemini): {titulo}")
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
        Decide si aprobar o rechazar un video usando Gemini.
        
        Args:
            analisis: Resultados del análisis de Video Intelligence
            blacklist: Configuración de elementos prohibidos
            
        Returns:
            Dict con: aprobado, razon, confianza, modelo
        """
        if self._gemini_available:
            resultado = self._gemini.decidir_moderacion(analisis, blacklist)
            logger.info(f"🔍 Moderación (Gemini): aprobado={resultado.get('aprobado')}")
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
        Análisis de sentimiento usando Gemini.
        
        Args:
            textos: Textos detectados por OCR
            
        Returns:
            Dict con análisis de sentimiento
        """
        if self._gemini_available:
            return self._gemini.analizar_sentimiento(textos)
        
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
