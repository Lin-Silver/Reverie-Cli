// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FileChanges } from "./FileChanges";

afterEach(() => { cleanup(); vi.useRealTimers(); });
const change = { path: "src/sample.py", operation: "modify", diff: "@@ -1 +1 @@\n-old\n+new", additions: 1, deletions: 1, unavailable: false, truncated: false, timestamp: "" };

describe("file change previews", () => {
  it("clears an old session error when no session is selected", async () => {
    window.reverie = { request: vi.fn().mockRejectedValue(new Error("Old session failed")) } as unknown as typeof window.reverie;
    const view = render(<FileChanges sessionId="one" running={false} revision={0} />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    view.rerender(<FileChanges sessionId="" running={false} revision={0} />);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("暂无文件改动")).toBeTruthy();
  });

  it("renders the backend diff, supports collapsing files and refresh", async () => {
    const request = vi.fn().mockResolvedValue({ changes: [change] });
    window.reverie = { request } as unknown as typeof window.reverie;
    const { container } = render(<FileChanges sessionId="one" running={false} revision={0} />);
    expect(await screen.findByText("+new")).toBeTruthy();
    expect(container.querySelector(".added")?.textContent).toContain("+new");
    expect(container.querySelector(".removed")?.textContent).toContain("-old");
    expect(screen.getByLabelText("+1 −1")).toBeTruthy();
    expect(container.querySelector("details")?.open).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "刷新改动" }));
    await waitFor(() => expect(request).toHaveBeenCalledTimes(2));
  });

  it("discards stale responses when switching sessions", async () => {
    let finish: (value: unknown) => void = () => {};
    const request = vi.fn().mockImplementation((_action, payload) => payload.sessionId === "one"
      ? new Promise((resolve) => { finish = resolve; })
      : Promise.resolve({ changes: [] }));
    window.reverie = { request } as unknown as typeof window.reverie;
    const view = render(<FileChanges sessionId="one" running={false} revision={0} />);
    view.rerender(<FileChanges sessionId="two" running={false} revision={0} />);
    await act(async () => { finish({ changes: [change] }); });
    expect(screen.queryByText("+new")).toBeNull();
    expect(screen.getByText("暂无文件改动")).toBeTruthy();
  });

  it("refreshes while a model turn is running and stops after completion", async () => {
    vi.useFakeTimers();
    const request = vi.fn().mockResolvedValue({ changes: [] });
    window.reverie = { request } as unknown as typeof window.reverie;
    const view = render(<FileChanges sessionId="one" running={true} revision={0} />);
    await act(async () => {});
    request.mockResolvedValue({ changes: [change] });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(screen.getByText("+new")).toBeTruthy();
    view.rerender(<FileChanges sessionId="one" running={false} revision={0} />);
    await act(async () => {});
    const count = request.mock.calls.length;
    await act(async () => { await vi.advanceTimersByTimeAsync(3000); });
    expect(request).toHaveBeenCalledTimes(count);
  });
});
