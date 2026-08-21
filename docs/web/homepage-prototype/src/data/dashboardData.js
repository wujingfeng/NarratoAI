import {
  ClockCounterClockwise,
  Coins,
  ImageSquare,
  FilmSlate,
  House,
  MagicWand,
  MicrophoneStage,
  Scissors,
  Translate,
  VideoCamera,
  UserCircle,
} from "@phosphor-icons/react";

const navItem = (id, icon, group, to = null) => ({
  id,
  labelKey: `dashboard.nav.${id}`,
  icon,
  to,
  unavailableMessageKey: to ? null : `dashboard.unavailable.${id}`,
  group,
});

export const dashboardNavItems = [
  navItem("overview", House, "main", "/dashboard"),
  navItem("create", MagicWand, "main", "/dashboard/create"),
  navItem("projects", ClockCounterClockwise, "main", "/dashboard/projects"),
  navItem("narration", FilmSlate, "tools", "/dashboard/narration/settings"),
  navItem("translation", Translate, "tools", "/dashboard/video-translation/upload"),
  navItem("remix", Scissors, "tools"),
  navItem("credits", Coins, "account"),
  navItem("account", UserCircle, "account"),
];

export const dashboardTools = [
  {
    id: "image",
    titleKey: "dashboard.featuredTools.image.title",
    descriptionKey: "dashboard.featuredTools.image.description",
    tone: "rose",
    icon: ImageSquare,
    unavailableMessageKey: "dashboard.unavailable.aiImage",
  },
  {
    id: "video",
    titleKey: "dashboard.featuredTools.video.title",
    descriptionKey: "dashboard.featuredTools.video.description",
    tone: "violet",
    icon: VideoCamera,
    to: "/dashboard/ai-video",
    unavailableMessageKey: "dashboard.unavailable.aiVideo",
  },
  {
    id: "voice",
    titleKey: "dashboard.featuredTools.voice.title",
    descriptionKey: "dashboard.featuredTools.voice.description",
    tone: "cyan",
    icon: MicrophoneStage,
    unavailableMessageKey: "dashboard.unavailable.aiVoice",
  },
];

export const dashboardCreationEntries = [
  { id: "narration", titleKey: "dashboard.creationEntries.narration.title", descriptionKey: "dashboard.creationEntries.narration.description", icon: FilmSlate, to: "/dashboard/narration/settings", tone: "violet" },
  { id: "translation", titleKey: "dashboard.creationEntries.translation.title", descriptionKey: "dashboard.creationEntries.translation.description", icon: Translate, to: "/dashboard/video-translation/upload", tone: "cyan" },
  { id: "remix", titleKey: "dashboard.creationEntries.remix.title", descriptionKey: "dashboard.creationEntries.remix.description", icon: Scissors, unavailableMessageKey: "dashboard.unavailable.remix", tone: "orange" },
];

export const dashboardPromotions = [
  { id: "accelerator", eyebrow: "限时创作加速计划", title: "本周升级，额外获得 20% 创作点", action: "立即查看", unavailableMessage: "活动详情功能建设中" },
  { id: "new-tools", eyebrow: "AI 创作能力上新", title: "三项新工具，让灵感更快成为作品", action: "去体验", unavailableMessage: "工具详情功能建设中" },
];

