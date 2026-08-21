import { Check } from "@phosphor-icons/react";
import { useI18n } from "../../i18n/useI18n.js";

export function NarrationStepper({ steps, currentStage = "settings" }) {
  const { t } = useI18n();
  return <ol className="narration-stepper" aria-label={t("narration.stepperLabel")}>
    {steps.map((step, index) => {
      const currentIndex = Math.max(0, steps.findIndex((candidate) => candidate.id === currentStage));
      const complete = index < currentIndex;
      return <li className={complete ? "is-complete" : index === currentIndex ? "is-current" : ""} key={step.id}>
      <span className="narration-stepper__number">{complete ? <Check weight="bold" aria-hidden="true" /> : index + 1}</span>
      <span>{t(step.labelKey)}</span>
    </li>;
    })}
  </ol>;
}
