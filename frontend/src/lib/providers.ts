import useSWR from "swr";
import { fetch_ } from "@/lib/api";

// ── Types ───────────────────────────────────────────────────────────────────

export interface ProviderPreset {
  id: string;
  name: string;
  base_url: string;
  api_format: string;
  models: string[];
  placeholder: string;
  website: string;
  color: string;
}

export interface ConfiguredProvider extends ProviderPreset {
  configured: boolean;
  api_key_set: boolean;
  active_model: string;
  enabled: boolean;
  custom?: boolean;
}

export interface ProviderConfig {
  provider_id: string;
  name?: string;
  api_key: string;
  base_url?: string;
  model?: string;
  api_format?: string;
  enabled?: boolean;
}

export interface ProviderTestResult {
  ok: boolean;
  latency_ms: number;
  models_available: string[];
  error?: string;
}

// ── Hooks ───────────────────────────────────────────────────────────────────

export function useProviderPresets() {
  return useSWR<ProviderPreset[]>("provider-presets", () =>
    fetch_<ProviderPreset[]>("/admin/providers/presets")
  );
}

export function useConfiguredProviders() {
  return useSWR<ConfiguredProvider[]>("configured-providers", () =>
    fetch_<ConfiguredProvider[]>("/admin/providers"), {
    refreshInterval: 10000,
  });
}

// ── Actions ─────────────────────────────────────────────────────────────────

export async function saveProvider(config: ProviderConfig): Promise<{ status: string }> {
  return fetch_< { status: string }>("/admin/providers", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export async function deleteProvider(providerId: string): Promise<{ status: string }> {
  return fetch_<{ status: string }>(`/admin/providers/${providerId}`, {
    method: "DELETE",
  });
}

export async function testProvider(data: {
  base_url: string;
  api_key: string;
  api_format?: string;
  model?: string;
}): Promise<ProviderTestResult> {
  return fetch_<ProviderTestResult>("/admin/providers/test", {
    method: "POST",
    body: JSON.stringify(data),
  });
}
