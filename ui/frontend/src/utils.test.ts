import { describe, expect, it } from "vitest";
import { formatDate, formatNumber, navItems, percent, queueRows, runOption, stageProgress, statusLabel, statusTone } from "./utils";

describe("review workbench utilities", () => {
  it("formats values and preserves invalid dates for auditability", () => {
    expect(formatNumber(1234)).toBe("1,234");
    expect(formatNumber(undefined)).toBe("0");
    expect(formatDate()).toBe("—");
    expect(formatDate("not-a-date")).toBe("not-a-date");
    expect(statusLabel("grounding_failed")).toBe("Grounding Failed");
  });

  it("maps status tones and percentages", () => {
    expect(statusTone("certified")).toBe("good");
    expect(statusTone("requires_review")).toBe("warn");
    expect(statusTone("grounding_failed")).toBe("bad");
    expect(statusTone("unknown")).toBe("neutral");
    expect(percent(2, 4)).toBe(50);
    expect(percent(1, 0)).toBe(0);
  });

  it("computes queue and stage progress", () => {
    const rows = [
      { requires_review: true, grounding_status: "failed", readiness_status: "failed" },
      { requires_review: false, grounding_status: "certified", readiness_status: "ready" },
    ] as any;
    expect(queueRows(rows, "all")).toHaveLength(2);
    expect(queueRows(rows, "requires_review")).toHaveLength(1);
    expect(queueRows(rows, "grounding_failed")).toHaveLength(1);
    expect(queueRows(rows, "readiness_failed")).toHaveLength(1);
    expect(queueRows(rows, "other")).toHaveLength(2);
    expect(stageProgress([{ status: "completed" }, { status: "missing" }] as any)).toBe(50);
    expect(runOption({ run_id: "run", rule_count: 2 } as any)).toBe("run · 2 rules");
    expect(navItems.length).toBe(8);
  });
});
