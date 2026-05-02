"use client";
import { useState, useCallback } from "react";
import {
  useConfiguredProviders,
  saveProvider,
  deleteProvider,
  testProvider,
  type ConfiguredProvider,
  type ProviderTestResult,
} from "@/lib/providers";
import { useTranslation } from "@/contexts/LanguageContext";

// ── Icons (inline SVG to avoid external deps) ──────────────────────────────

function CheckIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function XIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

function LoaderIcon({ className = "" }: { className?: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className} style={{ animation: "spin 1s linear infinite" }}>
      <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
  );
}

function EyeIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" /><circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
      <line x1="1" y1="1" x2="23" y2="23" />
    </svg>
  );
}

function TestTubeIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14.5 2v17.5c0 1.4-1.1 2.5-2.5 2.5h0c-1.4 0-2.5-1.1-2.5-2.5V2" />
      <path d="M8.5 2h7" /><path d="M14.5 16h-5" />
    </svg>
  );
}

function ExternalLinkIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" /><line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  );
}

// ── Provider Card ───────────────────────────────────────────────────────────

function ProviderCard({
  provider,
  onConfigure,
}: {
  provider: ConfiguredProvider;
  onConfigure: () => void;
}) {
  const { t } = useTranslation();
  const isCustom = provider.custom;
  return (
    <div
      onClick={onConfigure}
      className="relative overflow-hidden rounded-xl border border-[var(--card-border)] bg-[var(--card)] p-5 cursor-pointer transition-all duration-200 hover:border-[var(--accent)] hover:shadow-lg hover:shadow-[var(--accent)]/5 group"
    >
      {/* Color accent bar */}
      <div
        className="absolute top-0 left-0 right-0 h-1 opacity-80"
        style={{ background: provider.color || "#666" }}
      />

      <div className="flex items-start justify-between mt-1">
        <div className="flex items-center gap-3">
          {/* Provider icon */}
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center text-white text-sm font-bold shadow-md"
            style={{ background: provider.color || "#666" }}
          >
            {provider.name.charAt(0)}
          </div>
          <div>
            <div className="font-medium text-sm">{provider.name}</div>
            <div className="text-xs text-[var(--muted)] mt-0.5 truncate max-w-[180px]">
              {provider.base_url}
            </div>
          </div>
        </div>

        {/* Status badge */}
        <div className="flex items-center gap-1.5">
          {provider.api_key_set ? (
            <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              {t("providers.configuredBadge")}
            </span>
          ) : (
            <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-zinc-500/15 text-zinc-400">
              <span className="w-1.5 h-1.5 rounded-full bg-zinc-500" />
              {t("providers.notConfiguredBadge")}
            </span>
          )}
        </div>
      </div>

      {/* Model info */}
      {provider.active_model && (
        <div className="mt-3 text-xs text-[var(--muted)]">
          <span className="text-[var(--foreground)] font-mono bg-[var(--background)] px-1.5 py-0.5 rounded">
            {provider.active_model}
          </span>
        </div>
      )}

      {/* Edit hint */}
      <div className="absolute bottom-3 right-4 text-xs text-[var(--muted)] opacity-0 group-hover:opacity-100 transition-opacity">
        {t("providers.editHint")} →
      </div>
    </div>
  );
}

