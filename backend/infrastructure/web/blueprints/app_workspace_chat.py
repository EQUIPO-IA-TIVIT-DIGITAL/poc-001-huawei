"""
Endpoint para Chat Interactivo con IA para validar contexto de Workspaces
"""

from flask import Blueprint, request, jsonify, session
from datetime import datetime
import json
import os
import re
from functools import wraps

from infrastructure.repositories.workspace_repository import WorkspaceRepositoryFirestore
from infrastructure.services.logging_service import get_logger
from infrastructure.services.ai_cost_control import AIUsageTracker
from infrastructure.dependencies import get_ai_adapter
from infrastructure.rate_limiter import limiter, AI_CHAT_LIMIT, API_LIMIT

logger = get_logger(__name__)

# Lazy init de IA (usar gateway local provisto por DI; evitar conexión al importar)
def _get_ai_adapter():
    return get_ai_adapter()

def workspace_auth_required(f):
    """Decorator para required autenticación"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Permitir peticiones OPTIONS sin autenticación (CORS preflight)
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)
        if 'username' not in session:
            return jsonify({'success': False, 'error': 'No autenticado'}), 401
        return f(*args, **kwargs)
    return decorated_function

workspace_chat_bp = Blueprint('workspace_chat', __name__)

# Handler global para OPTIONS en todos los endpoints de este blueprint
@workspace_chat_bp.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = jsonify({"status": "ok"})
        response.status_code = 200
        return response


@workspace_chat_bp.route('/workspaces/<workspace_id>/chat/validate', methods=['POST', 'OPTIONS'])
@limiter.limit(AI_CHAT_LIMIT, methods=["POST"])
@workspace_auth_required
def validate_workspace_context(workspace_id):
    """
    Inicia validación interactiva del contexto del workspace con IA
    
    La IA analiza el contexto y genera preguntas si necesita más claridad
    """
    # Manejar preflight CORS
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    
    try:
        usuario = session.get('username')
        
        # ===== CONTROL DE COSTOS DE IA =====
        
        # 1. Verificar límites diarios del usuario
        allowed, limit_error = AIUsageTracker.check_user_limits(usuario)
        if not allowed:
            logger.warning(f"🚫 Límite de IA alcanzado para {usuario}: {limit_error}")
            return jsonify({
                'success': False,
                'error': limit_error,
                'usage': AIUsageTracker.get_user_usage_today(usuario)
            }), 429
        
        workspace_repo = WorkspaceRepositoryFirestore()
        workspace = workspace_repo.obtener_por_id(workspace_id)
        
        if not workspace or workspace.usuario != usuario:
            return jsonify({'success': False, 'error': 'Workspace no encontrado'}), 404
        
        # Construir prompt para validación
        prompt = f"""Eres un asistente EXIGENTE y experto en configuración de sistemas de moderación de contenido con IA.

Tu tarea es analizar la configuración de un proyecto (workspace) y evaluar si el contexto proporcionado es SUFICIENTE y CLARO para que una IA de análisis de videos pueda tomar decisiones PRECISAS y CONTEXTUALES.

**INFORMACIÓN DEL PROYECTO:**

📁 Nombre: {workspace.nombre}
📝 Descripción: {workspace.descripcion or 'Sin descripción'}
📂 Categoría: {getattr(workspace, 'categoria', 'general')}
🎯 Nivel de Tolerancia: {getattr(workspace, 'nivel_tolerancia', 'medio')}

🎬 Tipo de Contenido Esperado:
{getattr(workspace, 'tipo_contenido', 'No especificado')}

👁️ Elementos Visuales Comunes:
{getattr(workspace, 'elementos_visuales', 'No especificados')}

💬 Contexto Proporcionado:
{workspace.contexto or 'Sin contexto adicional'}

---

**TU ANÁLISIS (SÉ CRÍTICO Y CONSTRUCTIVO):**

