import { useState } from "react";
import { CaretDown, ChatCenteredText } from "@phosphor-icons/react";

const FAQS = [
  ["没有字幕文件也能用吗？", "可以。影创工坊会自动识别视频中的对白并生成时间轴字幕，你仍可在合成前校对。"],
  ["生成前可以修改片段和文案吗？", "可以。AI 先给出推荐片段、文案和节奏，你可以逐项替换、改写或调整顺序。"],
  ["创作点如何计费？", "原型中暂不接入真实计费；正式版本会在生成前透明展示预计创作点消耗。"],
  ["生成失败会扣费吗？", "失败任务不会按成功成片计费，正式规则会在任务记录中清晰展示。"],
];

export function FaqSection() {
  const [openIndex, setOpenIndex] = useState(null);
  return (
    <section className="faq-panel" aria-labelledby="faq-title">
      <div className="panel-title"><ChatCenteredText size={22} weight="duotone" /><h2 id="faq-title">常见问题</h2></div>
      <div className="faq-list">
        {FAQS.map(([question, answer], index) => {
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
