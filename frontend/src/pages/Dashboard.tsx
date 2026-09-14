import { useEffect, useState } from 'react';
import { Link } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Clock,
  Eye,
  FolderKanban,
  Play,
  Plus,
  Shield,
  Sparkles,
  Timer,
  TrendingUp,
  Video,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { apiRequest } from '../lib/api';
import { VideoDetailsModal } from '../components/VideoDetailsModal';
import { DonutChart } from '../components/dashboard/DonutChart';
import { StatCard } from '../components/ui/stat-card';
import { StatusBadge } from '../components/ui/status-badge';
import { PageContainer, PageSection } from '../components/ui/page-container';
import { PageHeader } from '../components/ui/page-header';
import { EmptyState } from '../components/ui/empty-state';
import { Button } from '../components/ui/button';
import { Card } from '../components/ui/card';
import { toast } from 'sonner';
import { getApiBaseUrl } from '../lib/backendUrl';
import { useTranslation } from '../i18n';
import { cn } from '../lib/utils';

interface VideoData {
  id: string;
  titulo: string;
  descripcion: string;
  estado: string;
  fecha_subida?: string;
  resultado_ia?: string;
  thumbnail_url?: string;
}

type VideoUiState = 'uploading' | 'processing' | 'approved' | 'rejected';

interface DashboardVideo extends VideoData {
  uiState: VideoUiState;
}

interface Stats {
  total: number;
  aprobados: number;
  pendientes: number;
  rechazados: number;
}

