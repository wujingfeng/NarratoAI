import { useState } from "react";
import { CaretDown, ChatCenteredText } from "@phosphor-icons/react";
import { useI18n } from "../i18n/useI18n.js";

export function FaqSection() {
  const { t } = useI18n();
  const [openIndex, setOpenIndex] = useState(null);
  const faqs = [1, 2, 3, 4].map((id) => [t(`home.faq.items.item${id}.question`), t(`home.faq.items.item${id}.answer`)]);
  return (
    <section className="faq-panel" aria-labelledby="faq-title">
      <div className="panel-title"><ChatCenteredText size={22} weight="duotone" /><h2 id="faq-title">{t("home.faq.title")}</h2></div>
      <div className="faq-list">
        {faqs.map(([question, answer], index) => {
          const open = openIndex === index;
          return (
            <div className={`faq-item ${open ? "is-open" : ""}`} key={question}>
              <button type="button" aria-expanded={open} onClick={() => setOpenIndex(open ? null : index)}>
                <span><b>Q</b>{question}</span><CaretDown size={18} />
              </button>
              <div className="faq-answer" aria-hidden={!open}><div><p>{answer}</p></div></div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
