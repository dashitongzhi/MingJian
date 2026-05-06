"use client";

import { useCallback, useMemo, useState } from "react";
import useSWR from "swr";
import { toast } from "@/lib/toast";
import {
  fetchAllAgents,
  createCustomAgent,
  updateCustomAgent,
  deleteCustomAgent,
  type AgentInfo,
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
  Users,
  Check,
  AlertCircle,
} from "lucide-react";

// ── Helpers ────────────────────────────────────────────────────────────

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

function truncate(text: string, maxLen: number): string {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + "…";
}

// ── Agent Form ─────────────────────────────────────────────────────────

interface AgentFormData {
  name: string;
  name_en: string;
  icon: string;
  description: string;
  priority: number;
}

const emptyForm: AgentFormData = {
  name: "",
  name_en: "",
  icon: "",
  description: "",
  priority: 2,
};

function AgentForm({
  initial,
  onSubmit,
  onCancel,
  submitLabel,
  t,
}: {
  initial?: AgentFormData;
  onSubmit: (data: AgentFormData) => void;
  onCancel: () => void;
  submitLabel: string;
  t: (key: string) => string;
}) {
  const [form, setForm] = useState<AgentFormData>(initial || emptyForm);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim() || !form.name_en.trim() || !form.icon.trim()) return;
    onSubmit({
      name: form.name.trim(),
      name_en: form.name_en.trim(),
      icon: form.icon.trim(),
      description: form.description.trim(),
      priority: form.priority,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--muted)]">
            {t("agents.agentName")}
          </label>
          <Input
            placeholder={t("agents.namePlaceholder")}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
        </div>
        <div>
          <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--muted)]">
            {t("agents.agentNameEn")}
          </label>
          <Input
            placeholder={t("agents.nameEnPlaceholder")}
            value={form.name_en}
            onChange={(e) => setForm({ ...form, name_en: e.target.value })}
            required
          />
        </div>
        <div>
          <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--muted)]">
            {t("agents.agentIcon")}
          </label>
          <Input
            placeholder={t("agents.iconPlaceholder")}
            value={form.icon}
            onChange={(e) => setForm({ ...form, icon: e.target.value })}
            required
          />
        </div>
        <div>
          <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--muted)]">
            {t("agents.priority")}
          </label>
          <select
            className="h-8 w-full rounded-lg border border-[var(--input)] bg-[var(--background)] px-2.5 text-[13px] outline-none focus-visible:border-ring"
            value={form.priority}
            onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })}
          >
            <option value={1}>{t("agents.priorityHigh")} (1)</option>
            <option value={2}>{t("agents.priorityLow")} (2)</option>
          </select>
        </div>
      </div>

      <div>
        <label className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.12em] text-[var(--muted)]">
          {t("agents.agentDescription")}
        </label>
        <Textarea
          placeholder={t("agents.descriptionPlaceholder")}
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          rows={3}
        />
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

// ── Custom Agent Columns ───────────────────────────────────────────────

