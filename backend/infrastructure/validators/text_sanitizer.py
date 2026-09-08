"""
Utilidades de sanitización y validación de texto para prevenir XSS y otras inyecciones
Centraliza la lógica de limpieza de inputs del usuario
"""

import re
import html
from typing import Optional
import logging

logger = logging.getLogger(__name__)

# Caracteres prohibidos en nombres de workspace (filesystem unsafe)
CARACTERES_PROHIBIDOS_FILESYSTEM = ['/', '\\', '<', '>', ':', '"', '|', '?', '*', '\n', '\r', '\t']

# Patrones peligrosos para detección de inyecciones
PATRONES_PELIGROSOS = [
    r'<script[^>]*>.*?</script>',  # Scripts
    r'javascript:',  # JavaScript URLs
    r'on\w+\s*=',  # Event handlers (onclick, onerror, etc)
    r'<iframe[^>]*>',  # Iframes
    r'<object[^>]*>',  # Objects
    r'<embed[^>]*>',  # Embeds
]


def sanitize_text_input(
    text: str,
    max_length: Optional[int] = None,
    allow_newlines: bool = False,
    strip_html: bool = True
) -> str:
    """
    Sanitiza entrada de texto del usuario para prevenir XSS e inyecciones
    
    Args:
        text: Texto a sanitizar
        max_length: Longitud máxima permitida (None = sin límite)
        allow_newlines: Si se permiten saltos de línea
        strip_html: Si se debe eliminar completamente el HTML
        
    Returns:
        Texto sanitizado y seguro
    """
    if not text or not isinstance(text, str):
        return ""
    
    # 1. Eliminar caracteres de control peligrosos (excepto \n si se permite)
    if allow_newlines:
        # Permitir solo \n, eliminar otros caracteres de control
        text = ''.join(char for char in text if ord(char) >= 32 or char == '\n')
    else:
        # Eliminar todos los caracteres de control
        text = ''.join(char for char in text if ord(char) >= 32)
    
    # 2. Detectar y alertar sobre patrones peligrosos ANTES de escapar
    for patron in PATRONES_PELIGROSOS:
        if re.search(patron, text, re.IGNORECASE):
            logger.warning(f"⚠️ Intento de inyección detectado - patrón: {patron[:30]}")
    
    # 3. Escape de HTML para prevenir XSS
    if strip_html:
        text = html.escape(text)
    
    # 4. Normalizar espacios múltiples
    text = re.sub(r'\s+', ' ', text)
    
    # 5. Aplicar límite de longitud
    if max_length and len(text) > max_length:
        text = text[:max_length]
    
    # 6. Trim espacios al inicio/final
    text = text.strip()
    
    return text


def sanitize_workspace_name(nombre: str) -> str:
    """
    Sanitiza el nombre de un workspace aplicando reglas específicas
    
    Args:
        nombre: Nombre propuesto para el workspace
        
    Returns:
        Nombre sanitizado
        
    Raises:
        ValueError: Si el nombre contiene caracteres prohibidos después de sanitización
    """
    # Sanitizar texto básico
    nombre = sanitize_text_input(nombre, max_length=50, allow_newlines=False)
    
    # Verificar caracteres prohibidos del filesystem
    caracteres_encontrados = [c for c in CARACTERES_PROHIBIDOS_FILESYSTEM if c in nombre]
    if caracteres_encontrados:
        raise ValueError(
            f"El nombre contiene caracteres no permitidos: {', '.join(caracteres_encontrados)}"
        )
    
    return nombre


def sanitize_workspace_description(descripcion: str) -> str:
    """
    Sanitiza la descripción de un workspace
    
    Args:
        descripcion: Descripción del workspace
        
    Returns:
        Descripción sanitizada
    """
    return sanitize_text_input(descripcion, max_length=200, allow_newlines=False)


def sanitize_workspace_context(contexto: str) -> str:
    """
    Sanitiza el contexto de un workspace (permite más longitud y saltos de línea)
    
    Args:
        contexto: Contexto para análisis IA
        
    Returns:
        Contexto sanitizado
    """
    return sanitize_text_input(contexto, max_length=1000, allow_newlines=True)


def validate_hex_color(color: str) -> bool:
    """
    Valida que un color esté en formato hexadecimal válido (#RRGGBB)
    
    Args:
        color: String de color a validar
        
    Returns:
        True si es válido, False si no
    """
    if not color:
        return False
    
    patron = r'^#[0-9A-Fa-f]{6}$'
    return bool(re.match(patron, color))


def validate_categoria(categoria: str) -> bool:
    """
    Valida que la categoría sea una de las permitidas
    
    Args:
        categoria: Categoría a validar
        
    Returns:
        True si es válida
    """
    categorias_validas = [
        "deportes", "seguridad", "educacion", "eventos", 
        "industrial", "entretenimiento", "salud", "general"
    ]
    return categoria in categorias_validas


def validate_nivel_tolerancia(nivel: str) -> bool:
    """
    Valida que el nivel de tolerancia sea uno de los permitidos
    
    Args:
        nivel: Nivel de tolerancia a validar
        
    Returns:
        True si es válido
    """
    return nivel in ["bajo", "medio", "alto"]


def validate_workspace_name_length(nombre: str, min_len: int = 3, max_len: int = 50) -> bool:
    """
    Valida que el nombre del workspace tenga la longitud correcta
    
    Args:
        nombre: Nombre a validar
        min_len: Longitud mínima
        max_len: Longitud máxima
        
    Returns:
        True si la longitud es válida
    """
    return min_len <= len(nombre.strip()) <= max_len