// ── Config Panel ────────────────────────────────────────────────────────────

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
  const [fetchedModels, setFetchedModels] = useState<string[]>(provider.models || []);

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
  }, [provider.id, apiKey, baseUrl, model, apiFormat, onSaved, onClose]);

  const handleDelete = useCallback(async () => {
    if (!confirm(`${t("providers.deleteConfirmPrefix")} ${provider.name}?`)) return;
    await deleteProvider(provider.id);
    onSaved();
    onClose();
  }, [provider.id, provider.name, onSaved, onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-[var(--card)] border border-[var(--card-border)] rounded-2xl w-full max-w-lg mx-4 shadow-2xl overflow-hidden animate-fadeIn"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-[var(--card-border)]">
          <div className="flex items-center gap-3">
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-sm font-bold"
              style={{ background: provider.color || "#666" }}
            >
              {provider.name.charAt(0)}
            </div>
            <div>
              <h3 className="font-semibold text-base">{provider.name}</h3>
              <p className="text-xs text-[var(--muted)]">{provider.api_format === "anthropic" ? "Anthropic Format" : "OpenAI Format"}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-[var(--muted)] hover:text-[var(--foreground)] transition-colors p-1">
            <XIcon />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4 max-h-[60vh] overflow-y-auto">
          {/* API Format */}
          <div>
            <label className="text-xs font-medium text-[var(--muted)] uppercase tracking-wider">{t("providers.apiFormat")}</label>
            <div className="flex gap-2 mt-1.5">
              {["openai", "anthropic"].map((fmt) => (
                <button
                  key={fmt}
                  onClick={() => setApiFormat(fmt)}
                  className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                    apiFormat === fmt
                      ? "bg-[var(--accent)] text-white"
                      : "bg-[var(--background)] text-[var(--muted)] hover:text-[var(--foreground)]"
                  }`}
                >
                  {fmt === "openai" ? t("providers.openaiCompatible") : t("providers.anthropicNative")}
                </button>
              ))}
            </div>
          </div>

          {/* Base URL */}
          <div>
            <label className="text-xs font-medium text-[var(--muted)] uppercase tracking-wider">Base URL</label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="mt-1.5 w-full px-3 py-2 bg-[var(--background)] border border-[var(--card-border)] rounded-lg text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors"
              placeholder="https://api.openai.com/v1"
            />
          </div>

          {/* API Key */}
          <div>
            <label className="text-xs font-medium text-[var(--muted)] uppercase tracking-wider">API Key</label>
            <div className="relative mt-1.5">
              <input
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="w-full px-3 py-2 pr-10 bg-[var(--background)] border border-[var(--card-border)] rounded-lg text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors"
                placeholder={provider.placeholder || t("providers.apiKeyPlaceholder")}
                autoComplete="off"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute inset-y-0 right-0 flex items-center pr-3 text-[var(--muted)] hover:text-[var(--foreground)]"
              >
                {showKey ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </div>
            {provider.website && (
              <a
                href={provider.website}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-xs text-[var(--accent)] mt-1.5 hover:underline"
              >
                {t("providers.getApiKey")} <ExternalLinkIcon />
              </a>
            )}
          </div>

          {/* Model */}
          <div>
            <label className="text-xs font-medium text-[var(--muted)] uppercase tracking-wider">{t("providers.model")}</label>
            <div className="flex gap-1.5 mt-1.5">
              <input
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="flex-1 px-3 py-2 bg-[var(--background)] border border-[var(--card-border)] rounded-lg text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors"
                placeholder={t("providers.chooseModelPlaceholder")}
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
                  className="px-2 py-2 bg-[var(--background)] border border-[var(--card-border)] rounded-lg text-sm focus:outline-none focus:border-[var(--accent)]"
                >
                  <option value="">▼</option>
                  {fetchedModels.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              )}
            </div>
          </div>

          {/* Test button */}
          <button
            onClick={handleTest}
            disabled={testing || (!apiKey && !provider.api_key_set)}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium bg-[var(--background)] border border-[var(--card-border)] hover:border-[var(--accent)] disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            {testing ? (
              <><LoaderIcon className="animate-spin" /> {t("providers.testing")}</>
            ) : (
              <><TestTubeIcon /> {t("providers.testConnection")}</>
            )}
          </button>

          {/* Test result */}
          {testResult && (
            <div
              className={`p-3 rounded-lg text-sm ${
                testResult.ok
                  ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-400"
                  : "bg-red-500/10 border border-red-500/20 text-red-400"
              }`}
            >
              {testResult.ok ? (
                <div className="flex items-center gap-2">
                  <CheckIcon />
                  <span>{t("providers.connectionSuccess")}! {t("providers.latency")} {testResult.latency_ms}ms</span>
                  {testResult.models_available.length > 0 && (
                    <span className="text-xs opacity-70">({testResult.models_available.length} {t("providers.modelsAvailable")})</span>
                  )}
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <XIcon />
                  <span>{testResult.error || t("providers.connectionFailed")}</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-5 border-t border-[var(--card-border)]">
          <button
            onClick={handleDelete}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm text-red-400 hover:bg-red-500/10 transition-colors"
          >
            <TrashIcon /> {t("common.delete")}
          </button>
          <div className="flex gap-2">
            <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-[var(--muted)] hover:text-[var(--foreground)] transition-colors">
              {t("common.cancel")}
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-5 py-2 rounded-lg text-sm font-medium bg-[var(--accent)] text-white hover:opacity-90 disabled:opacity-40 transition-all"
            >
              {saving ? t("common.saving") : t("common.save")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Custom Provider Card ────────────────────────────────────────────────────

function AddCustomCard({ onClick }: { onClick: () => void }) {
  const { t } = useTranslation();
  return (
    <div
      onClick={onClick}
      className="relative overflow-hidden rounded-xl border-2 border-dashed border-[var(--card-border)] p-5 cursor-pointer transition-all duration-200 hover:border-[var(--accent)] hover:bg-[var(--accent)]/5 group flex flex-col items-center justify-center min-h-[140px]"
    >
      <div className="w-10 h-10 rounded-full bg-[var(--background)] border border-[var(--card-border)] flex items-center justify-center text-[var(--muted)] group-hover:text-[var(--accent)] group-hover:border-[var(--accent)] transition-colors text-xl">
        +
      </div>
      <div className="mt-2 text-sm font-medium text-[var(--muted)] group-hover:text-[var(--accent)] transition-colors">
        {t("providers.customProvider")}
      </div>
      <div className="text-xs text-[var(--muted)] opacity-60 mt-0.5">
        {t("providers.customProviderDescription")}
      </div>
    </div>
  );
}

// ── Custom Config Panel ─────────────────────────────────────────────────────

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
  }, [name, baseUrl, apiKey, model, apiFormat, onSaved, onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="bg-[var(--card)] border border-[var(--card-border)] rounded-2xl w-full max-w-lg mx-4 shadow-2xl overflow-hidden animate-fadeIn"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-[var(--card-border)]">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-[var(--background)] border border-dashed border-[var(--accent)] text-[var(--accent)] text-lg">
              +
            </div>
            <div>
              <h3 className="font-semibold text-base">{t("providers.customProvider")}</h3>
              <p className="text-xs text-[var(--muted)]">{t("providers.customProviderSubtitle")}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-[var(--muted)] hover:text-[var(--foreground)] transition-colors p-1">
            <XIcon />
          </button>
        </div>

        {/* Body */}
        <div className="p-5 space-y-4 max-h-[60vh] overflow-y-auto">
          {/* Name */}
          <div>
            <label className="text-xs font-medium text-[var(--muted)] uppercase tracking-wider">{t("providers.providerName")}</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1.5 w-full px-3 py-2 bg-[var(--background)] border border-[var(--card-border)] rounded-lg text-sm focus:outline-none focus:border-[var(--accent)] transition-colors"
              placeholder={t("providers.providerNamePlaceholder")}
            />
          </div>

          {/* API Format */}
          <div>
            <label className="text-xs font-medium text-[var(--muted)] uppercase tracking-wider">{t("providers.apiFormat")}</label>
            <div className="flex gap-2 mt-1.5">
              {["openai", "anthropic"].map((fmt) => (
                <button
                  key={fmt}
                  onClick={() => setApiFormat(fmt)}
                  className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
                    apiFormat === fmt
                      ? "bg-[var(--accent)] text-white"
                      : "bg-[var(--background)] text-[var(--muted)] hover:text-[var(--foreground)]"
                  }`}
                >
                  {fmt === "openai" ? t("providers.openaiCompatible") : t("providers.anthropicNative")}
                </button>
              ))}
            </div>
          </div>

          {/* Base URL */}
          <div>
            <label className="text-xs font-medium text-[var(--muted)] uppercase tracking-wider">Base URL</label>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              className="mt-1.5 w-full px-3 py-2 bg-[var(--background)] border border-[var(--card-border)] rounded-lg text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors"
              placeholder={apiFormat === "anthropic" ? "https://api.anthropic.com/v1/openai" : "https://your-api.com/v1"}
            />
          </div>

          {/* API Key */}
          <div>
            <label className="text-xs font-medium text-[var(--muted)] uppercase tracking-wider">API Key</label>
            <div className="relative mt-1.5">
              <input
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                className="w-full px-3 py-2 pr-10 bg-[var(--background)] border border-[var(--card-border)] rounded-lg text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors"
                placeholder="sk-... / your-api-key"
                autoComplete="off"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute inset-y-0 right-0 flex items-center pr-3 text-[var(--muted)] hover:text-[var(--foreground)]"
              >
                {showKey ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </div>
          </div>

          {/* Model */}
          <div>
            <label className="text-xs font-medium text-[var(--muted)] uppercase tracking-wider">{t("providers.model")}</label>
            <div className="flex gap-1.5 mt-1.5">
              <input
                type="text"
                value={model}
                onChange={(e) => setModel(e.target.value)}
                className="flex-1 px-3 py-2 bg-[var(--background)] border border-[var(--card-border)] rounded-lg text-sm font-mono focus:outline-none focus:border-[var(--accent)] transition-colors"
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
                  className="px-2 py-2 bg-[var(--background)] border border-[var(--card-border)] rounded-lg text-sm focus:outline-none focus:border-[var(--accent)]"
                >
                  <option value="">▼</option>
                  {fetchedModels.map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              )}
            </div>
          </div>

          {/* Test button */}
          <button
            onClick={handleTest}
            disabled={testing || !apiKey || !baseUrl}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium bg-[var(--background)] border border-[var(--card-border)] hover:border-[var(--accent)] disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            {testing ? (
              <><LoaderIcon className="animate-spin" /> {t("providers.testing")}</>
            ) : (
              <><TestTubeIcon /> {t("providers.testConnection")}</>
            )}
          </button>

          {/* Test result */}
          {testResult && (
            <div
              className={`p-3 rounded-lg text-sm ${
                testResult.ok
                  ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-400"
                  : "bg-red-500/10 border border-red-500/20 text-red-400"
              }`}
            >
              {testResult.ok ? (
                <div className="flex items-center gap-2">
                  <CheckIcon />
                  <span>{t("providers.connectionSuccess")}! {t("providers.latency")} {testResult.latency_ms}ms</span>
                  {testResult.models_available.length > 0 && (
                    <span className="text-xs opacity-70">({testResult.models_available.length} {t("providers.modelsAvailable")})</span>
                  )}
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <XIcon />
                  <span>{testResult.error || t("providers.connectionFailed")}</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 p-5 border-t border-[var(--card-border)]">
          <button onClick={onClose} className="px-4 py-2 rounded-lg text-sm text-[var(--muted)] hover:text-[var(--foreground)] transition-colors">
            {t("common.cancel")}
          </button>
          <button
            onClick={handleSave}
            disabled={saving || !name || !baseUrl || !apiKey}
            className="px-5 py-2 rounded-lg text-sm font-medium bg-[var(--accent)] text-white hover:opacity-90 disabled:opacity-40 transition-all"
          >
            {saving ? t("common.saving") : t("common.save")}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────────

export default function ProvidersPage() {
  const { t } = useTranslation();
  const { data: providers, mutate } = useConfiguredProviders();
  const [configuring, setConfiguring] = useState<ConfiguredProvider | null>(null);
  const [showCustomPanel, setShowCustomPanel] = useState(false);

  const configuredCount = providers?.filter((p) => p.api_key_set).length || 0;

  return (
    <>
      <style jsx global>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>

      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">{t("providers.title")}</h1>
            <p className="text-[var(--muted)] mt-1">
              {t("providers.subtitlePrefix")} · {t("providers.configured")} {configuredCount}/{providers?.length || 0} {t("providers.providers")}
            </p>
          </div>
        </div>

        {/* Provider grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {providers?.map((provider) => (
            <ProviderCard
              key={provider.id}
              provider={provider}
              onConfigure={() => setConfiguring(provider)}
            />
          ))}
          <AddCustomCard onClick={() => setShowCustomPanel(true)} />
        </div>

        {/* Info banner */}
        <div className="p-4 rounded-xl bg-[var(--accent)]/5 border border-[var(--accent)]/10 text-sm text-[var(--muted)]">
          <strong className="text-[var(--foreground)]">💡 {t("providers.hintTitle")}</strong>
          {t("providers.hint")}
        </div>
      </div>

      {/* Config panel overlay */}
      {configuring && (
        <ConfigPanel
          provider={configuring}
          onClose={() => setConfiguring(null)}
          onSaved={() => mutate()}
        />
      )}

      {/* Custom provider panel */}
      {showCustomPanel && (
        <CustomConfigPanel
          onClose={() => setShowCustomPanel(false)}
          onSaved={() => mutate()}
        />
      )}
    </>
  );
}
