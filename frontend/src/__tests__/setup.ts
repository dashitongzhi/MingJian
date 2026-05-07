import "@testing-library/jest-dom/vitest";
import { beforeEach, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  router: {
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
    push: vi.fn(),
    refresh: vi.fn(),
    replace: vi.fn(),
  },
  setTheme: vi.fn(),
  setLocale: vi.fn(),
  toastError: vi.fn(),
  toggleLocale: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useRouter: () => mocks.router,
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("next-themes", () => ({
  ThemeProvider: ({ children }: { children: unknown }) => children,
  useTheme: () => ({
    resolvedTheme: "light",
    setTheme: mocks.setTheme,
    theme: "light",
  }),
}));

vi.mock("@/contexts/LanguageContext", () => ({
  LanguageProvider: ({ children }: { children: unknown }) => children,
  useTranslation: () => ({
    locale: "zh",
    setLocale: mocks.setLocale,
    t: (key: string) => key,
    toggleLocale: mocks.toggleLocale,
  }),
}));

vi.mock("@/lib/toast", () => ({
  toast: {
    error: mocks.toastError,
  },
}));

vi.stubGlobal("fetch", mocks.fetch);

beforeEach(() => {
  mocks.fetch.mockReset();
  mocks.router.back.mockClear();
  mocks.router.forward.mockClear();
  mocks.router.prefetch.mockClear();
  mocks.router.push.mockClear();
  mocks.router.refresh.mockClear();
  mocks.router.replace.mockClear();
  mocks.setLocale.mockClear();
  mocks.setTheme.mockClear();
  mocks.toastError.mockClear();
  mocks.toggleLocale.mockClear();
});
