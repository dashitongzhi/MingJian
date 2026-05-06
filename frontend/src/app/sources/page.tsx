"use client";

import { useCallback, useMemo, useState } from "react";
import useSWR from "swr";
import { toast } from "sonner";
import {
  fetchSourceReputations,
  fetchCustomSources,
  createCustomSource,
  updateCustomSource,
  deleteCustomSource,
  type SourceReputation,
  type CustomSource,
} from "@/lib/api";
import { useTranslation } from "@/contexts/LanguageContext";
import { DataTable } from "@/components/ui/data-table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import type { ColumnDef } from "@tanstack/react-table";
import {
  Plus,
  Pencil,
  Trash2,
  X,
  Database,
  Check,
  AlertCircle,
  ExternalLink,
} from "lucide-react";

// ── Helpers ────────────────────────────────────────────────────────────

function scoreColor(score: number): string {
  if (score >= 0.7) return "text-[var(--accent-green)]";
  if (score >= 0.4) return "text-[var(--accent-amber)]";
  return "text-[var(--accent-red)]";
}

function scoreDotColor(score: number): string {
  if (score >= 0.7) return "bg-[var(--accent-green)]";
  if (score >= 0.4) return "bg-[var(--accent-amber)]";
  return "bg-[var(--accent-red)]";
}

function SkeletonRows({ count = 6 }: { count?: number }) {
  return (
    <div className="divide-y divide-[var(--card-border)]/50">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="py-4">
          <div className="skeleton h-3 w-2/3" />
          <div className="skeleton mt-3 h-3 w-full" />
        </div>
      ))}
    </div>
  );
}

function EmptyState({
  title,
  description,
  icon,
}: {
  title: string;
  description?: string;
  icon?: React.ReactNode;
}) {
  return (
    <div className="min-h-[200px] py-12 text-center">
      {icon && (
        <div className="mx-auto mb-4 text-[var(--muted)] opacity-50">
          {icon}
        </div>
      )}
      {!icon && (
        <div className="mx-auto mb-4 h-px w-16 bg-[var(--accent)]/40" />
      )}
      <div className="heading-section">{title}</div>
      {description && (
        <div className="mx-auto mt-2 max-w-sm text-[13px] text-[var(--muted)] leading-relaxed">
          {description}
        </div>
      )}
    </div>
  );
}

const SOURCE_TYPES = [
  "rss",
  "api",
  "scraper",
  "webhook",
  "database",
  "file",
  "other",
];

// ── Reputation Columns ─────────────────────────────────────────────────

function reputationColumns(
  t: (key: string) => string
): ColumnDef<SourceReputation, unknown>[] {
  return [
    {
      accessorKey: "display_name",
      header: t("sources.sourceName"),
      cell: ({ row }) => (
        <span className="font-medium">
          {row.original.display_name || row.original.source_key}
        </span>
      ),
    },
    {
      accessorKey: "source_type",
      header: t("sources.sourceType"),
      cell: ({ row }) => (
        <span className="rounded bg-[var(--bg-secondary)] px-2 py-0.5 text-[11px] font-medium text-[var(--muted-foreground)]">
          {row.original.source_type || "-"}
        </span>
      ),
    },
    {
      accessorKey: "confirmed_count",
      header: t("evidence.confirmed"),
      cell: ({ row }) => (
        <span className="font-mono text-[var(--accent-green)] tabular-nums">
          {row.original.confirmed_count}
        </span>
      ),
    },
    {
      accessorKey: "refuted_count",
      header: t("evidence.refuted"),
      cell: ({ row }) => (
        <span className="font-mono text-[var(--accent-red)] tabular-nums">
          {row.original.refuted_count}
        </span>
      ),
    },
    {
      accessorKey: "reputation_score",
      header: t("sources.reputationScore"),
      cell: ({ row }) => (
        <span className="inline-flex items-center gap-1.5">
          <span
            className={`h-1.5 w-1.5 rounded-full ${scoreDotColor(row.original.reputation_score)}`}
          />
          <span
            className={`font-mono text-xs tabular-nums ${scoreColor(row.original.reputation_score)}`}
          >
            {(row.original.reputation_score * 100).toFixed(0)}%
          </span>
        </span>
      ),
    },
    {
      accessorKey: "noise_rate",
      header: t("sources.noiseRate"),
      cell: ({ row }) => (
        <span className="font-mono text-xs text-[var(--muted)] tabular-nums">
          {(row.original.noise_rate * 100).toFixed(1)}%
        </span>
      ),
    },
  ];
}

