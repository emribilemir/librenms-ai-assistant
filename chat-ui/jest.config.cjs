module.exports = {
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/src/test/setup.js"],
  moduleNameMapper: { "\\.module\\.css$": "<rootDir>/src/test/styleMock.js" },
  testPathIgnorePatterns: ["<rootDir>/e2e/"],
  transformIgnorePatterns: [
    "/node_modules/(?!(@assistant-ui|assistant-stream|assistant-cloud|safe-content-frame|nanoid)/)",
  ],
};
