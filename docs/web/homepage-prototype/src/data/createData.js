import { FilmSlate, Scissors, Translate } from "@phosphor-icons/react";

export const creationTypes = [
  { id: "narration", title: "短剧解说", titleKey: "create.types.narration.title", description: "自动梳理剧情并生成解说视频", descriptionKey: "create.types.narration.description", icon: FilmSlate, tone: "violet", maxVideos: 5 },
  { id: "translation", title: "视频翻译", titleKey: "create.types.translation.title", description: "为视频生成多语言字幕与配音", descriptionKey: "create.types.translation.description", icon: Translate, tone: "cyan", maxVideos: 1 },
  { id: "remix", title: "短剧混剪", titleKey: "create.types.remix.title", description: "组合多个素材片段，快速生成混剪", descriptionKey: "create.types.remix.description", icon: Scissors, tone: "orange", maxVideos: 10 },
];

// 保留空导出以兼容旧调用方；创建页不再使用任何默认素材。
export const initialCreateVideos = [];
