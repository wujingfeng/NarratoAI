import { useCallback, useEffect, useRef, useState } from "react";
import { SiteHeader } from "../components/SiteHeader.jsx";
import { HeroSection } from "../components/HeroSection.jsx";
import { DemoSection, TOOL_DATA } from "../components/DemoSection.jsx";
import { CapabilitySection } from "../components/CapabilitySection.jsx";
import { FaqSection } from "../components/FaqSection.jsx";
import { FinalCtaSection } from "../components/FinalCtaSection.jsx";
import { SiteFooter } from "../components/SiteFooter.jsx";
import { VideoModal } from "../components/VideoModal.jsx";
import { Toast } from "../components/Toast.jsx";

export function HomePage() {
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

  const chooseTool = useCallback(
    (toolId, message) => {
      setActiveTool(toolId);
      if (message) showToast(message);
    },
    [showToast],
  );

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
        <HeroSection
          onStart={() => chooseTool("narration", "已选择：短剧解说，正式工作台接入后继续")}
          onViewDemo={() => scrollTo("demo")}
        />
        <DemoSection
          activeTool={activeTool}
          onToolChange={setActiveTool}
          onOpenCase={openCase}
          onTemplate={(caseItem) =>
            showToast(`已选择：${caseItem.toolName}，正式工作台接入后继续`)
          }
        />
        <CapabilitySection
          activeTool={activeTool}
          onChooseTool={(toolId) => {
            chooseTool(toolId, `已选择：${TOOL_DATA[toolId].label}，正式工作台接入后继续`);
            scrollTo("demo");
          }}
        />
        <section className="lower-grid page-container" aria-label="常见问题与开始创作">
          <FaqSection />
          <FinalCtaSection
            onStart={() => chooseTool("narration", "已选择：短剧解说，正式工作台接入后继续")}
          />
        </section>
      </main>
      <SiteFooter onNavigate={scrollTo} onFeedback={showToast} isInert={pageContentHidden} />
      <VideoModal caseItem={modalCase} onClose={closeModal} returnFocusRef={modalTriggerRef} />
      <Toast message={toast} onClose={() => setToast("")} isInert={pageContentHidden} />
    </div>
  );
}
