import { Loader2, MessageSquare, Send, Sparkles } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { AudioQueryResult } from '../../services/audioAnalysisService';

interface ChatMessage {
  id: string;
  type: 'user' | 'assistant';
  question?: string;
  result?: AudioQueryResult;
  timestamp: Date;
}

interface ChatTabProps {
  chatMessages: ChatMessage[];
  querying: boolean;
  queryInput: string;
  setQueryInput: (value: string) => void;
  onQuery: () => void;
}

const SUGGESTIONS = [
  '¿De qué temas se habla?',
  '¿Se mencionan fechas o plazos?',
  '¿Quién habla sobre el presupuesto?',
  '¿Qué decisiones se tomaron?',
];

export function ChatTab({
  chatMessages,
  querying,
  queryInput,
  setQueryInput,
  onQuery,
}: ChatTabProps) {
  return (
    <div className="bg-white rounded-3xl shadow-sm border border-slate-200/60 overflow-hidden flex flex-col" style={{ height: '600px' }}>
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {chatMessages.length === 0 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-left rounded-2xl border border-red-100 bg-red-50/50 p-6"
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-[14px] bg-red-100 flex items-center justify-center border border-red-200/60">
                <MessageSquare className="w-5 h-5 text-red-600" />
              </div>
              <h3 className="font-bold text-slate-800 text-lg">Haz una consulta sobre el audio</h3>
            </div>
            <p className="text-[15px] font-medium text-slate-500 leading-relaxed pl-[52px]">
              Escribe una pregunta y el sistema buscará en la transcripción para responder con contexto y momento exacto.
            </p>
          </motion.div>
        )}

        <AnimatePresence>
          {chatMessages.map((msg) => (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 15, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3 }}
              className={`flex ${msg.type === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              {msg.type === 'user' ? (
                <div className="max-w-md bg-slate-800 text-white rounded-[20px] rounded-br-[8px] px-6 py-4 shadow-sm">
                  <p className="leading-relaxed font-medium text-[15px]">{msg.question}</p>
                </div>
              ) : (
                <div className="max-w-2xl bg-slate-50 rounded-[20px] rounded-bl-[8px] px-6 py-5 space-y-4 border border-slate-100/80">
                  {msg.result?.respuesta && (
                    <p className="text-slate-700 whitespace-pre-wrap leading-relaxed text-[15px]">{msg.result.respuesta}</p>
                  )}

                  {msg.result?.momentos_relevantes && msg.result.momentos_relevantes.length > 0 && (
                    <div className="space-y-3 pt-3 mt-4 border-t border-slate-200/60">
                      <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5" />
                        Momentos relevantes
                      </p>
                      {msg.result.momentos_relevantes.map((m) => (
                        <div
                          key={`${msg.id}-${m.timestamp_seconds}-${m.timestamp}`}
                          className="flex items-start gap-3 p-4 bg-white rounded-xl border border-slate-100 hover:border-slate-200 transition-colors shadow-sm"
                        >
                          <span className="bg-slate-100 text-slate-600 px-2.5 py-1 rounded-md text-xs font-bold font-mono flex-shrink-0 border border-slate-200/60">
                            {m.timestamp}
                          </span>
                          <div className="text-[14px]">
                            <p className="text-slate-700 leading-relaxed">{m.contexto}</p>
                            {m.relevancia && (
                              <p className="text-slate-400 text-[12px] mt-1.5 italic">&ldquo;{m.relevancia}&rdquo;</p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {msg.result?.text_matches && msg.result.text_matches.length > 0 && (
                    <div className="space-y-3 pt-3 mt-4 border-t border-slate-200/60">
                      <p className="text-[11px] font-bold text-slate-400 uppercase tracking-widest">
                        Coincidencias textuales
                      </p>
                      {msg.result.text_matches.map((m) => (
                        <div
                          key={`${msg.id}-${m.start_time}-${m.timestamp}`}
                          className="flex items-start gap-3 p-4 bg-white rounded-xl border border-slate-100 shadow-sm"
                        >
                          <span className="bg-slate-100 text-slate-600 px-2.5 py-1 rounded-md text-xs font-bold font-mono flex-shrink-0 border border-slate-200/60">
                            {m.timestamp}
                          </span>
                          <p className="text-[14px] text-slate-700">{m.text}</p>
                        </div>
                      ))}
                    </div>
                  )}

                  {msg.result?.confianza && (
                    <p className="text-[12px] font-medium text-slate-400 pt-2 flex items-center gap-2">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      Confianza: {msg.result.confianza} • {msg.result.segments_found} segmentos encontrados
                    </p>
                  )}
                </div>
              )}
            </motion.div>
          ))}
        </AnimatePresence>

        {querying && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex justify-start"
          >
            <div className="bg-slate-50 rounded-[20px] rounded-bl-[8px] px-6 py-5 flex items-center gap-3 border border-slate-100/80">
              <div className="flex gap-1.5">
                <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-slate-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-[14px] font-medium text-slate-500">Analizando transcripción...</span>
            </div>
          </motion.div>
        )}
      </div>

      <div className="border-t border-slate-100 p-6 space-y-4 bg-slate-50/50">
        <div className="flex flex-wrap gap-2">
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              onClick={() => setQueryInput(suggestion)}
              className="px-4 py-2 bg-white text-slate-500 border border-slate-200/60 rounded-full text-[13px] font-semibold hover:bg-slate-100 hover:text-slate-800 transition-all duration-200 shadow-sm"
            >
              {suggestion}
            </button>
          ))}
        </div>

        <div className="flex gap-3">
          <input
            type="text"
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && onQuery()}
            placeholder="Escribe tu pregunta sobre el contenido del audio..."
            className="flex-1 px-5 py-3.5 bg-white border border-slate-200/60 rounded-full focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none transition-all text-[15px] shadow-sm font-medium text-slate-800"
            disabled={querying}
          />
          <motion.button
            whileHover={{ scale: 1.05 }}
            whileTap={{ scale: 0.95 }}
            onClick={onQuery}
            disabled={!queryInput.trim() || querying}
            className="px-5 py-3.5 bg-red-500 text-white rounded-full shadow-md hover:bg-red-600 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
          >
            <Send className="w-5 h-5 ml-1" />
          </motion.button>
        </div>
      </div>
    </div>
  );
}
