import {
  ArrowRight,
  CloudArrowUp,
  Cpu,
  DownloadSimple,
  FilmSlate,
  MagicWand,
  Scissors,
  Sparkle,
  Translate,
  UserFocus,
  VideoCamera,
} from "@phosphor-icons/react";
import { useI18n } from "../i18n/useI18n.js";

const capabilityMeta = [
  {
    id: "narration",
    tone: "violet",
    icon: FilmSlate,
  },
  {
    id: "translation",
    tone: "cyan",
    icon: Translate,
  },
  {
    id: "remix",
    tone: "orange",
    icon: Scissors,
  },
];

const processStepMeta = [
  { id: "upload", icon: CloudArrowUp },
  { id: "analysis", icon: Cpu },
  { id: "review", icon: UserFocus },
  { id: "compose", icon: VideoCamera },
  { id: "export", icon: DownloadSimple },
];

function CapabilityCard({ item, selected, onChoose, t }) {
  const Icon = item.icon;
  return (
    <article className={`capability-card capability-card--${item.tone} ${selected ? "is-selected" : ""}`}>
      <div className="capability-card__copy">
        <span className="capability-card__icon"><Icon size={35} weight="duotone" /></span>
        <h3>{t(`home.capabilities.items.${item.id}.title`)}</h3>
        <p>{t(`home.capabilities.items.${item.id}.subtitle`)}</p>
        <small>{t(`home.capabilities.items.${item.id}.features`)}</small>
        <button type="button" onClick={() => onChoose(item.id)}>{t("home.capabilities.tryNow")} <ArrowRight size={17} /></button>
      </div>
      <div className="capability-orbit" aria-hidden="true">
        <span className="capability-orbit__halo" />
        <span className="capability-orbit__core"><Icon size={76} weight="duotone" /></span>
        <i /><i /><i />
      </div>
    </article>
  );
}

function ProcessStepper({ t }) {
  return (
    <div className="process-panel">
      <div className="process-steps">
        {processStepMeta.map(({ id, icon: Icon }, index) => (
          <div className="process-step" key={id}>
            <div className="process-step__node"><Icon size={28} weight="duotone" /></div>
            <span><b>{index + 1}</b>{t(`home.capabilities.process.${id}`)}</span>
            {index < processStepMeta.length - 1 && <i className="process-step__connector" />}
          </div>
        ))}
      </div>
      <div className="process-note"><Sparkle size={30} weight="duotone" /><p>{t("home.capabilities.processNoteLine1")}<br />{t("home.capabilities.processNoteLine2")}</p></div>
    </div>
  );
}

export function CapabilitySection({ activeTool, onChooseTool }) {
  const { t } = useI18n();
  return (
    <section id="capabilities" className="capability-section section-anchor page-container">
      <div className="capability-heading">
        <span className="section-kicker">{t("home.capabilities.kicker")}</span>
        <h2>{t("home.capabilities.headingPrefix")}<span className="gradient-text">{t("home.capabilities.headingAccent")}</span></h2>
        <p><MagicWand size={18} weight="duotone" /> {t("home.capabilities.description")}</p>
      </div>
      <div className="capability-grid">
        {capabilityMeta.map((item) => (
          <CapabilityCard key={item.id} item={item} selected={activeTool === item.id} onChoose={onChooseTool} t={t} />
        ))}
      </div>
      <ProcessStepper t={t} />
    </section>
  );
}
