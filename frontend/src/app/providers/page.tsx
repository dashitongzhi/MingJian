"use client";

import { useState, useCallback, type ReactNode } from "react";
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

function ProviderStatus({ configured }: { configured: boolean }) {
  const { t } = useTranslation();

  return (
    <span className={`inline-flex items-center gap-2 text-xs ${configured ? "text-[var(--accent-green)]" : "text-[var(--muted)]"}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${configured ? "bg-[var(--accent-green)]" : "bg-[var(--muted)]"}`} />
      {configured ? t("providers.configuredBadge") : t("providers.notConfiguredBadge")}
    </span>
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
      className="group grid min-h-[150px] w-full grid-rows-[auto_1fr_auto] rounded-xl border border-[var(--card-border)] bg-[var(--card)] p-5 text-left transition-[border-color,transform,opacity,background-color] duration-200 hover:-translate-y-0.5 hover:border-[var(--accent)] hover:bg-[var(--card-hover)]"
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

      <div className="mt-5 border-t border-[var(--card-border)] pt-4">
        <div className="text-[11px] uppercase tracking-[0.16em] text-[var(--muted)]">{t("providers.model")}</div>
        <div className="mt-2 min-h-5 truncate font-mono text-xs text-[var(--muted-foreground)]">
          {provider.active_model || "-"}
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between text-xs text-[var(--muted)]">
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
}: {
  label: string;
  children: ReactNode;
  hint?: ReactNode;
}) {
  return (
    <div className="grid gap-2 md:grid-cols-[140px_1fr] md:items-start">
      <label className="pt-2 text-xs uppercase tracking-[0.14em] text-[var(--muted)]">{label}</label>
      <div>
        {children}
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
              ? "bg-[var(--accent)] text-black"
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="grid w-full max-w-4xl overflow-hidden rounded-xl border border-[var(--card-border)] bg-[var(--card)] animate-fadeIn md:grid-cols-[220px_1fr]"
        onClick={(e) => e.stopPropagation()}
      >
        {rail}
        {children}
      </div>
    </div>
  );
}

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
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState(provider.base_url);
  const [model, setModel] = useState(provider.active_model || "");
  const [apiFormat, setApiFormat] = useState(provider.api_format || "openai");
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<ProviderTestResult | null>(null);
  const [fetchedModels, setFetchedModels] = useState<string[]>([]);

  const handleTest = useCallback(async () => {
    if (!apiKey && !provider.api_key_set) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testProvider({
        base_url: baseUrl,
        api_key: apiKey || "(saved)",
        api_format: apiFormat,
        model: model || undefined,
      });
      setTestResult(result);
      if (result.models_available.length > 0) {
        setFetchedModels(result.models_available);
        if (!model) {
          setModel(result.models_available[0]);
        }
      }
    } catch (e: any) {
      setTestResult({ ok: false, latency_ms: 0, models_available: [], error: e.message });
    } finally {
      setTesting(false);
    }
  }, [apiKey, baseUrl, apiFormat, model, provider.api_key_set]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await saveProvider({
        provider_id: provider.id,
        api_key: apiKey || "(unchanged)",
        base_url: baseUrl,
        model: model || undefined,
        api_format: apiFormat,
        enabled: true,
      });
      onSaved();
      onClose();
    } catch (e: any) {
      alert(`${t("providers.saveFailed")}: ${e.message}`);
    } finally {
      setSaving(false);
    }
  }, [provider.id, apiKey, baseUrl, model, apiFormat, onSaved, onClose, t]);

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
      <div className="min-w-0">
        <div className="flex items-start justify-between gap-4 border-b border-[var(--card-border)] p-5">
          <div className="min-w-0">
            <h3 className="truncate text-base font-semibold">{provider.name || provider.id}</h3>
            <p className="mt-1 text-xs text-[var(--muted)]">{provider.api_format === "anthropic" ? "Anthropic Format" : "OpenAI Format"}</p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </div>

        <div className="max-h-[68vh] space-y-5 overflow-y-auto p-5">
          <FieldBlock label={t("providers.apiFormat")}>
            <FormatToggle value={apiFormat} onChange={setApiFormat} />
          </FieldBlock>

          <FieldBlock label="Base URL">
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="w-full rounded-lg border border-[var(--card-border)] bg-[var(--background)] px-3 py-2 font-mono text-sm transition-colors focus:border-[var(--accent)] focus:outline-none"
              placeholder="https://api.openai.com/v1"
            />
          </FieldBlock>

          <FieldBlock
            label="API Key"
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
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="w-full rounded-lg border border-[var(--card-border)] bg-[var(--background)] px-3 py-2 pr-10 font-mono text-sm transition-colors focus:border-[var(--accent)] focus:outline-none"
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
            hint={fetchedModels.length === 0 ? t("providers.testToLoadModels") : undefined}
          >
            <div className="flex gap-2">
              <input
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="min-w-0 flex-1 rounded-lg border border-[var(--card-border)] bg-[var(--background)] px-3 py-2 font-mono text-sm transition-colors focus:border-[var(--accent)] focus:outline-none"
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
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
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

          <div className="border-t border-[var(--card-border)] pt-5 md:ml-[140px]">
            <Button
              variant="outline"
              onClick={handleTest}
              disabled={testing || (!apiKey && !provider.api_key_set)}
              className="w-full"
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
          <Button variant="destructive" size="sm" onClick={handleDelete}>
            <Trash2 className="size-4" /> {t("common.delete")}
          </Button>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              {t("common.cancel")}
            </Button>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? t("common.saving") : t("common.save")}
            </Button>
          </div>
        </div>
      </div>
    </PanelShell>
  );
}

