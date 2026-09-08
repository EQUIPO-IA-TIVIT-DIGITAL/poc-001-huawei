"""
whisper_adapter — Cliente faster-whisper (large-v3-turbo) OpenAI-compat
POST /v1/audio/transcriptions con multipart. Fallback a local ffmpeg extract.
"""
import logging
import mimetypes
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class WhisperAdapter:
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        from config.app_config import AppConfig
        self.base_url = (base_url or AppConfig.WHISPER_BASE_URL).rstrip("/")
        self.model = model or AppConfig.WHISPER_MODEL

    def is_available(self) -> bool:
        try:
            import httpx
            # whisper webservice usa :9000, health en /
            base = self.base_url.replace("/v1", "")
            r = httpx.get(f"{base}/health", timeout=3)
            if r.status_code < 500:
                return True
            r2 = httpx.get(f"{self.base_url}/models", timeout=3)
            return r2.status_code < 500
        except Exception as e:
            logger.debug("Whisper not available %s: %s", self.base_url, e)
            return False

    @property
    def disponible(self) -> bool:
        return self.is_available()

    def _extract_audio(self, video_path: str) -> str:
        """Extrae audio a wav 16k mono via ffmpeg."""
        fd, out = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        cmd = ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", out]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            return out
        except Exception as e:
            logger.error("ffmpeg extract audio fallo: %s", e)
            try:
                os.unlink(out)
            except Exception:
                pass
            raise

    def transcribe(self, video_path: str, language: str = "es") -> dict:
        """Transcribe video_path via Whisper API. Retorna {success, segments, text}."""
        audio_path: Optional[str] = None
        to_clean: Optional[str] = None
        # si es video, extrae audio
        ext = Path(video_path).suffix.lower()
        if ext in (".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"):
            audio_path = self._extract_audio(video_path)
            to_clean = audio_path
        else:
            audio_path = video_path

        try:
            import httpx
            # Intenta OpenAI-compat /v1/audio/transcriptions
            url = f"{self.base_url}/audio/transcriptions" if self.base_url.endswith("/v1") else f"{self.base_url}/asr"
            # probar v1 primero
            with open(audio_path, "rb") as f:
                files = {"file": (Path(audio_path).name, f, mimetypes.guess_type(audio_path)[0] or "audio/wav")}
                data = {"model": self.model, "language": language, "response_format": "verbose_json"}
                try:
                    r = httpx.post(url, files=files, data=data, timeout=300)
                except Exception:
                    # fallback a /asr (onerahmet)
                    alt = self.base_url.replace("/v1", "") + "/asr?task=transcribe&language=es&output=json"
                    f.seek(0)
                    r = httpx.post(alt, files=files, data={"output": "json"}, timeout=300)
            if r.status_code >= 400:
                raise RuntimeError(f"Whisper HTTP {r.status_code}: {r.text[:500]}")
            j = r.json()
            # normaliza a segments [{start,end,text}]
            segments: list[dict] = []
            if isinstance(j, dict) and "segments" in j:
                for s in j["segments"]:
                    segments.append({"start": float(s.get("start", 0)), "end": float(s.get("end", 0)), "text": s.get("text", ""), "speaker": "SPEAKER_1"})
            elif isinstance(j, dict) and "text" in j:
                segments = [{"start": 0.0, "end": 0.0, "text": j["text"], "speaker": "SPEAKER_1"}]
            else:
                segments = [{"start": 0.0, "end": 0.0, "text": str(j), "speaker": "SPEAKER_1"}]
            return {"success": True, "segments": segments, "text": " ".join(s["text"] for s in segments), "model": self.model}
        except Exception as e:
            logger.error("Whisper transcribe error: %s", e)
            return {"success": False, "segments": [], "text": "", "error": str(e)}
        finally:
            if to_clean and os.path.exists(to_clean):
                try:
                    os.unlink(to_clean)
                except Exception:
                    pass

    # Shim compat con GCPSpeechAdapter.transcribe_video
    def transcribe_video(self, video_path: str, video_id: str = "", duration_hint: float = 0) -> dict:
        r = self.transcribe(video_path)
        if not r.get("success"):
            return {"success": False, "tiene_audio": False, "transcripcion": ""}
        segs = r.get("segments", [])
        return {
            "success": True,
            "tiene_audio": len(segs) > 0,
            "tiene_voz": len(segs) > 0,
            "transcripcion": r.get("text", ""),
            "segmentos": segs,
            "palabras_totales": len(r.get("text", "").split()),
            "duracion_audio": duration_hint,
            "idiomas_detectados": ["es"],
            "confianza_transcripcion": 0.85,
            "palabras_temporales": [],
        }
