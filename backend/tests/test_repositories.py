"""
Tests de repositorios SQLAlchemy con SQLite en memoria.
Cubren: paginación keyset, CRUD de usuarios/videos y aislamiento por usuario.
"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from infrastructure.db.base import Base
from infrastructure.db.models import VideoModel, UserModel
import infrastructure.repositories.sqlalchemy_repositories as sr
from infrastructure.repositories.sqlalchemy_repositories import (
    SQLAlchemyVideoRepository,
    SQLAlchemyUserRepository,
)
from domain.entities import Video, Usuario, EstadoVideo, RolUsuario


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = scoped_session(sessionmaker(bind=engine))
    sr.SessionLocal = factory
    yield factory
    factory.remove()
    engine.dispose()


@pytest.fixture()
def video_repo(session_factory):
    return SQLAlchemyVideoRepository()


@pytest.fixture()
def user_repo(session_factory):
    return SQLAlchemyUserRepository()


def _make_video(video_id: str, usuario: str, minutes: int) -> VideoModel:
    ts = datetime(2026, 1, 1, 12, 0, 0) + timedelta(minutes=minutes)
    return VideoModel(
        id=video_id,
        usuario=usuario,
        s3_uri=f"s3://bucket/videos/{video_id}.mp4",
        created_at=ts,
        updated_at=ts,
    )


def _make_usuario(username: str, idx: int = 0) -> Usuario:
    return Usuario(
        id=f"uid-{username}-{idx}",
        username=username,
        email=f"{username}@test.local",
        nombre_completo=username.title(),
        rol=RolUsuario.SOCIO,
        password_hash=Usuario.hash_password("Password#123"),
    )


# ==================== PAGINACIÓN ====================


class TestPaginacionKeyset:
    def test_recorrido_completo_sin_duplicados_ni_omisiones(self, session_factory, video_repo):
        db = session_factory()
        db.add_all([_make_video(f"vid-{i:02d}", "tester", i) for i in range(7)])
        db.commit()
        db.close()

        seen, cursor, pages = [], None, 0
        while True:
            page, cursor = video_repo.obtener_todos_paginado(limit=3, cursor=cursor)
            seen.extend(v.id for v in page)
            pages += 1
            if cursor is None:
                break
            assert pages < 10, "bucle infinito"

        assert len(seen) == 7
        assert len(set(seen)) == 7, f"duplicados: {seen}"
        assert set(seen) == {f"vid-{i:02d}" for i in range(7)}

    def test_ultima_pagina_parcial_y_cursor_final_none(self, session_factory, video_repo):
        db = session_factory()
        db.add_all([_make_video(f"vid-{i:02d}", "tester", i) for i in range(7)])
        db.commit()
        db.close()

        page1, cursor1 = video_repo.obtener_todos_paginado(limit=3)
        assert len(page1) == 3 and cursor1 is not None
        page2, cursor2 = video_repo.obtener_todos_paginado(limit=3, cursor=cursor1)
        assert len(page2) == 3 and cursor2 is not None
        page3, cursor3 = video_repo.obtener_todos_paginado(limit=3, cursor=cursor2)
        assert len(page3) == 1 and cursor3 is None

    def test_orden_descendente_por_fecha(self, session_factory, video_repo):
        db = session_factory()
        db.add_all([_make_video(f"vid-{i:02d}", "tester", i) for i in range(5)])
        db.commit()
        db.close()

        page, _ = video_repo.obtener_todos_paginado(limit=5)
        ids = [v.id for v in page]
        assert ids == sorted(ids, reverse=True)

    def test_cursor_invalido_degrada_sin_excepcion(self, session_factory, video_repo):
        db = session_factory()
        db.add_all([_make_video(f"vid-{i:02d}", "tester", i) for i in range(5)])
        db.commit()
        db.close()

        page, _ = video_repo.obtener_todos_paginado(limit=3, cursor="cursor-basura")
        assert len(page) == 3

    def test_estabilidad_con_inserciones_concurrentes(self, session_factory, video_repo):
        """Insertar nuevos videos entre páginas no debe duplicar ni omitir el resto."""
        db = session_factory()
        db.add_all([_make_video(f"old-{i:02d}", "tester", i) for i in range(4)])
        db.commit()
        db.close()

        page1, cursor1 = video_repo.obtener_todos_paginado(limit=2)

        # Inserción "concurrente" de videos más nuevos
        db = session_factory()
        db.add_all([_make_video(f"new-{i:02d}", "tester", 100 + i) for i in range(2)])
        db.commit()
        db.close()

        seen = [v.id for v in page1]
        cursor = cursor1
        while cursor is not None:
            page, cursor = video_repo.obtener_todos_paginado(limit=2, cursor=cursor)
            seen.extend(v.id for v in page)

        # Los antiguos aparecen exactamente una vez
        assert len([s for s in seen if s.startswith("old-")]) == 4
        assert len(set(seen)) == len(seen), f"duplicados: {seen}"


# ==================== CRUD VIDEOS ====================


class TestVideoRepository:
    def test_guardar_y_obtener_por_id(self, video_repo):
        video = Video(
            id="v-1",
            usuario="user1",
            ruta_archivo="s3://bucket/videos/v-1.mp4",
            nombre_archivo="v-1.mp4",
            descripcion="video de prueba",
        )
        guardado = video_repo.guardar(video)
        assert guardado.id == "v-1"

        obtenido = video_repo.obtener_por_id("v-1")
        assert obtenido is not None
        assert obtenido.usuario == "user1"

    def test_obtener_por_usuario_aisla_datos(self, session_factory, video_repo):
        db = session_factory()
        db.add_all([
            _make_video("a-1", "alice", 0),
            _make_video("a-2", "alice", 1),
            _make_video("b-1", "bob", 2),
        ])
        db.commit()
        db.close()

        alice = video_repo.obtener_por_usuario("alice")
        bob = video_repo.obtener_por_usuario("bob")

        assert {v.id for v in alice} == {"a-1", "a-2"}
        assert {v.id for v in bob} == {"b-1"}

    def test_eliminar(self, session_factory, video_repo):
        db = session_factory()
        db.add(_make_video("del-1", "tester", 0))
        db.commit()
        db.close()

        assert video_repo.eliminar("del-1") is True
        assert video_repo.obtener_por_id("del-1") is None
        assert video_repo.eliminar("del-1") is False

    def test_actualizar_estado(self, session_factory, video_repo):
        db = session_factory()
        db.add(_make_video("st-1", "tester", 0))
        db.commit()
        db.close()

        assert video_repo.actualizar_estado("st-1", EstadoVideo.COMPLETADO) is True
        assert video_repo.obtener_por_id("st-1").estado == EstadoVideo.COMPLETADO
        assert video_repo.actualizar_estado("no-existe", EstadoVideo.COMPLETADO) is False


# ==================== USUARIOS ====================


class TestUserRepository:
    def test_guardar_y_autenticar_bcrypt(self, user_repo):
        usuario = _make_usuario("carlos")
        ok, error, guardado = user_repo.guardar_atomic(usuario)
        assert ok is True, error
        assert guardado is not None

        autenticado = user_repo.autenticar("carlos", "Password#123")
        assert autenticado is not None
        assert autenticado.username == "carlos"

        assert user_repo.autenticar("carlos", "wrong") is None

    def test_username_duplicado_rechazado(self, user_repo):
        ok1, _, _ = user_repo.guardar_atomic(_make_usuario("dup", 0))
        ok2, error, _ = user_repo.guardar_atomic(_make_usuario("dup", 1))
        assert ok1 is True
        assert ok2 is False
        assert error == "username_exists"

    def test_username_case_insensitive(self, user_repo):
        user_repo.guardar_atomic(_make_usuario("Maria"))
        assert user_repo.obtener_por_username("maria") is not None
        assert user_repo.obtener_por_username("MARIA") is not None

    def test_password_hash_es_bcrypt(self, user_repo):
        user_repo.guardar_atomic(_make_usuario("hasher"))
        db = user_repo.obtener_por_username("hasher")
        assert db.password_hash.startswith("$2b$")

    def test_obtener_por_email(self, user_repo):
        user_repo.guardar_atomic(_make_usuario("correo"))
        assert user_repo.obtener_por_email("correo@test.local") is not None
        assert user_repo.obtener_por_email("CORREO@TEST.LOCAL") is not None
        assert user_repo.obtener_por_email("otro@test.local") is None

    def test_eliminar_usuario(self, user_repo):
        user_repo.guardar_atomic(_make_usuario("temporal"))
        uid = user_repo.obtener_por_username("temporal").id
        assert user_repo.eliminar(uid) is True
        assert user_repo.obtener_por_username("temporal") is None
