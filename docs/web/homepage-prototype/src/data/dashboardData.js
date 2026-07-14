import {
  BookOpenText,
  ClockCounterClockwise,
  Coins,
  FilmSlate,
  House,
  MagicWand,
  Scissors,
  Sparkle,
  Translate,
  UserCircle,
} from "@phosphor-icons/react";

const navItem = (id, label, icon, group, to = null) => ({
  id,
  label,
  icon,
  to,
  unavailableMessage: to ? null : `${label}功能建设中`,
  group,
});

export const dashboardNavItems = [
  navItem("overview", "概览", House, "main", "/dashboard"),
  navItem("projects", "我的项目", ClockCounterClockwise, "main"),
  navItem("narration", "短剧解说", FilmSlate, "tools"),
  navItem("translation", "视频翻译", Translate, "tools"),
  navItem("remix", "短剧混剪", Scissors, "tools"),
  navItem("credits", "创作点", Coins, "account"),
  navItem("account", "账户中心", UserCircle, "account"),
];

export const dashboardTools = [
  {
    id: "narration",
    title: "短剧解说",
    description: "智能识别剧情，高效生成解说成片",
    tone: "violet",
    icon: FilmSlate,
    unavailableMessage: "短剧解说功能建设中",
  },
  {
    id: "translation",
    title: "视频翻译",
    description: "多语言字幕与配音一站式处理",
    tone: "cyan",
    icon: Translate,
    unavailableMessage: "视频翻译功能建设中",
  },
  {
    id: "remix",
    title: "短剧混剪",
    description: "自动提取高光片段，快速完成混剪",
    tone: "orange",
    icon: Scissors,
    unavailableMessage: "短剧混剪功能建设中",
  },
];

export const recentProjects = [
  { id: "narration-01", title: "霸总短剧解说 01", tool: "短剧解说", status: "complete", statusLabel: "已完成", progress: null, credits: 120, image: "/assets/short-drama-thumb.webp" },
  { id: "remix-city", title: "都市逆袭 · 混剪", tool: "短剧混剪", status: "processing", statusLabel: "处理中 66%", progress: 66, credits: 80, image: "/assets/film-action-thumb.webp" },
  { id: "translation-mystery", title: "悬疑短剧翻译", tool: "视频翻译", status: "draft", statusLabel: "草稿", progress: null, credits: 150, image: "/assets/documentary-thumb.webp" },
];

export const dashboardCredits = { balance: 1280, monthlyUsed: 240 };

export const inspirations = [
  {
    id: "storytelling",
    title: "解说节奏指南",
    description: "掌握悬念、转折与高潮的叙事密度",
    image: "/assets/short-drama-thumb.webp",
    icon: BookOpenText,
    unavailableMessage: "解说节奏指南功能建设中",
  },
  {
    id: "creative-remix",
    title: "热门混剪灵感",
    description: "从近期热门题材中找到创作方向",
    image: "/assets/film-action-thumb.webp",
    icon: Sparkle,
    unavailableMessage: "热门混剪灵感功能建设中",
  },
];

export const dashboardPrimaryAction = {
  label: "新建创作",
  icon: MagicWand,
  unavailableMessage: "新建创作功能建设中",
};
