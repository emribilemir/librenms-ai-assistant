import { readPluginIdentity } from "./identity";

test("reads non-secret plugin identity from the root data attribute before legacy global config", () => {
  const root = document.createElement("div");
  root.dataset.aiAssistantConfig = JSON.stringify({ token: "signed-token", apiBase: "/ai-api/v1" });
  expect(readPluginIdentity({ __LIBRENMS_AI_ASSISTANT__: { token: "legacy" } }, root)).toEqual({ token: "signed-token", apiBase: "/ai-api/v1" });
});

test("rejects malformed root config without throwing or manufacturing an identity", () => {
  const root = document.createElement("div");
  root.dataset.aiAssistantConfig = "not-json";
  expect(readPluginIdentity({}, root)).toEqual({});
});
