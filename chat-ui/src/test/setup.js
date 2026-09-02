import "@testing-library/jest-dom";
import { ReadableStream, TransformStream, WritableStream } from "node:stream/web";
import { TextDecoder, TextEncoder } from "node:util";

Object.assign(global, {
  ReadableStream,
  TransformStream,
  WritableStream,
  TextDecoder,
  TextEncoder,
});

if (!global.Response) global.Response = class Response {};
if (!global.Request) global.Request = class Request {};
if (!global.Headers) global.Headers = class Headers {};
if (!global.ResizeObserver) {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
