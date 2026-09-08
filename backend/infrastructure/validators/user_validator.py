"""
Validador robusto de usuarios
Implementa validaciones completas con prevención de race conditions
"""
import re
import logging
from typing import Optional, Tuple, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Resultado de una validación"""
    is_valid: bool
    error_message: Optional[str] = None
    field: Optional[str] = None


class UserValidator:
    """
    Validador de usuarios con reglas de negocio estrictas
    """
    
    # Patrones de validación
    USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_.-]{3,30}$')
    EMAIL_PATTERN = re.compile(
        r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    )
    
    # Dominios de email temporales/desechables comunes (blacklist)
    DISPOSABLE_EMAIL_DOMAINS = {
        'tempmail.com', 'guerrillamail.com', '10minutemail.com',
        'throwaway.email', 'temp-mail.org', 'mailinator.com',
        'trashmail.com', 'yopmail.com', 'fakeinbox.com'
    }
    
    # Palabras prohibidas en usernames
    RESERVED_USERNAMES = {
        'admin', 'administrator', 'root', 'system', 'moderator',
        'tivit', 'support', 'help', 'api', 'null', 'undefined',
        'test', 'demo', 'guest', 'public', 'private'
    }
    
    @staticmethod
    def normalize_username(username: str) -> str:
        """Normaliza un username (lowercase, trim)"""
        return (username or "").strip().lower()
    
    @staticmethod
    def normalize_email(email: str) -> str:
        """Normaliza un email (lowercase, trim)"""
        return (email or "").strip().lower()
    
    @classmethod
    def validate_username(cls, username: str) -> ValidationResult:
        """
        Valida el formato y contenido de un username
        
        Reglas:
        - 3-30 caracteres
        - Solo alfanuméricos, punto, guión bajo, guión medio
        - No puede ser una palabra reservada
        - No puede contener espacios
        """
        if not username:
            return ValidationResult(False, "El username es obligatorio", "username")
        
        # Normalizar
        username_normalized = cls.normalize_username(username)
        
        # Verificar longitud
        if len(username_normalized) < 3:
            return ValidationResult(
                False, 
                "El username debe tener al menos 3 caracteres", 
                "username"
            )
        
        if len(username_normalized) > 30:
            return ValidationResult(
                False, 
                "El username no puede tener más de 30 caracteres", 
                "username"
            )
        
        # Verificar formato
        if not cls.USERNAME_PATTERN.match(username_normalized):
            return ValidationResult(
                False,
                "El username solo puede contener letras, números, puntos, guiones bajos y guiones medios",
                "username"
            )
        
        # Verificar palabras reservadas
        if username_normalized in cls.RESERVED_USERNAMES:
            return ValidationResult(
                False,
                "Este username está reservado y no puede ser usado",
                "username"
            )
        
        # No puede empezar con punto o guión
        if username_normalized[0] in '.,-_':
            return ValidationResult(
                False,
                "El username no puede empezar con punto o guión",
                "username"
            )
        
        return ValidationResult(True)
    
    @classmethod
    def validate_email(cls, email: str) -> ValidationResult:
        """
        Valida el formato y dominio de un email
        
        Reglas:
        - Formato válido RFC 5322
        - No puede ser de dominio desechable
        - Máximo 254 caracteres (RFC 5321)
        """
        if not email:
            return ValidationResult(False, "El email es obligatorio", "email")
        
        # Normalizar
        email_normalized = cls.normalize_email(email)
        
        # Verificar longitud máxima (RFC 5321)
        if len(email_normalized) > 254:
            return ValidationResult(
                False,
                "El email no puede tener más de 254 caracteres",
                "email"
            )
        
        # Verificar formato básico
        if not cls.EMAIL_PATTERN.match(email_normalized):
            return ValidationResult(
                False,
                "El email debe tener un formato válido (ejemplo@dominio.com)",
                "email"
            )
        
        # Extraer dominio
        try:
            domain = email_normalized.split('@')[1]
        except IndexError:
            return ValidationResult(
                False,
                "El email debe contener un dominio válido",
                "email"
            )
        
        # Verificar dominios desechables
        if domain in cls.DISPOSABLE_EMAIL_DOMAINS:
            return ValidationResult(
                False,
                "No se permiten emails de dominios temporales o desechables",
                "email"
            )
        
        # Verificar que el dominio tenga al menos un punto
        if '.' not in domain:
            return ValidationResult(
                False,
                "El dominio del email debe ser válido",
                "email"
            )
        
        return ValidationResult(True)
    
    @classmethod
    def validate_password_strength(cls, password: str) -> ValidationResult:
        """
        Valida la fortaleza de una contraseña
        
        Reglas:
        - Mínimo 8 caracteres
        - Al menos una letra mayúscula
        - Al menos una letra minúscula
        - Al menos un número
        - No puede contener espacios
        - No puede ser una contraseña común
        """
        if not password:
            return ValidationResult(False, "La contraseña es obligatoria", "password")
        
        # Longitud mínima
        if len(password) < 8:
            return ValidationResult(
                False,
                "La contraseña debe tener al menos 8 caracteres",
                "password"
            )
        
        # Máximo razonable
        if len(password) > 128:
            return ValidationResult(
                False,
                "La contraseña no puede tener más de 128 caracteres",
                "password"
            )
        
        # No puede contener espacios
        if ' ' in password:
            return ValidationResult(
                False,
                "La contraseña no puede contener espacios",
                "password"
            )
        
        # Debe tener al menos una mayúscula
        if not any(c.isupper() for c in password):
            return ValidationResult(
                False,
                "La contraseña debe contener al menos una letra mayúscula",
                "password"
            )
        
        # Debe tener al menos una minúscula
        if not any(c.islower() for c in password):
            return ValidationResult(
                False,
                "La contraseña debe contener al menos una letra minúscula",
                "password"
            )
        
        # Debe tener al menos un número
        if not any(c.isdigit() for c in password):
            return ValidationResult(
                False,
                "La contraseña debe contener al menos un número",
                "password"
            )
        
        # Lista de contraseñas comunes prohibidas
        common_passwords = {
            'password', '12345678', 'qwerty123', 'abc123456',
            'password1', 'password123', 'admin123', 'welcome1',
            '1q2w3e4r', 'qwertyuiop', 'Aa123456', 'Password1'
        }
        
        if password.lower() in common_passwords:
            return ValidationResult(
                False,
                "Esta contraseña es muy común y no puede ser usada",
                "password"
            )
        
        return ValidationResult(True)
    
    @classmethod
    def validate_nombre_completo(cls, nombre_completo: str) -> ValidationResult:
        """
        Valida el nombre completo
        
        Reglas:
        - Mínimo 2 caracteres
        - Máximo 100 caracteres
        - Solo letras, espacios, apóstrofes, guiones
        """
        if not nombre_completo:
            return ValidationResult(
                False,
                "El nombre completo es obligatorio",
                "nombre_completo"
            )
        
        nombre = nombre_completo.strip()
        
        if len(nombre) < 2:
            return ValidationResult(
                False,
                "El nombre completo debe tener al menos 2 caracteres",
                "nombre_completo"
            )
        
        if len(nombre) > 100:
            return ValidationResult(
                False,
                "El nombre completo no puede tener más de 100 caracteres",
                "nombre_completo"
            )
        
        # Verificar caracteres permitidos
        allowed_pattern = re.compile(r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s'-]+$")
        if not allowed_pattern.match(nombre):
            return ValidationResult(
                False,
                "El nombre solo puede contener letras, espacios, apóstrofes y guiones",
                "nombre_completo"
            )
        
        return ValidationResult(True)
    
    @classmethod
    def validate_all_for_registration(
        cls,
        username: str,
        email: str,
        password: str,
        nombre_completo: str
    ) -> Tuple[bool, List[ValidationResult]]:
        """
        Valida todos los campos para registro de usuario
        
        Returns:
            Tuple[bool, List[ValidationResult]]: (es_valido, lista_de_errores)
        """
        results = []
        
        # Validar username
        username_result = cls.validate_username(username)
        if not username_result.is_valid:
            results.append(username_result)
        
        # Validar email
        email_result = cls.validate_email(email)
        if not email_result.is_valid:
            results.append(email_result)
        
        # Validar contraseña
        password_result = cls.validate_password_strength(password)
        if not password_result.is_valid:
            results.append(password_result)
        
        # Validar nombre completo
        nombre_result = cls.validate_nombre_completo(nombre_completo)
        if not nombre_result.is_valid:
            results.append(nombre_result)
        
        is_valid = len(results) == 0
        return is_valid, results
