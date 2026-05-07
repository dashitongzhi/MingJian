import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import ErrorBoundary from "@/components/ErrorBoundary";
import { toast } from "@/lib/toast";

function BrokenChild() {
  throw new Error("render failed");
}

describe("ErrorBoundary", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders children normally when there is no error", () => {
    render(
      <ErrorBoundary>
        <div>Healthy content</div>
      </ErrorBoundary>,
    );

    expect(screen.getByText("Healthy content")).toBeInTheDocument();
  });

  it("catches render errors and shows the fallback UI", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(
      <ErrorBoundary>
        <BrokenChild />
      </ErrorBoundary>,
    );

    expect(screen.getByText("页面渲染出错")).toBeInTheDocument();
    expect(screen.getByText("render failed")).toBeInTheDocument();
  });

  it("reports caught errors through toast.error", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);

    render(
      <ErrorBoundary>
        <BrokenChild />
      </ErrorBoundary>,
    );

    expect(toast.error).toHaveBeenCalledWith("发生错误");
  });

  it("resets error state when retry is clicked", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    let shouldThrow = true;

    function RecoverableChild() {
      if (shouldThrow) throw new Error("temporary failure");
      return <div>Recovered content</div>;
    }

    render(
      <ErrorBoundary>
        <RecoverableChild />
      </ErrorBoundary>,
    );

    shouldThrow = false;
    fireEvent.click(screen.getByRole("button", { name: "重试" }));

    expect(screen.getByText("Recovered content")).toBeInTheDocument();
    expect(screen.queryByText("页面渲染出错")).not.toBeInTheDocument();
  });
});
