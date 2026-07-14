import {
  CaretRight,
  FilmSlate,
  Scissors,
  Translate,
} from "@phosphor-icons/react";

const tools = [
  {
    id: "commentary",
    title: "短剧解说",
    description: "加旁白讲剧情",
    icon: FilmSlate,
    tone: "violet",
  },
  {
    id: "translation",
    title: "视频翻译",
    description: "多语言翻译配音",
    icon: Translate,
    tone: "blue",
  },
  {
    id: "remix",
    title: "短剧混剪",
    description: "智能截取高光",
    icon: Scissors,
    tone: "orange",
  },
];

export function ToolCards({ activeTool, onSelect }) {
  const activeName = tools.find((tool) => tool.id === activeTool)?.title;

  return (
    <section className="tool-section">
      <div className="tool-cards" role="group" aria-label="创作工具">
        {tools.map((tool) => {
          const Icon = tool.icon;
          const selected = tool.id === activeTool;
          return (
            <button
              className={`tool-card tool-card--${tool.tone} ${selected ? "is-selected" : ""}`}
              type="button"
              aria-pressed={selected}
              onClick={() => onSelect(tool.id)}
              key={tool.id}
            >
              <span className="tool-icon" aria-hidden="true"><Icon weight="duotone" /></span>
              <span className="tool-copy">
                <strong>{tool.title}</strong>
                <small>{tool.description}</small>
              </span>
              <CaretRight className="tool-caret" weight="bold" aria-hidden="true" />
            </button>
          );
        })}
      </div>
      <p className="tool-selection" aria-live="polite">{activeName}已选中</p>
    </section>
  );
}
