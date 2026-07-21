import { ChatCircleDots, Heart, Lightning, Smiley } from "@phosphor-icons/react";

export const narrationSteps = ["upload", "settings", "analysis", "edit", "script", "voice", "export"].map((id) => ({ id, labelKey: `narration.steps.${id}` }));

export const narrationStyles = [
  { id: "reversal", titleKey: "narration.styles.reversal.title", descriptionKey: "narration.styles.reversal.description", icon: Lightning, tone: "violet" },
  { id: "suspense", titleKey: "narration.styles.suspense.title", descriptionKey: "narration.styles.suspense.description", icon: ChatCircleDots, tone: "orange" },
  { id: "emotion", titleKey: "narration.styles.emotion.title", descriptionKey: "narration.styles.emotion.description", icon: Heart, tone: "pink" },
  { id: "casual", titleKey: "narration.styles.casual.title", descriptionKey: "narration.styles.casual.description", icon: Smiley, tone: "cyan" },
];

export const narrationRatios = [
  { id: "original", labelKey: "narration.ratios.original", glyph: "portrait" },
  { id: "landscape", labelKey: "narration.ratios.landscape", glyph: "landscape" },
  { id: "square", labelKey: "narration.ratios.square", glyph: "square" },
];

export const subtitleStyles = [
  { id: "glow", labelKey: "narration.subtitleStyles.glow", className: "narration-subtitle--glow" },
  { id: "classic", labelKey: "narration.subtitleStyles.classic", className: "narration-subtitle--classic" },
  { id: "shadow", labelKey: "narration.subtitleStyles.shadow", className: "narration-subtitle--shadow" },
];
