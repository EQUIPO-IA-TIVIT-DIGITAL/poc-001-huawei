import { AlertCircle, CheckCircle, Globe, MapPin, Mic2, Sparkles, Users } from 'lucide-react';
import { motion } from 'framer-motion';
import { AudioAnalysis } from '../../services/audioAnalysisService';

interface SummaryTabProps {
  analysis: AudioAnalysis;
}

export function SummaryTab({ analysis }: SummaryTabProps) {
  const summary = analysis.summary || {};
  const summaryText = (summary.resumen || '').toString();
  const insufficient = /insuficiente/i.test(summaryText);
  const shortAudio = analysis.video_duration > 0 && analysis.video_duration < 15;

  if (!summary || Object.keys(summary).length === 0) {
    return (
      <div className="bg-white rounded-3xl shadow-sm border border-slate-200/60 p-12 text-center">
        <div className="w-20 h-20 rounded-[24px] bg-slate-50 border border-slate-100 flex items-center justify-center mx-auto mb-5 shadow-sm">
          <Sparkles className="w-10 h-10 text-slate-300" />
        </div>
        <p className="text-slate-600 font-bold text-lg">Resumen no disponible</p>
        <p className="text-[15px] font-medium text-slate-400 mt-2">El audio no generó suficiente contenido para resumir.</p>
      </div>
    );
  }

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: { staggerChildren: 0.1 },
    },
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
      className="bg-white rounded-3xl shadow-sm border border-slate-200/60 p-8 lg:p-10 space-y-8"
    >
      {/* Resumen principal */}
      {summary.resumen && (
        <motion.div variants={itemVariants}>
          <div className="flex items-center gap-3 mb-5">
            <div className="w-10 h-10 rounded-2xl bg-red-50 border border-red-100/60 flex items-center justify-center">
              <Sparkles className="w-5 h-5 text-red-500" />
            </div>
            <h3 className="text-xl font-bold text-slate-800">Resumen</h3>
          </div>

          {insufficient ? (
            <div className="p-6 rounded-[20px] border border-amber-200/60 bg-amber-50/50 space-y-3">
              <div className="flex items-start gap-3">
                <AlertCircle className="w-5 h-5 mt-0.5 flex-shrink-0 text-amber-500" />
                <p className="font-bold text-amber-800 text-[15px]">Contenido insuficiente para generar resumen estructurado.</p>
              </div>
              <p className="text-[14px] font-medium text-amber-700 pl-8">
                Consejo: el modelo suele requerir al menos 15 segundos de audio claro para identificar temas y construir un resumen útil.
              </p>
              {shortAudio && (
                <p className="text-[13px] font-bold text-amber-600 pl-8">Duración detectada: {Math.round(analysis.video_duration)}s.</p>
              )}
            </div>
          ) : (
            <p className="text-slate-600 leading-relaxed whitespace-pre-wrap text-[15px] font-medium">{summary.resumen}</p>
          )}
        </motion.div>
      )}

      {/* Temas principales */}
      {summary.temas_principales?.length > 0 && (
        <motion.div variants={itemVariants}>
          <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-4">Temas principales</h3>
          <div className="flex flex-wrap gap-2.5">
            {summary.temas_principales.map((tema: string) => (
              <span key={tema} className="px-4 py-2 bg-red-50/80 text-red-600 border border-red-100/80 rounded-full text-[13px] font-bold shadow-sm">
                {tema}
              </span>
            ))}
          </div>
        </motion.div>
      )}

      {/* Puntos clave */}
      {summary.puntos_clave?.length > 0 && (
        <motion.div variants={itemVariants}>
          <h3 className="text-[11px] font-bold text-slate-400 uppercase tracking-widest mb-4">Puntos clave</h3>
          <ul className="space-y-3">
            {summary.puntos_clave.map((punto: string) => (
              <li key={punto} className="flex items-start gap-3.5 text-[15px] font-medium text-slate-700 bg-slate-50/50 p-4 rounded-2xl border border-slate-100/60">
                <div className="w-6 h-6 rounded-full bg-emerald-100 border border-emerald-200/60 flex items-center justify-center flex-shrink-0 mt-0.5">
                  <CheckCircle className="w-4 h-4 text-emerald-500" strokeWidth={3} />
                </div>
                <span className="leading-relaxed">{punto}</span>
              </li>
            ))}
          </ul>
        </motion.div>
      )}

      {/* Info grid */}
      <motion.div variants={itemVariants} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {summary.personas_mencionadas?.length > 0 && (
          <div className="p-5 bg-slate-50 border border-slate-100/80 rounded-[20px]">
            <div className="flex items-center gap-2 mb-4">
              <Users className="w-4 h-4 text-slate-400" />
              <h4 className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Personas mencionadas</h4>
            </div>
            <div className="flex flex-wrap gap-2">
              {summary.personas_mencionadas.map((p: string) => (
                <span key={p} className="px-3 py-1.5 bg-white text-slate-700 border border-slate-200/60 shadow-sm rounded-lg text-[13px] font-bold tracking-wide">
                  {p}
                </span>
              ))}
            </div>
          </div>
        )}

        {summary.lugares_mencionados?.length > 0 && (
          <div className="p-5 bg-slate-50 border border-slate-100/80 rounded-[20px]">
            <div className="flex items-center gap-2 mb-4">
              <MapPin className="w-4 h-4 text-emerald-500" />
              <h4 className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Lugares mencionados</h4>
            </div>
            <div className="flex flex-wrap gap-2">
              {summary.lugares_mencionados.map((l: string) => (
                <span key={l} className="px-3 py-1.5 bg-white text-emerald-700 border border-emerald-100/60 shadow-sm rounded-lg text-[13px] font-bold tracking-wide flex items-center gap-1.5">
                  <MapPin className="w-3.5 h-3.5 text-emerald-500" />{l}
                </span>
              ))}
            </div>
          </div>
        )}

        {summary.tono_general && (
          <div className="p-5 bg-slate-50 border border-slate-100/80 rounded-[20px]">
            <div className="flex items-center gap-2 mb-2">
              <Mic2 className="w-4 h-4 text-purple-500" />
              <h4 className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Tono</h4>
            </div>
            <p className="text-slate-800 capitalize font-bold">{summary.tono_general}</p>
          </div>
        )}

        {summary.idioma_principal && (
          <div className="p-5 bg-slate-50 border border-slate-100/80 rounded-[20px]">
            <div className="flex items-center gap-2 mb-2">
              <Globe className="w-4 h-4 text-blue-500" />
              <h4 className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Idioma principal</h4>
            </div>
            <p className="text-slate-800 capitalize font-bold">{summary.idioma_principal}</p>
          </div>
        )}
      </motion.div>

      {/* Footer stats */}
      <motion.div variants={itemVariants} className="pt-6 border-t border-slate-100 items-center justify-between">
        <div className="flex flex-wrap items-center gap-6 text-[13px] text-slate-500 font-medium bg-slate-50/50 p-4 rounded-[20px] border border-slate-100/60 w-fit">
          <span className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-slate-300" />
            Total palabras: <strong className="text-slate-800">{summary.cantidad_palabras || '—'}</strong>
          </span>
          <span className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            Confianza: <strong className="text-slate-800">{(analysis.average_confidence * 100).toFixed(0)}%</strong>
          </span>
          <span className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-blue-400" />
            Segmentos: <strong className="text-slate-800">{analysis.total_segments}</strong>
          </span>
        </div>
      </motion.div>
    </motion.div>
  );
}
