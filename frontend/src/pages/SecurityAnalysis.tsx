import { useState, useEffect } from 'react';
import {
  securityVideoService,
  SecurityVideo,
  ContextualAnalysis,
  EstadoSecurityVideo,
} from '../services/securityVideoService';
import { getErrorMessage } from '../lib/errors';
import { toast } from 'sonner';
import {
  Search,
  Video,
  FileText,
  Download,
  RefreshCw,
  Clock,
  AlertCircle,
  Sparkles,
  Zap,
  Activity,
  Target,
  TrendingUp,
} from 'lucide-react';
import { PageContainer } from '../components/ui/page-container';
import { PageHeader } from '../components/ui/page-header';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Label } from '../components/ui/label';
import { Textarea } from '../components/ui/textarea';
import { Alert, AlertDescription } from '../components/ui/alert';
import { EmptyState } from '../components/ui/empty-state';
import { LoadingState } from '../components/ui/loading-state';
import { StatusBadge, type AppStatus } from '../components/ui/status-badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import { useTranslation } from '../i18n';

const statusFromAnalysis = (estado: ContextualAnalysis['estado']): AppStatus => {
  if (estado === 'completed') return 'completed';
  if (estado === 'error') return 'failed';
  if (estado === 'processing') return 'processing';
  return 'pending';
};