export default function Dashboard() {
  const [selectedVideoId, setSelectedVideoId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isTabVisible, setIsTabVisible] = useState(() => !document.hidden);
  const { user } = useAuth();
  const { t, formatDate } = useTranslation();

  const resolveVideoUiState = (video: VideoData): VideoUiState => {
    const unifiedStatus = `${video.resultado_ia || ''} ${video.estado || ''}`.toUpperCase();

    if (
      ['RECHAZADO', 'ERROR', 'FALLIDO', 'FAILED'].some((status) => unifiedStatus.includes(status))
    ) {
      return 'rejected';
    }

    if (
      ['APROBADO', 'COMPLETADO', 'FINALIZADO', 'DONE'].some((status) =>
        unifiedStatus.includes(status),
      )
    ) {
      return 'approved';
    }

    if (['SUBIENDO', 'UPLOADING', 'UPLOAD'].some((status) => unifiedStatus.includes(status))) {
      return 'uploading';
    }

    return 'processing';
  };

  useEffect(() => {
    const onVisibilityChange = () => setIsTabVisible(!document.hidden);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => document.removeEventListener('visibilitychange', onVisibilityChange);
  }, []);

  const { data: projectCount = 0 } = useQuery({
    queryKey: ['dashboard-projects'],
    queryFn: async () => {
      const response = await apiRequest<{ success: boolean; workspaces: unknown[] }>('/workspaces');
      return response?.success ? response.workspaces.length : 0;
    },
  });

  const {
    data: { videos, stats } = {
      videos: [] as DashboardVideo[],
      stats: { total: 0, aprobados: 0, pendientes: 0, rechazados: 0 },
    },
    isLoading,
  } = useQuery({
    queryKey: ['dashboard-videos'],
    queryFn: async () => {
      const response = await apiRequest<{ success: boolean; videos: VideoData[] }>(
        '/socio/mis-videos',
      );
      const videosData = response?.success ? response.videos : [];
      const dashboardVideos = videosData.map((video) => ({
        ...video,
        uiState: resolveVideoUiState(video),
      }));

      const total = dashboardVideos.length;
      const aprobados = dashboardVideos.filter((v) => v.uiState === 'approved').length;
      const pendientes = dashboardVideos.filter(
        (v) => v.uiState === 'processing' || v.uiState === 'uploading',
      ).length;
      const rechazados = dashboardVideos.filter((v) => v.uiState === 'rejected').length;

      return { videos: dashboardVideos, stats: { total, aprobados, pendientes, rechazados } };
    },
    refetchInterval: (query) => {
      if (!isTabVisible) return false;
      const hasPendingWork = query.state.data?.videos?.some(
        (video) => video.uiState === 'processing' || video.uiState === 'uploading',
      );
      return hasPendingWork ? 15000 : false;
    },
    refetchIntervalInBackground: false,
  });

  const isVideoFinalized = (video: DashboardVideo) =>
    video.uiState === 'approved' || video.uiState === 'rejected';

  const handleVideoClick = (video: DashboardVideo) => {
    if (!isVideoFinalized(video)) {
      toast.info(t('dashboard.videoPendingDetail'));
      return;
    }
    setSelectedVideoId(video.id);
    setIsModalOpen(true);
  };

  const getVideoTitle = (video: DashboardVideo) => {
    const title = video.titulo?.trim();
    if (title && !/^video\s*de\s*$/i.test(title)) return title;
    const description = video.descripcion?.trim();
    if (description) return description;
    if (video.id) return `Video #${video.id.slice(0, 6)}`;
    return t('dashboard.videoFallbackTitle');
  };

  const getVideoDate = (dateString?: string) => {
    if (!dateString) return t('dashboard.videoProcessing');
    const date = new Date(dateString);
    if (Number.isNaN(date.getTime())) return t('dashboard.videoProcessing');
    return formatDate(date, { day: 'numeric', month: 'short' });
  };

  const greeting = (() => {
    const hours = new Date().getHours();
    if (hours < 12) return t('dashboard.greetingMorning');
    if (hours < 18) return t('dashboard.greetingAfternoon');
    return t('dashboard.greetingEvening');
  })();

  const firstName = user?.nombre_completo?.split(' ')[0] || t('dashboard.greetingFallbackName');

  const quickActions = [
    {
      to: '/proyectos',
      icon: FolderKanban,
      label: t('dashboard.projects'),
      desc: t('dashboard.quickProjectsDesc'),
      tone: 'bg-info-surface text-info',
    },
    {
      to: '/security',
      icon: Shield,
      label: t('dashboard.quickSecurity'),
      desc: t('dashboard.quickSecurityDesc'),
      tone: 'bg-success-surface text-success',
    },
    {
      to: '/operational',
      icon: Activity,
      label: t('dashboard.quickOperational'),
      desc: t('dashboard.quickOperationalDesc'),
      tone: 'bg-warning-surface text-warning',
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={`${greeting}, ${firstName}`}
        description={
          stats.total > 0
            ? t('dashboard.summaryCount', { count: stats.total })
            : t('dashboard.summaryEmpty')
        }
        actions={
          <Button asChild>
            <Link to="/upload">
              <Plus aria-hidden="true" />
              {t('dashboard.uploadNewVideo')}
            </Link>
          </Button>
        }
      />

      {isLoading ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <StatCard
              key={index}
              title=""
              value={0}
              icon={Play}
              isLoading
            />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 md:gap-4 lg:grid-cols-4">
          <StatCard
            title={t('dashboard.totalVideos')}
            value={stats.total}
            icon={Video}
            tone="info"
            hideProgress
          />
          <StatCard
            title={t('dashboard.projects')}
            value={projectCount}
            icon={FolderKanban}
            tone="brand"
            hideProgress
          />
          <StatCard
            title={t('dashboard.approved')}
            value={stats.aprobados}
            total={stats.total}
            icon={CheckCircle2}
            tone="success"
          />
          <StatCard
            title={t('dashboard.pending')}
            value={stats.pendientes}
            total={stats.total}
            icon={Timer}
            tone="warning"
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-3 md:gap-4">
        {quickActions.map((action) => (
          <Link
            key={action.to}
            to={action.to}
            className="group flex items-center gap-4 rounded-xl border border-border bg-card p-5 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:border-gray-300 hover:shadow-popover"
          >
            <span
              className={cn(
                'flex h-10 w-10 shrink-0 items-center justify-center rounded-lg [&_svg]:size-5',
                action.tone,
              )}
            >
              <action.icon aria-hidden="true" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-semibold text-foreground">
                {action.label}
              </span>
              <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                {action.desc}
              </span>
            </span>
            <ArrowRight
              size={18}
              aria-hidden="true"
              className="shrink-0 text-gray-300 transition-all group-hover:translate-x-0.5 group-hover:text-primary"
            />
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-3">
        <PageSection className="lg:col-span-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold text-foreground">
                {t('dashboard.recentVideos')}
              </h2>
              <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-semibold text-muted-foreground">
                {videos.length}
              </span>
            </div>
            {videos.length > 0 && (
              <Link
                to="/mis-videos"
                className="flex items-center gap-1 text-xs font-semibold text-muted-foreground transition-colors hover:text-primary"
              >
                {t('common.viewAll')} <ArrowRight size={12} aria-hidden="true" />
              </Link>
            )}
          </div>

          {videos.length === 0 ? (
            <EmptyState
              icon={<Video aria-hidden="true" />}
              title={t('dashboard.noVideosTitle')}
              description={t('dashboard.noVideosDescription')}
              action={
                <Button asChild>
                  <Link to="/upload">{t('dashboard.uploadVideo')}</Link>
                </Button>
              }
            />
          ) : (
            <div className="grid grid-cols-1 content-start gap-3 sm:grid-cols-2">
              {videos.slice(0, 4).map((video) => (
                <button
                  key={video.id}
                  type="button"
                  onClick={() => handleVideoClick(video)}
                  className="group relative overflow-hidden rounded-xl border border-border bg-card text-left shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:shadow-popover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                >
                  <div className="relative aspect-[16/10] overflow-hidden bg-muted">
                    <img
                      crossOrigin="use-credentials"
                      src={`${getApiBaseUrl()}/socio/thumbnail/${video.id}`}
                      alt=""
                      className="absolute inset-0 h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
                      onError={(event) => {
                        event.currentTarget.style.display = 'none';
                      }}
                    />
                    <div className="absolute inset-0 flex items-center justify-center">
                      <Video size={30} className="text-gray-300" aria-hidden="true" />
                    </div>
                    <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/10 to-transparent" />
                    <div className="absolute right-3 top-3">
                      <StatusBadge status={video.uiState} />
                    </div>
                    <div className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100">
                      <span className="flex h-12 w-12 items-center justify-center rounded-full border border-white/30 bg-white/20 backdrop-blur-md">
                        <Play size={20} className="ml-0.5 text-white" fill="currentColor" aria-hidden="true" />
                      </span>
                    </div>
                    <div className="absolute inset-x-0 bottom-0 p-4">
                      <h3 className="line-clamp-1 text-sm font-semibold text-white">
                        {getVideoTitle(video)}
                      </h3>
                      <p className="mt-1 flex items-center gap-1.5 text-xs text-gray-300">
                        <Clock size={12} aria-hidden="true" />
                        {getVideoDate(video.fecha_subida)}
                      </p>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}
        </PageSection>

        <div className="flex flex-col gap-4">
          <Card className="p-5">
            <div className="mb-5 flex items-center gap-2.5">
              <TrendingUp size={18} className="text-info" aria-hidden="true" />
              <h3 className="text-sm font-semibold text-foreground">
                {t('dashboard.videoDistribution')}
              </h3>
            </div>
            <DonutChart stats={stats} />
          </Card>

          <Card className="p-5">
            <div className="mb-4 flex items-center gap-2.5">
              <Eye size={18} className="text-brand" aria-hidden="true" />
              <h3 className="text-sm font-semibold text-foreground">
                {t('dashboard.recentActivity')}
              </h3>
            </div>
            {videos.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                {t('dashboard.noActivity')}
              </p>
            ) : (
              <ul className="space-y-1">
                {videos.slice(0, 5).map((video) => (
                  <li key={video.id}>
                    <button
                      type="button"
                      onClick={() => handleVideoClick(video)}
                      className="flex w-full items-start gap-3 rounded-lg px-2 py-2.5 text-left transition-colors hover:bg-muted"
                    >
                      <span className="mt-1.5 flex flex-col items-center">
                        <Sparkles size={14} className="text-muted-foreground" aria-hidden="true" />
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="mb-1 block truncate text-sm font-medium text-foreground">
                          {getVideoTitle(video)}
                        </span>
                        <span className="flex flex-wrap items-center gap-2">
                          <StatusBadge status={video.uiState} />
                          <span className="text-xs text-muted-foreground">
                            {getVideoDate(video.fecha_subida)}
                          </span>
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      <VideoDetailsModal
        videoId={selectedVideoId}
        open={isModalOpen}
        onOpenChange={setIsModalOpen}
      />
    </PageContainer>
  );
}
