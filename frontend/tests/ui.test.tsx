import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, it, expect, vi, afterEach } from "vitest";
import { Badge, Pager, ErrorNotice, Confirm, Json } from "../src/ui";
import { api, ApiError, outcome, percentage } from "../src/api";
import { latencyPoints, intervalText } from "../src/Charts";
import { filterEvidence, FaultStudio } from "../src/research";
import { Customers } from "../src/operations";
import type { Dataset, Report, Session } from "../src/types";
const measured = JSON.parse(
  readFileSync(
    resolve("../research/phase-4/results/61dd8e8-final/dataset.json"),
    "utf8",
  ),
) as Dataset;
const report = JSON.parse(
  readFileSync(resolve("tests/fixtures/phase4-report.json"), "utf8"),
) as Report;
const catalog = JSON.parse(
  readFileSync(resolve("../research/phase-4/config/scenarios.v1.json"), "utf8"),
);
function wrapper(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>{node}</QueryClientProvider>,
  );
}
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});
describe("truthful outcomes and accessible controls", () => {
  it("keeps reported completion distinct from independently verified absence", () => {
    render(
      <>
        <Badge value="COMPLETED_REPORTED" />
        <Badge value="VERIFIED_ABSENT" />
        <Badge value="INCONCLUSIVE" />
      </>,
    );
    expect(screen.getByText("Completed reported")).toHaveClass("reported");
    expect(screen.getByText("Verified absent · scoped")).toHaveClass("good");
    expect(screen.getByText("Inconclusive")).toHaveClass("warn");
    expect(outcome("unexpected")[1]).toBe("muted");
    expect(percentage(null)).toBe("Undefined");
  });
  it("bounds pagination at both ends", () => {
    const change = vi.fn();
    const r = render(
      <Pager page={0} total={21} limit={20} onChange={change} />,
    );
    expect(screen.getByText("Previous")).toBeDisabled();
    fireEvent.click(screen.getByText("Next"));
    expect(change).toHaveBeenCalledWith(1);
    r.rerender(<Pager page={1} total={21} limit={20} onChange={change} />);
    expect(screen.getByText("Next")).toBeDisabled();
  });
  it("announces connection errors and offers a safe read retry", () => {
    const retry = vi.fn();
    render(
      <ErrorNotice
        error={new ApiError(503, "Backend unavailable")}
        retry={retry}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Backend unavailable");
    fireEvent.click(screen.getByText(/Try read again/));
    expect(retry).toHaveBeenCalledOnce();
  });
  it("requires opening the destructive confirmation before executing", () => {
    const action = vi.fn();
    HTMLDialogElement.prototype.close = vi.fn(function (
      this: HTMLDialogElement,
    ) {
      this.open = false;
    });
    HTMLDialogElement.prototype.showModal = vi.fn(function (
      this: HTMLDialogElement,
    ) {
      this.open = true;
    });
    render(
      <Confirm
        label="Request deletion"
        title="Delete synthetic data?"
        description="Permanent fences remain."
        onConfirm={action}
      />,
    );
    expect(action).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText("Request deletion"));
    expect(screen.getByRole("dialog")).toBeVisible();
    fireEvent.click(screen.getByText("Confirm request deletion"));
    expect(action).toHaveBeenCalledOnce();
  });
  it("renders evidence as escaped text, never HTML", () => {
    render(
      <Json
        value={{
          observation: "<script>unsafe()</script>",
          digest: "a".repeat(64),
        }}
      />,
    );
    expect(screen.getByText(/unsafe/)).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
  });
});
describe("real recorded result transformations", () => {
  it("derives positive and abstention denominators from the saved rows", () => {
    const phases = measured.trials.flatMap((t) => t.phases);
    const positives = phases.filter((p) => p.oracle.state === "RESIDUAL");
    expect(
      measured.summary.methods.eraseproof.full_positive_detection_yield
        .denominator,
    ).toBe(positives.length);
    expect(measured.summary.methods.eraseproof.coverage.denominator).toBe(
      phases.filter((p) => ["RESIDUAL", "ABSENT"].includes(p.oracle.state))
        .length,
    );
    expect(intervalText(measured.summary.methods.eraseproof.recall)).toMatch(
      /%$/,
    );
  });
  it("extracts observed latency samples without substituting summary values", () => {
    const points = latencyPoints(measured);
    for (const p of points)
      expect(p.values).toHaveLength(
        measured.trials
          .flatMap((t) => t.phases)
          .filter((row) => row.methods[p.name]?.elapsed_seconds > 0).length,
      );
  });
  it("filters actual evidence by target, recorded outcome and digest", () => {
    const target = report.evidence[0].target;
    const result = String(report.evidence[0].body.result);
    const filtered = filterEvidence(
      report.evidence,
      target,
      result,
      report.evidence[0].digest.slice(0, 16),
    );
    expect(filtered).toHaveLength(1);
    expect(filtered[0].digest).toBe(report.evidence[0].digest);
    expect(filterEvidence(report.evidence, "nonexistent", "", "")).toEqual([]);
  });
});
describe("role-dependent component controls", () => {
  const session: Session = {
    role: "readonly",
    csrf: "test-csrf",
    research_enabled: true,
  };
  it("does not offer a creation form to read-only users", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json({ items: [], total: 0, limit: 20, offset: 0 }),
      ),
    );
    wrapper(
      <Customers
        session={session}
        navigate={vi.fn()}
        params={new URLSearchParams()}
      />,
    );
    expect(screen.getByText(/Read-only session/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Create customer" }),
    ).toBeNull();
    await waitFor(() =>
      expect(
        screen.getByText("No matching synthetic customers"),
      ).toBeInTheDocument(),
    );
  });
  it("disables research launch for observers even if the host is enabled", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        Response.json(
          url.includes("scenarios")
            ? { version: catalog.version, items: catalog.scenarios }
            : { items: [] },
        ),
      ),
    );
    wrapper(
      <FaultStudio
        session={session}
        navigate={vi.fn()}
        params={new URLSearchParams()}
      />,
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Run isolated scenario/ }),
      ).toBeDisabled(),
    );
  });
});
describe("typed API transport", () => {
  it("preserves strict HTTP failures and does not mistake them for success", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        Response.json(
          { detail: "Read-only users cannot mutate data" },
          { status: 403 },
        ),
      ),
    );
    await expect(
      api("/live/customer/v1/customers", { method: "POST" }),
    ).rejects.toMatchObject({ status: 403 });
  });
  it("rejects HTML and unexpected primitive responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response("<html>gateway failure</html>", { status: 502 }),
      ),
    );
    await expect(api("/health")).rejects.toThrow(/unreadable/);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json("not an object")),
    );
    await expect(api("/health")).rejects.toThrow(/response shape/);
  });
  it("sends only a same-origin cookie session, never a browser API key", async () => {
    const fetch = vi.fn<typeof globalThis.fetch>(async () =>
      Response.json({ items: [] }),
    );
    vi.stubGlobal("fetch", fetch);
    await api("/health");
    const options = fetch.mock.calls[0]?.[1] as RequestInit | undefined;
    expect(options?.credentials).toBe("same-origin");
    expect(JSON.stringify(options?.headers)).not.toMatch(
      /Inspection-Token|Deletion-Token|Verification-Token/,
    );
  });
});

it("aborts a stalled API request and preserves an unknown outcome", async () => {
  vi.useFakeTimers();
  vi.stubGlobal(
    "fetch",
    vi.fn(
      (_url: string, options: RequestInit) =>
        new Promise((_resolve, reject) => {
          options.signal?.addEventListener("abort", () =>
            reject(new DOMException("Aborted", "AbortError")),
          );
        }),
    ),
  );
  const assertion = expect(api("/health")).rejects.toMatchObject({
    status: 504,
  });
  await vi.advanceTimersByTimeAsync(20001);
  await assertion;
});
