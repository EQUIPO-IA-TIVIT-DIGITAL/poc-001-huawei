"""
Tests de los handlers del worker RQ (worker.py).

Se stubbea el container de dependencias (worker_dependencies) y job_queue
para no requerir Redis real; se valida la lógica de estado, progreso,
persistencia de error y DLQ.
"""
import sys

import pytest
from unittest.mock import MagicMock, patch

import worker
from domain.entities import Video, EstadoVideo


def _make_video(estado=EstadoVideo.PENDIENTE):
    return Video(
        id="vid-w1",
        usuario="workeruser",
        ruta_archivo="s3://bucket/videos/vid-w1.mp4",
        nombre_archivo="vid-w1.mp4",
        descripcion="video worker",
        estado=estado,
    )


@pytest.fixture()
def stub_container(monkeypatch):
    """Container de dependencias con repos y procesador falsos."""
    video = _make_video()

    v_repo = MagicMock()
    v_repo.obtener_por_id.return_value = video
    v_repo.guardar.side_effect = lambda v: v

    procesador = MagicMock()
    # Por defecto el pipeline tiene éxito y devuelve el video
    procesador.ejecutar.return_value = video

    container = MagicMock()
    container.video_repository = v_repo
    container.video_processor = procesador

    monkeypatch.setattr(
        "infrastructure.worker_dependencies.get_worker_container",
        lambda: container,
    )
    return container, v_repo, procesador


@pytest.fixture()
def stub_job_queue(monkeypatch):
    """Intercepta las funciones de tracking/DLQ de job_queue."""
    calls = {"clear": [], "dlq": []}

    def clear(video_id):
        calls["clear"].append(video_id)

    def dlq(video_id, error, job_id=None):
        calls["dlq"].append({"video_id": video_id, "error": error, "job_id": job_id})

    monkeypatch.setattr(
        "infrastructure.services.job_queue.clear_active_socio_job", clear
    )
    monkeypatch.setattr(
        "infrastructure.services.job_queue.register_socio_dead_letter", dlq
    )
    return calls


class TestProcessSocioVideoExito:
    def test_retorna_success_y_persiste(self, stub_container, stub_job_queue):
        container, v_repo, procesador = stub_container

        result = worker.process_socio_video("vid-w1")

        assert result == {"success": True, "video_id": "vid-w1"}
        procesador.ejecutar.assert_called_once()
        # El video se guardó antes y después del pipeline
        assert v_repo.guardar.call_count >= 2
        # El job activo se limpió
        assert "vid-w1" in stub_job_queue["clear"]
        # No hubo DLQ
        assert stub_job_queue["dlq"] == []

    def test_inicializa_progreso_cero(self, stub_container, stub_job_queue):
        container, v_repo, _ = stub_container

        worker.process_socio_video("vid-w1")

        primer_guardado = v_repo.guardar.call_args_list[0].args[0]
        progreso = primer_guardado.metadatos_ia.get("progreso")
        assert progreso["step"] == 0
        assert progreso["total_steps"] == 5
        assert progreso["status"] == "pending"

    def test_video_en_error_se_resetea_a_pendiente(self, stub_container, stub_job_queue):
        container, v_repo, procesador = stub_container
        container.video_repository.obtener_por_id.return_value = _make_video(
            estado=EstadoVideo.ERROR
        )

        worker.process_socio_video("vid-w1")

        enviado = procesador.ejecutar.call_args.args[0]
        assert enviado.estado == EstadoVideo.PENDIENTE

    def test_video_no_encontrado_termina_sin_excepcion(self, stub_container, stub_job_queue):
        container, v_repo, _ = stub_container
        v_repo.obtener_por_id.return_value = None

        result = worker.process_socio_video("fantasma")

        assert result == {"success": False, "error": "Video no encontrado"}
        assert "fantasma" in stub_job_queue["clear"]


