import json
import time
import logging
import re
from typing import Dict

from domain.entities import OperationalAnalysis
from infrastructure.adapters.gemini_operational_prompts import build_cross_analysis_prompt
from infrastructure.services.log_utils import sanitize_context_for_log

logger = logging.getLogger(__name__)

class OperationalCrossAnalyzer:
    """Fase 3: Meta-análisis cruzado usando consolidador LLM"""
    
    def __init__(self, gemini_adapter):
        self.gemini_adapter = gemini_adapter
        
    def cross_analyze(self, segment_results: list, analysis: OperationalAnalysis, video_duration: float, vid: str) -> dict:
        if not self.gemini_adapter or not self.gemini_adapter.disponible:
            logger.warning(f"[{vid}] ⚠️ Gemini no disponible para cross-analysis")
            return {}

        if not segment_results:
            return {}

        try:
            prompt = build_cross_analysis_prompt(
                analysis_type=analysis.analysis_type,
                custom_context=analysis.custom_context,
                total_events=len(segment_results),
                video_duration=video_duration
            )

            if len(segment_results) > 40:
                return self._chunked_cross_analysis(segment_results, prompt, analysis, vid)

            full_prompt = f"{prompt}\n\nRESULTADOS DE CADA SEGMENTO:\n{json.dumps(segment_results, indent=2, ensure_ascii=False, default=str)}\n"
            logger.info(f"[{vid}]    🧠 Consolidando {len(segment_results)} segmentos...")

            # Fase 3: usar ThinkingConfig via analyze_text_with_thinking
            text = self.gemini_adapter.analyze_text_with_thinking(full_prompt)
            if not text:
                return {'error': 'Respuesta vacía del modelo en cross-analysis'}

            return self._parse_json_response(text, vid)

        except Exception as e:
            logger.error(f"[{vid}]    ❌ Error en cross-analysis: {e}")
            return {'error': str(e)}

    def _chunked_cross_analysis(self, segment_results: list, base_prompt: str, analysis: OperationalAnalysis, vid: str) -> dict:
        CHUNK_SIZE = 30
        partial_results = []

        for i in range(0, len(segment_results), CHUNK_SIZE):
            chunk = segment_results[i:i + CHUNK_SIZE]
            chunk_num = i // CHUNK_SIZE + 1
            chunk_prompt = f"{base_prompt}\n\nRESULTADOS PARCIALES (grupo {chunk_num}):\n{json.dumps(chunk, indent=2, ensure_ascii=False, default=str)}\n"

            text = self.gemini_adapter.analyze_text_with_thinking(chunk_prompt)
            partial = self._parse_json_response(text, vid) if text else {'error': 'empty_response'}
            partial_results.append(partial)

            if i + CHUNK_SIZE < len(segment_results):
                time.sleep(2)

        logger.info(f"[{vid}]    🧠 Meta-consolidación de {len(partial_results)} chunks...")
        safe_context = sanitize_context_for_log(analysis.custom_context)
        meta_prompt = f"""Consolida estos {len(partial_results)} resultados parciales en UN SOLO JSON final.
Tipo: {analysis.analysis_type}. Contexto: {safe_context}.
Elimina duplicados, suma conteos, genera resumen definitivo.

RESULTADOS PARCIALES:
{json.dumps(partial_results, indent=2, ensure_ascii=False, default=str)}

RESPONDE EXCLUSIVAMENTE en JSON válido.
"""
        text = self.gemini_adapter.analyze_text_with_thinking(meta_prompt)
        return self._parse_json_response(text, vid) if text else {'error': 'empty_meta_response'}

    def _parse_json_response(self, text: str, vid: str) -> dict:
        try:
            clean = text.strip()
            if clean.startswith('```'):
                lines = clean.split('\n')
                json_lines = [l for l in lines if not l.startswith('```')]
                clean = '\n'.join(json_lines).strip()

            # Try parsing the full cleaned text first (handles both {} and [] from Gemini)
            try:
                parsed = json.loads(clean)
                if isinstance(parsed, dict):
                    return parsed
                if isinstance(parsed, list):
                    return {'items': parsed}
            except json.JSONDecodeError:
                pass

            json_start = clean.find('{')
            json_end = clean.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                return json.loads(clean[json_start:json_end])

            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                return json.loads(json_match.group(0))

            return {'raw_response': text[:500]}
        except json.JSONDecodeError as e:
            try:
                json_match = re.search(r'\{[\s\S]*\}', text)
                if json_match:
                    raw_json = json_match.group(0)
                    raw_json = re.sub(r',\s*([}\]])', r'\1', raw_json)
                    return json.loads(raw_json)
            except Exception:
                pass
            return {'raw_response': text[:500]}
