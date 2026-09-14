import { useEffect, useMemo, useState } from 'react';
import { Link } from '@tanstack/react-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { HelpCircle, Plus, Video } from 'lucide-react';
import { PageContainer } from '../components/ui/page-container';
import { PageHeader } from '../components/ui/page-header';
import { Button } from '../components/ui/button';
import { SearchInput } from '../components/ui/search-input';
import { Pagination } from '../components/ui/pagination';
import { StatusBadge, type AppStatus } from '../components/ui/status-badge';
import { EmptyState } from '../components/ui/empty-state';
import { LoadingState } from '../components/ui/loading-state';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { VideoDetailsModal } from '../components/VideoDetailsModal';
import { AnalysisExplanationModal } from '../components/AnalysisExplanationModal';
import { VideoTableRow, type VideoRow } from '../components/workspaces/VideoTableRow';
import { authService } from '../services/auth';
import { apiRequest } from '../lib/api';
import { toast } from 'sonner';
import { useTranslation } from '../i18n';
import { cn } from '../lib/utils';

type FilterKey = 'all' | 'pending' | 'approved' | 'rejected';

interface VideoRecord extends VideoRow {
  id: string;
}

const statusFromRaw = (raw?: string): AppStatus => {
  const status = (raw || '').toUpperCase();
  if (['APROBADO', 'COMPLETADO', 'FINALIZADO', 'DONE'].some((s) => status.includes(s)))
    return 'approved';
  if (['RECHAZADO', 'ERROR', 'FALLIDO', 'FAILED'].some((s) => status.includes(s)))
    return 'rejected';
  if (status.includes('EN_REVISION')) return 'pending';
  if (['SUBIENDO', 'UPLOADING'].some((s) => status.includes(s))) return 'uploading';
  return 'processing';
};

