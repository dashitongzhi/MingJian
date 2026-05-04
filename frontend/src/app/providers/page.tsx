"use client";

import { useState, useCallback, type ReactNode } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import { Check, X, Loader2, Eye, EyeOff, FlaskConical, ExternalLink, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  useConfiguredProviders,
  saveProvider,
  deleteProvider,
  testProvider,
  type ConfiguredProvider,
  type ProviderTestResult,
} from "@/lib/providers";
import { useTranslation } from "@/contexts/LanguageContext";

// ── Zod schemas ─────────────────────────────────────────────────────────────

const providerEditSchema = z.object({
  api_key: z.string(),
  base_url: z.union([z.string().url("请输入有效的URL"), z.literal("")]),
  model: z.string().min(1, "请输入模型名称"),
  api_format: z.enum(["openai", "anthropic"]),
});

const customProviderSchema = z.object({
  name: z.string().min(1, "请输入供应商名称"),
  api_key: z.string().min(1, "请输入API Key"),
  base_url: z.string().min(1, "请输入Base URL").url("请输入有效的URL"),
  model: z.string(),
  api_format: z.enum(["openai", "anthropic"]),
});

type ProviderEditValues = z.infer<typeof providerEditSchema>;
type CustomProviderValues = z.infer<typeof customProviderSchema>;

// ── Shared helpers ──────────────────────────────────────────────────────────

function inputClass(hasError?: boolean) {
  return `input w-full ${
    hasError ? "border-[var(--accent-red)]" : ""
  }`;
}

// ── Small presentational components ─────────────────────────────────────────

function ProviderStatus({ configured }: { configured: boolean }) {
  const { t } = useTranslation();

  return configured ? (
    <span className="badge badge-success">{t("providers.configuredBadge")}</span>
  ) : (
    <span className="badge">{t("providers.notConfiguredBadge")}</span>
  );
}

function ProviderCard({
  provider,
  onConfigure,
}: {
  provider: ConfiguredProvider;
  onConfigure: () => void;
}) {
  const { t } = useTranslation();

  return (
    <button
      onClick={onConfigure}
      className="group grid min-h-[150px] w-full grid-rows-[auto_1fr_auto] card rounded-xl p-5 text-left magnetic-hover"
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg border border-[var(--card-border)] bg-[var(--background)] text-sm font-semibold text-[var(--accent)]">
            {(provider.name || "?").charAt(0)}
          </div>
          <div className="min-w-0">
            <div className="truncate text-sm font-medium">{provider.name || provider.id}</div>
            <div className="mt-1 truncate text-xs text-[var(--muted)]">{provider.base_url}</div>
          </div>
        </div>
        <ProviderStatus configured={provider.api_key_set} />
      </div>

      <div className="mt-5 pt-4">
        <div className="section-label">{t("providers.model")}</div>
        <div className="mt-2 min-h-5 truncate font-mono text-xs text-[var(--muted-foreground)]">
          {provider.active_model || "-"}
        </div>
      </div>

      <div className="divider-subtle mt-4 mb-3" />

      <div className="flex items-center justify-between text-xs text-[var(--muted)]">
        <span>{provider.api_format === "anthropic" ? "Anthropic Format" : "OpenAI Format"}</span>
        <span className="opacity-0 transition-opacity duration-200 group-hover:opacity-100">{t("providers.editHint")}</span>
      </div>
    </button>
  );
}

