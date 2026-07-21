import { Check } from "@phosphor-icons/react";
import { useI18n } from "../../i18n/useI18n.js";

export function NarrationStepper({ steps }) {
  const { t } = useI18n();
  return <ol className="narration-stepper" aria-label={t("narration.stepperLabel")}>
    {steps.map((step, index) => <li className={index < 1 ? "is-complete" : index === 1 ? "is-current" : ""} key={step.id}>
      <span className="narration-stepper__number">{index < 1 ? <Check weight="bold" aria-hidden="true" /> : index + 1}</span>
      <span>{t(step.labelKey)}</span>
    </li>)}
  </ol>;
}