// ── Source Form ─────────────────────────────────────────────────────────

interface SourceFormData {
  name: string;
  source_type: string;
  endpoint_url: string;
  config: string;
}

const emptyForm: SourceFormData = {
  name: "",
  source_type: "rss",
  endpoint_url: "",
  config: "",
};

function SourceForm({
  initial,
  onSubmit,
  onCancel,
  submitLabel,
  t,
}: {
  initial?: SourceFormData;
  onSubmit: (data: {
    name: string;
    source_type: string;
    endpoint_url: string;
    config?: Record<string, unknown>;
  }) => void;
  onCancel: () => void;
  submitLabel: string;
  t: (key: string) => string;
}) {
  const [form, setForm] = useState<SourceFormData>(initial || emptyForm);
  const [configError, setConfigError] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim() || !form.endpoint_url.trim()) return;

    let config: Record<string, unknown> | undefined;
    if (form.config.trim()) {
      try {
        config = JSON.parse(form.config);
        setConfigError(false);
      } catch {
        setConfigError(true);
        return;
      }
    }

    onSubmit({
      name: form.name.trim(),
      source_type: form.source_type,
      endpoint_url: form.endpoint_url.trim(),
      config,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--muted)]">
            {t("sources.sourceName")}
          </label>
          <Input
            placeholder={t("sources.namePlaceholder")}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
        </div>
        <div>
          <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--muted)]">
            {t("sources.sourceType")}
          </label>
          <select
            className="h-8 w-full rounded-lg border border-[var(--input)] bg-[var(--background)] px-2.5 text-[13px] outline-none focus-visible:border-ring"
            value={form.source_type}
            onChange={(e) => setForm({ ...form, source_type: e.target.value })}
          >
            {SOURCE_TYPES.map((st) => (
              <option key={st} value={st}>
                {st}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--muted)]">
          {t("sources.endpointUrl")}
        </label>
        <Input
          placeholder={t("sources.endpointPlaceholder")}
          value={form.endpoint_url}
          onChange={(e) => setForm({ ...form, endpoint_url: e.target.value })}
          required
        />
      </div>

      <div>
        <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--muted)]">
          {t("sources.configJson")}
        </label>
        <Textarea
          placeholder={t("sources.configPlaceholder")}
          value={form.config}
          onChange={(e) => {
            setForm({ ...form, config: e.target.value });
            setConfigError(false);
          }}
          className={`font-mono text-[12px] ${configError ? "border-[var(--accent-red)]" : ""}`}
          rows={3}
        />
        {configError && (
          <p className="mt-1 flex items-center gap-1 text-[11px] text-[var(--accent-red)]">
            <AlertCircle size={12} />
            {t("sources.configInvalid")}
          </p>
        )}
      </div>

      <div className="flex items-center justify-end gap-2 pt-2">
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" size="sm">
          <Check size={14} className="mr-1" />
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────

