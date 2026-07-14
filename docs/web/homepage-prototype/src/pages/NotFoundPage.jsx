import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <main>
      <h1 data-route-heading tabIndex="-1">
        页面未找到
      </h1>
      <p>你访问的页面不存在。</p>
      <nav aria-label="错误页面导航">
        <Link to="/">返回官网</Link>
        <Link to="/dashboard">前往工作台</Link>
      </nav>
    </main>
  );
}
