// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { UserQuestionPanel, type UserInputRequest } from "./UserQuestionPanel";

afterEach(cleanup);
const question: UserInputRequest = { question_id:"q1",question:"选择实现方式？",reason:"test",options:["A","B","C"],custom_answer:true,multiple:false,project_root:"project",session_id:"session",run_id:"run" };

it("waits for explicit selection and submission, and offers a fourth custom answer", async () => {
  const resolve = vi.fn().mockResolvedValue(undefined);
  render(<UserQuestionPanel question={question} resolve={resolve} />);
  expect((screen.getByRole("button",{name:"提交回答"}) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getAllByRole("radio")).toHaveLength(4);
  fireEvent.click(screen.getByLabelText("2. B"));
  expect(resolve).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"提交回答"}));
  await waitFor(() => expect(resolve).toHaveBeenCalledWith("B",false));
});

it("preserves custom newlines, keeps failed answers for retry, and separates cancellation", async () => {
  const resolve = vi.fn().mockRejectedValueOnce(new Error("still pending")).mockResolvedValue(undefined);
  render(<UserQuestionPanel question={question} resolve={resolve} />);
  fireEvent.click(screen.getByLabelText("4. 自定义回答"));
  fireEvent.change(screen.getByRole("textbox"),{target:{value:"我的选项\nsecond line 😀"}});
  fireEvent.click(screen.getByRole("button",{name:"提交回答"}));
  await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("still pending"));
  expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("我的选项\nsecond line 😀");
  expect(resolve).toHaveBeenCalledWith("我的选项\nsecond line 😀",false);
  fireEvent.click(screen.getByRole("button",{name:"取消询问"}));
  await waitFor(() => expect(resolve).toHaveBeenLastCalledWith(undefined,true));
});

it("uses multiselect only when explicitly requested", async () => {
  const resolve = vi.fn().mockResolvedValue(undefined);
  render(<UserQuestionPanel question={{...question,multiple:true}} resolve={resolve} />);
  fireEvent.click(screen.getByLabelText("3. C"));
  fireEvent.click(screen.getByLabelText("1. A"));
  fireEvent.click(screen.getByRole("button",{name:"提交回答"}));
  await waitFor(() => expect(resolve).toHaveBeenCalledWith("A\nC",false));
});

it("restores a question draft after navigating away and remounting", async () => {
  const drafts = new Map();
  const resolve = vi.fn().mockResolvedValue(undefined);
  const first = render(<UserQuestionPanel question={question} drafts={drafts} resolve={resolve} />);
  fireEvent.click(screen.getByLabelText("4. 自定义回答"));
  fireEvent.change(screen.getByRole("textbox"),{target:{value:"retained\n😀"}});
  first.unmount();
  render(<UserQuestionPanel question={question} drafts={drafts} resolve={resolve} />);
  expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("retained\n😀");
  fireEvent.click(screen.getByRole("button",{name:"提交回答"}));
  await waitFor(() => expect(drafts.has(question.question_id)).toBe(false));
  expect(resolve).toHaveBeenCalledWith("retained\n😀",false);
});
