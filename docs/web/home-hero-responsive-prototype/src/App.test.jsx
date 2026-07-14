import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { App } from "./App.jsx";

afterEach(() => {
  cleanup();
  window.HTMLElement.prototype.scrollIntoView.mockClear();
});

describe("home hero interactions", () => {
  it("opens and dismisses the mobile navigation with Escape", async () => {
    const user = userEvent.setup();
    render(<App />);

    const menuButton = screen.getByRole("button", { name: "打开导航菜单" });
    expect(menuButton).toHaveAttribute("aria-expanded", "false");

    await user.click(menuButton);
    expect(menuButton).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("navigation", { name: "移动端导航" })).toBeVisible();

    await user.keyboard("{Escape}");
    expect(menuButton).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("navigation", { name: "移动端导航" })).not.toBeInTheDocument();
  });

  it("shows actionable feedback for login and creation CTAs", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "登录" }));
    expect(screen.getByRole("status")).toHaveTextContent("登录入口已准备好");

    await user.click(screen.getByRole("button", { name: "开始创作" }));
    expect(screen.getByRole("status")).toHaveTextContent("正在为你打开创作工作台");
  });

  it("selects a creation tool and exposes the active state", async () => {
    const user = userEvent.setup();
    render(<App />);

    const tools = screen.getByRole("group", { name: "创作工具" });
    const translation = within(tools).getByRole("button", { name: /视频翻译/ });
    const commentary = within(tools).getByRole("button", { name: /短剧解说/ });

    expect(commentary).toHaveAttribute("aria-pressed", "true");
    expect(translation).toHaveAttribute("aria-pressed", "false");

    await user.click(translation);
    expect(translation).toHaveAttribute("aria-pressed", "true");
    expect(commentary).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByText("视频翻译已选中")).toBeVisible();
  });

  it("toggles the video preview playback state", async () => {
    const user = userEvent.setup();
    render(<App />);

    const playButton = screen.getByRole("button", { name: "播放预览" });
    await user.click(playButton);

    expect(screen.getByRole("button", { name: "暂停预览" })).toBeVisible();
    expect(screen.getByText("正在预览")).toBeVisible();
  });

  it("scrolls navigation and case actions to their real sections", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "产品能力" }));
    await user.click(screen.getByRole("button", { name: "查看案例" }));

    expect(window.HTMLElement.prototype.scrollIntoView).toHaveBeenCalledTimes(2);
  });

  it("keeps the brand home anchor connected to a real page target", () => {
    render(<App />);

    expect(screen.getByRole("link", { name: "影创工坊首页" })).toHaveAttribute("href", "#top");
    expect(document.querySelector("#top")).toBeInTheDocument();
  });

  it("renders the decorative sweep on AI 出片工作台 only", () => {
    render(<App />);

    const title = screen.getByRole("heading", { name: "专为自媒体小白打造的 AI 出片工作台" });
    const shine = title.querySelector('.hero-title-shine[aria-hidden="true"]');
    expect(shine).toBeInTheDocument();
    expect(shine).toHaveTextContent("AI 出片工作台");
    expect(shine).not.toHaveTextContent("专为自媒体小白打造的");
  });

  it("renders explicit depth, mirror and hollow-rail layers around the workbench", () => {
    render(<App />);

    const shell = document.querySelector(".workbench-shell");
    expect(shell.querySelector('.workbench-top-reflection[aria-hidden="true"]')).toBeInTheDocument();
    expect(shell.querySelector('.workbench-depth-frame--near[aria-hidden="true"]')).toBeInTheDocument();
    expect(shell.querySelector('.workbench-depth-frame--far[aria-hidden="true"]')).toBeInTheDocument();
    expect(shell.querySelector('.workbench-void-rail[aria-hidden="true"]')).toBeInTheDocument();
    expect(shell.querySelector('.workbench-side-face[aria-hidden="true"]')).toBeInTheDocument();
    expect(shell.querySelector('.workbench-bottom-face[aria-hidden="true"]')).toBeInTheDocument();
  });
});
