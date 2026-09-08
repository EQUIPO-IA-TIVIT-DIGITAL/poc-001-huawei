import { useState, useEffect } from 'react';
import { getApiBaseUrl } from '../lib/backendUrl';
import { createPortal } from 'react-dom';
import { MessageCircle, Send, Sparkles, X, CheckCircle, AlertCircle, Loader2 } from 'lucide-react';
import { Button } from './ui/button';

interface WorkspaceChatModalProps {
    open: boolean;
    onClose: () => void;
    workspaceId: string;
    workspaceName: string;
    onContextImproved?: () => void;
}

interface Message {
    role: 'user' | 'assistant' | 'system';
    content: string;
}

export function WorkspaceChatModal({ open, onClose, workspaceId, workspaceName, onContextImproved }: WorkspaceChatModalProps) {
    const [estado, setEstado] = useState<'validando' | 'preguntas' | 'mejorando' | 'chat' | 'completo'>('validando');
    const [loading, setLoading] = useState(false);
    const [preguntas, setPreguntas] = useState<string[]>([]);
    const [respuestasInputs, setRespuestasInputs] = useState<string[]>([]);
    const [mensajes, setMensajes] = useState<Message[]>([]);
    const [inputMensaje, setInputMensaje] = useState('');
    const [error, setError] = useState<string | null>(null);

    const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || getApiBaseUrl();

    // Ejecutar validación cuando se abre el modal
    useEffect(() => {
        if (open) {
            setEstado('validando');
            setError(null);
            validarContexto();
        }
    }, [open]);

    const validarContexto = async () => {
        setLoading(true);
        setError(null);
        
        try {
            const response = await fetch(`${API_BASE_URL}/workspaces/${workspaceId}/chat/validate`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });

            if (!response.ok) throw new Error('Error al validar contexto');

            const data = await response.json();
            
            if (data.validacion.suficiente) {
                setEstado('completo');
            } else {
                setPreguntas(data.validacion.preguntas || []);
                setRespuestasInputs(new Array(data.validacion.preguntas?.length || 0).fill(''));
                setEstado('preguntas');
            }
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const agregarRespuesta = () => {
        // Obsolete
    };

    const mejorarContexto = async (todasRespuestas: string[]) => {
        setEstado('mejorando');
        setLoading(true);
        
        try {
            const response = await fetch(`${API_BASE_URL}/workspaces/${workspaceId}/chat/improve`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({ respuestas: todasRespuestas })
            });

            if (!response.ok) throw new Error('Error al mejorar contexto');

            const data = await response.json();
            setEstado('completo');
            onContextImproved?.();
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    const enviarMensaje = async () => {
        if (!inputMensaje.trim()) return;
        
        const nuevoMensaje: Message = { role: 'user', content: inputMensaje };
        setMensajes(prev => [...prev, nuevoMensaje]);
        setInputMensaje('');
        setLoading(true);
        
        try {
            const response = await fetch(`${API_BASE_URL}/workspaces/${workspaceId}/chat/conversation`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify({
                    mensaje: inputMensaje,
                    historial: mensajes
                })
            });

            if (!response.ok) throw new Error('Error en conversación');

            const data = await response.json();
            setMensajes(prev => [...prev, { role: 'assistant', content: data.respuesta }]);
        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    if (!open) return null;

    return createPortal(
        <div 
            className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4"
            onClick={(e) => {
                e.stopPropagation();
                if (e.target === e.currentTarget) onClose();
            }}
        >
            <div 
                className="bg-white rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-hidden shadow-2xl"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="relative bg-gradient-to-r from-red-600 via-red-700 to-gray-900 px-6 py-5">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <div className="bg-white/20 p-2 rounded-xl backdrop-blur-sm">
                                <MessageCircle size={24} className="text-white" />
                            </div>
                            <div>
                                <h2 className="text-2xl font-bold text-white">Asistente IA</h2>
                                <p className="text-red-100 text-sm">{workspaceName}</p>
                            </div>
                        </div>
                        <button
                            onClick={(e) => {
                                e.stopPropagation();
                                onClose();
                            }}
                            className="text-white/80 hover:text-white transition-colors p-2 hover:bg-white/20 rounded-lg"
                        >
                            <X size={24} />
                        </button>
                    </div>
                </div>

                {/* Content */}
                <div className="p-6 space-y-4 max-h-[60vh] overflow-y-auto">
                    {error && (
                        <div className="bg-red-50 border-l-4 border-red-600 text-red-800 px-4 py-3 rounded-lg flex items-start gap-3">
                            <AlertCircle size={20} className="flex-shrink-0 mt-0.5" />
                            <p>{error}</p>
                        </div>
                    )}

                    {/* Estado: Validando */}
                    {estado === 'validando' && (
                        <div className="flex flex-col items-center justify-center py-12">
                            <Loader2 size={48} className="text-red-600 animate-spin mb-4" />
                            <p className="text-gray-700 font-semibold">Analizando tu configuración...</p>
                            <p className="text-gray-500 text-sm mt-2">La IA está revisando si el contexto es claro</p>
                        </div>
                    )}

                    {/* Estado: Preguntas */}
                    {estado === 'preguntas' && (
                        <div className="space-y-4">
                            <div className="bg-gradient-to-r from-yellow-50 to-orange-50 border border-yellow-200 rounded-xl p-4">
                                <div className="flex items-start gap-3">
                                    <Sparkles className="text-orange-600 mt-0.5 flex-shrink-0" size={20} />
                                    <div>
                                        <p className="font-semibold text-gray-800 mb-2">
                                            La IA necesita más información para ser precisa
                                        </p>
                                        <p className="text-sm text-gray-600">
                                            Responde estas preguntas para mejorar el análisis:
                                        </p>
                                    </div>
                                </div>
                            </div>

                            {preguntas.map((pregunta, idx) => (
                                <div key={idx} className="space-y-2">
                                    <label className="block text-sm font-semibold text-gray-800">
                                        {idx + 1}. {pregunta}
                                    </label>
                                    <textarea
                                        value={respuestasInputs[idx] || ''}
                                        onChange={(e) => {
                                            const newInputs = [...respuestasInputs];
                                            newInputs[idx] = e.target.value;
                                            setRespuestasInputs(newInputs);
                                        }}
                                        onClick={(e) => e.stopPropagation()}
                                        placeholder="Escribe tu respuesta..."
                                        className="w-full px-4 py-3 border-2 border-red-200 rounded-xl focus:ring-2 focus:ring-red-600 focus:border-red-600 resize-none"
                                        rows={3}
                                    />
                                </div>
                            ))}

                            <Button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    mejorarContexto(respuestasInputs);
                                }}
                                disabled={respuestasInputs.some(r => !r.trim()) || loading}
                                className="w-full mt-4 bg-red-600 hover:bg-red-700 text-white px-6 py-3 rounded-xl font-semibold"
                            >
                                Mejorar Contexto
                            </Button>
                        </div>
                    )}

                    {/* Estado: Mejorando */}
                    {estado === 'mejorando' && (
                        <div className="flex flex-col items-center justify-center py-12">
                            <Loader2 size={48} className="text-red-600 animate-spin mb-4" />
                            <p className="text-gray-700 font-semibold">Mejorando tu contexto...</p>
                            <p className="text-gray-500 text-sm mt-2">La IA está integrando tus respuestas</p>
                        </div>
                    )}

                    {/* Estado: Completo */}
                    {estado === 'completo' && (
                        <div className="bg-gradient-to-r from-green-50 to-emerald-50 border border-green-200 rounded-xl p-6">
                            <div className="flex items-start gap-4">
                                <div className="bg-green-100 p-3 rounded-full">
                                    <CheckCircle size={32} className="text-green-600" />
                                </div>
                                <div className="flex-1">
                                    <h3 className="text-lg font-bold text-gray-900 mb-2">
                                        ✅ Contexto Optimizado
                                    </h3>
                                    <p className="text-gray-700 mb-4">
                                        {respuestasInputs.length > 0
                                            ? 'Tu contexto ha sido mejorado con tus respuestas. La IA ahora tiene información más clara para analizar tus videos.'
                                            : 'Tu contexto es suficientemente claro. La IA está lista para analizar videos con precisión.'}
                                    </p>
                                    <Button
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            setEstado('chat');
                                        }}
                                        className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg text-sm font-semibold"
                                    >
                                        💬 Seguir conversando
                                    </Button>
                                </div>
                            </div>
                        </div>
                    )}

                    {/* Estado: Chat libre */}
                    {estado === 'chat' && (
                        <div className="space-y-4">
                            <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                                <p className="text-sm text-red-900">
                                    💡 Pregúntame lo que quieras sobre cómo configurar mejor tu proyecto
                                </p>
                            </div>

                            <div className="space-y-3 max-h-[40vh] overflow-y-auto">
                                {mensajes.map((msg, idx) => (
                                    <div
                                        key={idx}
                                        className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                                    >
                                        <div
                                            className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                                                msg.role === 'user'
                                                    ? 'bg-red-600 text-white'
                                                    : 'bg-gray-100 text-gray-900'
                                            }`}
                                        >
                                            <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                                        </div>
                                    </div>
                                ))}
                                {loading && (
                                    <div className="flex justify-start">
                                        <div className="bg-gray-100 rounded-2xl px-4 py-3">
                                            <Loader2 size={16} className="text-gray-600 animate-spin" />
                                        </div>
                                    </div>
                                )}
                            </div>

                            <div className="flex gap-2">
                                <input
                                    type="text"
                                    value={inputMensaje}
                                    onChange={(e) => setInputMensaje(e.target.value)}
                                    onClick={(e) => e.stopPropagation()}
                                    onKeyPress={(e) => {
                                        e.stopPropagation();
                                        if (e.key === 'Enter') enviarMensaje();
                                    }}
                                    placeholder="Escribe tu mensaje..."
                                    className="flex-1 px-4 py-3 border-2 border-red-200 rounded-xl focus:ring-2 focus:ring-red-600 focus:border-red-600"
                                    disabled={loading}
                                />
                                <Button
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        enviarMensaje();
                                    }}
                                    disabled={!inputMensaje.trim() || loading}
                                    className="bg-red-600 hover:bg-red-700 text-white px-6 py-3 rounded-xl font-semibold"
                                >
                                    <Send size={20} />
                                </Button>
                            </div>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="bg-gray-50 border-t px-6 py-4 flex justify-end gap-3">
                    <Button
                        onClick={(e) => {
                            e.stopPropagation();
                            onClose();
                        }}
                        className="bg-white border-2 border-gray-300 text-gray-700 hover:bg-gray-100 px-6 py-2 rounded-xl font-semibold"
                    >
                        Cerrar
                    </Button>
                </div>
            </div>
        </div>,
        document.body
    );
}