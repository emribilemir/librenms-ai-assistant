import fs from "node:fs";
import path from "node:path";

const css = fs.readFileSync(path.join(__dirname, "AssistantThread.module.css"), "utf8");
const inspectorCss = fs.readFileSync(path.join(__dirname, "ProcessingInspector.module.css"), "utf8");
const demoCss = fs.readFileSync(path.join(__dirname, "DemoControls.module.css"), "utf8");

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

test("suggestion surface communicates clickability without default or hover underlines", () => {
  expect(css).toMatch(/\.suggestion\s*\{[^}]*cursor:\s*pointer/i);
  expect(css).not.toMatch(/\.suggestionTitle\s*\{[^}]*text-decoration(?:-line)?:\s*underline/i);
  expect(css).not.toMatch(/\.suggestion:hover \.suggestionTitle\s*\{[^}]*text-decoration(?:-line)?:\s*underline/i);
  expect(css).toMatch(/\.suggestion:focus-visible\s*\{[^}]*outline:\s*2px solid/i);
});

test("demo follow-up is a whole clickable surface with an aligned trailing icon and no underline", () => {
  expect(demoCss).toMatch(/\.question button\s*\{[^}]*display:\s*grid[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\) auto/i);
  expect(demoCss).toMatch(/\.question button:focus-visible\s*\{[^}]*outline:\s*2px solid/i);
  expect(demoCss).not.toMatch(/\.question button:hover[^}]*text-decoration:\s*underline/i);
});

test("collapsed inspector is a compact continuation with no reserved height", () => {
  expect(inspectorCss).toMatch(/\.root\s*\{[^}]*margin-top:\s*(?:[0-8])px/i);
  expect(inspectorCss).not.toMatch(/\.root\s*\{[^}]*min-height/i);
});