export default function MyVideos() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [filter, setFilter] = useState<FilterKey>('all');
  const [searchInput, setSearchInput] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [selectedVideoIds, setSelectedVideoIds] = useState<Set<string>>(new Set());
  const [selectedVideo, setSelectedVideo] = useState<VideoRecord | null>(null);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);
  const [isExplanationOpen, setIsExplanationOpen] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [isBatchDeleteOpen, setIsBatchDeleteOpen] = useState(false);

  const [currentPage, setCurrentPage] = useState(1);
  const [rowsPerPage, setRowsPerPage] = useState(10);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearch(searchInput.trim().toLowerCase());
      setCurrentPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const { data: videos = [], isLoading } = useQuery({
    queryKey: ['my-videos'],
    queryFn: async () => {
      const response = await apiRequest<{ success: boolean; videos: VideoRecord[] }>(
        '/socio/mis-videos',
      );
      return response?.success ? response.videos : [];
    },
    enabled: authService.isAuthenticated(),
  });

  useEffect(() => {
    const PROCESSING_STATES = [
      'pendiente', 'procesando', 'en_progreso', 'en_revision',
      'uploading', 'uploaded', 'analyzing', 'classifying',
      'deep_analyzing', 'generating_report', 'motion_detecting', 'motion_detected',
    ];

    const hasProcessing = videos.some((video) => {
      const status = (video?.estado || video?.resultado_ia || '').toString().toLowerCase();
      return PROCESSING_STATES.includes(status);
    });

    if (hasProcessing) {
      const interval = setInterval(() => {
        queryClient.invalidateQueries({ queryKey: ['my-videos'] });
      }, 5000);
      return () => clearInterval(interval);
    }
  }, [videos, queryClient]);

  const deleteVideoMutation = useMutation({
    mutationFn: async (videoId: string) =>
      apiRequest(`/socio/videos/${videoId}`, { method: 'DELETE' }),
    onSuccess: (_, deletedVideoId) => {
      queryClient.setQueryData<VideoRecord[]>(['my-videos'], (old) =>
        old ? old.filter((video) => video.id !== deletedVideoId) : [],
      );
    },
  });

  const handleDelete = async (videoId: string) => {
    try {
      await deleteVideoMutation.mutateAsync(videoId);
      setSelectedVideoIds((prev) => {
        const next = new Set(prev);
        next.delete(videoId);
        return next;
      });
      toast.success(t('myVideos.deleted'));
    } catch (error) {
      console.error('Error deleting video:', error);
      toast.error(t('myVideos.deleteFailed'));
    }
  };

  const handleBatchDelete = async () => {
    const ids = Array.from(selectedVideoIds);
    if (ids.length === 0) return;

    const results = await Promise.allSettled(ids.map((id) => deleteVideoMutation.mutateAsync(id)));
    const failed = results.filter((result) => result.status === 'rejected').length;
    const success = results.length - failed;

    if (success > 0) toast.success(t('myVideos.deletedMany', { count: success }));
    if (failed > 0) toast.error(t('myVideos.deleteFailedMany', { count: failed }));

    setSelectedVideoIds(new Set());
  };

  const filteredVideos = useMemo(() => {
    const statusFiltered = videos.filter((video) => {
      const status = video.estado?.toUpperCase();
      if (filter === 'all') return true;
      if (filter === 'pending')
        return status === 'PENDIENTE' || status === 'PROCESANDO' || status === 'EN_REVISION';
      if (filter === 'approved') return status === 'APROBADO' || status === 'COMPLETADO';
      if (filter === 'rejected') return status === 'RECHAZADO' || status === 'ERROR';
      return true;
    });

    if (!debouncedSearch) return statusFiltered;

    return statusFiltered.filter((video) => {
      const title = (video.titulo || video.nombre_archivo || '').toLowerCase();
      const project = (video.workspace_nombre || '').toLowerCase();
      const status = (video.estado || '').toLowerCase();
      return (
        title.includes(debouncedSearch) ||
        project.includes(debouncedSearch) ||
        status.includes(debouncedSearch)
      );
    });
  }, [videos, filter, debouncedSearch]);

  useEffect(() => {
    setSelectedVideoIds((prev) => {
      const filteredIdSet = new Set(filteredVideos.map((video) => video.id));
      return new Set(Array.from(prev).filter((id) => filteredIdSet.has(id)));
    });
  }, [filteredVideos]);

  const totalPages = Math.max(1, Math.ceil(filteredVideos.length / rowsPerPage));
  const paginatedVideos = useMemo(() => {
    const start = (currentPage - 1) * rowsPerPage;
    return filteredVideos.slice(start, start + rowsPerPage);
  }, [filteredVideos, currentPage, rowsPerPage]);

  const handleVideoClick = (video: VideoRecord) => {
    const status = (video?.resultado_ia || video?.estado || '').toString().toUpperCase();
    if (['PENDIENTE', 'PROCESANDO', 'EN_PROGRESO', 'EN_REVISION'].includes(status)) {
      toast.info(t('dashboard.videoPendingDetail'));
      return;
    }
    setSelectedVideo(video);
    setIsDetailsOpen(true);
  };

  const allVisibleSelected =
    paginatedVideos.length > 0 && paginatedVideos.every((video) => selectedVideoIds.has(video.id));

  const toggleSelectAllVisible = (checked: boolean) => {
    setSelectedVideoIds((prev) => {
      const next = new Set(prev);
      paginatedVideos.forEach((video) => {
        if (checked) next.add(video.id);
        else next.delete(video.id);
      });
      return next;
    });
  };

  const handleToggleVideoSelect = (videoId: string, selected: boolean) => {
    setSelectedVideoIds((prev) => {
      const next = new Set(prev);
      if (selected) next.add(videoId);
      else next.delete(videoId);
      return next;
    });
  };

  const filters: { key: FilterKey; label: string }[] = [
    { key: 'all', label: t('myVideos.filterAll') },
    { key: 'pending', label: t('myVideos.filterPending') },
    { key: 'approved', label: t('myVideos.filterApproved') },
    { key: 'rejected', label: t('myVideos.filterRejected') },
  ];

  return (
    <PageContainer className="pb-16">
      <PageHeader
        icon={Video}
        title={t('myVideos.title')}
        description={t('myVideos.description')}
        actions={
          <>
            <Button variant="ghost" onClick={() => setIsExplanationOpen(true)}>
              <HelpCircle aria-hidden="true" />
              <span className="hidden sm:inline">{t('myVideos.howAiWorks')}</span>
            </Button>
            <Button asChild>
              <Link to="/upload">
                <Plus aria-hidden="true" />
                {t('myVideos.newVideo')}
              </Link>
            </Button>
          </>
        }
      />

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div
          role="group"
          aria-label={t('common.filter')}
          className="inline-flex max-w-full gap-1 overflow-x-auto rounded-lg border border-border bg-muted p-1"
        >
          {filters.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => {
                setFilter(item.key);
                setCurrentPage(1);
              }}
              aria-pressed={filter === item.key}
              className={cn(
                'whitespace-nowrap rounded-md px-4 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                filter === item.key
                  ? 'bg-card text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="sm:w-72">
          <SearchInput
            placeholder={t('myVideos.searchPlaceholder')}
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            onClear={() => setSearchInput('')}
            aria-label={t('common.search')}
          />
        </div>
      </div>

      {selectedVideoIds.size > 0 && (
        <div className="flex items-center justify-between gap-4 rounded-xl border border-info-border bg-info-surface px-5 py-3">
          <p className="flex items-center gap-2 text-sm font-semibold text-blue-800">
            <span className="h-2 w-2 rounded-full bg-info" aria-hidden="true" />
            {t('myVideos.selectedCount', { count: selectedVideoIds.size })}
          </p>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => setSelectedVideoIds(new Set())}>
              {t('common.deselect')}
            </Button>
            <Button
              variant="danger"
              size="sm"
              onClick={() => setIsBatchDeleteOpen(true)}
              disabled={deleteVideoMutation.isPending}
            >
              {t('myVideos.deleteSelected')}
            </Button>
          </div>
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-border bg-card shadow-card">
        <div className="grid grid-cols-12 items-center gap-4 border-b border-border bg-muted/50 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground sm:px-6">
          <div className="col-span-1 flex items-center">
            <input
              type="checkbox"
              checked={allVisibleSelected}
              onChange={(event) => toggleSelectAllVisible(event.target.checked)}
              aria-label={t('common.selectAllVideos')}
              className="h-4 w-4 cursor-pointer rounded border-gray-300 text-primary focus:ring-2 focus:ring-ring"
            />
          </div>
          <div className="col-span-3 sm:col-span-2">{t('myVideos.preview')}</div>
          <div className="col-span-8 sm:col-span-3">{t('myVideos.fileTitle')}</div>
          <div className="hidden sm:col-span-2 sm:block">{t('myVideos.project')}</div>
          <div className="hidden sm:col-span-2 sm:block">{t('myVideos.date')}</div>
          <div className="hidden sm:col-span-1 sm:block">{t('myVideos.aiStatus')}</div>
          <div className="col-span-12 sm:col-span-1" />
        </div>

        <div className="flex-1">
          {isLoading ? (
            <LoadingState label={t('common.loading')} />
          ) : paginatedVideos.length === 0 ? (
            <EmptyState
              icon={<Video aria-hidden="true" />}
              title={t('myVideos.noVideos')}
              description={t('dashboard.noVideosDescription')}
              action={
                <Button asChild>
                  <Link to="/upload">{t('dashboard.uploadVideo')}</Link>
                </Button>
              }
              className="border-0"
            />
          ) : (
            paginatedVideos.map((video) => (
              <VideoTableRow
                key={video.id}
                video={video}
                onClick={handleVideoClick}
                onDelete={setPendingDeleteId}
                isSelected={selectedVideoIds.has(video.id)}
                onToggleSelect={handleToggleVideoSelect}
                statusBadge={<StatusBadge status={statusFromRaw(video.resultado_ia || video.estado)} />}
              />
            ))
          )}
        </div>

        {filteredVideos.length > 0 && (
          <div className="px-4 py-4 sm:px-6">
            <Pagination
              page={currentPage}
              totalPages={totalPages}
              onPageChange={setCurrentPage}
              totalItems={filteredVideos.length}
              rowsPerPage={rowsPerPage}
              rowsPerPageOptions={[10, 50, 100]}
              onRowsPerPageChange={(rows) => {
                setRowsPerPage(rows);
                setCurrentPage(1);
              }}
            />
          </div>
        )}
      </div>

      <VideoDetailsModal
        videoId={selectedVideo?.id || null}
        open={isDetailsOpen}
        onOpenChange={setIsDetailsOpen}
      />

      <AnalysisExplanationModal
        isOpen={isExplanationOpen}
        onClose={() => setIsExplanationOpen(false)}
      />

      <ConfirmDialog
        open={pendingDeleteId !== null}
        onOpenChange={(open) => !open && setPendingDeleteId(null)}
        onConfirm={() => {
          if (pendingDeleteId) handleDelete(pendingDeleteId);
          setPendingDeleteId(null);
        }}
        title={t('myVideos.deleteConfirmTitle')}
        description={t('myVideos.deleteConfirmDescription')}
        confirmText={t('common.delete')}
        loading={deleteVideoMutation.isPending}
      />

      <ConfirmDialog
        open={isBatchDeleteOpen}
        onOpenChange={setIsBatchDeleteOpen}
        onConfirm={async () => {
          await handleBatchDelete();
          setIsBatchDeleteOpen(false);
        }}
        title={t('myVideos.deleteBatchTitle')}
        description={t('myVideos.deleteBatchDescription', { count: selectedVideoIds.size })}
        confirmText={t('common.delete')}
        loading={deleteVideoMutation.isPending}
      />
    </PageContainer>
  );
}
