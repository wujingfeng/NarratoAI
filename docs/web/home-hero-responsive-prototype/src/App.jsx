import { useEffect, useRef, useState } from "react";
import { BenefitStrip } from "./components/BenefitStrip.jsx";
import { DemoTeaser } from "./components/DemoTeaser.jsx";
import { HeroCopy } from "./components/HeroCopy.jsx";
import { SiteHeader } from "./components/SiteHeader.jsx";
import { Toast } from "./components/Toast.jsx";
import { WorkbenchPanel } from "./components/WorkbenchPanel.jsx";

export function App() {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [toastMessage, setToastMessage] = useState("");
  const workbenchRef = useRef(null);
  const demoRef = useRef(null);

  useEffect(() => {
    const closeOnEscape = (event) => {
      if (event.key === "Escape") setMobileMenuOpen(false);
    };

    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, []);

  useEffect(() => {
    if (!toastMessage) return undefined;
    const timeoutId = window.setTimeout(() => setToastMessage(""), 3600);
    return () => window.clearTimeout(timeoutId);
  }, [toastMessage]);

  const scrollTo = (ref) => {
    ref.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    setMobileMenuOpen(false);
  };

  const openLogin = () => {
    setMobileMenuOpen(false);
    setToastMessage("登录入口已准备好，原型阶段暂不连接账号系统");
  };

  const startCreating = () => {
    setToastMessage("正在为你打开创作工作台");
    scrollTo(workbenchRef);
  };

  return (
    <div className="app-shell" id="top">
      <div className="ambient ambient--cyan" aria-hidden="true" />
      <div className="ambient ambient--violet" aria-hidden="true" />
      <div className="perspective-grid" aria-hidden="true" />

      <SiteHeader
        menuOpen={mobileMenuOpen}
        onMenuToggle={() => setMobileMenuOpen((open) => !open)}
        onProductClick={() => scrollTo(workbenchRef)}
        onCasesClick={() => scrollTo(demoRef)}
        onLogin={openLogin}
      />

      <main>
        <section className="hero-composition" aria-labelledby="hero-title">
          <HeroCopy
            onCreate={startCreating}
            onCases={() => scrollTo(demoRef)}
          />

          <div className="workbench-placement" ref={workbenchRef}>
            <WorkbenchPanel />
          </div>

          <BenefitStrip />
        </section>

        <DemoTeaser ref={demoRef} onCreate={startCreating} />
      </main>

      <Toast message={toastMessage} />
    </div>
  );
}
