import { useState, useEffect, useRef } from 'react';
import {
  FolderOpen,
  Plus,
  Trash2,
  Copy,
  Video,
  MoreVertical,
  Layers,
  ArrowRight,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import { useNavigate } from '@tanstack/react-router';
import { workspaceService, type Workspace } from '../services/workspace';
import { getErrorMessage } from '../lib/errors';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { PageContainer, PageSection } from '../components/ui/page-container';
import { PageHeader } from '../components/ui/page-header';
import { SearchInput } from '../components/ui/search-input';
import { EmptyState } from '../components/ui/empty-state';
import { LoadingState } from '../components/ui/loading-state';
import { StatCard } from '../components/ui/stat-card';
import { Badge } from '../components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select';
import { ConfirmDialog } from '../components/ConfirmDialog';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../components/ui/dialog';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { CreateWorkspaceModal } from '../components/CreateWorkspaceModal';
import { WorkspaceChatButton } from '../components/WorkspaceChatButton';
import { useTranslation, type TranslationKey } from '../i18n';

type SortKey = 'alfabetico' | 'fecha_creacion' | 'actividad' | 'num_videos';

const SORT_OPTIONS: { value: SortKey; labelKey: TranslationKey }[] = [
  { value: 'alfabetico', labelKey: 'workspaces.sortAlphabetical' },
  { value: 'fecha_creacion', labelKey: 'workspaces.sortCreated' },
  { value: 'actividad', labelKey: 'workspaces.sortActivity' },
  { value: 'num_videos', labelKey: 'workspaces.sortVideos' },
];

export default function WorkspacesPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [filteredWorkspaces, setFilteredWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<SortKey>('alfabetico');
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Workspace | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [duplicateTarget, setDuplicateTarget] = useState<Workspace | null>(null);
  const [duplicateName, setDuplicateName] = useState('');
  const [duplicating, setDuplicating] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadWorkspaces();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sortBy]);

  // Close kebab menu on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpenMenuId(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    // Filter workspaces based on search query
    if (searchQuery.trim() === '') {
      setFilteredWorkspaces(workspaces);
    } else {
      const query = searchQuery.toLowerCase();
      const filtered = workspaces.filter(
        (ws) =>
          ws.nombre.toLowerCase().includes(query) ||
          ws.descripcion.toLowerCase().includes(query) ||
          ws.contexto.toLowerCase().includes(query),
      );
      setFilteredWorkspaces(filtered);
    }
  }, [searchQuery, workspaces]);

  const loadWorkspaces = async () => {
    try {
      setLoading(true);
      const ws = await workspaceService.listWorkspaces(sortBy);
      setWorkspaces(ws);
      setFilteredWorkspaces(ws);
    } catch (error) {
      console.error('Error loading workspaces:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await workspaceService.deleteWorkspace(deleteTarget.id, 'mover_general');
      setDeleteTarget(null);
      loadWorkspaces();
    } catch (error) {
      console.error('Error deleting workspace:', error);
    } finally {
      setDeleting(false);
    }
  };

  const handleOpenDuplicate = (workspace: Workspace) => {
    setDuplicateTarget(workspace);
    setDuplicateName(`${workspace.nombre} (Copia)`);
  };

  const handleDuplicate = async () => {
    if (!duplicateTarget || !duplicateName.trim()) return;
    setDuplicating(true);
    try {
      await workspaceService.duplicateWorkspace(duplicateTarget.id, duplicateName.trim());
      setDuplicateTarget(null);
      loadWorkspaces();
    } catch (error) {
      console.error('Error duplicating workspace:', getErrorMessage(error));
    } finally {
      setDuplicating(false);
    }
  };

  const totalVideos = filteredWorkspaces.reduce(
    (sum, ws) => sum + (ws.estadisticas?.total_videos || 0),
    0,
  );
  const totalApproved = filteredWorkspaces.reduce(
    (sum, ws) => sum + (ws.estadisticas?.aprobados || 0),
    0,
  );
  const totalRejected = filteredWorkspaces.reduce(
    (sum, ws) => sum + (ws.estadisticas?.rechazados || 0),
    0,
  );

  if (loading) {
    return (
      <PageContainer>
        <LoadingState label={t('common.loadingProjects')} />
      </PageContainer>
    );
  }

  return (
    <PageContainer className="pb-16">
      <PageHeader
        icon={Layers}
        title={t('workspaces.title')}
        description={t('workspaces.description')}
        actions={
          <Button onClick={() => setShowCreateModal(true)}>
            <Plus aria-hidden="true" />
            {t('workspaces.new')}
          </Button>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard title={t('workspaces.statProjects')} value={filteredWorkspaces.length} icon={FolderOpen} tone="brand" hideProgress />
        <StatCard title={t('workspaces.statVideos')} value={totalVideos} icon={Video} tone="info" hideProgress />
        <StatCard title={t('workspaces.statApproved')} value={totalApproved} icon={CheckCircle2} tone="success" hideProgress />
        <StatCard title={t('workspaces.statRejected')} value={totalRejected} icon={XCircle} tone="warning" hideProgress />
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="sm:w-80">
          <SearchInput
            placeholder={t('workspaces.searchPlaceholder')}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onClear={() => setSearchQuery('')}
            aria-label={t('common.search')}
          />
        </div>
        <div className="sm:w-56">
          <Select value={sortBy} onValueChange={(value) => setSortBy(value as SortKey)}>
            <SelectTrigger aria-label={t('workspaces.sortLabel')}>
              <SelectValue placeholder={t('workspaces.sortLabel')} />
            </SelectTrigger>
            <SelectContent>
              {SORT_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  {t(option.labelKey)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {filteredWorkspaces.length === 0 ? (
        <EmptyState
          icon={<FolderOpen aria-hidden="true" />}
          title={searchQuery ? t('workspaces.emptySearchTitle') : t('workspaces.emptyTitle')}
          description={
            searchQuery
              ? t('workspaces.emptySearchDescription', { query: searchQuery })
              : t('workspaces.emptyDescription')
          }
          action={
            searchQuery ? (
              <Button variant="outline" onClick={() => setSearchQuery('')}>
                {t('common.clearSelection')}
              </Button>
            ) : (
              <Button onClick={() => setShowCreateModal(true)}>
                <Plus aria-hidden="true" />
                {t('workspaces.start')}
              </Button>
            )
          }
        />
      ) : (
        <PageSection>
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filteredWorkspaces.map((workspace) => (
              <Card
                key={workspace.id}
                variant="interactive"
                className="group flex cursor-pointer flex-col overflow-hidden"
                onClick={() => navigate({ to: `/proyecto/${workspace.id}` })}
              >
                <CardContent className="flex flex-1 flex-col p-5 pt-5">
                  <div className="mb-4 flex items-start justify-between">
                    <div className="flex min-w-0 items-center gap-3">
                      <div
                        className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-lg border"
                        style={{
                          backgroundColor: `${workspace.color}15`,
                          borderColor: `${workspace.color}30`,
                        }}
                      >
                        {workspace.icono_url ? (
                          <img
                            src={workspace.icono_url}
                            alt={workspace.nombre}
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <FolderOpen size={20} style={{ color: workspace.color }} aria-hidden="true" />
                        )}
                      </div>
                      <div className="min-w-0">
                        <h3 className="truncate text-[15px] font-semibold leading-tight text-foreground">
                          {workspace.nombre}
                        </h3>
                        {workspace.es_general && (
                          <Badge variant="muted" className="mt-1">
                            {t('workspaces.default')}
                          </Badge>
                        )}
                      </div>
                    </div>

                    {!workspace.es_general && (
                      <div className="relative" ref={openMenuId === workspace.id ? menuRef : null}>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={t('workspaces.moreOptions')}
                          aria-expanded={openMenuId === workspace.id}
                          onClick={(e) => {
                            e.stopPropagation();
                            setOpenMenuId(openMenuId === workspace.id ? null : workspace.id);
                          }}
                        >
                          <MoreVertical aria-hidden="true" />
                        </Button>

                        {openMenuId === workspace.id && (
                          <div className="absolute right-0 top-10 z-20 w-44 rounded-lg border border-border bg-popover py-1 shadow-popover">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setOpenMenuId(null);
                                handleOpenDuplicate(workspace);
                              }}
                              className="flex w-full items-center gap-2 px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted"
                            >
                              <Copy size={15} aria-hidden="true" /> {t('workspaces.duplicate')}
                            </button>
                            <div className="my-1 border-t border-border" />
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setOpenMenuId(null);
                                setDeleteTarget(workspace);
                              }}
                              className="flex w-full items-center gap-2 px-3 py-2 text-sm font-medium text-error transition-colors hover:bg-error-surface"
                            >
                              <Trash2 size={15} aria-hidden="true" /> {t('common.delete')}
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {workspace.descripcion ? (
                    <p className="mb-5 line-clamp-2 flex-1 text-sm leading-relaxed text-muted-foreground">
                      {workspace.descripcion}
                    </p>
                  ) : (
                    <div className="mb-2 min-h-[40px] flex-1" />
                  )}

                  <div className="mb-4 flex flex-wrap items-center gap-2">
                    <Badge variant="muted">
                      <Video aria-hidden="true" />
                      {workspace.estadisticas?.total_videos || 0}
                    </Badge>
                    {(workspace.estadisticas?.aprobados || 0) > 0 && (
                      <Badge variant="success">
                        <CheckCircle2 aria-hidden="true" />
                        {workspace.estadisticas.aprobados}
                      </Badge>
                    )}
                    {(workspace.estadisticas?.rechazados || 0) > 0 && (
                      <Badge variant="destructive">
                        <XCircle aria-hidden="true" />
                        {workspace.estadisticas.rechazados}
                      </Badge>
                    )}
                  </div>

                  <div className="mt-auto border-t border-border pt-4">
                    {!workspace.es_general ? (
                      <WorkspaceChatButton
                        workspaceId={workspace.id}
                        variant="secondary"
                        className="w-full"
                        onContextImproved={() => loadWorkspaces()}
                        isContextualized={workspace.metadatos?.ia_contextualizada}
                      />
                    ) : (
                      <div className="flex items-center justify-center gap-2 text-sm font-semibold text-muted-foreground transition-colors group-hover:text-primary">
                        {t('workspaces.explore')}
                        <ArrowRight
                          size={16}
                          className="transition-transform duration-300 group-hover:translate-x-1"
                          aria-hidden="true"
                        />
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </PageSection>
      )}

      <CreateWorkspaceModal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        onCreated={() => {
          loadWorkspaces();
        }}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        onConfirm={handleDelete}
        title={t('workspaces.deleteTitle')}
        description={t('workspaces.deleteDescription', { name: deleteTarget?.nombre ?? '' })}
        confirmText={t('common.delete')}
        loading={deleting}
      />

      <Dialog open={duplicateTarget !== null} onOpenChange={(open) => !open && setDuplicateTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{t('workspaces.duplicateTitle')}</DialogTitle>
            <DialogDescription>
              {t('workspaces.duplicateDescription', { name: duplicateTarget?.nombre ?? '' })}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="duplicate-name">{t('workspaces.duplicateLabel')}</Label>
            <Input
              id="duplicate-name"
              value={duplicateName}
              onChange={(e) => setDuplicateName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleDuplicate();
              }}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDuplicateTarget(null)} disabled={duplicating}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleDuplicate} loading={duplicating} disabled={!duplicateName.trim()}>
              {t('workspaces.duplicateConfirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageContainer>
  );
}
