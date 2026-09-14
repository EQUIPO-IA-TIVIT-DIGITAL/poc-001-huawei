import { MessageSquare, Send, Sparkles } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { AudioQueryResult } from '../../services/audioAnalysisService';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { useTranslation } from '../../i18n';
import type { TranslationKey } from '../../i18n/es';

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

const SUGGESTION_KEYS: TranslationKey[] = [
  'audioTabs.suggestionThemes',
  'audioTabs.suggestionDates',
  'audioTabs.suggestionBudget',
  'audioTabs.suggestionDecisions',
];

export function ChatTab({
  chatMessages,
  querying,
  queryInput,
  setQueryInput,
  onQuery,
}: ChatTabProps) {
  const { t } = useTranslation();

  return (
    <div className="flex h-[600px] flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
      <div className="flex-1 space-y-4 overflow-y-auto p-6">
        {chatMessages.length === 0 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-2xl border border-brand-border bg-brand-soft p-6 text-left"
          >
            <div className="mb-3 flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-brand-border bg-brand-soft">
                <MessageSquare className="h-5 w-5 text-primary" aria-hidden="true" />
              </div>
              <h3 className="text-lg font-bold text-foreground">{t('audioTabs.chatEmptyTitle')}</h3>
            </div>
            <p className="pl-[52px] text-[15px] font-medium leading-relaxed text-muted-foreground">
              {t('audioTabs.chatEmptyDesc')}
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
                <div className="max-w-md rounded-2xl rounded-br-lg bg-foreground px-6 py-4 text-background shadow-sm">
                  <p className="text-[15px] font-medium leading-relaxed">{msg.question}</p>
                </div>
              ) : (
                <div className="max-w-2xl space-y-4 rounded-2xl rounded-bl-lg border border-border bg-muted/50 px-6 py-5">
                  {msg.result?.respuesta && (
                    <p className="whitespace-pre-wrap text-[15px] leading-relaxed text-foreground">
                      {msg.result.respuesta}
                    </p>
                  )}

                  {msg.result?.momentos_relevantes && msg.result.momentos_relevantes.length > 0 && (
                    <div className="mt-4 space-y-3 border-t border-border pt-3">
                      <p className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-widest text-muted-foreground">
                        <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                        {t('audioTabs.relevantMoments')}
                      </p>
                      {msg.result.momentos_relevantes.map((m) => (
                        <div
                          key={`${msg.id}-${m.timestamp_seconds}-${m.timestamp}`}
                          className="flex items-start gap-3 rounded-xl border border-border bg-card p-4 shadow-sm transition-colors hover:border-primary/40"
                        >
                          <span className="flex-shrink-0 rounded-md border border-border bg-muted px-2.5 py-1 font-mono text-xs font-bold text-muted-foreground">
                            {m.timestamp}
                          </span>
                          <div className="text-[14px]">
                            <p className="leading-relaxed text-foreground">{m.contexto}</p>
                            {m.relevancia && (
                              <p className="mt-1.5 text-[12px] italic text-muted-foreground">
                                &ldquo;{m.relevancia}&rdquo;
                              </p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {msg.result?.text_matches && msg.result.text_matches.length > 0 && (
                    <div className="mt-4 space-y-3 border-t border-border pt-3">
                      <p className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">
                        {t('audioTabs.textMatches')}
                      </p>
                      {msg.result.text_matches.map((m) => (
                        <div
                          key={`${msg.id}-${m.start_time}-${m.timestamp}`}
                          className="flex items-start gap-3 rounded-xl border border-border bg-card p-4 shadow-sm"
                        >
                          <span className="flex-shrink-0 rounded-md border border-border bg-muted px-2.5 py-1 font-mono text-xs font-bold text-muted-foreground">
                            {m.timestamp}
                          </span>
                          <p className="text-[14px] text-foreground">{m.text}</p>
                        </div>
                      ))}
                    </div>
                  )}

                  {msg.result?.confianza && (
                    <p className="flex items-center gap-2 pt-2 text-[12px] font-medium text-muted-foreground">
                      <span className="h-1.5 w-1.5 rounded-full bg-success" />
                      {t('audioTabs.confidenceSegments', {
                        confidence: msg.result.confianza,
                        segments: msg.result.segments_found,
                      })}
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
            aria-live="polite"
          >
            <div className="flex items-center gap-3 rounded-2xl rounded-bl-lg border border-border bg-muted/50 px-6 py-5">
              <div className="flex gap-1.5">
                <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground" style={{ animationDelay: '0ms' }} />
                <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground" style={{ animationDelay: '150ms' }} />
                <span className="h-2 w-2 animate-bounce rounded-full bg-muted-foreground" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-[14px] font-medium text-muted-foreground">
                {t('audioTabs.analyzingTranscription')}
              </span>
            </div>
          </motion.div>
        )}
      </div>

      <div className="space-y-4 border-t border-border bg-muted/30 p-6">
        <div className="flex flex-wrap gap-2">
          {SUGGESTION_KEYS.map((key) => (
            <Button
              key={key}
              variant="outline"
              size="sm"
              className="rounded-full"
              onClick={() => setQueryInput(t(key))}
            >
              {t(key)}
            </Button>
          ))}
        </div>

        <div className="flex gap-3">
          <div className="flex-1">
            <Input
              type="text"
              value={queryInput}
              onChange={(e) => setQueryInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  onQuery();
                }
              }}
              placeholder={t('audioTabs.queryPlaceholder')}
              disabled={querying}
              className="rounded-full"
            />
          </div>
          <Button
            onClick={onQuery}
            disabled={!queryInput.trim() || querying}
            size="icon"
            className="rounded-full"
            aria-label={t('audioTabs.sendQuestion')}
          >
            <Send aria-hidden="true" />
          </Button>
        </div>
      </div>
    </div>
  );
}