1. **Evalúa RIGUROSAMENTE** si la información es suficiente para que una IA entienda:
   - Qué tipo de videos se subirán exactamente
   - Qué elementos visuales son normales/esperados (uniformes, equipamiento, escenarios)
   - Qué comportamientos son aceptables en este contexto específico
   - Qué nivel de intensidad es normal (contacto físico, velocidad, riesgo)
   - Qué situaciones podrían parecer peligrosas pero son NORMALES en este dominio

2. **SIEMPRE incluye sugerencias de mejora**, incluso si el contexto es aceptable.
   La IA de moderación necesita el MÁXIMO detalle posible para no generar falsos positivos.

3. **Si la información ES SUFICIENTE (pero mejorable):**
   - Responde con: {{"suficiente": true, "mensaje": "✅ El contexto es aceptable, pero estas mejoras ayudarían a la IA...", "sugerencias": ["sugerencia concreta 1", "sugerencia concreta 2"]}}
   - OBLIGATORIO: incluir al menos 1-2 sugerencias concretas de mejora

4. **Si FALTA INFORMACIÓN CRÍTICA:**
   - Responde con: {{"suficiente": false, "preguntas": ["¿pregunta 1?", "¿pregunta 2?"], "razon": "explicación de qué falta"}}

**CRITERIOS DE SUFICIENCIA (SER ESTRICTO):**
- ¿Está claro el DOMINIO del contenido? (deportes, educación, seguridad, etc.)
- ¿Se especifican los ELEMENTOS VISUALES que aparecerán? (NO basta con decir "deportes", hay que decir QUÉ deporte, QUÉ se verá)
- ¿Se menciona el CONTEXTO específico? (competencias, entrenamientos, clases, vigilancia de qué)
- ¿Se indica el NIVEL de intensidad esperado? (contacto leve, contacto fuerte, riesgo)
- ¿Se aclara qué comportamientos son NORMALES en este contexto?
- ¿Se especifica qué DEBERÍA SER RECHAZADO? (contenido fuera de tema, violencia real vs deportiva, etc.)
- ¿Se menciona el público objetivo? (niños, adultos, profesionales)

**REGLAS ESTRICTAS:**
- NUNCA respondas que todo está "perfecto" o "excelente" sin sugerencias
- Si la información provista por el usuario (en descripción o contexto) YA RESPONDE DUDAS CLAVES, puedes aprobarlo (suficiente: true) SIN IMPORTAR la categoría.
- Si es categoría "general" o "entretenimiento" y la info es VAGA, pide MÁS detalles. Pero si el contexto añadido es muy claro, APRUÉBALO.
- Si es "deportes" con tolerancia "alto", verifica QUÉ deporte, QUÉ nivel de contacto es normal, QUÉ equipamiento. Si ya lo dice, apruébalo.
- Si es "seguridad", verifica QUÉ están vigilando, en QUÉ entorno, QUÉ es una alerta vs. normalidad. Si ya lo dice, apruébalo.
- Máximo 3 preguntas, las más importantes y CONCISAS (máximo 150 caracteres por pregunta). ¡No dejes oraciones a medias!
- Sugerencias deben ser CONCRETAS y ACCIONABLES (no genéricas)

