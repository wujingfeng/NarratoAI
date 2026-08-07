import { describe, it, expect, beforeEach } from "vitest";
import { render, fireEvent } from "@testing-library/react";
import { ScriptSegmentCard } from "../../src/components/chat/ScriptSegmentCard";
import { useProjectStore } from "../../src/features/project/store";

describe("ScriptSegmentCard", () => {
  beforeEach(() => {
    useProjectStore.getState().reset();
    useProjectStore.setState({
      script: {
        segments: [
          { id: "seg-1", start: 0, end: 12, text: "原文案 1", tone: "悬疑" },
          { id: "seg-2", start: 12, end: 24, text: "原文案 2", tone: "悬疑" },
        ],
      },
    });
  });

  it("渲染所有 segment", () => {
    const { container } = render(<ScriptSegmentCard segments={useProjectStore.getState().script.segments} />);
    expect(container.querySelectorAll(".script-card__row")).toHaveLength(2);
    expect(container.textContent).toContain("原文案 1");
    expect(container.textContent).toContain("原文案 2");
  });

  it("点击'改'进入编辑态", () => {
    const { container, getAllByText } = render(<ScriptSegmentCard segments={useProjectStore.getState().script.segments} />);
    fireEvent.click(getAllByText("改")[0]!);
    const input = container.querySelector(".script-card__input") as HTMLInputElement;
    expect(input).toBeInTheDocument();
    expect(input.value).toBe("原文案 1");
  });

  it("编辑后保存写入 store", () => {
    const { container, getAllByText } = render(<ScriptSegmentCard segments={useProjectStore.getState().script.segments} />);
    fireEvent.click(getAllByText("改")[0]!);
    const input = container.querySelector(".script-card__input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "新文案" } });
    fireEvent.click(getAllByText("保存")[0]!);
    const segs = useProjectStore.getState().script.segments;
    expect(segs[0]?.text).toBe("新文案");
  });

  it("编辑后取消不写 store", () => {
    const { container, getAllByText } = render(<ScriptSegmentCard segments={useProjectStore.getState().script.segments} />);
    fireEvent.click(getAllByText("改")[0]!);
    const input = container.querySelector(".script-card__input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "丢弃" } });
    fireEvent.click(getAllByText("取消")[0]!);
    const segs = useProjectStore.getState().script.segments;
    expect(segs[0]?.text).toBe("原文案 1");
  });
});