function customAgentColumns(
  t: (key: string) => string,
  onEdit: (agent: AgentInfo) => void,
  onDelete: (key: string) => void
): ColumnDef<AgentInfo, unknown>[] {
  return [
    {
      accessorKey: "icon",
      header: t("agents.agentIcon"),
      cell: ({ row }) => (
        <span className="text-xl leading-none">{row.original.icon}</span>
      ),
      size: 60,
    },
    {
      accessorKey: "name",
      header: t("agents.agentName"),
      cell: ({ row }) => (
        <span className="font-medium">{row.original.name}</span>
      ),
    },
    {
      accessorKey: "name_en",
      header: t("agents.agentNameEn"),
      cell: ({ row }) => (
        <span className="text-[var(--muted)]">{row.original.name_en}</span>
      ),
    },
    {
      accessorKey: "priority",
      header: t("agents.priority"),
      cell: ({ row }) => (
        <span
          className={`rounded px-2 py-0.5 text-[11px] font-medium ${
            row.original.priority === 1
              ? "bg-[var(--accent-green)]/10 text-[var(--accent-green)]"
              : "bg-[var(--card-border)]/50 text-[var(--muted-foreground)]"
          }`}
        >
          {row.original.priority === 1
            ? t("agents.priorityHigh")
            : t("agents.priorityLow")}
        </span>
      ),
      size: 100,
    },
    {
      accessorKey: "description",
      header: t("agents.agentDescription"),
      cell: ({ row }) => (
        <span className="text-[13px] text-[var(--muted)]">
          {truncate(row.original.description, 60)}
        </span>
      ),
    },
    {
      id: "actions",
      header: "",
      cell: ({ row }) => (
        <div className="flex items-center gap-1">
          <button
            className="rounded p-1.5 text-[var(--muted)] transition-colors hover:bg-[var(--sidebar-accent)] hover:text-[var(--foreground)]"
            onClick={() => onEdit(row.original)}
            title={t("agents.editAgent")}
          >
            <Pencil size={14} />
          </button>
          <button
            className="rounded p-1.5 text-[var(--muted)] transition-colors hover:bg-[var(--accent-red)]/10 hover:text-[var(--accent-red)]"
            onClick={() => onDelete(row.original.role_key)}
            title={t("common.delete")}
          >
            <Trash2 size={14} />
          </button>
        </div>
      ),
      size: 80,
    },
  ];
}

// ── Default Agent Card ─────────────────────────────────────────────────