Responde SOLO con JSON válido, sin markdown ni explicaciones adicionales.
"""

        # Verificar si Gemini está disponible
        ai_adapter = _get_ai_adapter()
        if not ai_adapter.disponible:
            logger.warning(f"🤖 IA no disponible para validación de workspace {workspace_id}")
            return jsonify({
                'success': True,
                'workspace_id': workspace_id,
                'validacion': {
                    'suficiente': True,
                    'mensaje': '⚠️ Servicio de IA no configurado. La validación automática no está disponible. Puedes continuar sin ella, pero asegúrate de revisar manualmente que el contexto sea claro y específico.',
                    'sugerencias': [
                        'Configura un proveedor de IA para habilitar la validación',
                        'Revisa que la descripción sea específica y detallada',
                        'Menciona claramente qué tipo de contenido se subirá'
                    ],
                    'sin_ia': True
                },
                'timestamp': datetime.now().isoformat()
            }), 200

        logger.info(f"🔍 Validando contexto workspace '{workspace.nombre}' (id={workspace_id}): "
                    f"categoria={getattr(workspace, 'categoria', 'general')}, "
                    f"tolerancia={getattr(workspace, 'nivel_tolerancia', 'medio')}, "
                    f"contexto_len={len(workspace.contexto or '')}")

        try:
            # Llamar a la pasarela de IA local/API comercial.
            ai_response = ai_adapter.chat(
                [{"role": "user", "content": prompt}],
                json_mode=True,
                temperature=0.3,
                max_tokens=1500,
            ).strip()
            
            # Limpiar respuesta (quitar markdown si existe)
            if '```json' in ai_response:
                ai_response = ai_response.split('```json')[1].split('```')[0].strip()
            elif '```' in ai_response:
                ai_response = ai_response.split('```')[1].split('```')[0].strip()
            
            # Buscar JSON en la respuesta
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                ai_response = json_match.group(0)
            
            # Intentar parsear JSON, con reparación de truncados
            try:
                validacion = json.loads(ai_response)
            except json.JSONDecodeError:
                # Intentar reparar JSON truncado (comillas/llaves sin cerrar)
                repaired = ai_response.rstrip()
                if repaired.count('"') % 2 != 0:
                    repaired += '"'
                if repaired.count('[') > repaired.count(']'):
                    repaired += ']' * (repaired.count('[') - repaired.count(']'))
                if repaired.count('{') > repaired.count('}'):
                    repaired += '}' * (repaired.count('{') - repaired.count('}'))
                try:
                    validacion = json.loads(repaired)
                except json.JSONDecodeError:
                    logger.warning(f"JSON de IA irreparable, usando fallback crítico. Respuesta: {ai_response[:200]}")
                    validacion = {
                        "suficiente": False,
                        "preguntas": [
                            "¿Podrías describir con más detalle qué tipo de videos se subirán a este proyecto?",
                            "¿Qué elementos visuales son normales en tu contenido? (personas, equipamiento, escenarios)",
                            "¿Qué comportamientos o situaciones son aceptables en este contexto?"
                        ],
                        "razon": "La IA no pudo completar el análisis. Por favor, proporciona más detalles sobre el contexto de tu proyecto para asegurar una moderación precisa."
                    }
            
        except Exception as e:
            logger.error(f"Error al consultar IA: {e}")
            # Fallback: pedir más info en vez de aprobar ciegamente
            validacion = {
                "suficiente": False,
                "preguntas": [
                    "¿Qué tipo de contenido se subirá a este proyecto?",
                    "¿Qué elementos visuales son esperados y normales?",
                    "¿Cuál es el público objetivo de este contenido?"
                ],
                "razon": "La validación IA no está disponible temporalmente. Por favor, describe mejor el contexto para asegurar una moderación precisa cuando el servicio se recupere."
            }
        
        logger.info(f"✅ Validación workspace {workspace_id}: "
                    f"suficiente={validacion.get('suficiente')}, "
                    f"sugerencias={len(validacion.get('sugerencias', []))}, "
                    f"preguntas={len(validacion.get('preguntas', []))}")

        # Registrar uso de IA (estimación de tokens)
        input_tokens = len(prompt) // 4  # Aproximación: 1 token ≈ 4 caracteres
        output_tokens = len(str(validacion)) // 4
        
        ai_model = ai_adapter.get_model_name("text") if hasattr(ai_adapter, "get_model_name") else "ai-gateway"
        AIUsageTracker.log_usage(
            usuario=usuario,
            endpoint='validate',
            workspace_id=workspace_id,
            workspace_nombre=workspace.nombre,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=0,  # No medimos latencia aquí
            model=ai_model,
            success=True,
            prompt=prompt
        )

        # Si es suficiente, marcar en la base de datos
        if validacion.get('suficiente') is True:
            if not workspace.metadatos:
                workspace.metadatos = {}
            workspace.metadatos['ia_contextualizada'] = True
            workspace_repo.guardar(workspace)

        return jsonify({
            'success': True,
            'workspace_id': workspace_id,
            'validacion': validacion,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Error en validación de workspace: {e}")
        return jsonify({'success': False, 'error': "Error interno del servidor"}), 500


@workspace_chat_bp.route('/workspaces/<workspace_id>/chat/improve', methods=['POST', 'OPTIONS'])
@limiter.limit(AI_CHAT_LIMIT, methods=["POST"])
@workspace_auth_required
def improve_workspace_context(workspace_id):
    """
    El usuario responde las preguntas de la IA y esta mejora el contexto automáticamente
    """
    # Manejar preflight CORS
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    
    try:
        usuario = session.get('username')
        data = request.get_json()
        respuestas = data.get('respuestas', [])  # Lista de respuestas del usuario
        
        workspace_repo = WorkspaceRepositoryFirestore()
        workspace = workspace_repo.obtener_por_id(workspace_id)
        
        if not workspace or workspace.usuario != usuario:
            return jsonify({'success': False, 'error': 'Workspace no encontrado'}), 404
        
        logger.info(f"📝 Mejorando contexto workspace {workspace_id}: "
                    f"respuestas={len(respuestas)}, "
                    f"contexto_actual_len={len(workspace.contexto or '')}")

        # Fallback determinístico cuando Gemini no está disponible o falla.
        def _build_fallback_context(ctx_actual: str, respuestas_usuario: list) -> str:
            base = (ctx_actual or '').strip()
            extras = [str(r).strip() for r in respuestas_usuario if str(r).strip()]
            if not extras:
                return base[:1000]

            bloques = []
            if base:
                bloques.append(base)
            bloques.append("Contexto adicional confirmado por el usuario:")
            for r in extras:
                bloques.append(f"- {r}")

            return "\n".join(bloques)[:1000]
        
        # Construir conversación
        respuestas_texto = "\n".join([f"- {r}" for r in respuestas])
        
        prompt = f"""Basándote en la configuración original del workspace y las respuestas del usuario, MEJORA el contexto para que sea más claro y útil para la IA de moderación.

