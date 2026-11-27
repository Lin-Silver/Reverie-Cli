import { net, type IncomingMessage, type WebContents } from "electron";
import { once } from "node:events";
import { createWriteStream } from "node:fs";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { browserUrl } from "./browser-policy";

/** Stream the reviewed link in the guest's Chromium Session. The Rust host owns the private staging file. */
export async function downloadLink(contents: WebContents, url: string, staged: string, signal: AbortSignal) {
  signal.throwIfAborted();
  const request = net.request({url, session:contents.session, origin:new URL(contents.getURL()).origin,
    credentials:"include", redirect:"manual"});
  const controller = new AbortController();
  const cancelled = AbortSignal.any([signal,controller.signal]);
  const stop = () => request.abort();
  const closed = () => controller.abort();
  cancelled.addEventListener("abort",stop,{once:true});
  contents.once("destroyed",closed);
  request.on("error",error => controller.abort(error));
  request.on("redirect",(_status,method,next) => {
    if (method === "GET" && browserUrl(next) && next !== "about:blank") request.followRedirect();
    else controller.abort(new Error("Unsupported browser download redirect."));
  });
  try {
    const ready = once(request,"response",{signal:cancelled});
    request.end();
    const [response] = await ready as [IncomingMessage];
    if (response.statusCode < 200 || response.statusCode >= 300) throw new Error("Download HTTP status "+response.statusCode);
    if (!(response instanceof Readable)) throw new Error("Chromium returned an unreadable download.");
    await pipeline(response,createWriteStream(staged,{flags:"wx",mode:0o600}),{signal:cancelled});
  } catch (error) {
    request.abort(); throw error;
  } finally {
    cancelled.removeEventListener("abort",stop);
    contents.off("destroyed",closed);
  }
}
