import {
  List,
  Sparkle,
  Triangle,
  X,
} from "@phosphor-icons/react";

function HeaderNavigation({ ariaLabel, onProductClick, onCasesClick }) {
  return (
    <nav className="header-nav" aria-label={ariaLabel}>
      <button type="button" onClick={onProductClick}>产品能力</button>
      <button type="button" onClick={onCasesClick}>案例 Demo</button>
      <button type="button" onClick={onCasesClick}>价格</button>
    </nav>
  );
}

export function SiteHeader({
  menuOpen,
  onMenuToggle,
  onProductClick,
  onCasesClick,
  onLogin,
}) {
  return (
    <header className="site-header">
      <a className="brand" href="#top" aria-label="影创工坊首页">
        <span className="brand-mark" aria-hidden="true">
          <Triangle weight="duotone" />
        </span>
        <span>影创工坊</span>
      </a>

      <HeaderNavigation
        ariaLabel="主导航"
        onProductClick={onProductClick}
        onCasesClick={onCasesClick}
      />

      <button className="login-button" type="button" onClick={onLogin}>
        登录
      </button>

      <button
        className="menu-button"
        type="button"
        aria-label={menuOpen ? "关闭导航菜单" : "打开导航菜单"}
        aria-expanded={menuOpen}
        aria-controls="mobile-navigation"
        onClick={onMenuToggle}
      >
        {menuOpen ? <X weight="bold" /> : <List weight="bold" />}
      </button>

      {menuOpen ? (
        <nav
          className="mobile-navigation"
          id="mobile-navigation"
          aria-label="移动端导航"
        >
          <div className="mobile-nav-kicker">
            <Sparkle weight="fill" />
            AI 视频创作工作台
          </div>
          <button type="button" onClick={onProductClick}>产品能力</button>
          <button type="button" onClick={onCasesClick}>案例 Demo</button>
          <button type="button" onClick={onCasesClick}>价格</button>
          <button className="mobile-login" type="button" onClick={onLogin}>登录</button>
        </nav>
      ) : null}
    </header>
  );
}