function WizardRail({ steps, active = 0 }: { steps: string[]; active?: number }) {
  return (
    <div className="hidden border-r border-[var(--card-border)] bg-[var(--background)]/55 p-5 md:block">
      <div className="space-y-4">
        {steps.map((step, index) => (
          <div key={step} className="flex items-center gap-3">
            <span
              className={`grid h-6 w-6 place-items-center rounded-full border font-mono text-[11px] ${
                index <= active
                  ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
                  : "border-[var(--card-border)] text-[var(--muted)]"
              }`}
            >
              {index + 1}
            </span>
            <span className={`text-xs ${index <= active ? "text-[var(--foreground)]" : "text-[var(--muted)]"}`}>{step}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function FieldBlock({
  label,
  children,
  hint,
  error,
}: {
  label: string;
  children: ReactNode;
  hint?: ReactNode;
  error?: string;
}) {
  return (
    <div className="grid gap-2 md:grid-cols-[140px_1fr] md:items-start">
      <label className="section-label pt-2">{label}</label>
      <div>
        {children}
        {error && <div className="mt-1 text-xs text-[var(--accent-red)]">{error}</div>}
        {hint && <div className="mt-2 text-xs text-[var(--muted)]">{hint}</div>}
      </div>
    </div>
  );
}

function FormatToggle({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const { t } = useTranslation();

  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-[var(--card-border)] bg-[var(--card-border)]">
      {["openai", "anthropic"].map((fmt) => (
        <button
          key={fmt}
          type="button"
          onClick={() => onChange(fmt)}
          className={`px-3 py-2 text-sm transition-[background-color,color,opacity] duration-200 ${
            value === fmt
              ? "bg-[var(--accent)] text-[var(--accent-foreground)]"
              : "bg-[var(--background)] text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
          }`}
        >
          {fmt === "openai" ? t("providers.openaiCompatible") : t("providers.anthropicNative")}
        </button>
      ))}
    </div>
  );
}

function InlineTestResult({ result }: { result: ProviderTestResult | null }) {
  const { t } = useTranslation();
  if (!result) return null;

  return (
    <div className={`mt-3 flex items-start gap-2 text-sm ${result.ok ? "text-[var(--accent-green)]" : "text-[var(--accent-red)]"}`}>
      <span className="mt-0.5">{result.ok ? <Check className="size-4" /> : <X className="size-4" />}</span>
      <span>
        {result.ok ? (
          <>
            {t("providers.connectionSuccess")} · {t("providers.latency")} {result.latency_ms}ms
            {result.models_available.length > 0 && (
              <span className="text-[var(--muted)]"> · {result.models_available.length} {t("providers.modelsAvailable")}</span>
            )}
          </>
        ) : (
          result.error || t("providers.connectionFailed")
        )}
      </span>
    </div>
  );
}

function PanelShell({
  children,
  onClose,
  rail,
}: {
  children: ReactNode;
  onClose: () => void;
  rail: ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--overlay)] p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="grid w-full max-w-4xl overflow-hidden rounded-xl card animate-fadeIn md:grid-cols-[220px_1fr]"
        onClick={(e) => e.stopPropagation()}
      >
        {rail}
        {children}
      </div>
    </div>
  );
}

// ── ConfigPanel (edit existing provider) ────────────────────────────────────

function ConfigPanel({
  provider,
  onClose,
  onSaved,
}: {
  provider: ConfiguredProvider;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<ProviderTestResult | null>(null);
  const [fetchedModels, setFetchedModels] = useState<string[]>([]);

  const {
    register,
    handleSubmit,
    control,
    watch,
    setValue,
    getValues,
    formState: { errors },
  } = useForm<ProviderEditValues>({
    resolver: zodResolver(providerEditSchema),
    defaultValues: {
      api_key: "",
      base_url: provider.base_url,
      model: provider.active_model || "",
      api_format: (provider.api_format as "openai" | "anthropic") || "openai",
    },
    mode: "onTouched",
  });

  const watchedModel = watch("model");
  const watchedApiKey = watch("api_key");

  const handleTest = useCallback(async () => {
    const values = getValues();
    if (!values.api_key && !provider.api_key_set) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testProvider({
        base_url: values.base_url,
        api_key: values.api_key || "(saved)",
        api_format: values.api_format,
        model: values.model || undefined,
      });
      setTestResult(result);
      if (result.ok) {
        toast.success("连接测试成功");
      } else {
        toast.error("连接测试失败");
      }
      if (result.models_available.length > 0) {
        setFetchedModels(result.models_available);
        if (!values.model) {
          setValue("model", result.models_available[0], { shouldValidate: true, shouldTouch: true });
        }
      }
    } catch (e: any) {
      setTestResult({ ok: false, latency_ms: 0, models_available: [], error: e.message });
      toast.error("连接测试失败");
    } finally {
      setTesting(false);
    }
  }, [getValues, provider.api_key_set, setValue]);

  const onSubmit = useCallback(
    async (data: ProviderEditValues) => {
      setSaving(true);
      try {
        await saveProvider({
          provider_id: provider.id,
          api_key: data.api_key || "(unchanged)",
          base_url: data.base_url,
          model: data.model || undefined,
          api_format: data.api_format,
          enabled: true,
        });
        toast.success("供应商已保存");
        onSaved();
        onClose();
      } catch (e: any) {
        toast.error(`${t("providers.saveFailed")}: ${e.message}`);
      } finally {
        setSaving(false);
      }
    },
    [provider.id, onSaved, onClose, t],
  );

  const handleDelete = useCallback(async () => {
    if (!confirm(`${t("providers.deleteConfirmPrefix")} ${provider.name || provider.id}?`)) return;
    await deleteProvider(provider.id);
    onSaved();
    onClose();
  }, [provider.id, provider.name, onSaved, onClose, t]);

  return (
    <PanelShell
      onClose={onClose}
      rail={<WizardRail active={testResult?.ok ? 3 : 2} steps={[t("providers.apiFormat"), "Base URL", "API Key", t("providers.model")]} />}
    >
      <form onSubmit={handleSubmit(onSubmit, () => toast.error("请检查表单信息"))} className="min-w-0">
        <div className="flex items-start justify-between gap-4 border-b border-[var(--card-border)] p-5">
          <div className="min-w-0">
            <h3 className="heading-section truncate">{provider.name || provider.id}</h3>
            <p className="mt-1 text-xs text-[var(--muted)]">{provider.api_format === "anthropic" ? "Anthropic Format" : "OpenAI Format"}</p>
          </div>
          <Button type="button" variant="ghost" size="icon" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </div>

        <div className="max-h-[68vh] space-y-5 overflow-y-auto p-5">
          <FieldBlock label={t("providers.apiFormat")} error={errors.api_format?.message}>
            <Controller
              name="api_format"
              control={control}
              render={({ field }) => <FormatToggle value={field.value} onChange={field.onChange} />}
            />
          </FieldBlock>

          <FieldBlock label="Base URL" error={errors.base_url?.message}>
            <input
              type="text"
              {...register("base_url")}
              className={inputClass(!!errors.base_url)}
              placeholder="https://api.openai.com/v1"
            />
          </FieldBlock>

          <FieldBlock
            label="API Key"
            error={errors.api_key?.message}
            hint={
              provider.website ? (
                <a href={provider.website} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[var(--accent)] hover:opacity-80">
                  {t("providers.getApiKey")} <ExternalLink className="size-3" />
                </a>
              ) : null
            }
          >
            <div className="relative">
              <input
                type={showKey ? "text" : "password"}
                {...register("api_key")}
                className={inputClass(!!errors.api_key).replace("w-full", "w-full pr-10")}
                placeholder={provider.placeholder || t("providers.apiKeyPlaceholder")}
                autoComplete="off"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute inset-y-0 right-0 flex items-center pr-3 text-[var(--muted)] hover:text-[var(--foreground)]"
              >
                {showKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          </FieldBlock>

          <FieldBlock
            label={t("providers.model")}
            error={errors.model?.message}
            hint={fetchedModels.length === 0 ? t("providers.testToLoadModels") : undefined}
          >
            <div className="flex gap-2">
              <input
                type="text"
                {...register("model")}
                className={inputClass(!!errors.model).replace("w-full", "min-w-0 flex-1")}
                placeholder={t("providers.modelInputPlaceholder")}
                list={`models-${provider.id}`}
              />
              <datalist id={`models-${provider.id}`}>
                {fetchedModels.map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
              {fetchedModels.length > 0 && (
                <select
                  value={watchedModel}
                  onChange={(e) => setValue("model", e.target.value, { shouldValidate: true, shouldTouch: true })}
                  className="w-24 rounded-lg border border-[var(--card-border)] bg-[var(--background)] px-2 py-2 text-sm focus:border-[var(--accent)] focus:outline-none"
                >
                  <option value="">▼</option>
                  {fetchedModels.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              )}
            </div>
          </FieldBlock>

          <div className="divider-subtle pt-5 md:ml-[140px]">
            <Button
              type="button"
              variant="outline"
              onClick={handleTest}
              disabled={testing || (!watchedApiKey && !provider.api_key_set)}
              className="btn btn-primary w-full"
            >
              {testing ? (
                <>
                  <Loader2 className="size-4 animate-spin" /> {t("providers.testing")}
                </>
              ) : (
                <>
                  <FlaskConical className="size-4" /> {t("providers.testConnection")}
                </>
              )}
            </Button>
            <InlineTestResult result={testResult} />
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-[var(--card-border)] p-5">
          <Button type="button" variant="destructive" size="sm" onClick={handleDelete}>
            <Trash2 className="size-4" /> {t("common.delete")}
          </Button>
          <div className="flex gap-2">
            <Button type="button" variant="ghost" className="btn btn-ghost" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" disabled={saving || !watchedModel} className="btn btn-primary">
              {saving ? t("common.saving") : t("common.save")}
            </Button>
          </div>
        </div>
      </form>
    </PanelShell>
  );
}

// ── AddCustomCard ───────────────────────────────────────────────────────────

function AddCustomCard({ onClick }: { onClick: () => void }) {
  const { t } = useTranslation();

  return (
    <button
      onClick={onClick}
      className="grid min-h-[150px] w-full place-items-center rounded-xl border border-dashed border-[var(--card-border)] bg-transparent p-5 text-center magnetic-hover transition-[border-color,background-color] duration-200 hover:border-[var(--accent)] hover:bg-[var(--card)]"
    >
      <div>
        <div className="mx-auto grid h-9 w-9 place-items-center rounded-lg border border-[var(--card-border)] text-lg text-[var(--accent)]">+</div>
        <div className="mt-3 text-sm font-medium">{t("providers.customProvider")}</div>
        <div className="mt-1 max-w-[220px] text-xs leading-5 text-[var(--muted)]">{t("providers.customProviderDescription")}</div>
      </div>
    </button>
  );
}

// ── CustomConfigPanel (add new custom provider) ─────────────────────────────

function CustomConfigPanel({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<ProviderTestResult | null>(null);
  const [fetchedModels, setFetchedModels] = useState<string[]>([]);

  const {
    register,
    handleSubmit,
    control,
    watch,
    setValue,
    getValues,
    formState: { errors },
  } = useForm<CustomProviderValues>({
    resolver: zodResolver(customProviderSchema),
    defaultValues: {
      name: "",
      api_key: "",
      base_url: "",
      model: "",
      api_format: "openai",
    },
    mode: "onTouched",
  });

  const watchedName = watch("name");
  const watchedApiKey = watch("api_key");
  const watchedBaseUrl = watch("base_url");
  const watchedApiFormat = watch("api_format");
  const watchedModel = watch("model");

  const handleTest = useCallback(async () => {
    const values = getValues();
    if (!values.api_key || !values.base_url) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testProvider({
        base_url: values.base_url,
        api_key: values.api_key,
        api_format: values.api_format,
        model: values.model || undefined,
      });
      setTestResult(result);
      if (result.ok) {
        toast.success("连接测试成功");
      } else {
        toast.error("连接测试失败");
      }
      if (result.models_available.length > 0) {
        setFetchedModels(result.models_available);
        if (!values.model) {
          setValue("model", result.models_available[0], { shouldValidate: true, shouldTouch: true });
        }
      }
    } catch (e: any) {
      setTestResult({ ok: false, latency_ms: 0, models_available: [], error: e.message });
      toast.error("连接测试失败");
    } finally {
      setTesting(false);
    }
  }, [getValues, setValue]);

  const onSubmit = useCallback(
    async (data: CustomProviderValues) => {
      setSaving(true);
      try {
        const providerId = `custom-${data.name.toLowerCase().replace(/[^a-z0-9]/g, "-").replace(/-+/g, "-")}`;
        await saveProvider({
          provider_id: providerId,
          name: data.name,
          api_key: data.api_key,
          base_url: data.base_url,
          model: data.model || undefined,
          api_format: data.api_format,
          enabled: true,
        });
        toast.success("供应商已保存");
        onSaved();
        onClose();
      } catch (e: any) {
        toast.error(`${t("providers.saveFailed")}: ${e.message}`);
      } finally {
        setSaving(false);
      }
    },
    [onSaved, onClose, t],
  );

  return (
    <PanelShell
      onClose={onClose}
      rail={<WizardRail active={testResult?.ok ? 4 : 3} steps={[t("providers.providerName"), t("providers.apiFormat"), "Base URL", "API Key", t("providers.model")]} />}
    >
      <form onSubmit={handleSubmit(onSubmit, () => toast.error("请检查表单信息"))} className="min-w-0">
        <div className="flex items-start justify-between gap-4 border-b border-[var(--card-border)] p-5">
          <div>
            <h3 className="heading-section">{t("providers.customProvider")}</h3>
            <p className="mt-1 text-xs text-[var(--muted)]">{t("providers.customProviderSubtitle")}</p>
          </div>
          <Button type="button" variant="ghost" size="icon" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </div>

        <div className="max-h-[68vh] space-y-5 overflow-y-auto p-5">
          <FieldBlock label={t("providers.providerName")} error={errors.name?.message}>
            <input
              type="text"
              {...register("name")}
              className={inputClass(!!errors.name)}
              placeholder={t("providers.providerNamePlaceholder")}
            />
          </FieldBlock>

          <FieldBlock label={t("providers.apiFormat")} error={errors.api_format?.message}>
            <Controller
              name="api_format"
              control={control}
              render={({ field }) => <FormatToggle value={field.value} onChange={field.onChange} />}
            />
          </FieldBlock>

          <FieldBlock label="Base URL" error={errors.base_url?.message}>
            <input
              type="text"
              {...register("base_url")}
              className={inputClass(!!errors.base_url)}
              placeholder={watchedApiFormat === "anthropic" ? "https://api.anthropic.com/v1/openai" : "https://your-api.com/v1"}
            />
          </FieldBlock>

          <FieldBlock label="API Key" error={errors.api_key?.message}>
            <div className="relative">
              <input
                type={showKey ? "text" : "password"}
                {...register("api_key")}
                className={inputClass(!!errors.api_key).replace("w-full", "w-full pr-10")}
                placeholder="sk-... / your-api-key"
                autoComplete="off"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute inset-y-0 right-0 flex items-center pr-3 text-[var(--muted)] hover:text-[var(--foreground)]"
              >
                {showKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          </FieldBlock>

          <FieldBlock label={t("providers.model")} error={errors.model?.message}>
            <div className="flex gap-2">
              <input
                type="text"
                {...register("model")}
                className={inputClass(!!errors.model).replace("w-full", "min-w-0 flex-1")}
                placeholder={t("providers.chooseModelPlaceholder")}
                list="custom-models"
              />
              <datalist id="custom-models">
                {fetchedModels.map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
              {fetchedModels.length > 0 && (
                <select
                  value={watchedModel}
                  onChange={(e) => setValue("model", e.target.value, { shouldValidate: true, shouldTouch: true })}
                  className="w-24 rounded-lg border border-[var(--card-border)] bg-[var(--background)] px-2 py-2 text-sm focus:border-[var(--accent)] focus:outline-none"
                >
                  <option value="">▼</option>
                  {fetchedModels.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              )}
            </div>
          </FieldBlock>

          <div className="divider-subtle pt-5 md:ml-[140px]">
            <Button
              type="button"
              variant="outline"
              onClick={handleTest}
              disabled={testing || !watchedApiKey || !watchedBaseUrl}
              className="btn btn-primary w-full"
            >
              {testing ? (
                <>
                  <Loader2 className="size-4 animate-spin" /> {t("providers.testing")}
                </>
              ) : (
                <>
                  <FlaskConical className="size-4" /> {t("providers.testConnection")}
                </>
              )}
            </Button>
            <InlineTestResult result={testResult} />
          </div>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-[var(--card-border)] p-5">
          <Button type="button" variant="ghost" className="btn btn-ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button type="submit" disabled={saving || !watchedName || !watchedApiKey || !watchedBaseUrl} className="btn btn-primary">
            {saving ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </form>
    </PanelShell>
  );
}

// ── Skeleton & Page ─────────────────────────────────────────────────────────

function ProvidersSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {[0, 1, 2, 3, 4, 5].map((item) => (
        <div key={item} className="min-h-[150px] card rounded-xl p-5">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-[var(--card-border)] animate-pulse" />
            <div className="flex-1 space-y-2">
              <div className="h-4 w-1/2 rounded bg-[var(--card-border)] animate-pulse" />
              <div className="h-3 w-3/4 rounded bg-[var(--card-border)]/70 animate-pulse" />
            </div>
          </div>
          <div className="mt-8 h-8 rounded bg-[var(--card-border)]/60 animate-pulse" />
        </div>
      ))}
    </div>
  );
}

export default function ProvidersPage() {
  const { t } = useTranslation();
  const { data: providers, error, isLoading, mutate } = useConfiguredProviders();
  const [configuring, setConfiguring] = useState<ConfiguredProvider | null>(null);
  const [showCustomPanel, setShowCustomPanel] = useState(false);

  const configuredCount = providers?.filter((p) => p.api_key_set).length || 0;
  const totalProviders = providers?.length || 0;

  return (
    <>
      <div className="space-y-8">
        {/* ── Header ────────────────────────────────────────────────────────── */}
        <div className="grid gap-6 pb-6 lg:grid-cols-[1fr_280px]">
          <div>
            <p className="section-label mb-3">{t("providers.configured")}</p>
            <h1 className="heading-display">{t("providers.title")}</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--muted-foreground)]">{t("providers.subtitlePrefix")}</p>
          </div>
          <div className="liquid-glass rounded-xl p-5">
            <div className="flex items-center justify-between">
              <span className="section-label">{t("providers.providers")}</span>
              <span className="font-mono text-xs text-[var(--accent)]">{configuredCount}/{totalProviders}</span>
            </div>
            <div className="mt-4 gradient-progress">
              <div
                className="gradient-progress-fill"
                style={{ width: totalProviders ? `${(configuredCount / totalProviders) * 100}%` : "0%" }}
              />
            </div>
          </div>
        </div>

        <div className="divider-subtle" />

        {isLoading && <ProvidersSkeleton />}

        {!isLoading && error && (
          <div className="rounded-xl border border-[var(--accent-red)]/30 bg-[var(--accent-red-bg)] p-5 text-sm text-[var(--accent-red)]">
            <div className="font-medium">{t("common.failed")}</div>
            <div className="mt-1 text-xs text-[var(--muted-foreground)]">{error.message || "Request failed"}</div>
          </div>
        )}

        {!isLoading && !error && (
          <>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
              {providers?.map((provider) => (
                <ProviderCard
                  key={provider.id}
                  provider={provider}
                  onConfigure={() => setConfiguring(provider)}
                />
              ))}
              <AddCustomCard onClick={() => setShowCustomPanel(true)} />
            </div>

            {providers?.length === 0 && (
              <div className="empty-state card rounded-xl py-12">
                <div className="empty-state-title">{t("providers.providers")}</div>
              </div>
            )}

            <div className="card rounded-lg border-l-2 border-l-[var(--accent)] px-4 py-3 text-sm text-[var(--muted-foreground)]">
              <strong className="mr-2 text-[var(--foreground)]">{t("providers.hintTitle")}</strong>
              {t("providers.hint")}
            </div>
          </>
        )}
      </div>

      {configuring && (
        <ConfigPanel
          provider={configuring}
          onClose={() => setConfiguring(null)}
          onSaved={() => mutate()}
        />
      )}

      {showCustomPanel && (
        <CustomConfigPanel
          onClose={() => setShowCustomPanel(false)}
          onSaved={() => mutate()}
        />
      )}
    </>
  );
}
