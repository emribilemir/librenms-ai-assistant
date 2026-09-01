import "@testing-library/jest-dom";
import { ReadableStream } from "node:stream/web";
import { TextDecoder, TextEncoder } from "node:util";

Object.assign(global, { ReadableStream, TextDecoder, TextEncoder });
