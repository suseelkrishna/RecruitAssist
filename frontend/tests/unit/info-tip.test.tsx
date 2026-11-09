/**
 * InfoTip and the Quality page's ReportCard: the (i) button is named for its topic, opens on
 * focus and on click, closes with Escape, and a report that is not produced yet shows its reason.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { HeadingWithInfo } from "@/components/HeadingWithInfo";
import { InfoTip } from "@/components/InfoTip";
import { ReportCard } from "@/components/ReportCard";

describe("InfoTip", () => {
  it("has an About label and opens on keyboard focus", async () => {
    const user = userEvent.setup();
    render(<InfoTip title="Mutation check">Planted bugs the tests should catch.</InfoTip>);
    expect(screen.getByRole("button", { name: "About Mutation check" })).toBeTruthy();
    expect(screen.queryByText("Planted bugs the tests should catch.")).toBeNull();
    await user.tab();
    expect(await screen.findByText("Planted bugs the tests should catch.")).toBeTruthy();
  });

  it("opens on click and closes with Escape", async () => {
    const user = userEvent.setup();
    render(<InfoTip title="Access matrix">Every function as every user.</InfoTip>);
    await user.click(screen.getByRole("button", { name: "About Access matrix" }));
    expect(await screen.findByText("Every function as every user.")).toBeTruthy();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByText("Every function as every user.")).toBeNull());
  });
});

describe("InfoTip by keyboard and touch", () => {
  it("opens with Enter, closes with Escape, and returns focus to the button", async () => {
    const user = userEvent.setup();
    render(<InfoTip title="Live checks">Checked when this page loads.</InfoTip>);
    const button = screen.getByRole("button", { name: "About Live checks" });
    button.focus();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByText("Checked when this page loads.")).toBeNull());
    await user.keyboard("{Enter}");
    expect(await screen.findByText("Checked when this page loads.")).toBeTruthy();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByText("Checked when this page loads.")).toBeNull());
    expect(document.activeElement).toBe(button);
  });

  // A real touch tap is checked in the Playwright smoke test; jsdom does not turn touches into clicks.
  it("opens on a press and closes on a press outside", async () => {
    const user = userEvent.setup();
    render(
      <div>
        <p>Outside</p>
        <InfoTip title="Funnel">Applications that reached each stage.</InfoTip>
      </div>,
    );
    await user.click(screen.getByRole("button", { name: "About Funnel" }));
    expect(await screen.findByText("Applications that reached each stage.")).toBeTruthy();
    await user.click(screen.getByText("Outside"));
    await waitFor(() => expect(screen.queryByText("Applications that reached each stage.")).toBeNull());
  });
});

describe("HeadingWithInfo", () => {
  it("puts the InfoTip right after the heading, named for it", () => {
    render(<HeadingWithInfo as="h1" title="Tasks" info="Overdue and pending work, most overdue first." />);
    const heading = screen.getByRole("heading", { level: 1, name: "Tasks" });
    expect(heading.nextElementSibling?.querySelector("button")?.getAttribute("aria-label") ?? heading.nextElementSibling?.textContent).toContain("About Tasks");
  });

  it("renders the heading alone without info", () => {
    render(<HeadingWithInfo title="Integrations" />);
    expect(screen.getByRole("heading", { level: 2, name: "Integrations" })).toBeTruthy();
    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("ReportCard", () => {
  it("shows Not available and the reason when the report is missing", async () => {
    const user = userEvent.setup();
    render(
      <ReportCard title="Test results" value={null} reason="Run python evals/quality_snapshot.py from backend/ to produce this.">
        <p>should not render</p>
      </ReportCard>,
    );
    expect(screen.getByText("Not available")).toBeTruthy();
    expect(screen.queryByText("should not render")).toBeNull();
    await user.click(screen.getByRole("button", { name: "About Test results" }));
    expect(await screen.findByText("Run python evals/quality_snapshot.py from backend/ to produce this.")).toBeTruthy();
  });

  it("shows the report when it is there", () => {
    render(
      <ReportCard title="Test results" value={{ passed: 5 }} reason={undefined}>
        <p>5 passed</p>
      </ReportCard>,
    );
    expect(screen.getByText("5 passed")).toBeTruthy();
    expect(screen.queryByText("Not available")).toBeNull();
  });
});
