import { CaretLeft, CaretRight } from "@phosphor-icons/react";
import { useRef, useState } from "react";
import { PromotionBanner } from "./PromotionBanner.jsx";

export function MarketingCarousel({ promotions, onUnavailable }) {
  const trackRef = useRef(null);
  const [activeIndex, setActiveIndex] = useState(0);

  const scrollToSlide = (index) => {
    const track = trackRef.current;
    if (!track) return;
    const nextIndex = (index + promotions.length) % promotions.length;
    track.scrollTo({ left: track.clientWidth * nextIndex, behavior: "smooth" });
    setActiveIndex(nextIndex);
  };

  return (
    <section className="dashboard-marketing" aria-label="促销信息">
      <div className="dashboard-marketing__track" ref={trackRef} onScroll={(event) => setActiveIndex(Math.round(event.currentTarget.scrollLeft / event.currentTarget.clientWidth))}>
        {promotions.map((promotion) => <PromotionBanner key={promotion.id} promotion={promotion} onUnavailable={onUnavailable} />)}
      </div>
      <div className="dashboard-marketing__controls" aria-label="促销轮播控制">
        <button type="button" aria-label="上一条促销" onClick={() => scrollToSlide(activeIndex - 1)}><CaretLeft aria-hidden="true" /></button>
        <span aria-live="polite">{activeIndex + 1} / {promotions.length}</span>
        <button type="button" aria-label="下一条促销" onClick={() => scrollToSlide(activeIndex + 1)}><CaretRight aria-hidden="true" /></button>
      </div>
    </section>
  );
}
