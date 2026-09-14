import { AlertCircle, CheckCircle, Globe, MapPin, Mic2, Sparkles, Users } from 'lucide-react';
import { motion } from 'framer-motion';
import { AudioAnalysis } from '../../services/audioAnalysisService';
import { useTranslation } from '../../i18n';

interface SummaryTabProps {
  analysis: AudioAnalysis;
}

export function SummaryTab({ analysis }: SummaryTabProps) {
  const { t } = useTranslation();
  const summary = analysis.summary || {};
  const summaryText = (summary.resumen || '').toString();
  const insufficient = /insuficiente/i.test(summaryText);
  const shortAudio = analysis.video_duration > 0 && analysis.video_duration < 15;

  if (!summary || Object.keys(summary).length === 0) {
    return (
      <div className="rounded-2xl border border-border bg-card p-12 text-center shadow-sm">
        <div className="mx-auto mb-5 flex h-20 w-20 items-center justify-center rounded-2xl border border-border bg-muted/40 shadow-sm">
          <Sparkles className="h-10 w-10 text-muted-foreground/50" aria-hidden="true" />
        </div>
        <p className="text-lg font-bold text-foreground">{t('audioTabs.summaryUnavailable')}</p>
        <p className="mt-2 text-[15px] font-medium text-muted-foreground">
          {t('audioTabs.summaryUnavailableDesc')}
        </p>
      </div>
    );
  }

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.1 } },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 15 },
    visible: { opacity: 1, y: 0 },
  };

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="space-y-8 rounded-2xl border border-border bg-card p-8 shadow-sm lg:p-10"
    >
      {summary.resumen && (
        <motion.div variants={itemVariants}>
          <div className="mb-5 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-brand-border bg-brand-soft">
              <Sparkles className="h-5 w-5 text-primary" aria-hidden="true" />
            </div>
            <h3 className="text-xl font-bold text-foreground">{t('audioTabs.summaryTitle')}</h3>
          </div>

          {insufficient ? (
            <div className="space-y-3 rounded-2xl border border-warning-border bg-warning-surface p-6">
              <div className="flex items-start gap-3">
                <AlertCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-warning" aria-hidden="true" />
                <p className="text-[15px] font-bold text-warning">{t('audioTabs.insufficientTitle')}</p>
              </div>
              <p className="pl-8 text-[14px] font-medium text-warning/90">{t('audioTabs.insufficientHint')}</p>
              {shortAudio && (
                <p className="pl-8 text-[13px] font-bold text-warning">
                  {t('audioTabs.detectedDuration', { seconds: Math.round(analysis.video_duration) })}
                </p>
              )}
            </div>
          ) : (
            <p className="whitespace-pre-wrap text-[15px] font-medium leading-relaxed text-foreground">
              {summary.resumen}
            </p>
          )}
        </motion.div>
      )}

      {summary.temas_principales?.length > 0 && (
        <motion.div variants={itemVariants}>
          <h3 className="mb-4 text-[11px] font-bold uppercase tracking-widest text-muted-foreground">
            {t('audioTabs.mainTopics')}
          </h3>
          <div className="flex flex-wrap gap-2.5">
            {summary.temas_principales.map((tema: string) => (
              <span
                key={tema}
                className="rounded-full border border-brand-border bg-brand-soft px-4 py-2 text-[13px] font-bold text-brand-hover shadow-sm"
              >
                {tema}
              </span>
            ))}
          </div>
        </motion.div>
      )}

      {summary.puntos_clave?.length > 0 && (
        <motion.div variants={itemVariants}>
          <h3 className="mb-4 text-[11px] font-bold uppercase tracking-widest text-muted-foreground">
            {t('audioTabs.keyPoints')}
          </h3>
          <ul className="space-y-3">
            {summary.puntos_clave.map((punto: string) => (
              <li
                key={punto}
                className="flex items-start gap-3.5 rounded-2xl border border-border bg-muted/30 p-4 text-[15px] font-medium text-foreground"
              >
                <div className="mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full border border-success-border bg-success-surface">
                  <CheckCircle className="h-4 w-4 text-success" strokeWidth={3} aria-hidden="true" />
                </div>
                <span className="leading-relaxed">{punto}</span>
              </li>
            ))}
          </ul>
        </motion.div>
      )}

      <motion.div variants={itemVariants} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {summary.personas_mencionadas?.length > 0 && (
          <div className="rounded-2xl border border-border bg-muted/30 p-5">
            <div className="mb-4 flex items-center gap-2">
              <Users className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
              <h4 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                {t('audioTabs.peopleMentioned')}
              </h4>
            </div>
            <div className="flex flex-wrap gap-2">
              {summary.personas_mencionadas.map((p: string) => (
                <span
                  key={p}
                  className="rounded-lg border border-border bg-card px-3 py-1.5 text-[13px] font-bold tracking-wide text-foreground shadow-sm"
                >
                  {p}
                </span>
              ))}
            </div>
          </div>
        )}

        {summary.lugares_mencionados?.length > 0 && (
          <div className="rounded-2xl border border-border bg-muted/30 p-5">
            <div className="mb-4 flex items-center gap-2">
              <MapPin className="h-4 w-4 text-success" aria-hidden="true" />
              <h4 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                {t('audioTabs.placesMentioned')}
              </h4>
            </div>
            <div className="flex flex-wrap gap-2">
              {summary.lugares_mencionados.map((l: string) => (
                <span
                  key={l}
                  className="flex items-center gap-1.5 rounded-lg border border-success-border bg-success-surface px-3 py-1.5 text-[13px] font-bold tracking-wide text-success shadow-sm"
                >
                  <MapPin className="h-3.5 w-3.5 text-success" aria-hidden="true" />
                  {l}
                </span>
              ))}
            </div>
          </div>
        )}

        {summary.tono_general && (
          <div className="rounded-2xl border border-border bg-muted/30 p-5">
            <div className="mb-2 flex items-center gap-2">
              <Mic2 className="h-4 w-4 text-primary" aria-hidden="true" />
              <h4 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                {t('audioTabs.tone')}
              </h4>
            </div>
            <p className="font-bold capitalize text-foreground">{summary.tono_general}</p>
          </div>
        )}

        {summary.idioma_principal && (
          <div className="rounded-2xl border border-border bg-muted/30 p-5">
            <div className="mb-2 flex items-center gap-2">
              <Globe className="h-4 w-4 text-info" aria-hidden="true" />
              <h4 className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                {t('audioTabs.mainLanguage')}
              </h4>
            </div>
            <p className="font-bold capitalize text-foreground">{summary.idioma_principal}</p>
          </div>
        )}
      </motion.div>

      <motion.div variants={itemVariants} className="border-t border-border pt-6">
        <div className="flex w-fit flex-wrap items-center gap-6 rounded-2xl border border-border bg-muted/30 p-4 text-[13px] font-medium text-muted-foreground">
          <span className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-muted-foreground/50" />
            {t('audioTabs.totalWords')}: <strong className="text-foreground">{summary.cantidad_palabras || '—'}</strong>
          </span>
          <span className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-success" />
            {t('audioTabs.summaryConfidence')}:{' '}
            <strong className="text-foreground">{(analysis.average_confidence * 100).toFixed(0)}%</strong>
          </span>
          <span className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-info" />
            {t('audioTabs.segmentsLabel')}: <strong className="text-foreground">{analysis.total_segments}</strong>
          </span>
        </div>
      </motion.div>
    </motion.div>
  );
}
