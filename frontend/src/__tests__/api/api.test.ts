import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetch_ } from "@/lib/api";

const fetchMock = vi.mocked(fetch);

describe("fetch_", () => {
  beforeEach(() => {
    fetchMock.mockReset();
  });

  it("returns parsed JSON for successful responses", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ status: "ok" }),
    } as Response);

    await expect(fetch_<{ status: string }>("/health")).resolves.toEqual({ status: "ok" });
  });

  it("throws an error with the status code for HTTP errors", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
      text: async () => "server exploded",
    } as Response);

    await expect(fetch_("/broken")).rejects.toThrow("API 500: server exploded");
  });

  it("calls fetch with the API URL and JSON headers", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: "123" }),
    } as Response);

    await fetch_("/items", {
      body: JSON.stringify({ name: "New item" }),
      method: "POST",
    });

    expect(fetchMock).toHaveBeenCalledWith("/api/items", {
      body: JSON.stringify({ name: "New item" }),
      headers: { "Content-Type": "application/json" },
      method: "POST",
    });
  });

  it("returns the parsed body from non-GET requests", async () => {
    fetchMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: "created" }),
    } as Response);

    await expect(fetch_<{ id: string }>("/items", { method: "POST" })).resolves.toEqual({
      id: "created",
    });
  });
});
