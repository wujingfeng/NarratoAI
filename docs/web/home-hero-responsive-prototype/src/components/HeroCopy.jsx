import {
  ArrowRight,
  PlayCircle,
  Sparkle,
} from "@phosphor-icons/react";

export function HeroCopy({ onCreate, onCases }) {
  return (
    <div className="hero-copy">
      <div className="eyebrow">
        <Sparkle weight="fill" aria-hidden="true" />
        <span>AI 视频创作 · 小白也能做出专业级视频</span>
      </div>

      <h1 id="hero-title">
        <span className="hero-title-lead">专为自媒体小白打造的</span>
        <span className="hero-title-gradient">AI 出片工作台</span>
        <span className="hero-title-shine" aria-hidden="true">
          <span className="hero-title-shine-gradient">AI 出片工作台</span>
        </span>
      </h1>

      <p className="hero-description">
        上传素材，AI 自动完成剪辑、文案、配音、字幕与合成。
        短剧解说、视频翻译、智能混剪，一个工作台搞定。
      </p>

      <div className="hero-actions">
        <button className="primary-action" type="button" onClick={onCreate}>
          <span>开始创作</span>
          <ArrowRight weight="bold" aria-hidden="true" />
        </button>
        <button className="secondary-action" type="button" onClick={onCases}>
          <PlayCircle weight="duotone" aria-hidden="true" />
          <span>查看案例</span>
        </button>
      </div>
    </div>
  );
}