**CONFIGURACIÓN ACTUAL:**
- Categoría: {getattr(workspace, 'categoria', 'general')}
- Tipo: {getattr(workspace, 'tipo_contenido', '')}
- Elementos: {getattr(workspace, 'elementos_visuales', '')}
- Contexto actual: {workspace.contexto}

**RESPUESTAS DEL USUARIO:**
{respuestas_texto}

**TU TAREA:**
Genera un contexto MEJORADO que:
1. Integre las respuestas del usuario
2. Sea específico y claro
3. Ayude a la IA a entender qué es normal en este proyecto
4. Mencione elementos visuales esperados
5. Aclare el nivel de intensidad aceptable
6. Máximo 800 caracteres, directo y útil

Responde SOLO con el texto del contexto mejorado, sin explicaciones ni formato markdown.
"""

        # Verificar si Gemini está disponible
        if not _get_ai_adapter().disponible:
            contexto_mejorado = _build_fallback_context(workspace.contexto, respuestas)
            workspace.contexto = contexto_mejorado
            workspace.fecha_modificacion = datetime.now().isoformat()
            workspace_repo.guardar(workspace)

            logger.warning(f"🤖 Gemini no disponible en improve. Usando fallback local para workspace {workspace_id}")
            return jsonify({
                'success': True,
                'workspace_id': workspace_id,
                'contexto_mejorado': contexto_mejorado,
                'fallback': True,
                'mensaje': 'Contexto actualizado sin IA (fallback local)'
            }), 200

        try:
            # Llamar a la pasarela de IA local
            contexto_mejorado = _get_ai_adapter().chat(
                [{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=1000,
            ).strip()
            
            # Limpiar texto
            contexto_mejorado = contexto_mejorado.replace('```', '').strip()
            
        except Exception as e:
            logger.error(f"Error al mejorar contexto con Gemini: {e}")
            contexto_mejorado = _build_fallback_context(workspace.contexto, respuestas)
            workspace.contexto = contexto_mejorado
            workspace.fecha_modificacion = datetime.now().isoformat()
            workspace_repo.guardar(workspace)

            return jsonify({
                'success': True,
                'workspace_id': workspace_id,
                'contexto_mejorado': contexto_mejorado,
                'fallback': True,
                'mensaje': 'Contexto actualizado con fallback local (Gemini no disponible)'
            }), 200
        
        # Actualizar workspace
        workspace.contexto = contexto_mejorado[:1000]  # Límite de seguridad
        workspace.fecha_modificacion = datetime.now().isoformat()
        
        # Marcar como contextualizada si el usuario aportó mejoras
        if not workspace.metadatos:
            workspace.metadatos = {}
        workspace.metadatos['ia_contextualizada'] = True
        
        workspace_repo.guardar(workspace)
        
        logger.info(f"✅ Contexto mejorado workspace {workspace_id}: "
                    f"nuevo_len={len(contexto_mejorado)}, "
                    f"preview={contexto_mejorado[:100]}...")
        
        return jsonify({
            'success': True,
            'contexto_mejorado': contexto_mejorado,
            'workspace_id': workspace_id,
            'mensaje': '✅ Contexto actualizado con éxito'
        })
        
    except Exception as e:
        print(f"Error mejorando contexto: {e}")
        return jsonify({'success': False, 'error': "Error interno del servidor"}), 500


@workspace_chat_bp.route('/workspaces/<workspace_id>/chat/conversation', methods=['POST', 'OPTIONS'])
@limiter.limit(AI_CHAT_LIMIT, methods=["POST"])
@workspace_auth_required
def chat_conversation(workspace_id):
    """
    Chat libre con la IA sobre el workspace para aclarar dudas
    """
    # Manejar preflight CORS
    if request.method == 'OPTIONS':
        return jsonify({'success': True}), 200
    
    try:
        usuario = session.get('username')
        data = request.get_json()
        mensaje_usuario = data.get('mensaje', '')
        historial = data.get('historial', [])
        
        workspace_repo = WorkspaceRepositoryFirestore()
        workspace = workspace_repo.obtener_por_id(workspace_id)
        
        if not workspace or workspace.usuario != usuario:
            return jsonify({'success': False, 'error': 'Workspace no encontrado'}), 404
        
        # Construir mensajes para la conversación
        system_prompt = f"""Eres un asistente experto que ayuda a configurar proyectos de análisis de video con IA.

