import { BrandMark } from "./BrandMark.jsx";

export function SiteFooter({ onNavigate, onFeedback, isInert = false }) {
  return (
    <footer className="site-footer" inert={isInert ? true : undefined} aria-hidden={isInert ? "true" : undefined}>
      <div className="page-container site-footer__inner">
        <button className="brand-button" type="button" onClick={() => onNavigate("hero")}><BrandMark compact /></button>
        <nav aria-label="页脚导航">
          <button type="button" onClick={() => onNavigate("capabilities")}>产品能力</button>
          <button type="button" onClick={() => onNavigate("demo")}>案例 Demo</button>
          <button type="button" onClick={() => onFeedback("价格页待接入")}>价格</button>
        </nav>
        <div className="site-footer__legal"><button type="button" onClick={() => onFeedback("用户协议待接入")}>用户协议</button><button type="button" onClick={() => onFeedback("隐私政策待接入")}>隐私政策</button></div>
      </div>
    </footer>
  );
}
