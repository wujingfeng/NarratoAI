import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { SiteHeader } from "../components/SiteHeader.jsx";
import { HeroSection } from "../components/HeroSection.jsx";
import { DemoSection } from "../components/DemoSection.jsx";
import { CapabilitySection } from "../components/CapabilitySection.jsx";
import { FaqSection } from "../components/FaqSection.jsx";
import { FinalCtaSection } from "../components/FinalCtaSection.jsx";
import { SiteFooter } from "../components/SiteFooter.jsx";
import { VideoModal } from "../components/VideoModal.jsx";
import { Toast } from "../components/Toast.jsx";

export function HomePage() {
  const navigate = useNavigate();
  const [activeTool, setActiveTool] = useState("narration");
  const [menuOpen, setMenuOpen] = useState(false);
  const [activeSection, setActiveSection] = useState("hero");
  const [modalCase, setModalCase] = useState(null);
  const [toast, setToast] = useState("");
  const toastTimer = useRef(null);
  const modalTriggerRef = useRef(null);

  const showToast = useCallback((message) => {
    setToast(message);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(""), 3200);
  }, []);

  const startCreation = useCallback(() => navigate("/dashboard"), [navigate]);

  const scrollTo = useCallback((id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    setMenuOpen(false);
  }, []);

  const openCase = useCallback((caseItem) => {
    modalTriggerRef.current = document.activeElement;
    setModalCase(caseItem);
  }, []);

  const closeModal = useCallback(() => setModalCase(null), []);

  useEffect(() => {
    const sections = ["hero", "demo", "capabilities"]
      .map((id) => document.getElementById(id))
      .filter(Boolean);
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible) setActiveSection(visible.target.id);
      },
      { rootMargin: "-20% 0px -58%", threshold: [0.08, 0.25, 0.5] },
    );
    sections.forEach((section) => observer.observe(section));
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    document.body.classList.toggle("menu-locked", menuOpen);
    return () => document.body.classList.remove("menu-locked");
  }, [menuOpen]);

  useEffect(() => () => window.clearTimeout(toastTimer.current), []);

  const modalOpen = Boolean(modalCase);
  const pageContentHidden = modalOpen || menuOpen;

  return (
    <div className="site-shell" data-page="home">
      <SiteHeader
        activeSection={activeSection}
        menuOpen={menuOpen}
        onMenuChange={setMenuOpen}
        onNavigate={scrollTo}
        onFeedback={showToast}
        isInert={modalOpen}
      />
      <main inert={pageContentHidden ? true : undefined} aria-hidden={pageContentHidden ? "true" : undefined}>
        <HeroSection onStart={startCreation} onViewDemo={() => scrollTo("demo")} />
        <DemoSection
          activeTool={activeTool}
          onToolChange={setActiveTool}
          onOpenCase={openCase}
          onTemplate={startCreation}
        />
        <CapabilitySection activeTool={activeTool} onChooseTool={startCreation} />
        <section className="lower-grid page-container" aria-label="常见问题与开始创作">
          <FaqSection />
          <FinalCtaSection onStart={startCreation} />
        </section>
      </main>
      <SiteFooter onNavigate={scrollTo} onFeedback={showToast} isInert={pageContentHidden} />
      <VideoModal caseItem={modalCase} onClose={closeModal} returnFocusRef={modalTriggerRef} />
      <Toast message={toast} onClose={() => setToast("")} isInert={pageContentHidden} />
    </div>
  );
}
