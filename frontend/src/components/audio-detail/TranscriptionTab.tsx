import { ReactNode } from 'react';
import { Copy, Loader2, Play, Search, X } from 'lucide-react';
import { AudioSegment, AudioAnalysis } from '../../services/audioAnalysisService';
import { audioAnalysisService } from '../../services/audioAnalysisService';

interface SearchResult extends AudioSegment {
  timestamp_formatted: string;
}

interface TranscriptionTabProps {
  analysis: AudioAnalysis;
  segments: AudioSegment[];
  totalSegments: number;
  segmentsCursor: string | null;
  loadingSegments: boolean;
  onLoadSegments: (reset?: boolean) => void;
  searchQuery: string;
  setSearchQuery: (value: string) => void;
  searching: boolean;
  onSearch: () => void;
  searchResults: SearchResult[];
  clearSearch: () => void;
  onCopyTranscription: () => void;
  onSeekTo: (seconds: number) => void;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function highlightText(text: string, query: string): Array<string | ReactNode> {
  if (!query.trim()) return [text];

  const pattern = new RegExp(`(${escapeRegExp(query)})`, 'ig');
  const parts = text.split(pattern);

  return parts.map((part, idx) => (
    pattern.test(part)
      ? <mark key={`${part}-${idx}`} className="bg-yellow-200/80 text-gray-900 px-0.5 rounded">{part}</mark>
      : part
  ));
}

export function TranscriptionTab({
  analysis,
  segments,
  totalSegments,
  segmentsCursor,
  loadingSegments,
  onLoadSegments,
  searchQuery,
  setSearchQuery,
  searching,
  onSearch,
  searchResults,
  clearSearch,
  onCopyTranscription,
  onSeekTo,
}: TranscriptionTabProps) {
  return (
    <div className="bg-white rounded-3xl shadow-sm border border-slate-200/60 overflow-hidden">
      {/* Search bar */}
      <div className="p-6 border-b border-slate-100 bg-white">
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && onSearch()}
              placeholder="Buscar en la transcripción..."
              className="w-full pl-11 pr-5 py-3.5 bg-slate-50/50 border border-slate-200/60 rounded-full focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 outline-none text-[15px] font-medium text-slate-800 transition-all shadow-sm"
            />
          </div>
          <button
            onClick={onSearch}
            disabled={!searchQuery.trim() || searching}
            className="px-5 py-3.5 bg-red-500 text-white rounded-full hover:bg-red-600 transition-all shadow-md disabled:opacity-50 disabled:shadow-none flex items-center justify-center"
          >
            {searching ? <Loader2 className="w-5 h-5 animate-spin" /> : <Search className="w-5 h-5" />}
          </button>
          <button
            onClick={onCopyTranscription}
            className="px-5 py-3.5 bg-white border border-slate-200/60 rounded-full hover:bg-slate-50 transition-all flex items-center gap-2 text-slate-600 shadow-sm font-semibold text-[14px]"
            title="Copiar transcripción completa"
          >
            <Copy className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Search results */}
      {searchResults.length > 0 && (
        <div className="p-4 bg-amber-50/50 border-b border-amber-100">
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm font-semibold text-amber-800">
              {searchResults.length} coincidencias para "{searchQuery}"
            </p>
            <button onClick={clearSearch} className="flex items-center gap-1 text-xs text-amber-600 hover:text-amber-800 transition-colors">
              <X className="w-3 h-3" />
              Limpiar
            </button>
          </div>
          <div className="space-y-2 max-h-52 overflow-y-auto">
            {searchResults.map((result) => (
              <div key={`${result.id}-${result.start_time}`} className="flex items-start gap-2.5 p-3 bg-white rounded-xl border border-amber-100 hover:border-amber-200 transition-colors">
                <button
                  onClick={() => onSeekTo(result.start_time)}
                  className="bg-gradient-to-r from-amber-500 to-orange-500 text-white px-2.5 py-1 rounded-lg text-xs font-mono flex-shrink-0 mt-0.5 hover:shadow-md transition-shadow"
                >
                  {result.timestamp_formatted}
                </button>
                <p className="text-sm text-gray-700 leading-relaxed">{highlightText(result.text, searchQuery)}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Segments list */}
      <div className="divide-y divide-slate-100/60 max-h-[500px] overflow-y-auto">
        {loadingSegments && segments.length === 0 ? (
          <div className="p-10 text-center">
            <Loader2 className="w-8 h-8 animate-spin mx-auto mb-3 text-red-500" />
            <p className="text-slate-500 text-[15px] font-medium">Cargando transcripción...</p>
          </div>
        ) : segments.length === 0 ? (
          <div className="p-10 text-center text-slate-400">
            <p className="text-[15px] font-medium">Sin segmentos de transcripción</p>
          </div>
        ) : (
          segments.map((segment, idx) => {
            const prevSpeaker = idx > 0 ? segments[idx - 1].speaker : null;
            const showSpeaker = segment.speaker && segment.speaker !== prevSpeaker;
            return (
              <div key={segment.id} className="hover:bg-slate-50/80 transition-colors group">
                {showSpeaker && (
                  <div className="px-6 pt-5 pb-1">
                    <span className="inline-flex items-center gap-1 bg-red-500 text-white text-[12px] font-bold px-3 py-1 rounded-full shadow-sm tracking-wide">
                      {segment.speaker}
                    </span>
                  </div>
                )}
                <div className="flex items-start gap-4 px-6 pb-4 pt-3">
                  <button
                    onClick={() => onSeekTo(segment.start_time)}
                    className="bg-slate-800 text-white px-3 py-1.5 rounded-full text-[13px] font-mono font-bold flex-shrink-0 mt-0.5 min-w-[78px] text-center inline-flex items-center justify-center gap-1.5 hover:bg-red-500 transition-all duration-300 shadow-sm"
                    title="Ir a este momento"
                  >
                    <Play className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity -ml-1 absolute group-hover:relative" />
                    {audioAnalysisService.formatTimestamp(segment.start_time)}
                  </button>
                  <p className="text-[15px] text-slate-700 flex-1 leading-relaxed">{highlightText(segment.text, searchQuery)}</p>
                  <span className="text-[12px] text-slate-400 flex-shrink-0 font-medium whitespace-nowrap">
                    {(segment.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Load more */}
      {segmentsCursor && segments.length < totalSegments && (
        <div className="p-6 border-t border-slate-100 text-center bg-slate-50/50">
          <button
            onClick={() => onLoadSegments(false)}
            disabled={loadingSegments}
            className="px-6 py-2.5 bg-white text-slate-600 border border-slate-200/60 rounded-full hover:bg-slate-50 transition-all text-[14px] font-bold disabled:opacity-50 shadow-sm"
          >
            {loadingSegments ? (
              <Loader2 className="w-4 h-4 animate-spin inline mr-2" />
            ) : null}
            Cargar más ({segments.length} de {totalSegments})
          </button>
        </div>
      )}

      {/* Footer info */}
      {analysis.full_transcription && analysis.full_transcription.length > 0 && (
        <div className="px-6 pb-5 pt-3 text-[12px] font-medium text-slate-400 text-center border-t border-slate-100">
          Transcripción total disponible en {analysis.total_segments} segmentos.
        </div>
      )}
    </div>
  );
}
