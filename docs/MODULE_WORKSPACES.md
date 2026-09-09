# Module: Workspaces

## Overview

Workspaces are the top-level organizational unit in TIVIT CU002. A workspace groups related videos together and stores a shared AI context that influences how uploaded videos are analyzed and moderated.

Each workspace has its own configuration (name, description, category, content type, tolerance level), an AI context used to guide the local AI moderation decisions, a video collection (up to 100 videos), and cached statistics.

---

## Data Model

```
Workspace
  id                  string       Primary key (SQLAlchemy)
  nombre              string       Display name (3-50 chars)
  descripcion         string       Optional longer description (max 200 chars)
  usuario             string       Owner username
  categoria           string       Content category
  nivel_tolerancia    string       "bajo" | "medio" | "alto"
  tipo_contenido      string       Description of expected content (max 1000 chars)
  orden               int          Display order (default 0)
  fecha_creacion      string       ISO 8601 timestamp
  stats               object       Cached counts by video status

  # Soft delete fields
  eliminado           bool         True if in the trash (default false)
  fecha_eliminacion   string       ISO 8601 timestamp of deletion (empty if active)
  eliminado_por       string       Username who deleted it (empty if active)
```

Persisted in PostgreSQL/SQLAlchemy table: `workspaces`

---

## Constraints

| Constraint | Value |
|------------|-------|
| Max workspaces per user | 20 |
| Max videos per workspace | 100 |
| Min workspace name length | 3 characters |
| Max workspace name length | 50 characters |
| Max description length | 200 characters |
| Max context (`tipo_contenido`) length | 1 000 characters |
| Prohibited characters in name | `/ \ < > : " \| ? * \n \r \t` |

The `General` workspace is created automatically for every user on first access and cannot be deleted, renamed, or modified.

---

## Input Sanitization

All user-supplied text fields are processed by `infrastructure/validators/text_sanitizer.py` before persistence. The sanitizer:

- Strips control characters and null bytes.
- Detects and rejects injection patterns (inline scripts, `<iframe>`, event handler attributes).
- Escapes HTML special characters.
- Enforces per-field length limits after sanitization.
- Logs injection attempts at WARNING level with the originating username.

---

## Atomic Operations

All write operations that must be consistent under concurrent access use SQLAlchemy database transactions or batch writes via `infrastructure/services/workspace_transactions.py`.

| Function | Guarantee |
|----------|-----------|
| `crear_workspace_atomico()` | Reads current workspace count and writes the new row in a single transaction; prevents exceeding the 20-workspace limit under parallel requests; enforces case-insensitive name uniqueness; **soft-deleted workspaces are excluded from both the limit count and uniqueness check** |
| `actualizar_workspace_atomico()` | Reads the workspace inside the transaction before writing; validates ownership and name uniqueness atomically against active workspaces only |
| `eliminar_workspace_con_batch()` | Moves all videos to the General workspace and marks the workspace as deleted in a single batch write; guarantees no orphaned video references |
| `duplicar_workspace_atomico()` | Verifies limit and name uniqueness inside one transaction before creating the duplicate; **soft-deleted workspaces are excluded from both checks** |

This eliminates the race conditions that previously allowed duplicate workspace names and over-limit creation under parallel requests.

---

## Soft Delete

Deleting a workspace is non-destructive by default. The workspace is flagged as deleted (`eliminado: true`) and moved to a trash state. Videos inside the workspace are not affected.

Hard delete is available as an explicit opt-in (`?hard_delete=true`) and permanently removes the workspace row. Before hard deletion, all videos are reassigned to the General workspace to maintain referential integrity.

### State transitions

```
active --[DELETE]--> deleted (trash)
deleted --[restore]--> active
deleted --[hard delete]--> permanently removed
```

### Rules

- The `General` workspace cannot be soft-deleted or hard-deleted.
- Only the workspace owner can delete or restore.
- Restored workspaces reappear in the normal workspace list immediately.

---

## Audit Log

Every CRUD operation on workspaces is recorded in the `workspace_audit_logs` SQLAlchemy table by `infrastructure/services/workspace_audit.py`. Each log entry contains:

```
timestamp       string    ISO 8601
usuario         string    Username who performed the action
accion          string    CREATED | UPDATED | DELETED | RESTORED | DUPLICATED
workspace_id    string
workspace_nombre string
cambios         object    Field-level diff { field: { old, new } } (updates only)
ip_address      string
user_agent      string
success         bool
```

Audit logs are append-only and are never deleted by application code.

---

## AI Cost Control

Local AI gateway calls (vLLM/OpenAI-compatible) for workspace context validation are governed by `infrastructure/services/ai_cost_control.py`.

| Limit | Value |
|-------|-------|
| Max input length | 5 000 characters |
| Max requests per user per day | 50 |
| Max tokens per user per day | 100 000 |
| Response cache TTL | 24 hours |

Identical validation requests within the cache TTL return the cached AI response without consuming quota. Usage is tracked per user in the `ai_usage_logs` and `ai_daily_limits` SQLAlchemy tables.

---

## Statistics

Workspace stats are cached and recalculated via `recalculate_workspace_stats()` on every video status change. Stats include total video count and a breakdown by status: `pendiente`, `procesando`, `completado`, `error`, `en_revision`, `aprobado`, `rechazado`.

---

## AI Context Validation

The `POST /workspaces/:id/chat/validate` endpoint allows users to verify whether their workspace configuration is sufficiently specific for the AI moderation pipeline. The local AI evaluates the current workspace settings and returns either a validation summary or a set of clarifying questions.

---

## Video Assignment

Every video belongs to exactly one workspace (`workspace_id` field on the `Video` entity). The default workspace is `general`. When a workspace is hard-deleted, all its videos are reassigned to the General workspace before deletion.

---

## API Endpoints

See [API.md](API.md) for full request/response documentation.

| Method | Path | Description |
|--------|------|-------------|
| POST | `/workspaces` | Create a workspace (atomic, enforces limits) |
| GET | `/workspaces` | List active workspaces for the authenticated user |
| GET | `/workspaces/trash` | List deleted workspaces (trash) |
| GET | `/workspaces/:id` | Get workspace details and stats |
| PUT | `/workspaces/:id` | Update workspace metadata (atomic) |
| DELETE | `/workspaces/:id` | Soft delete workspace |
| DELETE | `/workspaces/:id?hard_delete=true` | Permanently delete workspace and reassign videos |
| POST | `/workspaces/:id/restore` | Restore a soft-deleted workspace |
| POST | `/workspaces/:id/duplicate` | Duplicate a workspace configuration |
| POST | `/workspaces/:id/chat/validate` | AI validation of workspace context |

---

**Last Updated**: May 15, 2026  
**Version**: 3.3.0
