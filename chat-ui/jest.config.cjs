module.exports = {
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/src/test/setup.js"],
  moduleNameMapper: { "\\.module\\.css$": "<rootDir>/src/test/styleMock.js" },
  testPathIgnorePatterns: ["<rootDir>/e2e/"],
  // assistant-ui's Markdown renderer is a deliberately ESM-only dependency
  // graph; transform it in Jest just as Vite does in the shipped bundle.
  transformIgnorePatterns: [],
};
