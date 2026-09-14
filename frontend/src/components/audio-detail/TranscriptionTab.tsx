import { ReactNode } from 'react';
import { Copy, Loader2, Play, Search, X } from 'lucide-react';
import { AudioSegment, AudioAnalysis } from '../../services/audioAnalysisService';
import { audioAnalysisService } from '../../services/audioAnalysisService';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { useTranslation } from '../../i18n';

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

  return parts.map((part, idx) =>
    pattern.test(part) ? (
      <mark key={`${part}-${idx}`} className="rounded bg-warning/30 px-0.5 text-foreground">
        {part}
      </mark>
    ) : (
      part
    ),
  );
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
  const { t } = useTranslation();

  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-card shadow-sm">
      <div className="border-b border-border bg-card p-6">
        <div className="flex gap-3">
          <div className="flex-1">
            <Input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  onSearch();
                }
              }}
              placeholder={t('audioTabs.searchPlaceholder')}
              icon={<Search aria-hidden="true" />}
              className="rounded-full"
            />
          </div>
          <Button
            onClick={onSearch}
            disabled={!searchQuery.trim() || searching}
            size="icon"
            className="rounded-full"
            aria-label={t('common.search')}
          >
            {searching ? <Loader2 className="animate-spin" aria-hidden="true" /> : <Search aria-hidden="true" />}
          </Button>
          <Button
            onClick={onCopyTranscription}
            variant="outline"
            size="icon"
            className="rounded-full"
            title={t('audioTabs.copyTitle')}
            aria-label={t('audioTabs.copyTitle')}
          >
            <Copy aria-hidden="true" />
          </Button>
        </div>
      </div>

      {searchResults.length > 0 && (
        <div className="border-b border-warning-border bg-warning-surface p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-sm font-semibold text-warning">
              {t('audioTabs.matchesFor', { count: searchResults.length, query: searchQuery })}
            </p>
            <Button variant="ghost" size="sm" onClick={clearSearch} className="text-warning">
              <X aria-hidden="true" />
              {t('audioTabs.clear')}
            </Button>
          </div>
          <div className="max-h-52 space-y-2 overflow-y-auto">
            {searchResults.map((result) => (
              <div
                key={`${result.id}-${result.start_time}`}
                className="flex items-start gap-2.5 rounded-xl border border-warning-border bg-card p-3 transition-colors hover:border-warning"
              >
                <Button
                  size="xs"
                  onClick={() => onSeekTo(result.start_time)}
                  className="mt-0.5 flex-shrink-0 bg-warning font-mono hover:bg-warning/90"
                >
                  {result.timestamp_formatted}
                </Button>
                <p className="text-sm leading-relaxed text-foreground">
                  {highlightText(result.text, searchQuery)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="max-h-[500px] divide-y divide-border overflow-y-auto">
        {loadingSegments && segments.length === 0 ? (
          <div className="p-10 text-center" aria-live="polite">
            <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin text-primary" aria-hidden="true" />
            <p className="text-[15px] font-medium text-muted-foreground">{t('audioTabs.loadingTranscription')}</p>
          </div>
        ) : segments.length === 0 ? (
          <div className="p-10 text-center text-muted-foreground">
            <p className="text-[15px] font-medium">{t('audioTabs.noSegments')}</p>
          </div>
        ) : (
          segments.map((segment, idx) => {
            const prevSpeaker = idx > 0 ? segments[idx - 1].speaker : null;
            const showSpeaker = segment.speaker && segment.speaker !== prevSpeaker;
            return (
              <div key={segment.id} className="group transition-colors hover:bg-muted/40">
                {showSpeaker && (
                  <div className="px-6 pb-1 pt-5">
                    <span className="inline-flex items-center gap-1 rounded-full bg-primary px-3 py-1 text-[12px] font-bold tracking-wide text-primary-foreground shadow-sm">
                      {segment.speaker}
                    </span>
                  </div>
                )}
                <div className="flex items-start gap-4 px-6 pb-4 pt-3">
                  <Button
                    size="sm"
                    onClick={() => onSeekTo(segment.start_time)}
                    title={t('audioTabs.seekTo')}
                    aria-label={t('audioTabs.seekTo')}
                    className="mt-0.5 min-w-[78px] flex-shrink-0 justify-center font-mono"
                  >
                    <Play className="h-3.5 w-3.5 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden="true" />
                    {audioAnalysisService.formatTimestamp(segment.start_time)}
                  </Button>
                  <p className="flex-1 text-[15px] leading-relaxed text-foreground">
                    {highlightText(segment.text, searchQuery)}
                  </p>
                  <span className="flex-shrink-0 whitespace-nowrap text-[12px] font-medium text-muted-foreground">
                    {(segment.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>

      {segmentsCursor && segments.length < totalSegments && (
        <div className="border-t border-border bg-muted/30 p-6 text-center">
          <Button
            variant="outline"
            onClick={() => onLoadSegments(false)}
            disabled={loadingSegments}
            className="rounded-full"
          >
            {loadingSegments && <Loader2 className="animate-spin" aria-hidden="true" />}
            {t('audioTabs.loadMore', { loaded: segments.length, total: totalSegments })}
          </Button>
        </div>
      )}

      {analysis.full_transcription && analysis.full_transcription.length > 0 && (
        <div className="border-t border-border px-6 pb-5 pt-3 text-center text-[12px] font-medium text-muted-foreground">
          {t('audioTabs.transcriptionTotal', { count: analysis.total_segments })}
        </div>
      )}
    </div>
  );
}