export default function SecurityAnalysis() {
  const { t } = useTranslation();

  // Estados
  const [videos, setVideos] = useState<SecurityVideo[]>([]);
  const [analyses, setAnalyses] = useState<ContextualAnalysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // Formulario
  const [selectedVideoId, setSelectedVideoId] = useState('');
  const [contexto, setContexto] = useState('');
  const [modo, setModo] = useState<'ESTANDAR' | 'PROFUNDO'>('ESTANDAR');

  // Cargar datos iniciales
  useEffect(() => {
    cargarDatos();
  }, []);

  const cargarDatos = async () => {
    try {
      setLoading(true);

      // Cargar videos completados
      const videosRes = await securityVideoService.listarVideos({
        estado: EstadoSecurityVideo.COMPLETED,
      });
      setVideos(videosRes.videos);

      // Cargar análisis existentes
      try {
        const analysisRes = await securityVideoService.listarAnalisis();
        setAnalyses(analysisRes.analyses || []);
      } catch {
        // Si falla, puede que no haya análisis aún
        setAnalyses([]);
      }
    } catch (error) {
      toast.error(t('securityAnalysis.loadFailed'));
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const refrescarAnalisis = async () => {
    try {
      setRefreshing(true);
      const res = await securityVideoService.listarAnalisis();
      setAnalyses(res.analyses || []);
      toast.success(t('securityAnalysis.refreshed'));
    } catch {
      toast.error(t('securityAnalysis.refreshFailed'));
    } finally {
      setRefreshing(false);
    }
  };

  const iniciarAnalisis = async () => {
    if (!selectedVideoId) {
      toast.error(t('securityAnalysis.selectVideoError'));
      return;
    }
    if (!contexto.trim()) {
      toast.error(t('securityAnalysis.contextError'));
      return;
    }

    try {
      setSubmitting(true);
      const res = await securityVideoService.iniciarAnalisisContextual(
        selectedVideoId,
        contexto,
        modo,
      );

      if (res.success) {
        toast.success(t('securityAnalysis.started'));
        setContexto('');
        setSelectedVideoId('');

        // Refrescar lista
        await refrescarAnalisis();
      }
    } catch (error) {
      toast.error(getErrorMessage(error));
    } finally {
      setSubmitting(false);
    }
  };

  const descargarReporte = async (analysisId: string, formato: 'pdf' | 'json' | 'txt') => {
    try {
      const blob = await securityVideoService.descargarReporte(analysisId, formato);

      // Crear URL y descargar
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `reporte_${analysisId}.${formato}`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      toast.success(t('securityAnalysis.downloadSuccess', { format: formato.toUpperCase() }));
    } catch {
      toast.error(t('securityAnalysis.downloadFailed'));
    }
  };

  const formatFecha = (isoDate: string) => {
    const date = new Date(isoDate);
    return date.toLocaleDateString('es-PE', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getVideoNombre = (videoId: string) => {
    const video = videos.find((v) => v.id === videoId);
    return video ? `${video.nombre_camara} - ${video.ubicacion}` : videoId;
  };

  if (loading) {
    return (
      <PageContainer>
        <LoadingState label={t('common.loading')} />
      </PageContainer>
    );
  }

  return (
    <PageContainer className="max-w-5xl pb-16">
      <PageHeader
        icon={Search}
        title={t('securityAnalysis.title')}
        description={t('securityAnalysis.description')}
      />

      <Card variant="elevated">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles size={18} className="text-warning" aria-hidden="true" />
            {t('securityAnalysis.newAnalysis')}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="space-y-2">
            <Label htmlFor="security-video">{t('securityAnalysis.videoLabel')}</Label>
            <Select value={selectedVideoId} onValueChange={setSelectedVideoId}>
              <SelectTrigger id="security-video">
                <SelectValue placeholder={t('securityAnalysis.videoPlaceholder')} />
              </SelectTrigger>
              <SelectContent>
                {videos.map((video) => (
                  <SelectItem key={video.id} value={video.id}>
                    {video.nombre_camara} - {video.ubicacion} (
                    {securityVideoService.formatDuration(video.duracion_segundos)})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {videos.length === 0 && (
              <p className="text-sm text-warning">{t('securityAnalysis.noVideos')}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="security-context">{t('securityAnalysis.questionLabel')}</Label>
            <Textarea
              id="security-context"
              value={contexto}
              onChange={(e) => setContexto(e.target.value)}
              placeholder={t('securityAnalysis.questionPlaceholder')}
              rows={3}
            />
          </div>

          <div className="space-y-2">
            <span className="text-sm font-medium text-foreground">
              {t('securityAnalysis.modeLabel')}
            </span>
            <div className="grid gap-3 sm:grid-cols-2">
              <button
                type="button"
                aria-pressed={modo === 'ESTANDAR'}
                onClick={() => setModo('ESTANDAR')}
                className={`flex items-center gap-3 rounded-lg border-2 p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                  modo === 'ESTANDAR'
                    ? 'border-primary bg-brand-soft'
                    : 'border-border hover:border-gray-300'
                }`}
              >
                <Zap
                  size={20}
                  className={modo === 'ESTANDAR' ? 'text-primary' : 'text-muted-foreground'}
                  aria-hidden="true"
                />
                <div>
                  <div className="font-medium text-foreground">
                    {t('securityAnalysis.modeStandard')}
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {t('securityAnalysis.modeStandardDesc')}
                  </div>
                </div>
              </button>

              <button
                type="button"
                aria-pressed={modo === 'PROFUNDO'}
                onClick={() => setModo('PROFUNDO')}
                className={`flex items-center gap-3 rounded-lg border-2 p-4 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                  modo === 'PROFUNDO'
                    ? 'border-primary bg-brand-soft'
                    : 'border-border hover:border-gray-300'
                }`}
              >
                <Sparkles
                  size={20}
                  className={modo === 'PROFUNDO' ? 'text-primary' : 'text-muted-foreground'}
                  aria-hidden="true"
                />
                <div>
                  <div className="font-medium text-foreground">
                    {t('securityAnalysis.modeDeep')}
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {t('securityAnalysis.modeDeepDesc')}
                  </div>
                </div>
              </button>
            </div>
          </div>

          <Button
            fullWidth
            onClick={iniciarAnalisis}
            loading={submitting}
            disabled={submitting || !selectedVideoId || !contexto.trim()}
          >
            <Search aria-hidden="true" />
            {submitting ? t('securityAnalysis.submitting') : t('securityAnalysis.submit')}
          </Button>
        </CardContent>
      </Card>

      <Card variant="elevated">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <FileText size={18} className="text-success" aria-hidden="true" />
              {t('securityAnalysis.myAnalyses')}
            </CardTitle>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={refrescarAnalisis}
              disabled={refreshing}
              aria-label={t('common.refresh')}
            >
              <RefreshCw className={refreshing ? 'animate-spin' : ''} aria-hidden="true" />
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {analyses.length === 0 ? (
            <EmptyState
              icon={<Search aria-hidden="true" />}
              title={t('securityAnalysis.emptyTitle')}
              description={t('securityAnalysis.emptyDescription')}
              className="border-0"
            />
          ) : (
            <ul className="space-y-4">
              {analyses.map((analysis) => (
                <li
                  key={analysis.id}
                  className="rounded-lg border border-border p-4 transition-colors hover:border-gray-300"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="mb-1.5 flex flex-wrap items-center gap-2">
                        <span className="text-base font-medium text-foreground">
                          &ldquo;{analysis.contexto}&rdquo;
                        </span>
                        <StatusBadge status={statusFromAnalysis(analysis.estado)} />
                      </div>

                      <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
                        <span className="flex items-center gap-1.5">
                          <Video size={15} aria-hidden="true" />
                          {getVideoNombre(analysis.video_id)}
                        </span>
                        <span className="flex items-center gap-1.5">
                          <Clock size={15} aria-hidden="true" />
                          {formatFecha(analysis.fecha_creacion)}
                        </span>
                        <span className="rounded border border-brand-border bg-brand-soft px-2 py-0.5 text-xs font-semibold text-brand-hover">
                          {analysis.modo}
                        </span>
                      </div>

                      {analysis.estado === 'completed' && analysis.resultado && (
                        <div className="mt-3 rounded-lg border border-border bg-muted/50 p-3">
                          <p className="text-sm text-foreground">
                            {analysis.resultado.respuesta_consulta}
                          </p>
                          {analysis.resultado.estadisticas && (
                            <div className="mt-2 flex flex-wrap gap-4 text-xs text-muted-foreground">
                              <span className="flex items-center gap-1.5">
                                <Activity size={13} aria-hidden="true" />
                                {analysis.resultado.estadisticas.total_movimientos}{' '}
                                {t('securityAnalysis.movements')}
                              </span>
                              <span className="flex items-center gap-1.5">
                                <Target size={13} aria-hidden="true" />
                                {analysis.resultado.estadisticas.relevantes_contexto}{' '}
                                {t('securityAnalysis.relevant')}
                              </span>
                              <span className="flex items-center gap-1.5">
                                <TrendingUp size={13} aria-hidden="true" />
                                {analysis.resultado.estadisticas.porcentaje_relevancia}%{' '}
                                {t('securityAnalysis.relevance')}
                              </span>
                            </div>
                          )}
                        </div>
                      )}

                      {analysis.estado === 'error' && analysis.error && (
                        <Alert variant="error" className="mt-3">
                          <AlertCircle aria-hidden="true" />
                          <AlertDescription>{analysis.error}</AlertDescription>
                        </Alert>
                      )}

                      {analysis.estado === 'processing' && (
                        <Alert variant="info" className="mt-3">
                          <AlertDescription>{t('securityAnalysis.processing')}</AlertDescription>
                        </Alert>
                      )}
                    </div>

                    {analysis.estado === 'completed' && (
                      <div className="flex shrink-0 items-center gap-2">
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          className="text-error hover:bg-error-surface"
                          onClick={() => descargarReporte(analysis.id, 'pdf')}
                          aria-label={t('securityAnalysis.downloadPdf')}
                        >
                          <Download aria-hidden="true" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => descargarReporte(analysis.id, 'json')}
                          aria-label={t('securityAnalysis.downloadJson')}
                        >
                          <FileText aria-hidden="true" />
                        </Button>
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </PageContainer>
  );
}
