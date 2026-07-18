import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { createReadStream, existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { kernelExecutableName } from "./runtime-paths";

export const TRUSTED_KERNELS_FILENAME = "reverie-trusted-kernels.json";
export const KERNEL_INFO_SCHEMA = "reverie.kernel.v1";
export const KERNEL_BRIDGE_PROTOCOL = "sdk-bridge.v1";

export type TrustedKernel = {
  sha256: string;
  platform: string;
  arch: string;
  version: string;
  bridge_protocol: string;
};

export type KernelSelection = {
  path: string;
  source: "internal" | "external";
  reason: string;
};

type ResolverOptions = {
  internalPath: string;
  externalHome: string;
  manifestPath?: string;
  platform?: string;
  arch?: string;
  preferExternal?: boolean;
  probe?: (executable: string, expected: TrustedKernel) => Promise<boolean>;
};

export async function sha256File(filePath: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const hash = createHash("sha256");
    const stream = createReadStream(filePath);
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("error", reject);
    stream.on("end", () => resolve(hash.digest("hex")));
  });
}

async function readTrustedKernels(manifestPath: string): Promise<TrustedKernel[]> {
  try {
    const payload = JSON.parse(await readFile(manifestPath, "utf8")) as {
      schema?: unknown;
      kernels?: unknown;
    };
    if (payload.schema !== "reverie.trusted-kernels.v1" || !Array.isArray(payload.kernels)) return [];
    return payload.kernels.filter((entry): entry is TrustedKernel => {
      if (!entry || typeof entry !== "object") return false;
      const item = entry as Record<string, unknown>;
      return typeof item.sha256 === "string"
        && /^[a-f0-9]{64}$/i.test(item.sha256)
        && typeof item.platform === "string"
        && typeof item.arch === "string"
        && typeof item.version === "string"
        && item.bridge_protocol === KERNEL_BRIDGE_PROTOCOL;
    });
  } catch {
    return [];
  }
}

export async function probeKernelCompatibility(
  executable: string,
  expected: TrustedKernel,
): Promise<boolean> {
  return new Promise((resolve) => {
    execFile(
      executable,
      ["--kernel-info"],
      { timeout: 60_000, windowsHide: true, encoding: "utf8", maxBuffer: 64 * 1024 },
      (error, stdout) => {
        if (error) {
          resolve(false);
          return;
        }
        try {
          const info = JSON.parse(stdout.trim()) as Record<string, unknown>;
          resolve(
            info.schema === KERNEL_INFO_SCHEMA
            && info.bridge_protocol === expected.bridge_protocol
            && info.version === expected.version
            && info.platform === expected.platform
            && info.arch === expected.arch,
          );
        } catch {
          resolve(false);
        }
      },
    );
  });
}

export async function resolveKernelSelection(options: ResolverOptions): Promise<KernelSelection> {
  const platform = options.platform ?? process.platform;
  const arch = options.arch ?? process.arch;
  const internalPath = path.resolve(options.internalPath);
  if (!existsSync(internalPath)) throw new Error(`Bundled Reverie core not found: ${internalPath}`);
  if (options.preferExternal === false) {
    return {
      path: internalPath,
      source: "internal",
      reason: "bundled kernel preferred for fast desktop startup",
    };
  }

  const externalPath = path.resolve(options.externalHome, kernelExecutableName(platform));
  if (externalPath.toLowerCase() === internalPath.toLowerCase()) {
    return { path: internalPath, source: "internal", reason: "bundled kernel" };
  }
  if (!existsSync(externalPath)) {
    return { path: internalPath, source: "internal", reason: "no sibling kernel" };
  }

  const manifestPath = options.manifestPath
    ?? path.join(path.dirname(internalPath), TRUSTED_KERNELS_FILENAME);
  const trusted = await readTrustedKernels(manifestPath);
  const digest = await sha256File(externalPath).catch(() => "");
  const expected = trusted.find((entry) =>
    entry.platform === platform
    && entry.arch === arch
    && entry.sha256.toLowerCase() === digest.toLowerCase(),
  );
  if (!expected) {
    return { path: internalPath, source: "internal", reason: "sibling kernel is not in the build allowlist" };
  }

  const probe = options.probe ?? probeKernelCompatibility;
  if (!(await probe(externalPath, expected))) {
    return { path: internalPath, source: "internal", reason: "sibling kernel failed the compatibility handshake" };
  }
  return { path: externalPath, source: "external", reason: "trusted sibling kernel" };
}
