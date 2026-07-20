export function CreationSummary({ durationLabel, estimatedCredits, balance, onNext, disabled = false }) {
  return (
    <aside className="create-summary" aria-label="创作小结">
      <h2>创作小结</h2>
      <dl>
        <div><dt>素材时长</dt><dd>{durationLabel}</dd></div>
        <div><dt>API 预计费用</dt><dd className="create-summary__credits">{estimatedCredits ?? "待计算"} 创作点</dd></div>
        <div><dt>可用创作点</dt><dd>{balance}</dd></div>
      </dl>
      <button type="button" onClick={onNext} disabled={disabled}>开始创作</button>
      {disabled && <p>请等待全部素材校验完成后再开始</p>}
    </aside>
  );
}
