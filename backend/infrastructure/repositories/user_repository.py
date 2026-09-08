"""
Repositorio de Usuarios con Firestore
Persistencia permanente en Google Cloud Firestore
"""
from typing import List, Optional, Dict, Tuple
from threading import Lock
import logging

from domain.entities import Usuario, RolUsuario

logger = logging.getLogger(__name__)


def _normalize_username(value: str) -> str:
    return (value or "").strip().lower()


def _normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def _mask_identifier(value: str) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 2:
        return "*" * len(value)
    return f"{value[0]}***{value[-1]}"


class UsuarioRepositoryFirestore:
    """
    Repositorio de usuarios con persistencia en Firestore.
    
    Implementa el patrón Singleton con cache en memoria para rendimiento.
    Todos los cambios se persisten en Firestore automáticamente.
    
    Estructura en Firestore:
    - socios/{username} → Usuarios con rol SOCIO
    - administradores/{username} → Usuarios con rol ADMINISTRADOR
    """
    
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        """Implementación del patrón Singleton"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Inicializa el repositorio con conexión a Firestore"""
        if self._initialized:
            return
        
        self._cache: Dict[str, Usuario] = {}  # Cache por ID
        self._cache_username: Dict[str, Usuario] = {}  # Cache por username
        self._lock_repo = Lock()
        self._firestore = None
        self._initialized = True
        
        self._init_firestore()
        self._cargar_usuarios_desde_firestore()
    
    def _init_firestore(self):
        """Inicializa la conexión a Firestore"""
        try:
            from infrastructure.adapters.gcp_firestore import FirestoreAdapter
            from config.gcp_config import GCPConfig
            
            self._firestore = FirestoreAdapter(GCPConfig())
            
            if self._firestore.is_available():
                logger.info("✅ Repositorio de usuarios conectado a Firestore")
            else:
                logger.warning("⚠️ Firestore no disponible - usuarios solo en memoria")
        except Exception as e:
            logger.error(f"❌ Error conectando a Firestore: {e}")
            self._firestore = None
    
    def _cargar_usuarios_desde_firestore(self):
        """Carga usuarios existentes desde Firestore al cache"""
        if not self._firestore or not self._firestore.is_available():
            self._crear_usuarios_default()
            return
        
        try:
            # Cargar socios (límite de seguridad para evitar lectura completa en producción)
            socios = self._firestore.db.collection('socios').limit(10_000).stream()
            for doc in socios:
                data = doc.to_dict()
                usuario = self._dict_to_usuario(data)
                if usuario:
                    self._cache[usuario.id] = usuario
                    self._cache_username[_normalize_username(usuario.username)] = usuario
            
            logger.info(f"✅ Cargados {len(self._cache)} usuarios desde Firestore")
            
            # Si no hay usuarios, crear los por defecto
            if len(self._cache) == 0:
                self._crear_usuarios_default()
                
        except Exception as e:
            logger.error(f"❌ Error cargando usuarios: {e}")
            self._crear_usuarios_default()
    
    def _dict_to_usuario(self, data: Dict) -> Optional[Usuario]:
        """Convierte diccionario de Firestore a Usuario"""
        try:
            rol_str = data.get('rol', 'socio')
            rol = RolUsuario(rol_str) if isinstance(rol_str, str) else RolUsuario.SOCIO
            
            return Usuario(
                id=data.get('id', data.get('username', '')),
                username=data['username'],
                password_hash=data.get('password_hash', ''),
                nombre_completo=data.get('nombre_completo', ''),
                email=data.get('email', ''),
                rol=rol,
                activo=data.get('activo', True),
                azure_id=data.get('azure_id', ''),
                auth_provider=data.get('auth_provider', 'local'),
                foto_url=data.get('foto_url', ''),
                metadatos=data.get('metadatos', {}),
                notificaciones=data.get('notificaciones', [])
            )
        except Exception as e:
            logger.error(f"Error convirtiendo usuario: {e}")
            return None

    
    def _crear_usuarios_default(self):
        """Crea usuarios por defecto si no existen"""
        import os
        import uuid
        
        env = os.getenv('FLASK_ENV', 'development')
        
        if env == 'production':
            logger.info("⚠️ Producción: ejecuta init_firestore.py para crear usuarios")
            return
        
        # Solo en desarrollo
        # El rol ADMINISTRADOR ha sido eliminado del sistema
        
        if not self.existe_username('socio'):
            socio = Usuario(
                id=str(uuid.uuid4()),
                username="socio",
                password_hash=Usuario.hash_password("socio123"),
                nombre_completo="Usuario Socio",
                email="socio@accessfan.com",
                rol=RolUsuario.SOCIO
            )
            self.guardar(socio)
            logger.info("✅ Socio por defecto creado: socio/socio123")
    
    def guardar(self, usuario: Usuario) -> Usuario:
        """
        Guarda un usuario en Firestore y cache.
        DEPRECATED: Usar guardar_atomic() para nuevos usuarios.
        
        Args:
            usuario: Usuario a guardar
            
        Returns:
            Usuario guardado
        """
        with self._lock_repo:
            # Guardar en cache
            self._cache[usuario.id] = usuario
            self._cache_username[_normalize_username(usuario.username)] = usuario
            
            # Persistir en Firestore
            if self._firestore and self._firestore.is_available():
                try:
                    self._firestore.save_socio(usuario)
                    logger.info(
                        "✅ Usuario guardado en Firestore: %s",
                        _mask_identifier(_normalize_username(usuario.username)),
                    )
                except Exception as e:
                    logger.error(f"❌ Error guardando en Firestore: {e}")
            
            return usuario
    
    def guardar_atomic(self, usuario: Usuario) -> Tuple[bool, Optional[str], Optional[Usuario]]:
        """
        Guarda un usuario usando transacción atómica para prevenir race conditions.
        
        Args:
            usuario: Usuario a guardar
            
        Returns:
            Tuple[bool, Optional[str], Optional[Usuario]]: 
                (éxito, mensaje_error, usuario_guardado)
        """
        with self._lock_repo:
            # Verificar en cache primero (optimización)
            if _normalize_username(usuario.username) in self._cache_username:
                return False, "El username ya está registrado", None
            
            # Verificar email en cache
            for existing_user in self._cache.values():
                if _normalize_email(existing_user.email) == _normalize_email(usuario.email):
                    return False, "El email ya está registrado", None
            
            # Intentar guardar en Firestore con transacción atómica
            if self._firestore and self._firestore.is_available():
                success, error = self._firestore.save_socio_atomic(usuario)
                
                if not success:
                    return False, error, None
                
                # Si guardó exitosamente, actualizar cache
                self._cache[usuario.id] = usuario
                self._cache_username[_normalize_username(usuario.username)] = usuario
                
                logger.info(
                    "✅ Usuario creado atómicamente: %s",
                    _mask_identifier(_normalize_username(usuario.username)),
                )
                return True, None, usuario
            else:
                # Fallback: guardar solo en cache (modo sin Firestore)
                self._cache[usuario.id] = usuario
                self._cache_username[_normalize_username(usuario.username)] = usuario
                logger.warning("⚠️ Usuario guardado solo en cache (Firestore no disponible)")
                return True, None, usuario
    
    def crear(self, usuario: Usuario) -> Usuario:
        """Alias de guardar para compatibilidad"""
        return self.guardar(usuario)
    
    def obtener_por_id(self, usuario_id: str) -> Optional[Usuario]:
        """Obtiene usuario por ID"""
        with self._lock_repo:
            return self._cache.get(usuario_id)
    
    def obtener_por_username(self, username: str) -> Optional[Usuario]:
        """Obtiene usuario por username"""
        normalized_username = _normalize_username(username)
        with self._lock_repo:
            # Primero buscar en cache
            if normalized_username in self._cache_username:
                return self._cache_username[normalized_username]
            
            # Si no está en cache, buscar en Firestore
            if self._firestore and self._firestore.is_available():
                try:
                    # Buscar en socios
                    usuario = self._firestore.get_socio(username)
                    if usuario:
                        self._cache[usuario.id] = usuario
                        self._cache_username[_normalize_username(usuario.username)] = usuario
                        return usuario
                except Exception as e:
                    logger.error(f"Error buscando usuario: {e}")
            
            return None
    
    def obtener_por_email(self, email: str) -> Optional[Usuario]:
        """Obtiene usuario por email"""
        normalized_email = _normalize_email(email)
        with self._lock_repo:
            for usuario in self._cache.values():
                if _normalize_email(usuario.email) == normalized_email:
                    return usuario
            return None
    
    def obtener_todos(self) -> List[Usuario]:
        """Obtiene todos los usuarios"""
        with self._lock_repo:
            return list(self._cache.values())
    
    def obtener_por_rol(self, rol: RolUsuario) -> List[Usuario]:
        """Obtiene usuarios por rol"""
        with self._lock_repo:
            return [u for u in self._cache.values() if u.rol == rol]
    
    def obtener_socios(self) -> List[Usuario]:
        """Obtiene todos los socios"""
        return self.obtener_por_rol(RolUsuario.SOCIO)
    
    def autenticar(self, username: str, password: str) -> Optional[Usuario]:
        """
        Autentica un usuario.
        
        Args:
            username: Nombre de usuario
            password: Contraseña en texto plano
            
        Returns:
            Usuario si la autenticación es exitosa, None si falla
        """
        normalized_username = _normalize_username(username)
        usuario = self.obtener_por_username(normalized_username)
        if usuario and usuario.activo and usuario.verificar_password(password):
            logger.info("✅ Login exitoso: %s", _mask_identifier(normalized_username))
            return usuario
        
        logger.warning("❌ Login fallido: %s", _mask_identifier(normalized_username))
        return None
    
    def existe_username(self, username: str) -> bool:
        """Verifica si existe un username"""
        return self.obtener_por_username(username) is not None
    
    def existe_email(self, email: str) -> bool:
        """Verifica si existe un email"""
        return self.obtener_por_email(email) is not None
    
    def eliminar(self, usuario_id: str) -> bool:
        """Elimina un usuario"""
        with self._lock_repo:
            usuario = self._cache.get(usuario_id)
            if not usuario:
                return False
            
            # Eliminar de cache
            del self._cache[usuario_id]
            normalized_username = _normalize_username(usuario.username)
            if normalized_username in self._cache_username:
                del self._cache_username[_normalize_username(usuario.username)]
            
            # Eliminar de Firestore
            if self._firestore and self._firestore.is_available():
                try:
                    self._firestore.db.collection('socios').document(usuario.username).delete()
                    logger.info(
                        "✅ Usuario eliminado de Firestore: %s",
                        _mask_identifier(_normalize_username(usuario.username)),
                    )
                except Exception as e:
                    logger.error(f"❌ Error eliminando de Firestore: {e}")
            
            return True
    
    def contar_total(self) -> int:
        """Cuenta el total de usuarios"""
        with self._lock_repo:
            return len(self._cache)
    
    def contar_por_rol(self, rol: RolUsuario) -> int:
        """Cuenta usuarios por rol"""
        return len(self.obtener_por_rol(rol))


# Alias para compatibilidad con código existente
UsuarioRepositoryMemory = UsuarioRepositoryFirestore
