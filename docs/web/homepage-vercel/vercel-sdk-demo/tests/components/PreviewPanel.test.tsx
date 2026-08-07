import { describe, it, expect, beforeEach } from "vitest";
import { render } from "@testing-library/react";
import { PreviewPanel } from "../../src/components/preview/PreviewPanel";
import { VideoPlayer } from "../../src/components/preview/VideoPlayer";
import { RenderProgress } from "../../src/components/preview/RenderProgress";
import { ArtifactList } from "../../src/components/preview/ArtifactList";
import { useProjectStore } from "../../src/features/project/store";

describe("PreviewPanel", () => {
  beforeEach(() => {
    useProjectStore.getState().reset();
  });

  it("stage=idle 时只显示 VideoPlayer", () => {
    useProjectStore.setState({ render: { ...useProjectStore.getState().render, stage: "idle" } });
    const { container } = render(<PreviewPanel />);
    expect(container.querySelector(".player")).toBeInTheDocument();
    expect(container.querySelector(".render-progress")).toBeNull();
    expect(container.querySelector(".artifact-list")).toBeNull();
  });

  it("stage=tts 时同时显示 VideoPlayer + RenderProgress", () => {
    useProjectStore.setState({ render: { ...useProjectStore.getState().render, stage: "tts", progress: 0.25 } });
    const { container } = render(<PreviewPanel />);
    expect(container.querySelector(".player")).toBeInTheDocument();
    expect(container.querySelector(".render-progress")).toBeInTheDocument();
  });

  it("stage=subtitle 时显示渲染进度", () => {
    useProjectStore.setState({ render: { ...useProjectStore.getState().render, stage: "subtitle", progress: 0.5 } });
    const { container } = render(<PreviewPanel />);
    expect(container.querySelector(".render-progress")).toBeInTheDocument();
  });

  it("stage=encoding 时显示渲染进度", () => {
    useProjectStore.setState({ render: { ...useProjectStore.getState().render, stage: "encoding", progress: 0.95 } });
    const { container } = render(<PreviewPanel />);
    expect(container.querySelector(".render-progress")).toBeInTheDocument();
  });

  it("stage=done 时显示 RenderProgress + ArtifactList", () => {
    useProjectStore.setState({
      render: {
        ...useProjectStore.getState().render,
        stage: "done",
        progress: 1,
        artifacts: [
          { kind: "draft", url: "/api/x", label: "剪映草稿" },
        ],
      },
    });
    const { container } = render(<PreviewPanel />);
    expect(container.querySelector(".render-progress")).toBeInTheDocument();
    expect(container.querySelector(".artifact-list")).toBeInTheDocument();
  });
});

describe("VideoPlayer", () => {
  beforeEach(() => {
    useProjectStore.getState().reset();
  });

  it("无视频时显示空态", () => {
    const { container } = render(<VideoPlayer />);
    expect(container.querySelector(".player--empty")).toBeInTheDocument();
  });

  it("有 artifactUrl 时显示渲染产出", () => {
    useProjectStore.setState({
      render: { ...useProjectStore.getState().render, artifactUrl: "/api/x.zip" },
    });
    const { container } = render(<VideoPlayer />);
    expect(container.querySelector(".player__video")).toBeInTheDocument();
    expect(container.textContent).toContain("渲染产出");
  });

  it("有 videos 时显示视频", () => {
    useProjectStore.setState({
      videos: [{ id: "v1", name: "episode-1.mp4", durationSec: 120, thumbnailUrl: "/x" }],
    });
    const { container } = render(<VideoPlayer />);
    expect(container.querySelector(".player__video")).toBeInTheDocument();
    expect(container.textContent).toContain("episode-1.mp4");
  });
});

describe("RenderProgress", () => {
  beforeEach(() => {
    useProjectStore.getState().reset();
  });

  it("stage=tts 时显示'配音合成' + 百分比", () => {
    useProjectStore.setState({ render: { ...useProjectStore.getState().render, stage: "tts", progress: 0.25 } });
    const { container } = render(<RenderProgress />);
    expect(container.textContent).toContain("配音合成");
    expect(container.textContent).toContain("25%");
  });

  it("stage=done 显示'完成' + 100%", () => {
    useProjectStore.setState({ render: { ...useProjectStore.getState().render, stage: "done", progress: 1 } });
    const { container } = render(<RenderProgress />);
    expect(container.textContent).toContain("完成");
    expect(container.textContent).toContain("100%");
  });

  it("stage=未知值时显示原始字符串", () => {
    useProjectStore.setState({ render: { ...useProjectStore.getState().render, stage: "mystery" as never, progress: 0.1 } });
    const { container } = render(<RenderProgress />);
    expect(container.textContent).toContain("mystery");
  });
});

describe("ArtifactList", () => {
  beforeEach(() => {
    useProjectStore.getState().reset();
  });

  it("无 artifact 时显示空态", () => {
    const { container } = render(<ArtifactList />);
    expect(container.querySelector(".artifact-list--empty")).toBeInTheDocument();
  });

  it("有 artifact 时渲染列表", () => {
    useProjectStore.setState({
      render: {
        ...useProjectStore.getState().render,
        artifacts: [
          { kind: "draft", url: "/api/x.zip", label: "剪映草稿 zip" },
        ],
      },
    });
    const { container } = render(<ArtifactList />);
    expect(container.querySelectorAll(".artifact-list__row")).toHaveLength(1);
    expect(container.textContent).toContain("剪映草稿 zip");
  });
});