export default function SourcesPage() {
  const { t } = useTranslation();

  // Form state
  const [showForm, setShowForm] = useState(false);
  const [editingSource, setEditingSource] = useState<CustomSource | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Data fetching
  const {
    data: reputations,
    error: repError,
    isLoading: repLoading,
  } = useSWR("source-reputations", fetchSourceReputations);

  const {
    data: customSources,
    error: csError,
    isLoading: csLoading,
    mutate: mutateSources,
  } = useSWR("custom-sources", fetchCustomSources);

  const sortedReputations = useMemo(
    () => [...(reputations || [])].sort((a, b) => b.reputation_score - a.reputation_score),
    [reputations]
  );

  // ── CRUD Handlers ──────────────────────────────────────────────────

  const handleCreate = useCallback(
    async (data: {
      name: string;
      source_type: string;
      endpoint_url: string;
      config?: Record<string, unknown>;
    }) => {
      try {
        await createCustomSource(data);
        await mutateSources();
        setShowForm(false);
        toast.success(t("common.completed"));
      } catch (err) {
        toast.error(String(err instanceof Error ? err.message : err));
      }
    },
    [mutateSources, t]
  );

  const handleUpdate = useCallback(
    async (data: {
      name: string;
      source_type: string;
      endpoint_url: string;
      config?: Record<string, unknown>;
    }) => {
      if (!editingSource) return;
      try {
        await updateCustomSource(editingSource.id, data);
        await mutateSources();
        setEditingSource(null);
        toast.success(t("common.completed"));
      } catch (err) {
        toast.error(String(err instanceof Error ? err.message : err));
      }
    },
    [editingSource, mutateSources, t]
  );

  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await deleteCustomSource(id);
        await mutateSources();
        setDeletingId(null);
        toast.success(t("common.completed"));
      } catch (err) {
        toast.error(String(err instanceof Error ? err.message : err));
      }
    },
    [mutateSources, t]
  );

  return (
    <div className="mx-auto max-w-[1500px] space-y-8">
      {/* ── Header ─────────────────────────────────────────────────── */}
      <div>
        <div className="section-label">{t("sources.title")}</div>
        <h1 className="heading-display mt-3">{t("sources.subtitle")}</h1>
      </div>
      <div className="divider-line" />

      {/* ── Reputation Scores ──────────────────────────────────────── */}
      <section className="animate-fadeIn">
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h2 className="heading-section">{t("sources.reputation")}</h2>
            <p className="mt-1 text-[13px] text-[var(--muted)]">
              {t("sources.noReputationDescription")}
            </p>
          </div>
        </div>
        <div className="divider-subtle mb-5" />

        {repLoading && <SkeletonRows count={8} />}
        {repError && (
          <EmptyState
            title={t("common.failed")}
            description={String(repError.message || repError)}
          />
        )}
        {!repLoading && !repError && sortedReputations.length === 0 && (
          <EmptyState
            title={t("sources.noReputation")}
            description={t("sources.noReputationDescription")}
            icon={<Database size={40} />}
          />
        )}
        {!repLoading && !repError && sortedReputations.length > 0 && (
          <DataTable
            columns={reputationColumns(t)}
            data={sortedReputations}
            searchColumn="display_name"
            searchPlaceholder={t("sources.searchPlaceholder")}
            pageSize={15}
          />
        )}
      </section>

      <div className="divider-line" />

      {/* ── Custom Sources ─────────────────────────────────────────── */}
      <section className="animate-fadeIn">
        <div className="mb-5 flex items-center justify-between gap-4">
          <div>
            <h2 className="heading-section">{t("sources.customSources")}</h2>
          </div>
          {!showForm && !editingSource && (
            <Button
              size="sm"
              onClick={() => {
                setShowForm(true);
                setEditingSource(null);
              }}
            >
              <Plus size={14} className="mr-1" />
              {t("sources.addSource")}
            </Button>
          )}
        </div>
        <div className="divider-subtle mb-5" />

        {/* Inline form for create / edit */}
        {(showForm || editingSource) && (
          <div className="mb-6 rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
            <div className="mb-4 flex items-center justify-between">
              <div className="section-label">
                {editingSource
                  ? t("sources.editSource")
                  : t("sources.addSource")}
              </div>
              <button
                className="text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
                onClick={() => {
                  setShowForm(false);
                  setEditingSource(null);
                }}
              >
                <X size={16} />
              </button>
            </div>
            <div className="divider-subtle mb-4" />
            <SourceForm
              initial={
                editingSource
                  ? {
                      name: editingSource.name,
                      source_type: editingSource.source_type,
                      endpoint_url: editingSource.endpoint_url,
                      config: editingSource.config
                        ? JSON.stringify(editingSource.config, null, 2)
                        : "",
                    }
                  : undefined
              }
              onSubmit={editingSource ? handleUpdate : handleCreate}
              onCancel={() => {
                setShowForm(false);
                setEditingSource(null);
              }}
              submitLabel={
                editingSource ? t("common.save") : t("sources.addSource")
              }
              t={t}
            />
          </div>
        )}

        {/* Delete confirmation */}
        {deletingId && (
          <div className="mb-6 rounded-lg border border-[var(--accent-red)]/30 bg-[var(--accent-red)]/5 p-4">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-2 text-[13px] text-[var(--foreground)]">
                <AlertCircle size={16} className="text-[var(--accent-red)]" />
                {t("sources.deleteConfirm")}
              </div>
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setDeletingId(null)}
                >
                  {t("common.cancel")}
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => handleDelete(deletingId)}
                >
                  <Trash2 size={14} className="mr-1" />
                  {t("common.delete")}
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Custom sources list */}
        {csLoading && <SkeletonRows count={4} />}
        {csError && (
          <EmptyState
            title={t("common.failed")}
            description={String(csError.message || csError)}
          />
        )}
        {!csLoading && !csError && (!customSources || customSources.length === 0) && (
          <EmptyState
            title={t("sources.noSources")}
            description={t("sources.noSourcesDescription")}
            icon={
              <svg
                width="40"
                height="40"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <ellipse cx="12" cy="5" rx="9" ry="3" />
                <path d="M3 5V19A9 3 0 0 0 21 19V5" />
                <path d="M3 12A9 3 0 0 0 21 12" />
              </svg>
            }
          />
        )}
        {!csLoading &&
          !csError &&
          customSources &&
          customSources.length > 0 && (
            <div className="overflow-hidden rounded-lg border border-[var(--card-border)]">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[var(--card-border)] bg-[var(--bg-secondary)]">
                    <th className="px-4 py-3 text-left text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--muted)]">
                      {t("sources.sourceName")}
                    </th>
                    <th className="px-4 py-3 text-left text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--muted)]">
                      {t("sources.sourceType")}
                    </th>
                    <th className="hidden px-4 py-3 text-left text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--muted)] sm:table-cell">
                      {t("sources.endpointUrl")}
                    </th>
                    <th className="px-4 py-3 text-left text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--muted)]">
                      {t("common.status")}
                    </th>
                    <th className="px-4 py-3 text-right text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--muted)]">
                      {/* Actions */}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {customSources.map((source) => (
                    <tr
                      key={source.id}
                      className="border-b border-[var(--card-border)]/50 transition-colors hover:bg-[var(--bg-secondary)]/50"
                    >
                      <td className="px-4 py-3 font-medium text-[var(--foreground)]">
                        <div className="flex items-center gap-2">
                          <Database
                            size={14}
                            className="shrink-0 text-[var(--muted)]"
                          />
                          <span className="truncate">{source.name}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <span className="rounded bg-[var(--bg-secondary)] px-2 py-0.5 text-[11px] font-medium text-[var(--muted-foreground)]">
                          {source.source_type}
                        </span>
                      </td>
                      <td className="hidden px-4 py-3 sm:table-cell">
                        <span className="flex items-center gap-1 font-mono text-[12px] text-[var(--muted)]">
                          <span className="max-w-[260px] truncate">
                            {source.endpoint_url}
                          </span>
                          {source.endpoint_url.startsWith("http") && (
                            <a
                              href={source.endpoint_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="shrink-0 text-[var(--accent)] hover:underline"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <ExternalLink size={11} />
                            </a>
                          )}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center gap-1.5 text-[12px] ${
                            source.enabled
                              ? "text-[var(--accent-green)]"
                              : "text-[var(--muted)]"
                          }`}
                        >
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${
                              source.enabled
                                ? "bg-[var(--accent-green)]"
                                : "bg-[var(--muted)]"
                            }`}
                          />
                          {source.enabled
                            ? t("sources.enabled")
                            : t("sources.disabled")}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => {
                              setEditingSource(source);
                              setShowForm(false);
                            }}
                            title={t("sources.editSource")}
                          >
                            <Pencil size={14} />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => setDeletingId(source.id)}
                            title={t("sources.deleteSource")}
                          >
                            <Trash2 size={14} className="text-[var(--accent-red)]" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </section>
    </div>
  );
}
