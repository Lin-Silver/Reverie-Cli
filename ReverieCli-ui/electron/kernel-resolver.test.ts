import { createHash } from "node:crypto";
import { afterEach, describe, expect, it } from "vitest";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  KERNEL_BRIDGE_PROTOCOL,
  resolveKernelSelection,
  TRUSTED_KERNELS_FILENAME,
} from "./kernel-resolver";
import { kernelExecutableName } from "./runtime-paths";

const roots: string[] = [];
afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true });
});

function fixture(externalContents = "official external kernel") {
  const root = path.join(os.tmpdir(), `reverie-kernel-${process.pid}-${Date.now()}-${roots.length}`);
  roots.push(root);
  const internalDirectory = path.join(root, "internal");
  const externalDirectory = path.join(root, "portable");
  mkdirSync(internalDirectory, { recursive: true });
  mkdirSync(externalDirectory, { recursive: true });
  const name = kernelExecutableName();
  const internalPath = path.join(internalDirectory, name);
  const externalPath = path.join(externalDirectory, name);
  writeFileSync(internalPath, "bundled kernel");
  writeFileSync(externalPath, externalContents);
  return { internalDirectory, externalDirectory, internalPath, externalPath };
}

function writeManifest(internalDirectory: string, contents: string) {
  const digest = createHash("sha256").update(contents).digest("hex");
  writeFileSync(path.join(internalDirectory, TRUSTED_KERNELS_FILENAME), JSON.stringify({
    schema: "reverie.trusted-kernels.v1",
    kernels: [{
      sha256: digest,
      platform: process.platform,
      arch: process.arch,
      version: "2.5.0",
      bridge_protocol: KERNEL_BRIDGE_PROTOCOL,
    }],
  }));
}

describe("trusted kernel selection", () => {
  it("uses the unpacked bundled kernel without hashing or probing a sibling for the GUI", async () => {
    const files = fixture();
    writeManifest(files.internalDirectory, "official external kernel");
    let probes = 0;
    const selected = await resolveKernelSelection({
      internalPath: files.internalPath,
      externalHome: files.externalDirectory,
      preferExternal: false,
      probe: async () => {
        probes += 1;
        return true;
      },
    });
    expect(selected.source).toBe("internal");
    expect(selected.path).toBe(files.internalPath);
    expect(selected.reason).toContain("fast desktop startup");
    expect(probes).toBe(0);
  });

  it("uses a trusted sibling after its compatibility handshake", async () => {
    const files = fixture();
    writeManifest(files.internalDirectory, "official external kernel");
    const selected = await resolveKernelSelection({
      internalPath: files.internalPath,
      externalHome: files.externalDirectory,
      probe: async () => true,
    });
    expect(selected.source).toBe("external");
    expect(selected.path).toBe(files.externalPath);
  });

  it("falls back when the sibling hash is not trusted", async () => {
    const files = fixture("modified kernel");
    writeManifest(files.internalDirectory, "official external kernel");
    const selected = await resolveKernelSelection({
      internalPath: files.internalPath,
      externalHome: files.externalDirectory,
      probe: async () => true,
    });
    expect(selected.source).toBe("internal");
    expect(selected.reason).toContain("allowlist");
  });

  it("falls back when a trusted sibling fails the protocol probe", async () => {
    const files = fixture();
    writeManifest(files.internalDirectory, "official external kernel");
    const selected = await resolveKernelSelection({
      internalPath: files.internalPath,
      externalHome: files.externalDirectory,
      probe: async () => false,
    });
    expect(selected.source).toBe("internal");
    expect(selected.reason).toContain("handshake");
  });
});
