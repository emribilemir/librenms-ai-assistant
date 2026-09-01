import { fireEvent, render, screen } from "@testing-library/react";
import { DeleteThreadDialog } from "./DeleteThreadDialog";
import { RunMetrics } from "./RunMetrics";
import { RunProgress } from "./RunProgress";
import { ThreadDrawer } from "./ThreadDrawer";

test("delete confirmation focuses cancel and cancellation leaves the thread intact", () => {
  const cancel = jest.fn();
  render(<DeleteThreadDialog open threadTitle="Core switch" onCancel={cancel} onConfirm={jest.fn()} />);
  const cancelButton = screen.getByRole("button", { name: "Keep thread" });
  expect(cancelButton).toHaveFocus();
  fireEvent.click(cancelButton);
  expect(cancel).toHaveBeenCalledTimes(1);
});

test("metrics are expandable and expose their accessible disclosure state", () => {
  render(<RunMetrics metrics={{ planner_ms: 8, resolver_ms: null, backend_ms: 12, synthesis_ms: null, time_to_first_token_ms: null, time_to_first_visible_chunk_ms: 20, total_ms: 25 }} />);
  const disclosure = screen.getByRole("button", { name: "Show run metrics" });
  expect(disclosure).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(disclosure);
  expect(disclosure).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText("planner_ms")).toBeVisible();
});

test("narrow drawer uses named native controls with visible focus styling", () => {
  render(<ThreadDrawer open onClose={jest.fn()} onCreate={jest.fn()}><p>Thread list</p></ThreadDrawer>);
  expect(screen.getByRole("button", { name: "Close investigations" })).toBeVisible();
  expect(screen.getByRole("button", { name: "New investigation" })).toBeVisible();
  expect(document.querySelector("[data-focus-visible='true']")).toBeTruthy();
});

test("desktop investigations remain in the accessibility tree when the mobile drawer is closed", () => {
  render(<ThreadDrawer open={false} onClose={jest.fn()} onCreate={jest.fn()}><p>Thread list</p></ThreadDrawer>);
  expect(screen.getByLabelText("Investigations")).not.toHaveAttribute("aria-hidden", "true");
});

test("real pipeline stage updates are announced in a polite live region", () => {
  render(<RunProgress run={{ status: "running", stages: { planner: { status: "completed", durationMs: 8 }, resolver: { status: "running" } } }} />);
  expect(screen.getByText(/Pipeline status: planner completed, resolver running/)).toHaveAttribute("aria-live", "polite");
  expect(screen.getByText("8ms")).toBeVisible();
});
