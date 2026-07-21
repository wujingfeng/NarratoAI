import { Check, FilmSlate, PlayCircle } from "@phosphor-icons/react";
import { useI18n } from "../../i18n/useI18n.js";

export function ProjectTaskSteps({ steps }) {
  const { t } = useI18n();
  return (
    <section className="project-result-side-card" aria-labelledby="task-steps-title">
      <div className="project-result-side-card__heading"><h3 id="task-steps-title">{t("projectResult.details.taskSteps")}</h3><span>{t("projectResult.details.allComplete")}</span></div>
      <ol className="project-result-steps">
        {steps.map((step) => <li key={step.id}><i><Check weight="bold" aria-hidden="true" /></i><span>{t(step.labelKey)}</span></li>)}
      </ol>
    </section>
  );
}

export function ProjectOperationLog({ logs }) {
  const { t } = useI18n();
  return (
    <section className="project-result-side-card" aria-labelledby="operation-log-title">
      <h3 id="operation-log-title">{t("projectResult.details.operationLog")}</h3>
      <ol className="project-result-log">
        {logs.map(({ time, messageKey }) => <li key={time}><time>{time}</time><span>{t(messageKey)}</span></li>)}
      </ol>
    </section>
  );
}

export function ProjectCreditCost({ items, total }) {
  const { formatNumber, t } = useI18n();
  return (
    <section className="project-result-bottom-card project-result-cost" aria-labelledby="credit-cost-title">
      <div className="project-result-bottom-card__heading"><h3 id="credit-cost-title">{t("projectResult.details.creditCost")}</h3><span>{t("projectResult.details.totalCredits", { count: formatNumber(total) })}</span></div>
      <div className="project-result-cost__grid">
        {items.map(({ id, labelKey, value, icon: Icon, tone }) => <div className={`project-result-cost__item project-result-cost__item--${tone}`} key={id}><Icon aria-hidden="true" /><strong>{formatNumber(value)}</strong><span>{t(labelKey)}</span></div>)}
      </div>
    </section>
  );
}

export function ProjectSummary({ summary }) {
  const { formatDate, t } = useI18n();
  return (
    <section className="project-result-bottom-card project-result-summary" aria-labelledby="project-summary-title">
      <h3 id="project-summary-title">{t("projectResult.details.summary")}</h3>
      <div className="project-result-summary__grid">
        <div className="project-result-summary__media"><FilmSlate aria-hidden="true" /><span>{t(summary.sourceKey)}</span></div>
        <dl><div><dt>{t("projectResult.details.createdAt")}</dt><dd>{formatDate(summary.createdAt, { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Shanghai" })}</dd></div><div><dt>{t("projectResult.details.projectType")}</dt><dd>{t(summary.typeKey)}</dd></div></dl>
        <div className="project-result-summary__media"><PlayCircle aria-hidden="true" /><span>{t(summary.outputKey)}</span></div>
      </div>
    </section>
  );
}
