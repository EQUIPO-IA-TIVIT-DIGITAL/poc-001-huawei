"""
Tests de autenticación y autorización con el test client de Flask.

La app completa requiere dependencias pesadas (cv2, redis, openai); aquí se
valida la capa HTTP de sesión con stubs mínimos: se parchea el repositorio de
usuarios y los decoradores leen del mismo mecanismo (current_app.extensions).
"""
import pytest

from domain.entities import Usuario, RolUsuario


@pytest.fixture()
def app(monkeypatch):
    """App Flask con repositorio de usuarios respaldado por un dict en memoria."""
    import main as main_module

    usuarios = {}

    class _StubRepo:
        _usuarios_store = usuarios

        def obtener_por_id(self, uid):
            return usuarios.get(uid)

        def autenticar(self, username, password):
            for u in usuarios.values():
                if u.username == username and u.verificar_password(password):
                    return u
            return None

        def guardar(self, usuario):
            usuarios[usuario.id] = usuario
            return usuario

        def guardar_atomic(self, usuario):
            for u in usuarios.values():
                if u.username.lower() == usuario.username.lower():
                    return False, "El username ya está registrado", None
            usuarios[usuario.id] = usuario
            return True, None, usuario

        def existe_username(self, username):
            return any(u.username.lower() == username.lower() for u in usuarios.values())

        def contar_total(self):
            return len(usuarios)

    class _StubVideoRepo:
        def contar_total(self):
            return 0

    # create_app inicializa todas las dependencias; parcheamos init_dependencies
    # para no requerir cv2/redis/openai y registramos los repos stub.
    original_init = main_module.init_dependencies

    def fake_init(app):
        app.extensions["usuario_repository"] = _StubRepo()
        app.extensions["video_repository"] = _StubVideoRepo()
        app.extensions["task_queue"] = None
        return {
            "app_config": None,
            "storage_adapter": None,
            "db_adapter": None,
            "task_queue": None,
            "ai_service": None,
            "ai_adapter": None,
            "speech_adapter": None,
            "frame_extractor": None,
            "usuario_repository": app.extensions["usuario_repository"],
            "video_repository": app.extensions["video_repository"],
            "video_processor": None,
        }

    monkeypatch.setattr(main_module, "init_dependencies", fake_init)
    flask_app = main_module.create_app()
    flask_app.config["TESTING"] = True
    monkeypatch.setattr(main_module, "init_dependencies", original_init)
    return flask_app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def usuarios_store(app):
    """Acceso al diccionario de usuarios del repo stub registrado en extensions."""
    repo = app.extensions["usuario_repository"]
    return repo._usuarios_store


def _crear_usuario(store, username, password="Password#123", activo=True):
    usuario = Usuario(
        id=f"uid-{username}",
        username=username,
        email=f"{username}@test.local",
        nombre_completo=username.title(),
        rol=RolUsuario.SOCIO,
        activo=activo,
        password_hash=Usuario.hash_password(password),
    )
    store[usuario.id] = usuario
    return usuario


# ==================== SESIÓN / AUTH CHECK ====================


class TestAuthCheck:
    def test_sin_sesion_reporta_no_autenticado(self, client, usuarios_store):
        resp = client.get("/api/v1/auth/check")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["authenticated"] is False

    def test_con_sesion_devuelve_usuario(self, client, usuarios_store):
        _crear_usuario(usuarios_store, "ana")
        with client.session_transaction() as sess:
            sess["usuario_id"] = "uid-ana"
        resp = client.get("/api/v1/auth/check")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"]["authenticated"] is True
        assert data["data"]["user"]["username"] == "ana"


# ==================== DECORADORES DE AUTORIZACIÓN ====================


class TestAutorizacion:
    def test_endpoint_socio_sin_sesion_401(self, client, usuarios_store):
        resp = client.get("/socio/video/some-id/status")
        assert resp.status_code in (401, 302)

    def test_endpoint_socio_con_usuario_inexistente_401(self, client, usuarios_store):
        with client.session_transaction() as sess:
            sess["usuario_id"] = "uid-fantasma"
        resp = client.get("/socio/video/some-id/status")
        assert resp.status_code == 401

    def test_endpoint_socio_con_usuario_inactivo_403(self, client, usuarios_store):
        _crear_usuario(usuarios_store, "inactivo", activo=False)
        with client.session_transaction() as sess:
            sess["usuario_id"] = "uid-inactivo"
        resp = client.get("/socio/video/some-id/status")
        assert resp.status_code == 403

    def test_api_admin_requerido_siempre_403(self, client, usuarios_store):
        # Rol administrador deshabilitado: todas las rutas admin devuelven 403
        with client.session_transaction() as sess:
            sess["usuario_id"] = "uid-alguien"
        resp = client.get("/api/v1/admin/videos")
        assert resp.status_code == 403


# ==================== HEADERS DE SEGURIDAD ====================


class TestSecurityHeaders:
    def test_headers_presentes(self, client):
        resp = client.get("/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert "Content-Security-Policy" in resp.headers

    def test_csp_sin_unsafe_inline_en_scripts(self, client):
        resp = client.get("/health")
        csp = resp.headers.get("Content-Security-Policy", "")
        script_directive = next(
            (d for d in csp.split(";") if d.strip().startswith("script-src")), ""
        )
        assert "'unsafe-inline'" not in script_directive
        assert "cdn.jsdelivr.net" not in script_directive

    def test_sin_hsts_en_desarrollo(self, client):
        resp = client.get("/health")
        assert "Strict-Transport-Security" not in resp.headers