function AddCustomCard({ onClick }: { onClick: () => void }) {
  const { t } = useTranslation();

  return (
    <button
      onClick={onClick}
      className="grid min-h-[150px] w-full place-items-center rounded-xl border border-dashed border-[var(--card-border)] bg-transparent p-5 text-center transition-[border-color,background-color,transform] duration-200 hover:-translate-y-0.5 hover:border-[var(--accent)] hover:bg-[var(--card)]"
    >
      <div>
        <div className="mx-auto grid h-9 w-9 place-items-center rounded-lg border border-[var(--card-border)] text-lg text-[var(--accent)]">+</div>
        <div className="mt-3 text-sm font-medium">{t("providers.customProvider")}</div>
        <div className="mt-1 max-w-[220px] text-xs leading-5 text-[var(--muted)]">{t("providers.customProviderDescription")}</div>
      </div>
    </button>
  );
}

function CustomConfigPanel({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [apiFormat, setApiFormat] = useState("openai");
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testResult, setTestResult] = useState<ProviderTestResult | null>(null);
  const [fetchedModels, setFetchedModels] = useState<string[]>([]);

  const handleTest = useCallback(async () => {
    if (!apiKey || !baseUrl) return;
    setTesting(true);
    setTestResult(null);
    try {
      const result = await testProvider({
        base_url: baseUrl,
        api_key: apiKey,
        api_format: apiFormat,
        model: model || undefined,
      });
      setTestResult(result);
      if (result.models_available.length > 0) {
        setFetchedModels(result.models_available);
        if (!model) {
          setModel(result.models_available[0]);
        }
      }
    } catch (e: any) {
      setTestResult({ ok: false, latency_ms: 0, models_available: [], error: e.message });
    } finally {
      setTesting(false);
    }
  }, [apiKey, baseUrl, apiFormat, model]);

  const handleSave = useCallback(async () => {
    if (!name.trim() || !baseUrl.trim() || !apiKey.trim()) {
      alert(t("providers.requiredFields"));
      return;
    }
    setSaving(true);
    try {
      const providerId = `custom-${name.toLowerCase().replace(/[^a-z0-9]/g, "-").replace(/-+/g, "-")}`;
      await saveProvider({
        provider_id: providerId,
        name: name,
        api_key: apiKey,
        base_url: baseUrl,
        model: model || undefined,
        api_format: apiFormat,
        enabled: true,
      });
      onSaved();
      onClose();
    } catch (e: any) {
      alert(`${t("providers.saveFailed")}: ${e.message}`);
    } finally {
      setSaving(false);
    }
  }, [name, baseUrl, apiKey, model, apiFormat, onSaved, onClose, t]);

  return (
    <PanelShell
      onClose={onClose}
      rail={<WizardRail active={testResult?.ok ? 4 : 3} steps={[t("providers.providerName"), t("providers.apiFormat"), "Base URL", "API Key", t("providers.model")]} />}
    >
      <div className="min-w-0">
        <div className="flex items-start justify-between gap-4 border-b border-[var(--card-border)] p-5">
          <div>
            <h3 className="text-base font-semibold">{t("providers.customProvider")}</h3>
            <p className="mt-1 text-xs text-[var(--muted)]">{t("providers.customProviderSubtitle")}</p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </div>

        <div className="max-h-[68vh] space-y-5 overflow-y-auto p-5">
          <FieldBlock label={t("providers.providerName")}>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-lg border border-[var(--card-border)] bg-[var(--background)] px-3 py-2 text-sm transition-colors focus:border-[var(--accent)] focus:outline-none"
              placeholder={t("providers.providerNamePlaceholder")}
            />
          </FieldBlock>

          <FieldBlock label={t("providers.apiFormat")}>
            <FormatToggle value={apiFormat} onChange={setApiFormat} />
          </FieldBlock>

          <FieldBlock label="Base URL">
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="w-full rounded-lg border border-[var(--card-border)] bg-[var(--background)] px-3 py-2 font-mono text-sm transition-colors focus:border-[var(--accent)] focus:outline-none"
              placeholder={apiFormat === "anthropic" ? "https://api.anthropic.com/v1/openai" : "https://your-api.com/v1"}
            />
          </FieldBlock>

          <FieldBlock label="API Key">
            <div className="relative">
              <input
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="w-full rounded-lg border border-[var(--card-border)] bg-[var(--background)] px-3 py-2 pr-10 font-mono text-sm transition-colors focus:border-[var(--accent)] focus:outline-none"
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

          <FieldBlock label={t("providers.model")}>
            <div className="flex gap-2">
              <input
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="min-w-0 flex-1 rounded-lg border border-[var(--card-border)] bg-[var(--background)] px-3 py-2 font-mono text-sm transition-colors focus:border-[var(--accent)] focus:outline-none"
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
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
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

          <div className="border-t border-[var(--card-border)] pt-5 md:ml-[140px]">
            <Button
              variant="outline"
              onClick={handleTest}
              disabled={testing || !apiKey || !baseUrl}
              className="w-full"
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
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button
            onClick={handleSave}
            disabled={saving || !name || !baseUrl || !apiKey}
          >
            {saving ? t("common.saving") : t("common.save")}
          </Button>
        </div>
      </div>
    </PanelShell>
  );
}

function ProvidersSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {[0, 1, 2, 3, 4, 5].map((item) => (
        <div key={item} className="min-h-[150px] rounded-xl border border-[var(--card-border)] bg-[var(--card)] p-5">
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
        <div className="grid gap-6 border-b border-[var(--card-border)] pb-6 lg:grid-cols-[1fr_280px]">
          <div>
            <p className="mb-3 text-xs uppercase tracking-[0.18em] text-[var(--accent)]">{t("providers.configured")}</p>
            <h1 className="text-3xl font-semibold tracking-normal">{t("providers.title")}</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[var(--muted-foreground)]">{t("providers.subtitlePrefix")}</p>
          </div>
          <div className="rounded-xl border border-[var(--card-border)] bg-[var(--card)] p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs text-[var(--muted)]">{t("providers.providers")}</span>
              <span className="font-mono text-xs text-[var(--accent)]">{configuredCount}/{totalProviders}</span>
            </div>
            <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-[var(--background)]">
              <div
                className="h-full rounded-full bg-[var(--accent)] transition-[width,opacity] duration-300"
                style={{ width: totalProviders ? `${(configuredCount / totalProviders) * 100}%` : "0%" }}
              />
            </div>
          </div>
        </div>

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
              <div className="empty-state rounded-xl border border-[var(--card-border)] py-12">
                <div className="empty-state-title">{t("providers.providers")}</div>
              </div>
            )}

            <div className="border-l border-[var(--accent)]/40 bg-[var(--card)] px-4 py-3 text-sm text-[var(--muted-foreground)]">
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
