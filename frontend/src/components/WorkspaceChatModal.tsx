import { useState, useEffect, useCallback } from 'react';
import { getApiBaseUrl } from '../lib/backendUrl';
import {
    MessageCircle, Send, Sparkles, CheckCircle2, AlertCircle, Loader2, Lightbulb,
} from 'lucide-react';
import { Button } from './ui/button';
import { Textarea } from './ui/textarea';
import { Input } from './ui/input';
import { Alert, AlertDescription, AlertTitle } from './ui/alert';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from './ui/dialog';
import { useTranslation } from '../i18n';

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

type ChatState = 'validando' | 'preguntas' | 'mejorando' | 'chat' | 'completo';

interface ValidateResponse {
    validacion: {
        suficiente: boolean;
        preguntas?: string[];
    };
}

interface ConversationResponse {
    respuesta: string;
}

export function WorkspaceChatModal({
    open,
    onClose,
    workspaceId,
    workspaceName,
    onContextImproved,
}: WorkspaceChatModalProps) {
    const { t } = useTranslation();
    const [estado, setEstado] = useState<ChatState>('validando');
    const [loading, setLoading] = useState(false);
    const [preguntas, setPreguntas] = useState<string[]>([]);
    const [respuestasInputs, setRespuestasInputs] = useState<string[]>([]);
    const [mensajes, setMensajes] = useState<Message[]>([]);
    const [inputMensaje, setInputMensaje] = useState('');
    const [error, setError] = useState<string | null>(null);

    const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || getApiBaseUrl();

    const validarContexto = useCallback(async () => {
        setLoading(true);
        setError(null);

        try {
            const response = await fetch(`${API_BASE_URL}/workspaces/${workspaceId}/chat/validate`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
            });

            if (!response.ok) throw new Error(t('chat.validateError'));

            const data = (await response.json()) as ValidateResponse;

            if (data.validacion.suficiente) {
                setEstado('completo');
            } else {
                setPreguntas(data.validacion.preguntas || []);
                setRespuestasInputs(new Array(data.validacion.preguntas?.length || 0).fill(''));
                setEstado('preguntas');
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : t('chat.validateError'));
        } finally {
            setLoading(false);
        }
    }, [API_BASE_URL, workspaceId, t]);

    useEffect(() => {
        if (open) {
            setEstado('validando');
            setError(null);
            void validarContexto();
        }
    }, [open, validarContexto]);

    const mejorarContexto = async (todasRespuestas: string[]) => {
        setEstado('mejorando');
        setLoading(true);

        try {
            const response = await fetch(`${API_BASE_URL}/workspaces/${workspaceId}/chat/improve`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify({ respuestas: todasRespuestas }),
            });

            if (!response.ok) throw new Error(t('chat.improveError'));

            setEstado('completo');
            onContextImproved?.();
        } catch (err) {
            setError(err instanceof Error ? err.message : t('chat.improveError'));
        } finally {
            setLoading(false);
        }
    };

    const enviarMensaje = async () => {
        if (!inputMensaje.trim()) return;

        const contenido = inputMensaje;
        setMensajes((prev) => [...prev, { role: 'user', content: contenido }]);
        setInputMensaje('');
        setLoading(true);

        try {
            const response = await fetch(`${API_BASE_URL}/workspaces/${workspaceId}/chat/conversation`, {
                method: 'POST',
                credentials: 'include',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest',
                },
                body: JSON.stringify({
                    mensaje: contenido,
                    historial: mensajes,
                }),
            });

            if (!response.ok) throw new Error(t('chat.conversationError'));

            const data = (await response.json()) as ConversationResponse;
            setMensajes((prev) => [...prev, { role: 'assistant', content: data.respuesta }]);
        } catch (err) {
            setError(err instanceof Error ? err.message : t('chat.conversationError'));
        } finally {
            setLoading(false);
        }
    };

    return (
        <Dialog
            open={open}
            onOpenChange={(nextOpen) => {
                if (!nextOpen) onClose();
            }}
        >
            <DialogContent className="max-w-2xl gap-0 overflow-hidden p-0">
                <DialogHeader className="relative bg-gradient-to-br from-primary to-foreground px-6 py-5">
                    <div className="flex items-center gap-3">
                        <div className="rounded-xl bg-white/15 p-2 backdrop-blur">
                            <MessageCircle size={24} className="text-primary-foreground" aria-hidden="true" />
                        </div>
                        <div className="text-left">
                            <DialogTitle className="text-2xl font-bold text-primary-foreground">
                                {t('chat.title')}
                            </DialogTitle>
                            <DialogDescription className="text-sm text-primary-foreground/80">
                                {workspaceName}
                            </DialogDescription>
                        </div>
                    </div>
                </DialogHeader>

                <div className="max-h-[60vh] space-y-4 overflow-y-auto p-6">
                    {error && (
                        <Alert variant="error">
                            <AlertCircle aria-hidden="true" />
                            <AlertTitle>{t('common.error')}</AlertTitle>
                            <AlertDescription>{error}</AlertDescription>
                        </Alert>
                    )}

                    {estado === 'validando' && (
                        <div className="flex flex-col items-center justify-center py-12" aria-live="polite">
                            <Loader2 size={48} className="mb-4 animate-spin text-primary" aria-hidden="true" />
                            <p className="font-semibold text-foreground">{t('chat.validating')}</p>
                            <p className="mt-2 text-sm text-muted-foreground">{t('chat.validatingHint')}</p>
                        </div>
                    )}

                    {estado === 'preguntas' && (
                        <div className="space-y-4">
                            <Alert variant="warning">
                                <Sparkles aria-hidden="true" />
                                <AlertTitle>{t('chat.needsInfoTitle')}</AlertTitle>
                                <AlertDescription>{t('chat.needsInfoDesc')}</AlertDescription>
                            </Alert>

                            {preguntas.map((pregunta, idx) => (
                                <div key={pregunta} className="space-y-2">
                                    <label
                                        htmlFor={`chat-question-${idx}`}
                                        className="block text-sm font-semibold text-foreground"
                                    >
                                        {idx + 1}. {pregunta}
                                    </label>
                                    <Textarea
                                        id={`chat-question-${idx}`}
                                        value={respuestasInputs[idx] || ''}
                                        onChange={(e) => {
                                            const newInputs = [...respuestasInputs];
                                            newInputs[idx] = e.target.value;
                                            setRespuestasInputs(newInputs);
                                        }}
                                        placeholder={t('chat.answerPlaceholder')}
                                        rows={3}
                                    />
                                </div>
                            ))}

                            <Button
                                onClick={() => void mejorarContexto(respuestasInputs)}
                                disabled={respuestasInputs.some((r) => !r.trim()) || loading}
                                loading={loading}
                                className="mt-4 w-full"
                            >
                                {t('chat.improveContext')}
                            </Button>
                        </div>
                    )}

                    {estado === 'mejorando' && (
                        <div className="flex flex-col items-center justify-center py-12" aria-live="polite">
                            <Loader2 size={48} className="mb-4 animate-spin text-primary" aria-hidden="true" />
                            <p className="font-semibold text-foreground">{t('chat.improving')}</p>
                            <p className="mt-2 text-sm text-muted-foreground">{t('chat.improvingHint')}</p>
                        </div>
                    )}

                    {estado === 'completo' && (
                        <div className="rounded-xl border border-success-border bg-success-surface p-6">
                            <div className="flex items-start gap-4">
                                <div className="rounded-full bg-success-surface p-3">
                                    <CheckCircle2 size={32} className="text-success" aria-hidden="true" />
                                </div>
                                <div className="flex-1">
                                    <h3 className="mb-2 text-lg font-bold text-foreground">
                                        {t('chat.optimizedTitle')}
                                    </h3>
                                    <p className="mb-4 text-muted-foreground">
                                        {respuestasInputs.length > 0
                                            ? t('chat.optimizedWithAnswers')
                                            : t('chat.optimizedNoAnswers')}
                                    </p>
                                    <Button size="sm" onClick={() => setEstado('chat')}>
                                        <MessageCircle aria-hidden="true" />
                                        {t('chat.continueChat')}
                                    </Button>
                                </div>
                            </div>
                        </div>
                    )}

                    {estado === 'chat' && (
                        <div className="space-y-4">
                            <Alert variant="info">
                                <Lightbulb aria-hidden="true" />
                                <AlertDescription>{t('chat.chatHint')}</AlertDescription>
                            </Alert>

                            <div className="max-h-[40vh] space-y-3 overflow-y-auto" aria-live="polite">
                                {mensajes.map((msg, idx) => (
                                    <div
                                        key={`${msg.role}-${idx}`}
                                        className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                                    >
                                        <div
                                            className={`max-w-[80%] rounded-2xl px-4 py-3 ${msg.role === 'user'
                                                ? 'bg-primary text-primary-foreground'
                                                : 'bg-muted text-foreground'
                                                }`}
                                        >
                                            <p className="whitespace-pre-wrap text-sm">{msg.content}</p>
                                        </div>
                                    </div>
                                ))}
                                {loading && (
                                    <div className="flex justify-start">
                                        <div className="rounded-2xl bg-muted px-4 py-3">
                                            <Loader2 size={16} className="animate-spin text-muted-foreground" aria-hidden="true" />
                                        </div>
                                    </div>
                                )}
                            </div>

                            <div className="flex gap-2">
                                <Input
                                    type="text"
                                    value={inputMensaje}
                                    onChange={(e) => setInputMensaje(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === 'Enter') {
                                            e.preventDefault();
                                            void enviarMensaje();
                                        }
                                    }}
                                    placeholder={t('chat.messagePlaceholder')}
                                    disabled={loading}
                                />
                                <Button
                                    onClick={() => void enviarMensaje()}
                                    disabled={!inputMensaje.trim() || loading}
                                    size="icon"
                                    aria-label={t('chat.sendMessage')}
                                >
                                    <Send aria-hidden="true" />
                                </Button>
                            </div>
                        </div>
                    )}
                </div>

                <div className="flex justify-end gap-3 border-t border-border bg-muted/40 px-6 py-4">
                    <Button variant="outline" onClick={onClose}>
                        {t('common.close')}
                    </Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}
