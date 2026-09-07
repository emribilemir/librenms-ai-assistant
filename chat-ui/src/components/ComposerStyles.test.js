import fs from "node:fs";
import path from "node:path";

const css = fs.readFileSync(path.join(__dirname, "AssistantThread.module.css"), "utf8");
const inspectorCss = fs.readFileSync(path.join(__dirname, "ProcessingInspector.module.css"), "utf8");

test("disabled send action is not styled as a white primary circle", () => {
  expect(css).toMatch(/\.primaryButton:disabled\s*\{[^}]*background:\s*#[0-9a-f]{6}/i);
  expect(css).toMatch(/\.primaryButton:not\(\.stopButton\) svg\s*\{[^}]*color:\s*#20252a[^}]*display:\s*block[^}]*stroke:\s*#20252a/i);
  expect(css).toMatch(/\.primaryButton:not\(\.stopButton\) svg path\s*\{[^}]*stroke:\s*#20252a\s*!important/i);
  expect(css).toMatch(/\.primaryButton:disabled:not\(\.stopButton\) svg\s*\{[^}]*stroke:\s*#737e87/i);
});

test("composer owns one accessible focus treatment without a visible textarea ring", () => {
  expect(css).toMatch(/\.composer:focus-within\s*\{/);
  expect(css).toMatch(/\.composer \.input:focus-visible\s*\{[^}]*outline:\s*2px solid transparent/i);
  expect(css).not.toMatch(/\.input\s*\{[^}]*outline:\s*none/i);
});

test("suggestion surface communicates clickability with restrained underline, hover, and keyboard focus", () => {
  expect(css).toMatch(/\.suggestion\s*\{[^}]*cursor:\s*pointer/i);
  expect(css).toMatch(/\.suggestionTitle\s*\{[^}]*text-decoration-line:\s*underline[^}]*text-decoration-color:\s*rgba\(/i);
  expect(css).toMatch(/\.suggestion:hover \.suggestionTitle\s*\{[^}]*color:[^}]*text-decoration-color:/i);
  expect(css).toMatch(/\.suggestion:focus-visible\s*\{[^}]*outline:\s*2px solid/i);
});

test("collapsed inspector is a compact continuation with no reserved height", () => {
  expect(inspectorCss).toMatch(/\.root\s*\{[^}]*margin-top:\s*(?:[0-8])px/i);
  expect(inspectorCss).not.toMatch(/\.root\s*\{[^}]*min-height/i);
});
