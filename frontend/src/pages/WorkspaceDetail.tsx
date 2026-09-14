import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import {
  FolderOpen,
  Upload,
  Video,
  Clock,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Trash2,
} from 'lucide-react';
import { workspaceService, type Workspace } from '../services/workspace';
import { videoService } from '../services/video';
import { toast } from 'sonner';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { Badge } from '../components/ui/badge';
import { Alert, AlertDescription } from '../components/ui/alert';
import { Spinner } from '../components/ui/spinner';
import { EmptyState } from '../components/ui/empty-state';
import { LoadingState } from '../components/ui/loading-state';
import { ErrorState } from '../components/ui/error-state';
import { Breadcrumbs } from '../components/Breadcrumbs';
import { WorkspaceUploadModal } from '../components/WorkspaceUploadModal';
import { BatchNotification } from '../components/BatchNotification';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { VideoDetailsModal } from '../components/VideoDetailsModal';
import { getApiBaseUrl } from '../lib/backendUrl';
import { useTranslation } from '../i18n';

interface WorkspaceVideo {
  id: string;
  nombre_archivo: string;
  estado: string;
  resultado_ia?: string;
}

export default function WorkspaceDetailPage() {
  const { id } = useParams({ strict: false }) as { id: string };
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [videos, setVideos] = useState<WorkspaceVideo[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [showUploadModal, setShowUploadModal] = useState(false);

  // Estado para confirmación de eliminación de video
  const [videoToDelete, setVideoToDelete] = useState<{ id: string; nombre: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  // Estado para confirmación de eliminación del proyecto
  const [showDeleteProject, setShowDeleteProject] = useState(false);
  const [deletingProject, setDeletingProject] = useState(false);

  // Estado para batch upload
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);
  const [showBatchNotification, setShowBatchNotification] = useState(false);
  const [isTabVisible, setIsTabVisible] = useState(() => !document.hidden);

  // Estado para detalles del video
  const [selectedVideoId, setSelectedVideoId] = useState<string | null>(null);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);

  // Polling para auto-refresh cuando hay videos procesando
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const PROCESSING_STATES = [
    'pendiente', 'procesando', 'en_progreso', 'en_revision',
    'uploading', 'uploaded', 'analyzing', 'classifying',
    'deep_analyzing', 'generating_report', 'motion_detecting', 'motion_detected',
  ];

  const isVideoFinalized = (video: WorkspaceVideo) => {
    const status = (video?.resultado_ia || video?.estado || '').toString().toLowerCase();
    return !PROCESSING_STATES.includes(status);
  };

  const hasProcessingVideos = useCallback(
    (vids: WorkspaceVideo[]) =>
      vids.some((v) => PROCESSING_STATES.includes(v.estado?.toLowerCase())),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  useEffect(() => {
    const onVisibilityChange = () => setIsTabVisible(!document.hidden);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => document.removeEventListener('visibilitychange', onVisibilityChange);
  }, []);

  useEffect(() => {
    if (id) {
      loadWorkspace();
    }
    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  // Auto-polling: cuando hay videos procesando, refrescar cada 5s
  useEffect(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    if (isTabVisible && hasProcessingVideos(videos)) {
      pollingRef.current = setInterval(async () => {
        try {
          const vids = (await workspaceService.getWorkspaceVideos(
            id,
          )) as WorkspaceVideo[];
          setVideos(vids);
          if (!hasProcessingVideos(vids) && pollingRef.current) {
            clearInterval(pollingRef.current);
            pollingRef.current = null;
          }
        } catch {
          // El polling se reintenta en el siguiente tick
        }
      }, 5000);
    }

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [videos, hasProcessingVideos, id, isTabVisible]);

  const loadWorkspace = async () => {
    try {
      setLoading(true);
      setLoadError(false);
      const [ws, vids] = await Promise.all([
        workspaceService.getWorkspace(id),
        workspaceService.getWorkspaceVideos(id),
      ]);
      setWorkspace(ws);
      setVideos(vids as WorkspaceVideo[]);
    } catch {
      setLoadError(true);
    } finally {
      setLoading(false);
    }
  };

  const handleUploadClick = () => {
    setShowUploadModal(true);
  };

  const handleBatchUploadSuccess = (batchId: string, _videoIds: string[]) => {
    setShowUploadModal(false);
    setActiveBatchId(batchId);
    setShowBatchNotification(true);
    toast.info(t('workspaceDetail.uploadedToast'));
    loadWorkspace();
  };

  const handleBatchComplete = () => {
    setShowBatchNotification(false);
    setActiveBatchId(null);
    loadWorkspace();
  };

  const handleDeleteVideo = async () => {
    if (!videoToDelete) return;

    setDeleting(true);
    try {
      const result = await videoService.deleteVideo(videoToDelete.id);
      if (result?.success) {
        loadWorkspace();
      } else {
        toast.error(t('workspaceDetail.deleteVideoFailed'));
      }
    } catch {
      toast.error(t('workspaceDetail.deleteVideoFailed'));
    } finally {
      setDeleting(false);
      setVideoToDelete(null);
    }
  };

  const handleDeleteProject = async () => {
    if (!workspace) return;
    setDeletingProject(true);
    try {
      await workspaceService.deleteWorkspace(workspace.id, 'mover_general');
      navigate({ to: '/proyectos' });
    } catch {
      toast.error(t('workspaceDetail.deleteProjectFailed'));
    } finally {
      setDeletingProject(false);
      setShowDeleteProject(false);
    }
  };

  const handleVideoClick = (video: WorkspaceVideo) => {
    if (!isVideoFinalized(video)) {
      toast.info(t('workspaceDetail.pendingDetailToast'));
      return;
    }

    setSelectedVideoId(video.id);
    setIsDetailsOpen(true);
  };

  const statusBadge = (video: WorkspaceVideo) => {
    const status = (video.resultado_ia || video.estado || '').toUpperCase();
    if (status.includes('APROBADO') || status.includes('COMPLETADO')) {
      return <StatusBadgeWithIcon status="approved" label={t('workspaceDetail.statusApproved')} />;
    }
    if (status.includes('RECHAZADO') || status.includes('ERROR')) {
      return <StatusBadgeWithIcon status="rejected" label={t('workspaceDetail.statusRejected')} />;
    }
    if (status.includes('PROCES') || status.includes('PENDIENTE') || status.includes('PROGRESO')) {
      return (
        <StatusBadgeWithIcon
          status="processing"
          label={t('workspaceDetail.statusProcessing')}
        />
      );
    }
    return (
      <Badge variant="muted">{video.estado || t('workspaceDetail.statusUnknown')}</Badge>
    );
  };

  if (loading) {
    return <LoadingState label={t('workspaceDetail.loading')} />;
  }

  if (loadError && !workspace) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <ErrorState
          title={t('workspaceDetail.notFound')}
          description={t('workspaceDetail.loadFailed')}
          onRetry={loadWorkspace}
        />
        <div className="mt-4">
          <Button variant="outline" onClick={() => navigate({ to: '/proyectos' })}>
            {t('workspaceDetail.backToProjects')}
          </Button>
        </div>
      </div>
    );
  }

  if (!workspace) {
    return (
      <div className="mx-auto max-w-3xl p-6">
        <EmptyState
          icon={<FolderOpen aria-hidden="true" />}
          title={t('workspaceDetail.notFound')}
          action={
            <Button onClick={() => navigate({ to: '/proyectos' })}>
              {t('workspaceDetail.backToProjects')}
            </Button>
          }
        />
      </div>
    );
  }

  const counts = {
    total: videos.length,
    approved: videos.filter((v) => ['aprobado', 'completado'].includes(v.estado?.toLowerCase()))
      .length,
    rejected: videos.filter((v) => ['rechazado', 'error'].includes(v.estado?.toLowerCase())).length,
    review: videos.filter((v) =>
      ['en_revision', 'procesando', 'pendiente', 'en_progreso'].includes(v.estado?.toLowerCase()),
    ).length,
  };

  return (
    <div className="mx-auto w-full max-w-[1400px] space-y-6 pb-16 animate-in fade-in duration-500">
      <Breadcrumbs
        items={[{ label: t('nav.projects'), to: '/proyectos' }, { label: workspace.nombre }]}
      />

      {/* Header Container */}
      <Card variant="elevated" className="relative overflow-hidden p-8">
        <div
          className="pointer-events-none absolute -mr-20 -mt-20 right-0 top-0 h-64 w-64 rounded-full opacity-5 blur-3xl"
          style={{ backgroundColor: workspace.color }}
        />
        <div className="relative z-10 flex flex-col gap-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex items-center gap-5">
              <div
                className="flex h-16 w-16 items-center justify-center overflow-hidden rounded-2xl border"
                style={{
                  backgroundColor: workspace.color + '15',
                  borderColor: workspace.color + '30',
                }}
              >
                {workspace.icono_url ? (
                  <img
                    src={workspace.icono_url}
                    alt={workspace.nombre}
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <FolderOpen size={32} style={{ color: workspace.color }} aria-hidden="true" />
                )}
              </div>
              <div>
                <h1 className="text-3xl font-bold tracking-tight text-foreground">
                  {workspace.nombre}
                </h1>
                {workspace.descripcion && (
                  <p className="mt-1 max-w-2xl text-[15px] text-muted-foreground">
                    {workspace.descripcion}
                  </p>
                )}
              </div>
            </div>
            {!workspace.es_general && (
              <Button
                variant="outline"
                onClick={() => setShowDeleteProject(true)}
                className="text-error hover:bg-error-surface"
              >
                <Trash2 aria-hidden="true" />
                {t('workspaceDetail.deleteProject')}
              </Button>
            )}
          </div>

          {workspace.contexto && (
            <div className="max-w-4xl rounded-xl border border-border bg-muted/50 p-5">
              <h3 className="mb-2 flex items-center gap-2 font-semibold text-foreground">
                <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden="true" />
                {t('workspaceDetail.context')}
              </h3>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {workspace.contexto}
              </p>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard
              icon={<Video size={20} aria-hidden="true" />}
              value={counts.total}
              label={t('workspaceDetail.totalVideos')}
            />
            <StatCard
              icon={<CheckCircle size={20} aria-hidden="true" />}
              value={counts.approved}
              label={t('workspaceDetail.approved')}
              tone="success"
            />
            <StatCard
              icon={<XCircle size={20} aria-hidden="true" />}
              value={counts.rejected}
              label={t('workspaceDetail.rejected')}
              tone="error"
            />
            <StatCard
              icon={<Clock size={20} aria-hidden="true" />}
              value={counts.review}
              label={t('workspaceDetail.inReview')}
              tone="warning"
            />
          </div>
        </div>
      </Card>

      {/* Videos Section */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-foreground">{t('workspaceDetail.videosTitle')}</h2>
        <Button onClick={handleUploadClick}>
          <Upload aria-hidden="true" />
          {t('workspaceDetail.uploadVideo')}
        </Button>
      </div>

      {hasProcessingVideos(videos) && (
        <Alert variant="info" className="items-center">
          <Spinner size="sm" label={t('workspaceDetail.analyzing')} />
          <AlertDescription className="font-semibold text-info">
            {t('workspaceDetail.analyzing')}
          </AlertDescription>
        </Alert>
      )}

      {videos.length === 0 ? (
        <EmptyState
          icon={<Video aria-hidden="true" />}
          title={t('workspaceDetail.emptyTitle')}
          description={t('workspaceDetail.emptyDescription')}
          action={
            <Button onClick={handleUploadClick}>
              <Upload aria-hidden="true" />
              {t('workspaceDetail.startUpload')}
            </Button>
          }
        />
      ) : (
        <Card variant="elevated" className="overflow-hidden">
          <div className="grid grid-cols-12 items-center gap-4 border-b border-border bg-muted/50 px-8 py-4 text-xs font-bold uppercase tracking-wider text-muted-foreground">
            <div className="col-span-2">{t('workspaceDetail.colPreview')}</div>
            <div className="col-span-6">{t('workspaceDetail.colTitle')}</div>
            <div className="col-span-3">{t('workspaceDetail.colStatus')}</div>
            <div className="col-span-1 text-center">{t('workspaceDetail.colActions')}</div>
          </div>

          <div className="divide-y divide-border">
            {videos.map((video) => (
              <div
                key={video.id}
                onClick={() => handleVideoClick(video)}
                className="group grid cursor-pointer grid-cols-12 items-center gap-4 bg-card px-8 py-5 transition-colors hover:bg-muted/60"
              >
                <div className="col-span-2">
                  <div className="relative flex h-16 w-28 items-center justify-center overflow-hidden rounded-xl border border-border bg-muted transition-transform duration-300 group-hover:scale-105">
                    <Video className="absolute text-gray-300" size={24} aria-hidden="true" />
                    <img
                      crossOrigin="use-credentials"
                      src={`${getApiBaseUrl()}/socio/thumbnail/${video.id}`}
                      alt={video.nombre_archivo}
                      className="absolute inset-0 h-full w-full bg-muted object-cover transition-transform duration-500 group-hover:scale-110"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.opacity = '0';
                      }}
                    />
                  </div>
                </div>

                <div className="col-span-6 pr-6">
                  <span className="block truncate text-[15px] font-semibold text-foreground">
                    {video.nombre_archivo}
                  </span>
                </div>

                <div className="col-span-3">{statusBadge(video)}</div>

                <div className="col-span-1 flex justify-center">
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      setVideoToDelete({ id: video.id, nombre: video.nombre_archivo });
                    }}
                    className="text-muted-foreground opacity-0 transition-opacity hover:text-error group-hover:opacity-100 focus:opacity-100"
                    aria-label={t('workspaceDetail.deleteVideo')}
                  >
                    <Trash2 aria-hidden="true" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Modal de upload */}
      {workspace && (
        <WorkspaceUploadModal
          open={showUploadModal}
          onOpenChange={setShowUploadModal}
          workspaceId={workspace.id}
          workspaceName={workspace.nombre}
          onBatchUploadSuccess={handleBatchUploadSuccess}
        />
      )}

      {/* Modal de detalles del video */}
      <VideoDetailsModal
        videoId={selectedVideoId}
        open={isDetailsOpen}
        onOpenChange={setIsDetailsOpen}
      />

      {/* Notificación de batch */}
      {activeBatchId && showBatchNotification && (
        <BatchNotification
          batchId={activeBatchId}
          onClose={() => setShowBatchNotification(false)}
          onComplete={handleBatchComplete}
        />
      )}

      {/* Diálogo de confirmación para eliminar video */}
      <ConfirmDialog
        open={!!videoToDelete}
        onOpenChange={(open) => !open && setVideoToDelete(null)}
        title={t('workspaceDetail.deleteVideoTitle')}
        description={t('workspaceDetail.deleteVideoDescription', {
          name: videoToDelete?.nombre ?? '',
        })}
        confirmText={deleting ? t('common.deleting') : t('common.delete')}
        cancelText={t('common.cancel')}
        onConfirm={handleDeleteVideo}
        variant="danger"
        loading={deleting}
      />

      {/* Diálogo de confirmación para eliminar proyecto */}
      <ConfirmDialog
        open={showDeleteProject}
        onOpenChange={(open) => !open && setShowDeleteProject(false)}
        title={t('workspaceDetail.deleteProjectTitle')}
        description={t('workspaceDetail.deleteProjectDescription', {
          name: workspace?.nombre ?? '',
        })}
        confirmText={
          deletingProject ? t('common.deleting') : t('workspaceDetail.deleteProjectConfirm')
        }
        cancelText={t('common.cancel')}
        onConfirm={handleDeleteProject}
        variant="danger"
        loading={deletingProject}
      />
    </div>
  );
}

function StatCard({
  icon,
  value,
  label,
  tone = 'neutral',
}: {
  icon: React.ReactNode;
  value: number;
  label: string;
  tone?: 'neutral' | 'success' | 'error' | 'warning';
}) {
  const toneClasses = {
    neutral: 'bg-muted text-muted-foreground',
    success: 'bg-success-surface text-success',
    error: 'bg-error-surface text-error',
    warning: 'bg-warning-surface text-warning',
  } as const;

  return (
    <Card variant="elevated" className="flex items-center gap-4 p-5">
      <div className={`rounded-xl p-3 ${toneClasses[tone]}`}>{icon}</div>
      <div>
        <div className="mb-1 text-2xl font-bold leading-none text-foreground">{value}</div>
        <div className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          {label}
        </div>
      </div>
    </Card>
  );
}

function StatusBadgeWithIcon({
  status,
  label,
}: {
  status: 'approved' | 'rejected' | 'processing';
  label: string;
}) {
  const Icon = status === 'approved' ? CheckCircle : status === 'rejected' ? XCircle : AlertTriangle;
  const classes =
    status === 'approved'
      ? 'border-success-border bg-success-surface text-success'
      : status === 'rejected'
        ? 'border-error-border bg-error-surface text-error'
        : 'border-warning-border bg-warning-surface text-warning';

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-bold tracking-wide ${classes}`}
    >
      <Icon size={14} aria-hidden="true" />
      {label}
    </span>
  );
}