Estás ayudando al usuario a configurar este proyecto:
- Nombre: {workspace.nombre}
- Categoría: {getattr(workspace, 'categoria', 'general')}
- Tipo de contenido: {getattr(workspace, 'tipo_contenido', 'No especificado')}
- Elementos visuales: {getattr(workspace, 'elementos_visuales', 'No especificados')}
- Contexto actual: {workspace.contexto or 'Sin contexto'}

Tu rol es:
1. Hacer preguntas claras y específicas
2. Sugerir mejoras al contexto
3. Explicar por qué cierta información es importante para la IA
4. Ser amigable y conciso

No escribas el contexto completo por el usuario, solo hazle preguntas o sugerencias.
"""

        # Verificar si Gemini está disponible
        if not _get_ai_adapter().disponible:
            return jsonify({
                'success': False,
                'error': 'Chat de IA no disponible. Configura un proveedor de IA para usar esta función.'
            }), 400

        try:
            # Construir el prompt completo con historial
            full_prompt = system_prompt + "\n\n"
            
            # Agregar historial
            for msg in historial:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    full_prompt += f"Usuario: {content}\n"
                else:
                    full_prompt += f"Asistente: {content}\n"
            
            # Agregar mensaje actual
            full_prompt += f"\nUsuario: {mensaje_usuario}\nAsistente:"

            # Llamar a la pasarela de IA local
            respuesta_ia = _get_ai_adapter().chat(
                [{"role": "user", "content": full_prompt}],
                temperature=0.7,
                max_tokens=500,
            ).strip()
            
        except Exception as e:
            logger.error(f"Error en conversación con Gemini: {e}")
            return jsonify({'success': False, 'error': 'Error en conversación'}), 500
        
        return jsonify({
            'success': True,
            'respuesta': respuesta_ia,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Error en conversación: {e}")
        return jsonify({'success': False, 'error': "Error interno del servidor"}), 500
