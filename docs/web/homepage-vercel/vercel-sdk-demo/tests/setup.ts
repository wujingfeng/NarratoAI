import "@testing-library/jest-dom/vitest";

// jsdom 不实现 scrollIntoView，给个空实现避免 useEffect 报错
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function () {
    /* noop */
  };
}
