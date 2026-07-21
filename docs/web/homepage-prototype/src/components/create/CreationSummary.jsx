import { useI18n } from "../../i18n/useI18n.js";

export function CreationSummary({ durationLabel, estimatedCredits, balance, onNext, disabled = false }) {
  const { formatNumber, t } = useI18n();
  return (
    <aside className="create-summary" aria-labelledby="create-summary-heading">
      <h2 id="create-summary-heading">{t("create.summary.title")}</h2>
      <dl>
        <div>
          <dt>{t("create.summary.duration")}</dt>
          <dd className="create-summary__duration">{durationLabel}</dd>
        </div>
        <div>
          <dt>{t("create.summary.estimated")}</dt>
          <dd className="create-summary__credits">
            {estimatedCredits === null ? "—" : formatNumber(estimatedCredits)}
            {estimatedCredits !== null && <span>{t("dashboard.credits.title")}</span>}
          </dd>
        </div>
        <div>
          <dt>{t("create.summary.balance")}</dt>
          <dd className="create-summary__balance">{formatNumber(balance)}</dd>
        </div>
      </dl>
      <button className="create-summary__next" type="button" onClick={onNext} disabled={disabled}>
        {t("create.summary.next")}
      </button>
    </aside>
  );
}