function DefaultAgentCard({ agent }: { agent: AgentInfo }) {
  return (
    <div className="group rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-4 transition-all hover:border-[var(--accent)]/30 hover:shadow-sm">
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[var(--accent)]/10 text-xl">
          {agent.icon}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium text-[var(--foreground)] text-[13px]">
              {agent.name}
            </span>
            <span className="rounded bg-[var(--card-border)]/50 px-1.5 py-0.5 text-[10px] font-medium text-[var(--muted)]">
              {agent.name_en}
            </span>
          </div>
          <p className="mt-1.5 text-[12px] leading-relaxed text-[var(--muted)] line-clamp-2">
            {agent.description}
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────

export default function AgentsPage() {
  const { t } = useTranslation();

  // Form state
  const [showForm, setShowForm] = useState(false);
  const [editingAgent, setEditingAgent] = useState<AgentInfo | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Data fetching
  const {
    data: agents,
    error,
    isLoading,
    mutate: mutateAgents,
  } = useSWR("all-agents", fetchAllAgents);

  const defaultAgents = useMemo(
    () => (agents || []).filter((a) => !a.is_custom),
    [agents]
  );

  const customAgents = useMemo(
    () =>
      [...(agents || [])]
        .filter((a) => a.is_custom)
        .sort((a, b) => a.priority - b.priority),
    [agents]
  );

  // ── CRUD Handlers ──────────────────────────────────────────────────

  const handleCreate = useCallback(
    async (data: AgentFormData) => {
      try {
        await createCustomAgent(data);
        await mutateAgents();
        setShowForm(false);
        toast.success(t("common.completed"));
      } catch (err) {
        toast.error(String(err instanceof Error ? err.message : err));
      }
    },
    [mutateAgents, t]
  );

  const handleUpdate = useCallback(
    async (data: AgentFormData) => {
      if (!editingAgent) return;
      try {
        await updateCustomAgent(editingAgent.role_key, data);
        await mutateAgents();
        setEditingAgent(null);
        toast.success(t("common.completed"));
      } catch (err) {
        toast.error(String(err instanceof Error ? err.message : err));
      }
    },
    [editingAgent, mutateAgents, t]
  );

  const handleDelete = useCallback(
    async (key: string) => {
      try {
        await deleteCustomAgent(key);
        await mutateAgents();
        setDeletingId(null);
        toast.success(t("common.completed"));
      } catch (err) {
        toast.error(String(err instanceof Error ? err.message : err));
      }
    },
    [mutateAgents, t]
  );

  const columns = useMemo(
    () =>
      customAgentColumns(
        t,
        (agent) => {
          setShowForm(false);
          setEditingAgent(agent);
        },
        (key) => setDeletingId(key)
      ),
    [t]
  );

  return (
    <div className="mx-auto max-w-[1500px] space-y-8">
      {/* ── Header ─────────────────────────────────────────────────── */}
      <div>
        <div className="section-label">{t("agents.title")}</div>
        <h1 className="heading-display mt-3">{t("agents.subtitle")}</h1>
      </div>
      <div className="divider-line" />

      {/* ── Default Agents ────────────────────────────────────────── */}
      <section className="animate-fadeIn">
        <div className="mb-5 flex items-center justify-between">
          <div>
            <h2 className="heading-section">{t("agents.defaultAgents")}</h2>
            <p className="mt-1 text-[13px] text-[var(--muted)]">
              {t("agents.defaultAgentsDescription")}
            </p>
          </div>
          {!isLoading && defaultAgents.length > 0 && (
            <span className="text-[12px] text-[var(--muted)]">
              {defaultAgents.length} {t("agents.agentsCount")}
            </span>
          )}
        </div>
        <div className="divider-subtle mb-5" />

        {isLoading && <SkeletonRows count={4} />}
        {error && (
          <EmptyState
            title={t("common.failed")}
            description={String(error.message || error)}
          />
        )}
        {!isLoading && !error && defaultAgents.length === 0 && (
          <EmptyState
            title={t("agents.noCustomAgents")}
            icon={<Users size={40} />}
          />
        )}
        {!isLoading && !error && defaultAgents.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {defaultAgents.map((agent) => (
              <DefaultAgentCard key={agent.role_key} agent={agent} />
            ))}
          </div>
        )}
      </section>

      <div className="divider-line" />

      {/* ── Custom Agents ─────────────────────────────────────────── */}
      <section className="animate-fadeIn">
        <div className="mb-5 flex items-center justify-between gap-4">
          <div>
            <h2 className="heading-section">{t("agents.customAgents")}</h2>
            <p className="mt-1 text-[13px] text-[var(--muted)]">
              {t("agents.customAgentsDescription")}
            </p>
          </div>
          {!showForm && !editingAgent && (
            <Button
              size="sm"
              onClick={() => {
                setShowForm(true);
                setEditingAgent(null);
              }}
            >
              <Plus size={14} className="mr-1" />
              {t("agents.addAgent")}
            </Button>
          )}
        </div>
        <div className="divider-subtle mb-5" />

        {/* Inline form for create / edit */}
        {(showForm || editingAgent) && (
          <div className="mb-6 rounded-lg border border-[var(--card-border)] bg-[var(--card)] p-5">
            <div className="mb-4 flex items-center justify-between">
              <div className="section-label">
                {editingAgent
                  ? t("agents.editAgent")
                  : t("agents.addAgent")}
              </div>
              <button
                className="text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
                onClick={() => {
                  setShowForm(false);
                  setEditingAgent(null);
                }}
              >
                <X size={16} />
              </button>
            </div>
            <div className="divider-subtle mb-4" />
            <AgentForm
              initial={
                editingAgent
                  ? {
                      name: editingAgent.name,
                      name_en: editingAgent.name_en,
                      icon: editingAgent.icon,
                      description: editingAgent.description,
                      priority: editingAgent.priority,
                    }
                  : undefined
              }
              onSubmit={editingAgent ? handleUpdate : handleCreate}
              onCancel={() => {
                setShowForm(false);
                setEditingAgent(null);
              }}
              submitLabel={
                editingAgent ? t("common.save") : t("agents.addAgent")
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
                {t("agents.deleteConfirm")}
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
                  {t("common.delete")}
                </Button>
              </div>
            </div>
          </div>
        )}

        {/* Custom agents table */}
        {isLoading && <SkeletonRows count={4} />}
        {error && (
          <EmptyState
            title={t("common.failed")}
            description={String(error.message || error)}
          />
        )}
        {!isLoading && !error && customAgents.length === 0 && !showForm && (
          <EmptyState
            title={t("agents.noCustomAgents")}
            description={t("agents.noCustomAgentsDescription")}
            icon={<Users size={40} />}
          />
        )}
        {!isLoading && !error && customAgents.length > 0 && (
          <DataTable
            columns={columns}
            data={customAgents}
            searchColumn="name"
            searchPlaceholder={t("agents.agentName")}
            pageSize={10}
          />
        )}
      </section>
    </div>
  );
}