class TestProcessSocioVideoFallo:
    def test_error_persiste_estado_error_y_lanza(self, stub_container, stub_job_queue):
        container, v_repo, procesador = stub_container
        procesador.ejecutar.side_effect = RuntimeError("pipeline explotó")

        with pytest.raises(RuntimeError, match="pipeline explotó"):
            worker.process_socio_job("vid-w1") if hasattr(
                worker, "process_socio_job"
            ) else worker.process_socio_video("vid-w1")

        # El video quedó en ERROR con el mensaje
        guardado = v_repo.guardar.call_args.args[0]
        assert guardado.estado == EstadoVideo.ERROR
        assert "pipeline explotó" in guardado.metadatos_ia.get("error_procesamiento", "")

    def test_dlq_solo_sin_retries(self, stub_container, stub_job_queue, monkeypatch):
        container, v_repo, procesador = stub_container
        procesador.ejecutar.side_effect = RuntimeError("boom")

        # Con retries restantes: NO va a DLQ
        fake_job = MagicMock()
        fake_job.id = "job-1"
        fake_job.retries_left = 2
        monkeypatch.setattr("rq.get_current_job", lambda: fake_job)
        with pytest.raises(RuntimeError):
            worker.process_socio_video("vid-w1")
        assert stub_job_queue["dlq"] == []

        # Sin retries restantes: SÍ va a DLQ
        v_repo.guardar.reset_mock()
        fake_job.retries_left = 0
        with pytest.raises(RuntimeError):
            worker.process_socio_video("vid-w1")
        assert len(stub_job_queue["dlq"]) == 1
        dlq_entry = stub_job_queue["dlq"][0]
        assert dlq_entry["video_id"] == "vid-w1"
        assert dlq_entry["job_id"] == "job-1"
        assert "boom" in dlq_entry["error"]

    def test_callback_progreso_deduplica(self, stub_container, stub_job_queue):
        container, v_repo, procesador = stub_container

        captured_callback = None

        def capturar(video, blacklist, progress_callback=None):
            nonlocal captured_callback
            captured_callback = progress_callback
            # Duplicado: mismo step+status dos veces
            captured_callback(2, 5, "escaneando", "processing")
            calls_antes = v_repo.guardar.call_count
            captured_callback(2, 5, "escaneando", "processing")
            calls_despues = v_repo.guardar.call_count
            assert calls_despues == calls_antes  # deduplicado
            # Step distinto: sí persiste
            captured_callback(3, 5, "analizando", "processing")
            assert v_repo.guardar.call_count == calls_despues + 1
            return video

        procesador.ejecutar.side_effect = capturar
        worker.process_socio_video("vid-w1")
        assert captured_callback is not None


class TestOtrosHandlers:
    def test_process_operational_video_exito(self, stub_container, stub_job_queue, monkeypatch):
        analyzer = MagicMock()
        fake_mod = MagicMock()
        fake_mod.OperationalAnalyzer.return_value = analyzer
        fake_jq = MagicMock()
        fake_jq.clear_active_operational_job = lambda aid: stub_job_queue["clear"].append(aid)
        monkeypatch.setitem(sys.modules, "use_cases.operational_analyzer", fake_mod)
        monkeypatch.setitem(sys.modules, "infrastructure.services.job_queue", fake_jq)

        result = worker.process_operational_video("op-1")
        assert result == {"success": True, "analysis_id": "op-1"}
        analyzer.process.assert_called_once_with("op-1")

    def test_process_audio_analysis_exito(self, stub_container, stub_job_queue, monkeypatch):
        analyzer = MagicMock()
        fake_mod = MagicMock()
        fake_mod.AudioAnalyzer.return_value = analyzer
        fake_jq = MagicMock()
        fake_jq.clear_active_audio_job = lambda aid: stub_job_queue["clear"].append(aid)
        monkeypatch.setitem(sys.modules, "use_cases.audio_analyzer", fake_mod)
        monkeypatch.setitem(sys.modules, "infrastructure.services.job_queue", fake_jq)

        result = worker.process_audio_analysis("aud-1")
        assert result == {"success": True, "analysis_id": "aud-1"}
        analyzer.process.assert_called_once_with("aud-1")
