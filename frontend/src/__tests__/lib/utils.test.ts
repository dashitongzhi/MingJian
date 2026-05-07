import { describe, expect, it } from "vitest";
import { cn } from "@/lib/utils";

describe("cn", () => {
  it("combines class names", () => {
    expect(cn("flex", "items-center", "gap-2")).toBe("flex items-center gap-2");
  });

  it("resolves conflicting tailwind classes with the last value", () => {
    expect(cn("px-2 py-1", "px-4")).toBe("py-1 px-4");
    expect(cn("text-sm", "text-lg")).toBe("text-lg");
  });

  it("includes conditional classes when conditions are truthy", () => {
    expect(cn("base", { active: true, disabled: false })).toBe("base active");
  });

  it("filters falsy values", () => {
    expect(cn("base", null, undefined, false, "", "visible")).toBe("base visible");
  });
});