export const dashboardCases = [
  { id: "case-reversal", titleKey: "dashboard.cases.reversal.title", metaKey: "dashboard.cases.reversal.meta", video: "https://inchatcdn.beiyinapp.com/inchat/watermarks/meta/20260717/161528_a755036523c0e80a332e95ba206d7ff8.mp4", tone: "violet", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-action", titleKey: "dashboard.cases.action.title", metaKey: "dashboard.cases.action.meta", video: "https://inchatcdn.beiyinapp.com/inchat/watermarks/meta/20260717/140303_b6038a10ed49ce7df09b794e63f25147.mp4", tone: "orange", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-romance", titleKey: "dashboard.cases.romance.title", metaKey: "dashboard.cases.romance.meta", video: "https://inchatcdn.beiyinapp.com/inchat/watermarks/meta/20260716/233042_4f82d6da30287dd34ea1019effce4e68.mp4", tone: "rose", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-urban", titleKey: "dashboard.cases.urban.title", metaKey: "dashboard.cases.urban.meta", video: "https://gamecdn.beiyinapp.com/2025-12-31/87c1e9447144b3619d41aeffb29cd071.mp4", tone: "cyan", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-documentary", titleKey: "dashboard.cases.documentary.title", metaKey: "dashboard.cases.documentary.meta", video: "https://gamecdn.beiyinapp.com/2025-12-31/475446af01094c3191640626bc0444a2.mp4", tone: "gold", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-suspense", titleKey: "dashboard.cases.suspense.title", metaKey: "dashboard.cases.suspense.meta", video: "https://gamecdn.beiyinapp.com/2025-12-31/99d5e9af84da0ad9ec3104f768d0af4d.mp4", tone: "violet", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-reversal-02", titleKey: "dashboard.cases.reversal.title", metaKey: "dashboard.cases.reversal.meta", video: "https://inchatcdn.beiyinapp.com/inchat/watermarks/video/20260716/232908_ac811427ca1af51fd0d4aaca9d8c5b2a.mp4", tone: "violet", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-action-02", titleKey: "dashboard.cases.action.title", metaKey: "dashboard.cases.action.meta", video: "https://inchatcdn.beiyinapp.com/inchat/watermarks/video/20260716/193342_67f20ddc3c77c30628dc4417d870f244.mp4", tone: "orange", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-romance-02", titleKey: "dashboard.cases.romance.title", metaKey: "dashboard.cases.romance.meta", video: "https://inchatcdn.beiyinapp.com/inchat/watermarks/meta/20260716/152742_5c1f86d41153eebd25c34a7c8c95c639.mp4", tone: "rose", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-urban-02", titleKey: "dashboard.cases.urban.title", metaKey: "dashboard.cases.urban.meta", video: "https://gamecdn.beiyinapp.com/2026-02-03/0f7bc1b35238841b1292bc3604acdcf2.mp4", tone: "cyan", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-documentary-02", titleKey: "dashboard.cases.documentary.title", metaKey: "dashboard.cases.documentary.meta", video: "https://inchatcdn.beiyinapp.com/inchat/watermarks/meta/20260716/135425_dd2968b4fcd0f8d35b36b48b2feb4f3f.mp4", tone: "gold", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-suspense-02", titleKey: "dashboard.cases.suspense.title", metaKey: "dashboard.cases.suspense.meta", video: "https://gamecdn.beiyinapp.com/2026-02-03/a279e385cf6ae3911b27ebc22f3f5cb7.mp4", tone: "violet", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-reversal-03", titleKey: "dashboard.cases.reversal.title", metaKey: "dashboard.cases.reversal.meta", video: "https://inchatcdn.beiyinapp.com/inchat/watermarks/meta/20260716/135105_7e38d981e2cf93c295a2c952e4007d70.mp4", tone: "violet", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-action-03", titleKey: "dashboard.cases.action.title", metaKey: "dashboard.cases.action.meta", video: "https://inchatcdn.beiyinapp.com/inchat/watermarks/video/20260716/134848_6462724077f601f0eb4b3fc9a7c283e5.mp4", tone: "orange", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-romance-03", titleKey: "dashboard.cases.romance.title", metaKey: "dashboard.cases.romance.meta", video: "https://gamecdn.beiyinapp.com/2026-02-03/d604f5533d8b4bb0560230c5b4930d8.mp4", tone: "rose", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-urban-03", titleKey: "dashboard.cases.urban.title", metaKey: "dashboard.cases.urban.meta", video: "https://inchatcdn.beiyinapp.com/inchat/watermarks/meta/20260716/134614_63525f52721690aa54ed972c8f08e71e.mp4", tone: "cyan", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-documentary-03", titleKey: "dashboard.cases.documentary.title", metaKey: "dashboard.cases.documentary.meta", video: "https://inchatcdn.beiyinapp.com/inchat/watermarks/meta/20260716/125546_9543216ce64ecad2bdd79aae2c1a8db5.mp4", tone: "gold", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-suspense-03", titleKey: "dashboard.cases.suspense.title", metaKey: "dashboard.cases.suspense.meta", video: "https://inchatcdn.beiyinapp.com/inchat/watermarks/meta/20260716/100435_488962515e1cf4ab8ce921f252043626.mp4", tone: "violet", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-reversal-04", titleKey: "dashboard.cases.reversal.title", metaKey: "dashboard.cases.reversal.meta", video: "https://gamecdn.beiyinapp.com/2026-02-10/86ff488a26d0a9566ee68864070710bb.mp4", tone: "violet", unavailableMessageKey: "dashboard.unavailable.case" },
  { id: "case-action-04", titleKey: "dashboard.cases.action.title", metaKey: "dashboard.cases.action.meta", video: "https://gamecdn.beiyinapp.com/2026-02-10/5ddbe9d8975e28965b0669d46412a71f.mp4", tone: "orange", unavailableMessageKey: "dashboard.unavailable.case" },
];

export const inspirations = [
  {
    id: "storytelling",
    titleKey: "dashboard.inspirations.storytelling.title",
    descriptionKey: "dashboard.inspirations.storytelling.description",
    image: "/assets/short-drama-thumb.webp",
    unavailableMessageKey: "dashboard.unavailable.storytelling",
  },
  {
    id: "creative-remix",
    titleKey: "dashboard.inspirations.creativeRemix.title",
    descriptionKey: "dashboard.inspirations.creativeRemix.description",
    image: "/assets/film-action-thumb.webp",
    unavailableMessageKey: "dashboard.unavailable.creativeRemix",
  },
];

export const dashboardPrimaryAction = {
  labelKey: "dashboard.nav.create",
  icon: MagicWand,
  to: "/dashboard/create",
};
