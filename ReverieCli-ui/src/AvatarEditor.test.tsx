// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AvatarEditor, UserAvatar, avatarCrop } from "./AvatarEditor";
import { readFileSync } from "node:fs";

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

describe("avatar crop", () => {
  it("allows uploaded image previews in the packaged renderer policy", () => {
    const html = readFileSync("index.html", "utf8");
    expect(html.match(/img-src[^;]+/)?.[0].split(/\s+/)).toContain("blob:");
    expect(html).toContain("script-src 'self';");
  });
  it("crops the center and clamps movement to real image bounds", () => {
    expect(avatarCrop(600, 300, 1, 0, 0)).toMatchObject({ sx: 150, sy: 0, size: 300 });
    expect(avatarCrop(600, 300, 1, 10000, 0)).toMatchObject({ sx: 0, sy: 0, size: 300 });
    expect(avatarCrop(300, 600, 2, 0, -10000)).toMatchObject({ sx: 75, sy: 450, size: 150 });
  });

  it("shows a saved photo or Unicode initial", () => {
    const { container, rerender } = render(<UserAvatar name="小王" url="" />);
    expect(container.textContent).toBe("小");
    rerender(<UserAvatar name="小王" url="data:image/png;base64,YQ==" />);
    expect(container.querySelector("img")?.getAttribute("src")).toContain("data:image/png");
  });

  it("rejects unsupported files without changing the saved avatar", async () => {
    const save = vi.fn();
    render(<AvatarEditor name="王" url="" save={save} />);
    fireEvent.change(screen.getByLabelText("选择头像图片"), { target: { files: [new File(["svg"], "avatar.svg", { type: "image/svg+xml" })] } });
    await screen.findByRole("alert");
    expect(save).not.toHaveBeenCalled();
  });

  it("saves only the selected crop and lets cancellation retain the old photo", async () => {
    const revoke = vi.fn();
    vi.stubGlobal("URL", { createObjectURL: () => "blob:avatar", revokeObjectURL: revoke });
    vi.stubGlobal("Image", class {
      width = 600; height = 300; onload?: () => void;
      private source = "";
      set src(value: string) { this.source = value; queueMicrotask(() => this.onload?.()); }
      get src() { return this.source; }
    });
    const originalModal = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, "showModal");
    Object.defineProperty(HTMLDialogElement.prototype, "showModal", { configurable: true, value: function (this: HTMLDialogElement) { this.open = true; } });
    const drawImage = vi.fn();
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({ drawImage } as unknown as CanvasRenderingContext2D);
    vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockReturnValue("data:image/png;base64,YQ==");
    const save = vi.fn();
    render(<AvatarEditor name="王" url="" save={save} />);
    const file = new File(["photo"], "avatar.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("选择头像图片"), { target: { files: [file] } });
    await screen.findByRole("dialog");
    fireEvent.change(screen.getByLabelText("水平位置"), { target: { value: 120 } });
    fireEvent.click(screen.getByRole("button", { name: "保存头像" }));
    expect(drawImage).toHaveBeenCalledWith(expect.anything(), 0, 0, 300, 300, 0, 0, 256, 256);
    expect(save).toHaveBeenCalledWith("data:image/png;base64,YQ==");
    fireEvent.change(screen.getByLabelText("选择头像图片"), { target: { files: [file] } });
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() => expect(revoke).toHaveBeenCalledTimes(2));
    expect(save).toHaveBeenCalledTimes(1);
    if (originalModal) Object.defineProperty(HTMLDialogElement.prototype, "showModal", originalModal);
    else Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
    vi.unstubAllGlobals();
  });
});
