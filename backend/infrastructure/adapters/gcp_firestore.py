"""
Adaptador de Firestore para AccessFan
Maneja el almacenamiento persistente de datos en Google Firestore
"""
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore_v1.aggregation import AggregationQuery

import logging
from config.gcp_config import GCPConfig
from domain.entities import Video, Usuario, RolUsuario


logger = logging.getLogger(__name__)

class FirestoreAdapter:
    """
    Adaptador para Google Firestore
    
    Colecciones:
    - videos: Información de videos y análisis
    - socios: Cuentas de socios (usuarios)
    - blacklist: Palabras prohibidas
    """
    
    # Nombres de colecciones
    COLLECTION_VIDEOS = "videos"
    COLLECTION_SOCIOS = "socios"
    COLLECTION_BLACKLIST = "blacklist"
    COLLECTION_WORKSPACES = "workspaces"
    COLLECTION_EMAIL_INDEX = "email_index"

    @staticmethod
    def _email_index_id(email_normalized: str) -> str:
        """Devuelve un ID opaco y estable para el índice de emails (SHA-256).

        Usar un hash evita exponer el email en rutas de documentos Firestore.
        """
        return hashlib.sha256(email_normalized.encode()).hexdigest()
    
    def __init__(self, config: GCPConfig = None):
        """
        Inicializa el adaptador de Firestore
        
        Args:
            config: Configuración GCP (usa default si no se proporciona)
        """
        self.config = config or GCPConfig()
        self.db = None
        
        if self.config.is_gcp_enabled():
            self._initialize_client()
    
    def _initialize_client(self):
        """Inicializa el cliente de Firestore"""
        try:
            import os
            
            self.db = firestore.Client(project=self.config.PROJECT_ID)
            logger.info(f"Firestore inicializado: {self.config.PROJECT_ID}")
        except Exception as e:
            logger.warning(f"Error inicializando Firestore: {e}")
            self.db = None
    
    def is_available(self) -> bool:
        """Verifica si Firestore está disponible"""
        return self.db is not None
    
    # ==================== VIDEOS ====================
    
    def save_video(self, video: Video) -> bool:
        """
        Guarda o actualiza un video en Firestore
        
        Args:
            video: Entidad Video a guardar
            
        Returns:
            bool: True si se guardó correctamente
        """
        if not self.is_available():
            return False
        
        try:
            doc_ref = self.db.collection(self.COLLECTION_VIDEOS).document(video.id)
            
            # Obtener valores desde metadatos_ia o usar valores por defecto
            metadatos = video.metadatos_ia or {}
            
            video_data = {
                'id': video.id,
                'nombre_archivo': video.nombre_archivo,
                'ruta_gcs': video.ruta_archivo,  # URL de Cloud Storage
                'duracion': metadatos.get('duracion_segundos', 0),
                'formato': video.formato,
                'tamanio': metadatos.get('tamanio_bytes', 0),
                'socio_id': video.socio_id,
                'usuario': video.usuario,
                'workspace_id': getattr(video, 'workspace_id', 'general'),
                'descripcion': video.descripcion,
                'fecha_subida': metadatos.get('fecha_subida') or firestore.SERVER_TIMESTAMP,
                'fecha_creacion': getattr(video, 'fecha_creacion', None),
                'estado': video.estado.value if hasattr(video.estado, 'value') else str(video.estado),
                'palabras_detectadas': metadatos.get('palabras_detectadas', []),
                'tiene_palabras_prohibidas': metadatos.get('tiene_palabras_prohibidas', False),
                'es_aprobado': metadatos.get('es_aprobado', False),
                'mensaje_rechazo': metadatos.get('razon_rechazo', ''),
                'fecha_procesamiento': metadatos.get('fecha_procesamiento'),
                'metadatos_ia': metadatos,
                'updated_at': firestore.SERVER_TIMESTAMP
            }
            
            doc_ref.set(video_data, merge=True)
            logger.info(f"Video guardado en Firestore: {video.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error guardando video: {e}")
            return False
    
    def get_video(self, video_id: str) -> Optional[Video]:
        """
        Obtiene un video por su ID
        
        Args:
            video_id: ID del video
            
        Returns:
            Video: Entidad Video o None si no existe
        """
        if not self.is_available():
            return None
        
        try:
            doc_ref = self.db.collection(self.COLLECTION_VIDEOS).document(video_id)
            doc = doc_ref.get()
            
            if not doc.exists:
                return None
            
            data = doc.to_dict()
            return self._dict_to_video(data)
            
        except Exception as e:
            logger.error(f"Error obteniendo video: {e}")
            return None
    
    def get_videos_by_socio(self, socio_id: str) -> List[Video]:
        """
        Obtiene todos los videos de un socio
        
        Args:
            socio_id: ID del socio
            
        Returns:
            List[Video]: Lista de videos
        """
        if not self.is_available():
            return []
        
        try:
            logger.debug(f"Buscando videos con socio_id = '{socio_id}'")
            
            # Intentar buscar por socio_id primero
            query = self.db.collection(self.COLLECTION_VIDEOS)\
                .where(filter=FieldFilter('socio_id', '==', socio_id))\
                .limit(500)

            docs = list(query.stream())
            logger.debug(f"Encontrados {len(docs)} videos por socio_id")

            # Si no encuentra, intentar por usuario
            if len(docs) == 0:
                logger.debug(f"Intentando buscar por campo 'usuario' = '{socio_id}'")
                query2 = self.db.collection(self.COLLECTION_VIDEOS)\
                    .where(filter=FieldFilter('usuario', '==', socio_id))\
                    .limit(500)
                docs = list(query2.stream())
                logger.debug(f"Encontrados {len(docs)} videos por usuario")
            
            return [self._dict_to_video(doc.to_dict()) for doc in docs]
            
        except Exception as e:
            logger.error(f"Error obteniendo videos del socio: {e}")
            return []

    def get_videos_by_workspace(self, usuario: str, workspace_id: str) -> List[Video]:
        """
        Obtiene los videos de un usuario específicos de un workspace determinado en una sola db query.
        
        Args:
            usuario: ID o Username del usuario
            workspace_id: ID del workspace ("general" o uuid)
            
        Returns:
            List[Video]: Lista de videos pertenecientes a ese workspace
        """
        if not self.is_available():
            return []
            
        try:
            # Query filtrando ambos en el servidor
            query = self.db.collection(self.COLLECTION_VIDEOS)\
                .where(filter=FieldFilter('usuario', '==', usuario))\
                .where(filter=FieldFilter('workspace_id', '==', workspace_id))\
                .limit(500)

            docs = list(query.stream())

            # Fallback a socio_id si el doc viejo usó esa llave en vez de usuario
            if len(docs) == 0:
                query2 = self.db.collection(self.COLLECTION_VIDEOS)\
                    .where(filter=FieldFilter('socio_id', '==', usuario))\
                    .where(filter=FieldFilter('workspace_id', '==', workspace_id))\
                    .limit(500)
                docs = list(query2.stream())
                
            return [self._dict_to_video(doc.to_dict()) for doc in docs]
        except Exception as e:
            logger.error(f"Error obteniendo videos por workspace: {e}")
            return []

    
    def get_all_videos(self, limit: int = 100, cursor: str = None) -> tuple[List[Video], str]:
        """
        Obtiene todos los videos (para admin) con paginación mediante cursor
        
        Args:
            limit: Límite de resultados por página
            cursor: ID del último video de la página anterior (para paginación)
            
        Returns:
            tuple: (Lista de videos, cursor para siguiente página o None)
        """
        if not self.is_available():
            return [], None
        
        try:
            query = self.db.collection(self.COLLECTION_VIDEOS)\
                .order_by('fecha_subida', direction=firestore.Query.DESCENDING)
            
            # Si hay cursor, empezar después de ese documento
            if cursor:
                try:
                    last_doc = self.db.collection(self.COLLECTION_VIDEOS).document(cursor).get()
                    if last_doc.exists:
                        query = query.start_after(last_doc)
                except Exception as e:
                    logger.warning(f"Cursor inválido, empezando desde el inicio: {e}")
            
            # Pedir 1 extra para saber si hay más páginas
            docs = list(query.limit(limit + 1).stream())
            
            # Determinar si hay siguiente página
            has_more = len(docs) > limit
            if has_more:
                docs = docs[:limit]  # Quitar el documento extra
            
            videos = [self._dict_to_video(doc.to_dict()) for doc in docs]
            
            # El cursor de la siguiente página es el ID del último video
            next_cursor = videos[-1].id if has_more and videos else None
            
            return videos, next_cursor
            
        except Exception as e:
            logger.error(f"Error obteniendo todos los videos: {e}")
            return [], None
    
    def get_pending_videos(self) -> List[Video]:
        """
        Obtiene videos pendientes de revisión
        
        Returns:
            List[Video]: Videos con estado PENDIENTE
        """
        if not self.is_available():
            return []
        
        try:
            query = self.db.collection(self.COLLECTION_VIDEOS)\
                .where(filter=FieldFilter('estado', '==', 'PENDIENTE'))\
                .order_by('fecha_subida')\
                .limit(200)

            docs = query.stream()
            return [self._dict_to_video(doc.to_dict()) for doc in docs]
            
        except Exception as e:
            logger.error(f"Error obteniendo videos pendientes: {e}")
            return []
    
    def delete_video(self, video_id: str) -> bool:
        """
        Elimina un video de Firestore
        
        Args:
            video_id: ID del video
            
        Returns:
            bool: True si se eliminó correctamente
        """
        if not self.is_available():
            return False
        
        try:
            self.db.collection(self.COLLECTION_VIDEOS).document(video_id).delete()
            logger.info(f"Video eliminado de Firestore: {video_id}")
            return True
        except Exception as e:
            logger.error(f"Error eliminando video: {e}")
            return False
    
    # ==================== SOCIOS ====================
    
    def save_socio(self, usuario: Usuario) -> bool:
        """Guarda un socio en Firestore"""
        if not self.is_available():
            return False
        
        try:
            doc_ref = self.db.collection(self.COLLECTION_SOCIOS).document(usuario.username)
            
            socio_data = {
                'id': usuario.id,
                'username': usuario.username,
                'username_normalized': usuario.username.lower(),
                'password_hash': usuario.password_hash,
                'nombre_completo': usuario.nombre_completo,
                'email': usuario.email,
                'email_normalized': usuario.email.lower(),
                'rol': usuario.rol.value,
                'activo': usuario.activo,
                'azure_id': getattr(usuario, 'azure_id', ''),
                'auth_provider': getattr(usuario, 'auth_provider', 'local'),
                'foto_url': usuario.foto_url or '',
                'metadatos': usuario.metadatos if hasattr(usuario, 'metadatos') else {},
                'notificaciones': usuario.notificaciones if hasattr(usuario, 'notificaciones') else [],
                'fecha_creacion': getattr(usuario, 'fecha_creacion', None) or firestore.SERVER_TIMESTAMP,
                'ultimo_acceso': getattr(usuario, 'ultimo_acceso', None),
                'created_at': firestore.SERVER_TIMESTAMP,
                'updated_at': firestore.SERVER_TIMESTAMP
            }
            
            doc_ref.set(socio_data)
            logger.info(f"✅ Usuario guardado en Firestore: {usuario.username[:3]}***")
            return True
        except Exception as e:
            logger.error(f"❌ Error guardando socio: {e}")
            return False
    
    def save_socio_atomic(self, usuario: Usuario) -> Tuple[bool, Optional[str]]:
        """
        Guarda un socio de forma segura evitando duplicados de username y email.

        Estrategia (sin @transactional para mayor compatibilidad con ADC):
          1. Pre-verificación rápida de email en email_index.
          2. Uso de create() para el documento del socio — Firestore garantiza
             que create() falla atómicamente si el documento ya existe
             (AlreadyExists), evitando duplicados de username sin transacción.
          3. Registro del email_index con set() tras el create() exitoso.

        Returns:
            Tuple[bool, Optional[str]]: (éxito, mensaje_error)
        """
        if not self.is_available():
            return False, "Firestore no disponible"

        try:
            import google.api_core.exceptions
            email_normalized = usuario.email.lower()

            # 1. Verificar email en email_index (lectura simple, sin transacción)
            email_index_id = FirestoreAdapter._email_index_id(email_normalized)
            email_ref = self.db.collection(self.COLLECTION_EMAIL_INDEX).document(email_index_id)
            email_doc = email_ref.get()
            if email_doc.exists:
                return False, "El email ya está registrado con otro usuario"

            # 2. Preparar datos del socio
            socio_data = {
                'id': usuario.id,
                'username': usuario.username,
                'username_normalized': usuario.username.lower(),
                'password_hash': usuario.password_hash,
                'nombre_completo': usuario.nombre_completo,
                'email': usuario.email,
                'email_normalized': email_normalized,
                'rol': usuario.rol.value,
                'activo': usuario.activo,
                'azure_id': getattr(usuario, 'azure_id', ''),
                'auth_provider': getattr(usuario, 'auth_provider', 'local'),
                'foto_url': getattr(usuario, 'foto_url', '') or '',
                'metadatos': getattr(usuario, 'metadatos', {}),
                'notificaciones': getattr(usuario, 'notificaciones', []),
                'fecha_creacion': getattr(usuario, 'fecha_creacion', None) or firestore.SERVER_TIMESTAMP,
                'ultimo_acceso': getattr(usuario, 'ultimo_acceso', None),
                'created_at': firestore.SERVER_TIMESTAMP,
                'updated_at': firestore.SERVER_TIMESTAMP,
            }

            # 3. create() es atómico: falla con AlreadyExists si el username ya existe
            username_ref = self.db.collection(self.COLLECTION_SOCIOS).document(usuario.username)
            try:
                username_ref.create(socio_data)
            except google.api_core.exceptions.AlreadyExists:
                return False, f"El username '{usuario.username}' ya está registrado"

            # 4. Registrar email_index (post-create, no atómico con el paso 3 pero suficiente)
            email_ref.set({
                'username': usuario.username,
                'email': email_normalized,
                'created_at': firestore.SERVER_TIMESTAMP,
            })

            logger.info("✅ Usuario creado: %s***", usuario.username[:3])
            return True, None

        except ValueError as e:
            logger.warning("⚠️ Validación fallida al crear usuario: %s", e)
            return False, str(e)
        except Exception as e:
            logger.error("❌ Error guardando socio: %s", e, exc_info=True)
            return False, f"Error al crear usuario: {str(e)}"
    
    def get_socio(self, username: str) -> Optional[Usuario]:
        """Obtiene un socio por username"""
        if not self.is_available():
            return None
        
        try:
            doc = self.db.collection(self.COLLECTION_SOCIOS).document(username).get()
            
            if not doc.exists:
                return None
            
            data = doc.to_dict()
            return Usuario(
                id=data.get('id', username),
                username=data['username'],
                password_hash=data.get('password_hash', ''),
                nombre_completo=data.get('nombre_completo', ''),
                email=data.get('email', ''),
                rol=RolUsuario(data.get('rol', 'socio')),
                activo=data.get('activo', True),
                azure_id=data.get('azure_id', ''),
                auth_provider=data.get('auth_provider', 'local'),
                foto_url=data.get('foto_url', ''),
            )
        except Exception as e:
            logger.error(f"Error obteniendo socio: {e}")
            return None
    
    # ==================== BLACKLIST ====================
    
    def get_blacklist(self) -> List[str]:
        """
        Obtiene la lista de palabras prohibidas
        
        Returns:
            List[str]: Palabras prohibidas
        """
        if not self.is_available():
            return []
        
        try:
            doc = self.db.collection(self.COLLECTION_BLACKLIST).document('palabras').get()
            
            if doc.exists:
                data = doc.to_dict()
                return data.get('palabras', [])
            return []
        except Exception as e:
            logger.error(f"Error obteniendo blacklist: {e}")
            return []
    
    def update_blacklist(self, palabras: List[str]) -> bool:
        """
        Actualiza la blacklist completa
        
        Args:
            palabras: Lista de palabras prohibidas
            
        Returns:
            bool: True si se actualizó correctamente
        """
        if not self.is_available():
            return False
        
        try:
            doc_ref = self.db.collection(self.COLLECTION_BLACKLIST).document('palabras')
            doc_ref.set({
                'palabras': palabras,
                'updated_at': firestore.SERVER_TIMESTAMP
            })
            return True
        except Exception as e:
            logger.error(f"Error actualizando blacklist: {e}")
            return False
    
    # ==================== ESTADÍSTICAS ====================
    
    def _count_collection(self, collection_name: str) -> int:
        """
        Cuenta documentos en una colección usando Aggregation Query (1 lectura)
        
        Args:
            collection_name: Nombre de la colección
            
        Returns:
            int: Número de documentos
        """
        try:
            collection_ref = self.db.collection(collection_name)
            count_query = collection_ref.count()
            result = count_query.get()
            return result[0][0].value
        except Exception as e:
            logger.warning(f"Error en count de {collection_name}: {e}")
            # Fallback: contar hasta MAX_COUNT para evitar lectura completa
            MAX_COUNT = 10_000
            return sum(1 for _ in self.db.collection(collection_name).limit(MAX_COUNT).stream())
    
    def _count_by_field(self, collection_name: str, field: str, value: str) -> int:
        """
        Cuenta documentos filtrando por un campo usando Aggregation Query
        
        Args:
            collection_name: Nombre de la colección
            field: Campo para filtrar
            value: Valor del campo
            
        Returns:
            int: Número de documentos que coinciden
        """
        try:
            query = self.db.collection(collection_name).where(
                filter=FieldFilter(field, '==', value)
            )
            count_query = query.count()
            result = count_query.get()
            return result[0][0].value
        except Exception as e:
            logger.warning(f"Error en count filtrado {collection_name}.{field}={value}: {e}")
            return 0
    
    def get_statistics(self) -> dict:
        """
        Obtiene estadísticas generales OPTIMIZADO con Aggregation Queries
        
        Usa count() de Firestore para evitar cargar todos los documentos.
        Reduce de N lecturas a ~10 lecturas por llamada.
        
        Returns:
            dict: Estadísticas de la plataforma
        """
        if not self.is_available():
            return {'available': False}
        
        try:
            # Usar Aggregation Queries para contar (1 lectura cada una)
            total_videos = self._count_collection(self.COLLECTION_VIDEOS)
            
            # Contar por estado usando aggregation queries
            # Estados directos
            aprobados = self._count_by_field(self.COLLECTION_VIDEOS, 'estado', 'APROBADO')
            rechazados = self._count_by_field(self.COLLECTION_VIDEOS, 'estado', 'RECHAZADO')
            pendientes = self._count_by_field(self.COLLECTION_VIDEOS, 'estado', 'PENDIENTE')
            en_revision = self._count_by_field(self.COLLECTION_VIDEOS, 'estado', 'EN_REVISION')
            error = self._count_by_field(self.COLLECTION_VIDEOS, 'estado', 'ERROR')
            
            # Videos COMPLETADO necesitan verificación adicional del resultado_ia
            # Por ahora los contamos y los sumamos a aprobados (comportamiento legacy)
            completados = self._count_by_field(self.COLLECTION_VIDEOS, 'estado', 'COMPLETADO')
            # La mayoría de COMPLETADOS son aprobados (se puede refinar después)
            aprobados += completados
            
            # Contar usuarios usando aggregation queries
            total_socios = self._count_collection(self.COLLECTION_SOCIOS)
            
            return {
                'available': True,
                'videos': {
                    'total': total_videos,
                    'APROBADO': aprobados,
                    'RECHAZADO': rechazados,
                    'PENDIENTE': pendientes,
                    'EN_REVISION': en_revision,
                    'ERROR': error
                },
                'usuarios': {
                    'socios': total_socios
                }
            }
        except Exception as e:
            logger.error(f"Error obteniendo estadísticas: {e}")
            import traceback
            traceback.print_exc()
            return {'available': False, 'error': str(e)}
    
    # ==================== HELPERS ====================
    
    def _dict_to_video(self, data: Dict[str, Any]) -> Video:
        """Convierte un diccionario de Firestore a entidad Video"""
        from domain.entities import EstadoVideo
        
        # Reconstruir metadatos_ia desde los campos de Firestore
        metadatos_ia = data.get('metadatos_ia', {})
        metadatos_ia.update({
            'duracion_segundos': data.get('duracion', 0),
            'tamanio_bytes': data.get('tamanio', 0),
            'fecha_subida': data.get('fecha_subida'),
            'palabras_detectadas': data.get('palabras_detectadas', []),
            'tiene_palabras_prohibidas': data.get('tiene_palabras_prohibidas', False),
            'es_aprobado': data.get('es_aprobado'),
            'razon_rechazo': data.get('mensaje_rechazo', ''),
            'fecha_procesamiento': data.get('fecha_procesamiento'),
        })
        
        # Convertir estado string a enum
        estado_str = data.get('estado', 'PENDIENTE')
        try:
            if isinstance(estado_str, str):
                estado = EstadoVideo(estado_str.lower())
            else:
                estado = EstadoVideo.PENDIENTE
        except ValueError:
            estado = EstadoVideo.PENDIENTE
        
        return Video(
            id=data.get('id', ''),
            usuario=data.get('socio_id', data.get('usuario', '')),
            ruta_archivo=data.get('ruta_gcs', ''),
            descripcion=data.get('descripcion', ''),
            metadatos_ia=metadatos_ia,
            estado=estado,
            nombre_archivo=data.get('nombre_archivo', ''),
            workspace_id=data.get('workspace_id', 'general'),
            fecha_creacion=data.get('fecha_creacion')
        )
    
    # ==================== WORKSPACES ====================
    
    def save_workspace(self, workspace) -> bool:
        """Guarda o actualiza un workspace en Firestore"""
        if not self.is_available():
            return False
        
        try:
            from domain.entities import Workspace
            doc_ref = self.db.collection(self.COLLECTION_WORKSPACES).document(workspace.id)
            
            workspace_data = {
                'id': workspace.id,
                'usuario': workspace.usuario,
                'nombre': workspace.nombre,
                'descripcion': workspace.descripcion,
                'contexto': workspace.contexto,
                'categoria': getattr(workspace, 'categoria', 'general'),
                'tipo_contenido': getattr(workspace, 'tipo_contenido', ''),
                'elementos_visuales': getattr(workspace, 'elementos_visuales', ''),
                'nivel_tolerancia': getattr(workspace, 'nivel_tolerancia', 'medio'),
                'fecha_creacion': workspace.fecha_creacion,
                'fecha_modificacion': workspace.fecha_modificacion,
                'es_general': workspace.es_general,
                'color': workspace.color,
                'orden': workspace.orden,
                'eliminado': getattr(workspace, 'eliminado', False),
                'fecha_eliminacion': getattr(workspace, 'fecha_eliminacion', ''),
                'eliminado_por': getattr(workspace, 'eliminado_por', ''),
                'estadisticas': workspace.estadisticas,
                'permisos': workspace.permisos,
                'visibilidad': workspace.visibilidad,
                'metadatos': workspace.metadatos,
                'updated_at': firestore.SERVER_TIMESTAMP
            }
            
            doc_ref.set(workspace_data, merge=True)
            return True
        except Exception as e:
            logger.error(f"Error guardando workspace: {e}")
            return False
    
    def get_workspace(self, workspace_id: str):
        """Obtiene un workspace por ID"""
        if not self.is_available():
            return None
        
        try:
            from domain.entities import Workspace
            doc = self.db.collection(self.COLLECTION_WORKSPACES).document(workspace_id).get()
            
            if not doc.exists:
                return None
            
            data = doc.to_dict()
            return Workspace(
                id=data['id'],
                usuario=data['usuario'],
                nombre=data['nombre'],
                descripcion=data.get('descripcion', ''),
                contexto=data.get('contexto', ''),
                categoria=data.get('categoria', 'general'),
                tipo_contenido=data.get('tipo_contenido', ''),
                elementos_visuales=data.get('elementos_visuales', ''),
                nivel_tolerancia=data.get('nivel_tolerancia', 'medio'),
                fecha_creacion=data.get('fecha_creacion', ''),
                fecha_modificacion=data.get('fecha_modificacion', ''),
                es_general=data.get('es_general', False),
                color=data.get('color', '#3B82F6'),
                orden=data.get('orden', 0),
                eliminado=data.get('eliminado', False),
                fecha_eliminacion=data.get('fecha_eliminacion', ''),
                eliminado_por=data.get('eliminado_por', ''),
                estadisticas=data.get('estadisticas', {}),
                permisos=data.get('permisos', []),
                visibilidad=data.get('visibilidad', 'privado'),
                metadatos=data.get('metadatos', {})
            )
        except Exception as e:
            logger.error(f"Error obteniendo workspace: {e}")
            return None
    
    def get_workspaces_by_user(self, usuario: str):
        """Obtiene todos los workspaces de un usuario"""
        if not self.is_available():
            return []
        
        try:
            from domain.entities import Workspace
            # Query con filtro para excluir eliminados (requiere índice compuesto)
            query = self.db.collection(self.COLLECTION_WORKSPACES)\
                .where(filter=FieldFilter('usuario', '==', usuario))\
                .where(filter=FieldFilter('eliminado', '==', False))\
                .limit(200)
            
            docs = query.stream()
            workspaces = []
            for doc in docs:
                data = doc.to_dict()
                workspaces.append(Workspace(
                    id=data['id'],
                    usuario=data['usuario'],
                    nombre=data['nombre'],
                    descripcion=data.get('descripcion', ''),
                    contexto=data.get('contexto', ''),
                    categoria=data.get('categoria', 'general'),
                    tipo_contenido=data.get('tipo_contenido', ''),
                    elementos_visuales=data.get('elementos_visuales', ''),
                    nivel_tolerancia=data.get('nivel_tolerancia', 'medio'),
                    fecha_creacion=data.get('fecha_creacion', ''),
                    fecha_modificacion=data.get('fecha_modificacion', ''),
                    es_general=data.get('es_general', False),
                    color=data.get('color', '#3B82F6'),
                    orden=data.get('orden', 0),
                    eliminado=data.get('eliminado', False),
                    fecha_eliminacion=data.get('fecha_eliminacion', ''),
                    eliminado_por=data.get('eliminado_por', ''),
                    estadisticas=data.get('estadisticas', {}),
                    permisos=data.get('permisos', []),
                    visibilidad=data.get('visibilidad', 'privado'),
                    metadatos=data.get('metadatos', {})
                ))
            return workspaces
        except Exception as e:
            logger.error(f"Error obteniendo workspaces del usuario: {e}")
            return []
    
    def get_workspaces_eliminados(self, usuario: str):
        """Obtiene todos los workspaces eliminados de un usuario (papelera)"""
        if not self.is_available():
            return []
        
        try:
            from domain.entities import Workspace
            # Query para obtener solo eliminados
            query = self.db.collection(self.COLLECTION_WORKSPACES)\
                .where(filter=FieldFilter('usuario', '==', usuario))\
                .where(filter=FieldFilter('eliminado', '==', True))\
                .limit(100)
            
            docs = query.stream()
            workspaces = []
            for doc in docs:
                data = doc.to_dict()
                workspaces.append(Workspace(
                    id=data['id'],
                    usuario=data['usuario'],
                    nombre=data['nombre'],
                    descripcion=data.get('descripcion', ''),
                    contexto=data.get('contexto', ''),
                    categoria=data.get('categoria', 'general'),
                    tipo_contenido=data.get('tipo_contenido', ''),
                    elementos_visuales=data.get('elementos_visuales', ''),
                    nivel_tolerancia=data.get('nivel_tolerancia', 'medio'),
                    fecha_creacion=data.get('fecha_creacion', ''),
                    fecha_modificacion=data.get('fecha_modificacion', ''),
                    es_general=data.get('es_general', False),
                    color=data.get('color', '#3B82F6'),
                    orden=data.get('orden', 0),
                    eliminado=data.get('eliminado', False),
                    fecha_eliminacion=data.get('fecha_eliminacion', ''),
                    eliminado_por=data.get('eliminado_por', ''),
                    estadisticas=data.get('estadisticas', {}),
                    permisos=data.get('permisos', []),
                    visibilidad=data.get('visibilidad', 'privado'),
                    metadatos=data.get('metadatos', {})
                ))
            return workspaces
        except Exception as e:
            logger.error(f"Error obteniendo workspaces eliminados: {e}")
            return []
    
    def delete_workspace(self, workspace_id: str) -> bool:
        """Elimina un workspace de Firestore"""
        if not self.is_available():
            return False
        
        try:
            self.db.collection(self.COLLECTION_WORKSPACES).document(workspace_id).delete()
            return True
        except Exception as e:
            logger.error(f"Error eliminando workspace: {e}")
            return False

    # ==================== MÉTODOS GENÉRICOS ====================
    
    def obtener(self, collection_name: str, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un documento de cualquier colección por su ID
        
        Args:
            collection_name: Nombre de la colección
            document_id: ID del documento
            
        Returns:
            Dict: Datos del documento o None si no existe
        """
        if not self.is_available():
            return None
        
        try:
            doc = self.db.collection(collection_name).document(document_id).get()
            
            if not doc.exists:
                return None
            
            data = doc.to_dict()
            data['id'] = doc.id  # Incluir el ID en los datos
            return data
            
        except Exception as e:
            logger.error(f"Error obteniendo documento {collection_name}/{document_id}: {e}")
            return None
    
    def obtener_coleccion(self, collection_name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Obtiene todos los documentos de una colección
        
        Args:
            collection_name: Nombre de la colección
            limit: Límite de documentos a retornar
            
        Returns:
            List[Dict]: Lista de documentos
        """
        if not self.is_available():
            return []
        
        try:
            docs = self.db.collection(collection_name).limit(limit).stream()
            result = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id  # Incluir el ID en los datos
                result.append(data)
            return result
            
        except Exception as e:
            logger.error(f"Error obteniendo colección {collection_name}: {e}")
            return []
    
    def guardar(self, collection_name: str, document_id: str, data: Dict[str, Any], merge: bool = True) -> bool:
        """
        Guarda un documento en cualquier colección
        
        Args:
            collection_name: Nombre de la colección
            document_id: ID del documento
            data: Datos a guardar
            merge: Si True, fusiona con datos existentes
            
        Returns:
            bool: True si se guardó correctamente
        """
        if not self.is_available():
            return False
        
        try:
            doc_ref = self.db.collection(collection_name).document(document_id)
            data['updated_at'] = firestore.SERVER_TIMESTAMP
            doc_ref.set(data, merge=merge)
            return True
        except Exception as e:
            logger.error(f"Error guardando documento {collection_name}/{document_id}: {e}")
            return False

