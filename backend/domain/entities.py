"""
Entidades del dominio - Reglas de negocio puras
No depende de frameworks externos, solo Python estándar
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum
import hashlib
import hmac
import os


class EstadoVideo(Enum):
    """Estados posibles de un video"""

    PENDIENTE = "pendiente"
    PROCESANDO = "procesando"
    EN_REVISION = "en_revision"  # Nuevo: requiere revisión humana
    APROBADO = "aprobado"  # Nuevo: aprobado por admin
    RECHAZADO = "rechazado"  # Nuevo: rechazado por admin
    COMPLETADO = "completado"
    ERROR = "error"


class EstadoSecurityVideo(Enum):
    """Estados posibles de un video de seguridad"""

    UPLOADING = "uploading"  # Subiendo a Cloud Storage
    UPLOADED = "uploaded"  # Subido, listo para procesar
    MOTION_DETECTING = "motion_detecting"  # Detectando movimiento con OpenCV
    MOTION_DETECTED = "motion_detected"  # Movimiento detectado, clips extraídos
    ANALYZING = "analyzing"  # Análisis completo de todos los segmentos
    GENERATING_REPORT = "generating_report"  # Generando reporte
    COMPLETED = "completed"  # Completado con análisis y reporte
    ERROR = "error"  # Error en el procesamiento


# ClasificacionEvento eliminado - ahora todos los eventos se analizan objetivamente sin clasificación previa


class RolUsuario(Enum):
    """Roles de usuario en el sistema"""

    SOCIO = "socio"


@dataclass
class Video:
    """
    Entidad Video - Representa un video en el sistema

    Attributes:
        id: Identificador único del video
        usuario: Nombre o ID del usuario propietario
        ruta_archivo: Ruta donde se almacena el archivo de video
        descripcion: Descripción/título del contenido del video
        metadatos_ia: Diccionario con metadatos generados por IA
        estado: Estado actual del video en el procesamiento
        nombre_archivo: Nombre original del archivo subido
        workspace_id: ID del workspace al que pertenece
        fecha_creacion: Fecha y hora de creación del video (ISO format)
    """

    id: str
    usuario: str
    ruta_archivo: str
    descripcion: str
    metadatos_ia: Dict[str, Any] = field(default_factory=dict)
    estado: EstadoVideo = EstadoVideo.PENDIENTE
    nombre_archivo: str = ""  # Nombre original del archivo
    workspace_id: str = "general"  # ID del workspace al que pertenece este video
    fecha_creacion: Optional[str] = None  # Fecha de creación en formato ISO

    @property
    def formato(self) -> str:
        """Obtiene el formato/extensión del video desde el nombre del archivo"""
        if self.nombre_archivo:
            from pathlib import Path

            suffix = Path(self.nombre_archivo).suffix.lower()
            return suffix[1:] if suffix.startswith(".") else suffix
        if self.ruta_archivo:
            from pathlib import Path

            suffix = Path(self.ruta_archivo).suffix.lower()
            return suffix[1:] if suffix.startswith(".") else suffix
        return "mp4"  # Default

    @property
    def socio_id(self) -> str:
        """Alias para usuario (compatibilidad con código existente)"""
        return self.usuario

    def __post_init__(self):
        """Validaciones de reglas de negocio"""
        if not self.id or not isinstance(self.id, str):
            raise ReglaNegocioException("El ID del video debe ser una cadena no vacía")

        if not self.usuario or not isinstance(self.usuario, str):
            raise ReglaNegocioException("El usuario debe ser una cadena no vacía")

        if not self.ruta_archivo or not isinstance(self.ruta_archivo, str):
            raise ReglaNegocioException(
                "La ruta del archivo debe ser una cadena no vacía"
            )

        if not isinstance(self.metadatos_ia, dict):
            raise ReglaNegocioException("Los metadatos_ia deben ser un diccionario")

        # Si no hay nombre_archivo, extraerlo de la ruta
        if not self.nombre_archivo and self.ruta_archivo:
            from pathlib import Path

            self.nombre_archivo = Path(self.ruta_archivo).name

        if not isinstance(self.estado, EstadoVideo):
            raise ReglaNegocioException(
                "El estado debe ser una instancia de EstadoVideo"
            )

    def actualizar_estado(self, nuevo_estado: EstadoVideo) -> None:
        """
        Actualiza el estado del video siguiendo las reglas de negocio

        Args:
            nuevo_estado: Nuevo estado a asignar

        Raises:
            ReglaNegocioException: Si la transición de estado no es válida
        """
        transiciones_validas = {
            EstadoVideo.PENDIENTE: [EstadoVideo.PROCESANDO, EstadoVideo.ERROR],
            EstadoVideo.PROCESANDO: [
                EstadoVideo.COMPLETADO,
                EstadoVideo.EN_REVISION,
                EstadoVideo.APROBADO,
                EstadoVideo.RECHAZADO,
                EstadoVideo.ERROR,
            ],
            EstadoVideo.EN_REVISION: [EstadoVideo.APROBADO, EstadoVideo.RECHAZADO],
            EstadoVideo.APROBADO: [EstadoVideo.COMPLETADO],
            EstadoVideo.RECHAZADO: [EstadoVideo.PENDIENTE],  # Puede reintentar
            EstadoVideo.COMPLETADO: [],
            EstadoVideo.ERROR: [EstadoVideo.PENDIENTE, EstadoVideo.RECHAZADO, EstadoVideo.APROBADO],  # Puede reintentarse o finalizar
        }

        if nuevo_estado not in transiciones_validas[self.estado]:
            raise ReglaNegocioException(
                f"Transición inválida de {self.estado.value} a {nuevo_estado.value}"
            )

        self.estado = nuevo_estado

    def agregar_metadatos(self, clave: str, valor: Any) -> None:
        """
        Agrega metadatos generados por IA

        Args:
            clave: Clave del metadato
            valor: Valor del metadato
        """
        if not isinstance(clave, str) or not clave:
            raise ReglaNegocioException(
                "La clave del metadato debe ser una cadena no vacía"
            )

        self.metadatos_ia[clave] = valor

    def es_completado(self) -> bool:
        """Verifica si el video ha sido procesado completamente"""
        return self.estado == EstadoVideo.COMPLETADO

    def tiene_error(self) -> bool:
        """Verifica si el video tiene un error"""
        return self.estado == EstadoVideo.ERROR

    def esta_en_revision(self) -> bool:
        """Verifica si el video está pendiente de revisión humana"""
        return self.estado == EstadoVideo.EN_REVISION

    def esta_aprobado(self) -> bool:
        """Verifica si el video fue aprobado por un admin"""
        return self.estado == EstadoVideo.APROBADO

    def esta_rechazado(self) -> bool:
        """Verifica si el video fue rechazado por un admin"""
        return self.estado == EstadoVideo.RECHAZADO

    def aprobar(self, admin_usuario: str, comentario: str = "") -> None:
        """
        Aprueba el video (acción de admin)

        Args:
            admin_usuario: Usuario admin que aprueba
            comentario: Comentario opcional
        """
        if self.estado != EstadoVideo.EN_REVISION:
            raise ReglaNegocioException(
                f"Solo se pueden aprobar videos EN_REVISION. Estado actual: {self.estado.value}"
            )
        self.actualizar_estado(EstadoVideo.APROBADO)
        self.agregar_metadatos("aprobado_por", admin_usuario)
        self.agregar_metadatos("comentario_admin", comentario)
        self.agregar_metadatos("fecha_aprobacion", None)  # Se llena en el use case

    def rechazar(self, admin_usuario: str, razon: str) -> None:
        """
        Rechaza el video (acción de admin)

        Args:
            admin_usuario: Usuario admin que rechaza
            razon: Razón del rechazo (obligatoria)
        """
        if self.estado != EstadoVideo.EN_REVISION:
            raise ReglaNegocioException(
                f"Solo se pueden rechazar videos EN_REVISION. Estado actual: {self.estado.value}"
            )
        if not razon or not razon.strip():
            raise ReglaNegocioException("La razón del rechazo es obligatoria")
        self.actualizar_estado(EstadoVideo.RECHAZADO)
        self.agregar_metadatos("rechazado_por", admin_usuario)
        self.agregar_metadatos("razon_rechazo_admin", razon)
        self.agregar_metadatos("fecha_rechazo", None)  # Se llena en el use case

    def solicitar_revision_manual(self, motivo: str = "") -> None:
        """
        Marca el video para revisión manual solicitada por el usuario

        Args:
            motivo: Motivo de la solicitud (opcional)
        """
        if self.estado not in [
            EstadoVideo.ERROR,
            EstadoVideo.COMPLETADO,
            EstadoVideo.RECHAZADO,
        ]:
            raise ReglaNegocioException(
                f"Solo se puede solicitar revisión en videos COMPLETADOS, RECHAZADOS o con ERROR. Estado actual: {self.estado.value}"
            )

        self.agregar_metadatos("solicitud_revision_manual", True)
        self.agregar_metadatos("motivo_solicitud_revision", motivo)
        self.agregar_metadatos(
            "fecha_solicitud_revision", None
        )  # Se llena en el use case
        # Cambiar estado a EN_REVISION
        if self.estado in [
            EstadoVideo.ERROR,
            EstadoVideo.COMPLETADO,
            EstadoVideo.RECHAZADO,
        ]:
            self.estado = EstadoVideo.EN_REVISION


class ReglaNegocioException(Exception):
    """
    Excepción personalizada para violaciones de reglas de negocio

    Esta excepción se lanza cuando se intenta realizar una operación
    que viola las reglas de negocio del dominio.
    """

    def __init__(self, mensaje: str):
        self.mensaje = mensaje
        super().__init__(self.mensaje)

    def __str__(self) -> str:
        return f"Violación de regla de negocio: {self.mensaje}"


@dataclass
class Workspace:
    """
    Entidad Workspace - Representa un proyecto/carpeta para organizar videos
    
    Attributes:
        id: Identificador único del workspace
        usuario: Owner/creador del workspace
        nombre: Nombre del workspace (3-50 caracteres)
        descripcion: Descripción opcional del workspace
        contexto: Contexto compartido para análisis IA de todos los videos
        fecha_creacion: Timestamp de creación
        fecha_modificacion: Timestamp de última modificación
        es_general: True si es el workspace "General" por defecto
        color: Color hex para UI (#RRGGBB)
        orden: Orden manual para sorting
        estadisticas: Stats calculadas del workspace
        permisos: Lista de permisos (futuro: compartir workspaces)
        visibilidad: privado|compartido|publico
        metadatos: Información adicional
    """
    
    id: str
    usuario: str
    nombre: str
    descripcion: str = ""
    contexto: str = ""
    categoria: str = "general"  # deportes|seguridad|educacion|eventos|industrial|entretenimiento|salud|general
    tipo_contenido: str = ""  # Tipo específico de videos (ej: "partidos de fútbol", "vigilancia nocturna")
    elementos_visuales: str = ""  # Elementos comunes esperados (ej: "cascos, uniforme rojo, balón")
    nivel_tolerancia: str = "medio"  # bajo|medio|alto - Qué tan estricto debe ser el análisis
    fecha_creacion: str = ""
    fecha_modificacion: str = ""
    es_general: bool = False
    es_exhaustivo: bool = False
    color: str = "#3B82F6"
    icono_url: str = ""  # URL de la imagen del icono del proyecto
    orden: int = 0
    
    # Soft Delete
    eliminado: bool = False  # True si el workspace fue eliminado (soft delete)
    fecha_eliminacion: str = ""  # Timestamp de cuándo fue eliminado
    eliminado_por: str = ""  # Usuario que eliminó el workspace
    
    # Estadísticas calculadas
    estadisticas: Dict[str, Any] = field(default_factory=lambda: {
        "total_videos": 0,
        "aprobados": 0,
        "rechazados": 0,
        "en_revision": 0,
        "duracion_total_segundos": 0,
        "ultima_actividad": ""
    })
    
    # Permisos (para futuras funcionalidades de compartir)
    permisos: List[Dict[str, str]] = field(default_factory=list)
    visibilidad: str = "privado"  # privado|compartido|publico
    
    metadatos: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validaciones de reglas de negocio"""
        # Validar nombre
        if not isinstance(self.nombre, str) or not self.nombre.strip():
            raise ReglaNegocioException("El nombre del workspace es obligatorio")
        
        nombre_stripped = self.nombre.strip()
        if not (3 <= len(nombre_stripped) <= 50):
            raise ReglaNegocioException(
                "El nombre del workspace debe tener entre 3 y 50 caracteres"
            )
        
        # Validar contexto
        if self.contexto and len(self.contexto) > 1000:
            raise ReglaNegocioException(
                "El contexto no puede exceder 1000 caracteres"
            )
        
        # Validar color (formato hex básico)
        if self.color and not (self.color.startswith("#") and len(self.color) == 7):
            raise ReglaNegocioException(
                "El color debe estar en formato hexadecimal (#RRGGBB)"
            )
        
        # Validar visibilidad
        if self.visibilidad not in ["privado", "compartido", "publico"]:
            raise ReglaNegocioException(
                "La visibilidad debe ser: privado, compartido o publico"
            )
        
        # Validar categoria
        categorias_validas = ["deportes", "seguridad", "educacion", "eventos", "industrial", "entretenimiento", "salud", "general"]
        if self.categoria and self.categoria not in categorias_validas:
            raise ReglaNegocioException(
                f"La categoría debe ser una de: {', '.join(categorias_validas)}"
            )
        
        # Validar nivel_tolerancia
        if self.nivel_tolerancia and self.nivel_tolerancia not in ["bajo", "medio", "alto"]:
            raise ReglaNegocioException(
                "El nivel de tolerancia debe ser: bajo, medio o alto"
            )
    
    def actualizar_estadisticas(
        self,
        total_videos: int = 0,
        aprobados: int = 0,
        rechazados: int = 0,
        en_revision: int = 0,
        duracion_total: int = 0,
        ultima_actividad: str = ""
    ) -> None:
        """Actualiza las estadísticas del workspace"""
        self.estadisticas = {
            "total_videos": total_videos,
            "aprobados": aprobados,
            "rechazados": rechazados,
            "en_revision": en_revision,
            "duracion_total_segundos": duracion_total,
            "ultima_actividad": ultima_actividad
        }
    
    def es_propietario(self, usuario: str) -> bool:
        """Verifica si el usuario es propietario del workspace"""
        return self.usuario == usuario
    
    def puede_editar(self, usuario: str) -> bool:
        """Verifica si el usuario puede editar el workspace"""
        # Propietario siempre puede editar
        if self.es_propietario(usuario):
            return True
        
        # Verificar permisos explícitos (futuro)
        for permiso in self.permisos:
            if permiso.get("usuario") == usuario and permiso.get("rol") in ["editor", "admin"]:
                return True
        
        return False
    
    def puede_eliminar(self, usuario: str) -> bool:
        """Verifica si el usuario puede eliminar el workspace"""
        # Solo el propietario o admins explícitos pueden eliminar
        if self.es_propietario(usuario):
            return True
        
        for permiso in self.permisos:
            if permiso.get("usuario") == usuario and permiso.get("rol") == "admin":
                return True
        
        return False


@dataclass
class Notificacion:
    """
    Entidad Notificacion - Mensaje del sistema para el usuario

    Attributes:
        id: Identificador único de la notificación
        tipo: Tipo de notificación (info, warning, success, error, message)
        titulo: Título breve de la notificación
        mensaje: Contenido del mensaje
        fecha: Fecha y hora de creación
        leida: Si la notificación ha sido leída
        origen: Quién envió la notificación (sistema, admin username, etc.)
        video_id: ID del video relacionado (opcional)
    """

    id: str
    tipo: str  # info, warning, success, error, message
    titulo: str
    mensaje: str
    fecha: str
    leida: bool = False
    origen: str = "sistema"
    video_id: Optional[str] = None

    def marcar_leida(self):
        """Marca la notificación como leída"""
        self.leida = True

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario"""
        return {
            "id": self.id,
            "tipo": self.tipo,
            "titulo": self.titulo,
            "mensaje": self.mensaje,
            "fecha": self.fecha,
            "leida": self.leida,
            "origen": self.origen,
            "video_id": self.video_id,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "Notificacion":
        """Crea una notificación desde un diccionario"""
        return Notificacion(
            id=data.get("id", ""),
            tipo=data.get("tipo", "info"),
            titulo=data.get("titulo", ""),
            mensaje=data.get("mensaje", ""),
            fecha=data.get("fecha", ""),
            leida=data.get("leida", False),
            origen=data.get("origen", "sistema"),
            video_id=data.get("video_id"),
        )


@dataclass
class Usuario:
    """
    Entidad Usuario - Representa un usuario del sistema

    Attributes:
        id: Identificador único del usuario
        username: Nombre de usuario (único)
        password_hash: Hash de la contraseña (vacío para usuarios Azure AD)
        nombre_completo: Nombre completo del usuario
        email: Email del usuario
        rol: Rol del usuario en el sistema
        activo: Indica si el usuario está activo
        azure_id: OID del usuario en Azure AD/Entra ID (solo usuarios SSO)
        auth_provider: Proveedor de autenticación ('local' o 'azure_ad')
        metadatos: Información adicional del usuario
        notificaciones: Lista de notificaciones del usuario
        fecha_creacion: Fecha de creación del usuario (ISO 8601)
        ultimo_acceso: Fecha del último acceso del usuario (ISO 8601)
    """

    id: str
    username: str
    nombre_completo: str
    email: str
    rol: RolUsuario
    password_hash: str = ""  # Vacío para usuarios Azure AD
    activo: bool = True
    azure_id: str = ""  # OID de Microsoft (solo usuarios SSO)
    auth_provider: str = "local"  # 'local' | 'azure_ad'
    foto_url: str = ""  # URL de la foto de perfil en GCS
    metadatos: Dict[str, Any] = field(default_factory=dict)
    notificaciones: List[Dict[str, Any]] = field(default_factory=list)
    fecha_creacion: str = ""
    ultimo_acceso: str = ""

    def __post_init__(self):
        """Validaciones de reglas de negocio"""
        if not self.id or not isinstance(self.id, str):
            raise ReglaNegocioException(
                "El ID del usuario debe ser una cadena no vacía"
            )

        if not self.username or not isinstance(self.username, str):
            raise ReglaNegocioException("El username debe ser una cadena no vacía")

        if len(self.username) < 3:
            raise ReglaNegocioException("El username debe tener al menos 3 caracteres")

        # password_hash solo es obligatorio para usuarios locales
        if self.auth_provider == "local" and not self.password_hash:
            raise ReglaNegocioException("El password_hash es obligatorio para usuarios locales")

        if not self.email or not isinstance(self.email, str):
            raise ReglaNegocioException("El email debe ser una cadena no vacía")

        # Validación de email robusta con regex
        import re

        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, self.email):
            raise ReglaNegocioException(
                "El email debe tener un formato válido (ej: usuario@dominio.com)"
            )

        if not isinstance(self.rol, RolUsuario):
            raise ReglaNegocioException("El rol debe ser una instancia de RolUsuario")

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Genera un hash de la contraseña usando bcrypt (seguro con salt automático)

        Args:
            password: Contraseña en texto plano

        Returns:
            str: Hash bcrypt de la contraseña
        """
        import bcrypt

        rounds_env = os.getenv("BCRYPT_ROUNDS", "12")
        try:
            rounds = int(rounds_env)
        except ValueError:
            rounds = 12
        rounds = max(10, min(rounds, 14))

        salt = bcrypt.gensalt(rounds=rounds)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    def verificar_password(self, password: str) -> bool:
        """
        Verifica si una contraseña coincide con el hash almacenado
        Soporta tanto bcrypt (nuevo) como SHA256 (legacy) para migración

        Args:
            password: Contraseña a verificar

        Returns:
            bool: True si la contraseña es correcta
        """
        import bcrypt

        if not password:
            return False

        # Detectar si es hash bcrypt (empieza con $2b$) o SHA256 legacy (64 chars hex)
        if self.password_hash.startswith("$2b$") or self.password_hash.startswith(
            "$2a$"
        ):
            # Hash bcrypt
            try:
                return bcrypt.checkpw(
                    password.encode("utf-8"), self.password_hash.encode("utf-8")
                )
            except ValueError:
                return False
        else:
            # Hash SHA256 legacy - verificar y migrar automáticamente a bcrypt
            legacy_hash = hashlib.sha256(password.encode()).hexdigest()
            is_valid = hmac.compare_digest(self.password_hash, legacy_hash)
            if is_valid:
                # Auto-migrar a bcrypt
                rounds_env = os.getenv("BCRYPT_ROUNDS", "12")
                try:
                    rounds = int(rounds_env)
                except ValueError:
                    rounds = 12
                rounds = max(10, min(rounds, 14))
                salt = bcrypt.gensalt(rounds=rounds)
                self.password_hash = bcrypt.hashpw(
                    password.encode("utf-8"), salt
                ).decode("utf-8")
            return is_valid

    def es_socio(self) -> bool:
        """Verifica si el usuario es socio"""
        return self.rol == RolUsuario.SOCIO

    def desactivar(self) -> None:
        """Desactiva el usuario"""
        self.activo = False

    def activar(self) -> None:
        """Activa el usuario"""
        self.activo = True

    def agregar_notificacion(
        self,
        tipo: str,
        titulo: str,
        mensaje: str,
        origen: str = "sistema",
        video_id: str = None,
    ) -> Dict[str, Any]:
        """
        Agrega una notificación al usuario

        Args:
            tipo: Tipo de notificación (info, warning, success, error, message)
            titulo: Título de la notificación
            mensaje: Contenido del mensaje
            origen: Quién envía la notificación
            video_id: ID del video relacionado (opcional)

        Returns:
            Dict con la notificación creada
        """
        import uuid
        from datetime import datetime

        notificacion = {
            "id": str(uuid.uuid4()),
            "tipo": tipo,
            "titulo": titulo,
            "mensaje": mensaje,
            "fecha": datetime.now().isoformat(),
            "leida": False,
            "origen": origen,
            "video_id": video_id,
        }

        self.notificaciones.append(notificacion)
        return notificacion

    def marcar_notificacion_leida(self, notificacion_id: str) -> bool:
        """
        Marca una notificación como leída

        Args:
            notificacion_id: ID de la notificación

        Returns:
            bool: True si se marcó correctamente
        """
        for notif in self.notificaciones:
            if notif.get("id") == notificacion_id:
                notif["leida"] = True
                return True
        return False

    def marcar_todas_notificaciones_leidas(self) -> int:
        """
        Marca todas las notificaciones como leídas

        Returns:
            int: Número de notificaciones marcadas
        """
        count = 0
        for notif in self.notificaciones:
            if not notif.get("leida", False):
                notif["leida"] = True
                count += 1
        return count

    def eliminar_notificacion(self, notificacion_id: str) -> bool:
        """
        Elimina una notificación

        Args:
            notificacion_id: ID de la notificación

        Returns:
            bool: True si se eliminó correctamente
        """
        for i, notif in enumerate(self.notificaciones):
            if notif.get("id") == notificacion_id:
                self.notificaciones.pop(i)
                return True
        return False

    def obtener_notificaciones_no_leidas(self) -> List[Dict[str, Any]]:
        """Obtiene las notificaciones no leídas"""
        return [n for n in self.notificaciones if not n.get("leida", False)]

    def contar_notificaciones_no_leidas(self) -> int:
        """Cuenta las notificaciones no leídas"""
        return len(self.obtener_notificaciones_no_leidas())


# ========== ENTIDADES PARA ANÁLISIS DE SEGURIDAD ==========


@dataclass
class EventoSeguridad:
    """
    Representa un evento detectado en un video de seguridad (análisis objetivo sin clasificación)

    Attributes:
        id: Identificador único del evento
        security_video_id: ID del video de seguridad al que pertenece
        timestamp_inicio: Timestamp de inicio del evento (en segundos)
        timestamp_fin: Timestamp de fin del evento (en segundos)
        duracion: Duración del evento en segundos
        objetos_detectados: Lista de objetos detectados ["persona", "vehiculo", etc]
        acciones_detectadas: Lista de acciones detectadas ["caminar", "correr", etc]
        personas_count: Cantidad de personas detectadas
        vehiculos_count: Cantidad de vehículos detectados
        descripcion: Descripción objetiva generada por IA
        confianza: Nivel de confianza de la detección (0.0-1.0)
        analisis_detallado: Análisis completo de Video Intelligence + Gemini
        clip_url: URL del clip de video del evento
        frames_urls: URLs de frames clave del evento
        metadata: Metadata adicional (iluminación, calidad, etc)
    """

    id: str
    security_video_id: str
    timestamp_inicio: float
    timestamp_fin: float
    duracion: float
    objetos_detectados: List[str] = field(default_factory=list)
    acciones_detectadas: List[str] = field(default_factory=list)
    personas_count: int = 0
    vehiculos_count: int = 0
    descripcion: str = ""
    confianza: float = 0.0
    analisis_detallado: Dict[str, Any] = field(default_factory=dict)
    clip_url: str = ""
    frames_urls: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validaciones"""
        if not 0.0 <= self.confianza <= 1.0:
            raise ReglaNegocioException(
                "La confianza debe estar entre 0.0 y 1.0"
            )
        if self.duracion <= 0:
            raise ReglaNegocioException("La duración debe ser positiva")
        if self.personas_count < 0:
            raise ReglaNegocioException("El conteo de personas no puede ser negativo")
        if self.vehiculos_count < 0:
            raise ReglaNegocioException("El conteo de vehículos no puede ser negativo")


@dataclass
class SecurityVideo:
    """
    Entidad para videos de cámaras de seguridad (videos largos: 12h+)

    Attributes:
        id: Identificador único
        usuario: Usuario que subió el video
        nombre_camara: Nombre/identificador de la cámara
        ubicacion: Ubicación física de la cámara
        fecha_grabacion: Fecha de grabación del video (ISO format)
        duracion_segundos: Duración total en segundos
        ruta_gcs: Ruta en Google Cloud Storage (gs://bucket/path)
        estado: Estado del procesamiento
        metadata_tecnico: Metadata técnico (resolución, fps, codec, etc)
        eventos: Lista de eventos detectados
        estadisticas: Estadísticas del análisis
        reporte_txt_url: URL del reporte en formato TXT
        reporte_pdf_url: URL del reporte en formato PDF
        fecha_creacion: Fecha de creación del registro (ISO format)
        fecha_procesamiento: Fecha de procesamiento (ISO format)
        tiempo_procesamiento_segundos: Tiempo que tomó el procesamiento
        configuracion: Configuración usada en el análisis
    """

    id: str
    usuario: str
    nombre_camara: str
    ubicacion: str
    fecha_grabacion: str
    duracion_segundos: float
    ruta_gcs: str
    estado: EstadoSecurityVideo = EstadoSecurityVideo.UPLOADING
    metadata_tecnico: Dict[str, Any] = field(default_factory=dict)
    eventos: List[str] = field(default_factory=list)  # IDs de eventos
    estadisticas: Dict[str, Any] = field(default_factory=dict)
    reporte_txt_url: str = ""
    reporte_pdf_url: str = ""
    fecha_creacion: Optional[str] = None
    fecha_procesamiento: Optional[str] = None
    tiempo_procesamiento_segundos: Optional[float] = None
    configuracion: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validaciones"""
        if not self.id:
            raise ReglaNegocioException("El ID del video de seguridad es requerido")
        if not self.usuario:
            raise ReglaNegocioException("El usuario es requerido")
        # Permitir duracion_segundos = 0 durante el upload, se actualizará después
        if self.duracion_segundos < 0:
            raise ReglaNegocioException("La duración no puede ser negativa")
        if not self.ruta_gcs.startswith("gs://"):
            raise ReglaNegocioException(
                "La ruta GCS debe empezar con gs://"
            )

    def agregar_evento(self, evento_id: str):
        """Agrega un evento al video"""
        if evento_id not in self.eventos:
            self.eventos.append(evento_id)

    def actualizar_estado(self, nuevo_estado: EstadoSecurityVideo):
        """Actualiza el estado del video"""
        self.estado = nuevo_estado

    def esta_completado(self) -> bool:
        """Verifica si el procesamiento está completado"""
        return self.estado == EstadoSecurityVideo.COMPLETED

    def get_total_eventos(self) -> int:
        """Retorna el número total de eventos analizados"""
        return len(self.eventos)

    def get_duracion_analizada(self) -> float:
        """Retorna la duración total analizada en segundos"""
        return self.estadisticas.get("duracion_analizada_segundos", 0.0)

    def get_objetos_detectados(self) -> List[str]:
        """Retorna lista de objetos únicos detectados"""
        return self.estadisticas.get("objetos_unicos", [])

    def get_acciones_detectadas(self) -> List[str]:
        """Retorna lista de acciones únicas detectadas"""
        return self.estadisticas.get("acciones_unicas", [])

    def tiene_eventos_importantes(self) -> bool:
        """Verifica si hay eventos importantes detectados"""
        return self.estadisticas.get("eventos_importantes", 0) > 0


# ═══════════════════════════════════════════════════════════════
# ENTIDADES DE ANÁLISIS OPERATIVO
# ═══════════════════════════════════════════════════════════════

class EstadoOperationalAnalysis(Enum):
    """Estados del pipeline de análisis operativo"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    SCANNING = "scanning"
    ANALYZING = "analyzing"
    CROSS_ANALYZING = "cross_analyzing"
    GENERATING_REPORT = "generating_report"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


# Tipos de análisis operativo disponibles
# Límite de caracteres para contexto personalizado
MAX_CUSTOM_CONTEXT_LENGTH = 2000
_MAX_INLINE_EVENT_IDS = 300   # prevent Firestore 1 MB document limit; events stored separately

OPERATIONAL_ANALYSIS_TYPES = {
    "ACCESS_CONTROL": {
        "name": "Control de Acceso",
        "description": "Contar entradas/salidas, uso de fotcheck, accesos no autorizados",
        "icon": "🚪",
        "key_metrics": ["Entradas únicas", "Salidas únicas", "Cumplimiento fotcheck", "Accesos no autorizados"],
        "estimated_minutes_per_hour": 8
    },
    "OCCUPANCY": {
        "name": "Aforo",
        "description": "Personas simultáneas en un espacio, capacidad máxima, alertas de exceso",
        "icon": "👥",
        "key_metrics": ["Ocupación máxima", "Ocupación promedio", "Hora pico", "Alertas de exceso"],
        "estimated_minutes_per_hour": 7
    },
    "PEOPLE_FLOW": {
        "name": "Flujo de Personas",
        "description": "Tráfico por hora, horarios pico, patrones de uso",
        "icon": "🕐",
        "key_metrics": ["Personas totales", "Flujo por hora", "Hora pico", "Cuellos de botella"],
        "estimated_minutes_per_hour": 7
    },
    "MERCHANDISE_CONTROL": {
        "name": "Control de Mercancía",
        "description": "Objetos que entran/salen, cargas/descargas",
        "icon": "📦",
        "key_metrics": ["Objetos ingresados", "Objetos retirados", "Objetos sin supervisión", "Eventos de carga"],
        "estimated_minutes_per_hour": 9
    },
    "PARKING": {
        "name": "Estacionamiento",
        "description": "Vehículos que entran/salen, ocupación, permanencia",
        "icon": "🅿️",
        "key_metrics": ["Vehículos ingresados", "Vehículos retirados", "Ocupación máxima", "Hora pico"],
        "estimated_minutes_per_hour": 6
    },
    "WORK_SUPERVISION": {
        "name": "Supervisión de Obra/Trabajo",
        "description": "Trabajadores presentes, uso de EPP, actividad vs inactividad",
        "icon": "🏗️",
        "key_metrics": ["Trabajadores identificados", "Cumplimiento EPP", "Violaciones de seguridad", "Actividad vs inactividad"],
        "estimated_minutes_per_hour": 10
    }
}


@dataclass
class OperationalEvent:
    """Evento individual detectado en un análisis operativo"""
    id: str
    analysis_id: str
    timestamp_start: float = 0.0
    timestamp_end: float = 0.0
    event_type: str = ""         # ENTRY, EXIT, FOTCHECK_USED, FOTCHECK_SKIPPED, MOVEMENT, etc.
    scanner_event_type: str = "" # Tipo del dense scanner: MOVEMENT, ENTRY_EXIT, etc.
    person_description: str = ""
    carried_objects: str = ""
    direction: str = ""          # IN, OUT, THROUGH, STATIONARY
    zone: str = ""
    confidence: str = "MEDIUM"   # HIGH, MEDIUM, LOW
    details: Dict[str, Any] = field(default_factory=dict)
    frame_urls: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'analysis_id': self.analysis_id,
            'timestamp_start': self.timestamp_start,
            'timestamp_end': self.timestamp_end,
            'event_type': self.event_type,
            'scanner_event_type': self.scanner_event_type,
            'person_description': self.person_description,
            'carried_objects': self.carried_objects,
            'direction': self.direction,
            'zone': self.zone,
            'confidence': self.confidence,
            'details': self.details,
            'frame_urls': self.frame_urls
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'OperationalEvent':
        valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid)


@dataclass
class OperationalAnalysis:
    """Entidad principal de Análisis Operativo"""
    id: str
    video_filename: str = ""
    video_duration: float = 0.0
    video_gcs_url: str = ""
    video_size_mb: float = 0.0

    # Configuración del análisis
    analysis_type: str = "ACCESS_CONTROL"
    custom_context: str = ""           # Contexto del usuario (ej: "puerta piso 18")
    custom_questions: List[str] = field(default_factory=list)

    # Estado
    estado: EstadoOperationalAnalysis = EstadoOperationalAnalysis.PENDING
    progress: float = 0.0
    current_phase: str = ""
    error_message: str = ""

    # Resultados
    eventos: List[str] = field(default_factory=list)  # IDs de OperationalEvent
    summary: Dict[str, Any] = field(default_factory=dict)

    # Reportes
    report_txt_url: str = ""
    report_pdf_url: str = ""

    # Tiempos
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    phase_timings: Dict[str, float] = field(default_factory=dict)
    tiempo_procesamiento_segundos: float = 0.0

    # Estadísticas del escaneo
    scan_stats: Dict[str, Any] = field(default_factory=dict)

    # Usuario
    usuario: str = ""

    # Nombre cámara / ubicación (reutilizado del upload)
    nombre_camara: str = ""
    ubicacion: str = ""

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'video_filename': self.video_filename,
            'video_duration': self.video_duration,
            'video_gcs_url': self.video_gcs_url,
            'video_size_mb': self.video_size_mb,
            'analysis_type': self.analysis_type,
            'custom_context': self.custom_context,
            'custom_questions': self.custom_questions,
            'estado': self.estado.value if isinstance(self.estado, EstadoOperationalAnalysis) else self.estado,
            'progress': self.progress,
            'current_phase': self.current_phase,
            'error_message': self.error_message,
            'eventos': self.eventos,
            'summary': self.summary,
            'report_txt_url': self.report_txt_url,
            'report_pdf_url': self.report_pdf_url,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'phase_timings': self.phase_timings,
            'tiempo_procesamiento_segundos': self.tiempo_procesamiento_segundos,
            'scan_stats': self.scan_stats,
            'usuario': self.usuario,
            'nombre_camara': self.nombre_camara,
            'ubicacion': self.ubicacion
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'OperationalAnalysis':
        d = dict(data)
        # Convertir estado string a Enum
        if 'estado' in d and isinstance(d['estado'], str):
            try:
                d['estado'] = EstadoOperationalAnalysis(d['estado'])
            except ValueError:
                d['estado'] = EstadoOperationalAnalysis.PENDING
        valid = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**valid)

    def actualizar_estado(self, nuevo_estado: EstadoOperationalAnalysis, phase: str = "", progress: float = -1):
        self.estado = nuevo_estado
        if phase:
            self.current_phase = phase
        if progress >= 0:
            self.progress = progress

    def agregar_evento(self, evento_id: str):
        if evento_id not in self.eventos and len(self.eventos) < _MAX_INLINE_EVENT_IDS:
            self.eventos.append(evento_id)


# ═══════════════════════════════════════════════════════════════
# ENTIDADES DE ANÁLISIS DE AUDIO
# ═══════════════════════════════════════════════════════════════

class EstadoAudioAnalysis(Enum):
    """Estados del pipeline de análisis de audio"""
    PENDING = "pending"
    UPLOADING = "uploading"
    EXTRACTING_AUDIO = "extracting_audio"
    AUDIO_READY = "audio_ready"        # Checkpoint: audio extraído y en GCS
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"        # Checkpoint: transcripción completada
    INDEXING = "indexing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


# Duración máxima de archivo para análisis de audio: 2 horas
MAX_AUDIO_VIDEO_DURATION_SECONDS = 2 * 60 * 60  # 7200 segundos


@dataclass
class AudioSegment:
    """Segmento individual de transcripción con timestamps"""
    id: str
    analysis_id: str
    text: str = ""
    start_time: float = 0.0       # Segundos desde inicio del video
    end_time: float = 0.0         # Segundos desde inicio del video
    confidence: float = 0.0       # Confianza de la transcripción (0-1)
    speaker: str = ""             # Identificador del hablante (si aplica)
    language: str = "es"          # Idioma detectado
    words: List[Dict[str, Any]] = field(default_factory=list)  # Palabras individuales con timestamps
    search_terms: List[str] = field(default_factory=list)      # Términos normalizados para búsqueda

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'analysis_id': self.analysis_id,
            'text': self.text,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'confidence': self.confidence,
            'speaker': self.speaker,
            'language': self.language,
            'words': self.words,
            'search_terms': self.search_terms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AudioSegment':
        valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid)


@dataclass
class AudioAnalysis:
    """Entidad principal de Análisis de Audio"""
    id: str
    video_filename: str = ""
    video_duration: float = 0.0
    video_gcs_url: str = ""
    video_size_mb: float = 0.0

    # Audio extraído
    audio_gcs_url: str = ""
    audio_duration: float = 0.0

    # Estado
    estado: EstadoAudioAnalysis = EstadoAudioAnalysis.PENDING
    progress: float = 0.0
    current_phase: str = ""
    error_message: str = ""

    # Resultados de transcripción
    full_transcription: str = ""          # Texto completo transcrito (o preview si está en GCS)
    full_transcription_gcs_url: str = ""  # URL GCS del texto completo si supera ~100KB
    total_segments: int = 0               # Número de segmentos de transcripción
    detected_language: str = "es"         # Idioma principal detectado
    detected_languages: List[str] = field(default_factory=list)
    average_confidence: float = 0.0       # Confianza promedio de la transcripción
    speakers_detected: int = 0            # Número de hablantes distintos detectados
    embeddings_generated: bool = False    # True si se generaron embeddings para vector search

    # Resumen generado por IA
    summary: Dict[str, Any] = field(default_factory=dict)

    # Tiempos
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    tiempo_procesamiento_segundos: float = 0.0

    # Usuario
    usuario: str = ""

    # Título descriptivo (puede ser dado por el usuario o generado)
    titulo: str = ""
    descripcion: str = ""

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'video_filename': self.video_filename,
            'video_duration': self.video_duration,
            'video_gcs_url': self.video_gcs_url,
            'video_size_mb': self.video_size_mb,
            'audio_gcs_url': self.audio_gcs_url,
            'audio_duration': self.audio_duration,
            'estado': self.estado.value if isinstance(self.estado, EstadoAudioAnalysis) else self.estado,
            'progress': self.progress,
            'current_phase': self.current_phase,
            'error_message': self.error_message,
            'full_transcription': self.full_transcription,
            'full_transcription_gcs_url': self.full_transcription_gcs_url,
            'total_segments': self.total_segments,
            'detected_language': self.detected_language,
            'detected_languages': self.detected_languages,
            'average_confidence': self.average_confidence,
            'speakers_detected': self.speakers_detected,
            'embeddings_generated': self.embeddings_generated,
            'summary': self.summary,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'completed_at': self.completed_at,
            'tiempo_procesamiento_segundos': self.tiempo_procesamiento_segundos,
            'usuario': self.usuario,
            'titulo': self.titulo,
            'descripcion': self.descripcion,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AudioAnalysis':
        d = dict(data)
        # Convertir estado string a Enum
        if 'estado' in d and isinstance(d['estado'], str):
            try:
                d['estado'] = EstadoAudioAnalysis(d['estado'])
            except ValueError:
                d['estado'] = EstadoAudioAnalysis.PENDING
        valid = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**valid)

    def actualizar_estado(self, nuevo_estado: EstadoAudioAnalysis, phase: str = "", progress: float = -1):
        self.estado = nuevo_estado
        if phase:
            self.current_phase = phase
        if progress >= 0:
            self.progress = progress
