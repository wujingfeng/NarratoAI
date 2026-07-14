import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173";
const executablePath =
  process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await chromium.launch({ executablePath, headless: true });
const page = await browser.newPage({ viewport: { width: 1487, height: 1058 } });
const failures = [];
const failedThumbnailUrl = new URL("/assets/documentary-thumb.webp", baseUrl).href;
let thumbnail404Observed = false;

await page.route("**/favicon.ico", (route) => route.fulfill({ status: 204 }));
await page.route("**/assets/documentary-thumb.webp", (route) => {
  route.fulfill({ status: 404, contentType: "image/webp", body: "" });
});

page.on("console", (message) => {
  if (message.type() === "error") {
    const location = message.location().url;
    if (location === failedThumbnailUrl && message.text().includes("404")) return;
    failures.push(`console.error${location ? ` (${location})` : ""}: ${message.text()}`);
  }
});
page.on("pageerror", (error) => failures.push(`pageerror: ${error.message}`));
page.on("requestfailed", (request) => {
  failures.push(`requestfailed: ${request.method()} ${request.url()} ${request.failure()?.errorText}`);
});
page.on("response", (response) => {
  if (response.url() === failedThumbnailUrl && response.status() === 404) {
    thumbnail404Observed = true;
    return;
  }
  if (response.status() >= 400) failures.push(`response ${response.status()}: ${response.url()}`);
});

function check(condition, message) {
  if (!condition) throw new Error(message);
}

async function expectToast(trigger, message) {
  await trigger.click();
  await page.getByRole("status").filter({ hasText: message }).waitFor();
  check(page.url() === `${baseUrl}/dashboard`, `${message} 不得改变路由`);
}

try {
  await page.goto(`${baseUrl}/dashboard`, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "工作台概览" }).waitFor();
  const desktopMetrics = await page.evaluate(() => {
    const sidebar = document.querySelector(".dashboard-sidebar").getBoundingClientRect();
    const main = document.querySelector(".dashboard-main").getBoundingClientRect();
    const banner = document.querySelector("[data-dashboard-banner]").getBoundingClientRect();
    const membership = document.querySelector(".dashboard-membership-card")?.getBoundingClientRect();
    const creation = document.querySelector(".creation-entry-card").getBoundingClientRect();
    const toolCards = [...document.querySelectorAll(".tool-quick-start__card")].map((element) =>
      element.getBoundingClientRect(),
    );
    const recent = document.querySelector(".recent-projects").getBoundingClientRect();
    const credits = document.querySelector(".credits-overview").getBoundingClientRect();
    const inspiration = document.querySelector(".inspiration-panel").getBoundingClientRect();
    return {
      pageWidth: document.documentElement.scrollWidth,
      viewportWidth: innerWidth,
      sidebarWidth: sidebar.width,
      sidebarLeft: sidebar.left,
      mainLeft: main.left,
      bannerWidth: banner.width,
      bannerHeight: banner.height,
      membership: membership && { left: membership.left, right: membership.right },
      creation: { left: creation.left, right: creation.right, top: creation.top },
      toolCards: toolCards.map(({ left, right, top }) => ({ left, right, top })),
      lowerCards: [recent, credits, inspiration].map(({ left, right, top }) => ({ left, right, top })),
      mobileNavDisplay: getComputedStyle(document.querySelector(".dashboard-mobile-nav")).display,
      background: getComputedStyle(document.querySelector(".dashboard-shell")).backgroundColor,
    };
  });
  check(desktopMetrics.pageWidth <= desktopMetrics.viewportWidth + 1, "桌面不得横向溢出");
  check(desktopMetrics.sidebarWidth >= 220 && desktopMetrics.sidebarWidth <= 280, "1487 桌面侧栏宽度接近参考稿");
  check(desktopMetrics.sidebarLeft === 0, "桌面侧栏贴齐左侧");
  check(desktopMetrics.mainLeft >= desktopMetrics.sidebarWidth, "主内容不得压到侧栏");
  check(desktopMetrics.bannerWidth >= 900, "促销 Banner 占据主内容主宽度");
  check(desktopMetrics.bannerHeight >= 145 && desktopMetrics.bannerHeight <= 165, "促销 Banner 高度接近参考稿");
  check(desktopMetrics.mobileNavDisplay === "none", "桌面隐藏移动底栏");
  check(desktopMetrics.background === "rgb(5, 8, 18)", "工作台使用深色背景 Token");
  check(desktopMetrics.membership, "侧栏存在真实会员入口");
  check(
    desktopMetrics.membership.left >= desktopMetrics.sidebarLeft &&
      desktopMetrics.membership.right <= desktopMetrics.sidebarWidth,
    "会员入口不得越过侧栏",
  );
  check(desktopMetrics.toolCards.length === 3, "桌面首排存在三张工具卡");
  check(desktopMetrics.creation.right <= desktopMetrics.toolCards[0].left, "创建卡与工具卡不得相交");
  check(
    desktopMetrics.toolCards.every((card) => Math.abs(card.top - desktopMetrics.creation.top) <= 1),
    "桌面首排四卡顶部对齐",
  );
  check(
    desktopMetrics.toolCards.slice(1).every((card, index) => desktopMetrics.toolCards[index].right <= card.left),
    "桌面工具卡不得相交",
  );
  check(
    desktopMetrics.lowerCards[0].right <= desktopMetrics.lowerCards[1].left &&
      desktopMetrics.lowerCards[1].right <= desktopMetrics.lowerCards[2].left,
    "桌面下排保持最近项目、创作点、灵感三列关系",
  );
  check(
    desktopMetrics.lowerCards.every((card) => Math.abs(card.top - desktopMetrics.lowerCards[0].top) <= 1),
    "桌面下排模块顶部对齐",
  );
  check(await page.getByRole("button", { name: /升级会员/ }).count() === 1, "会员入口使用真实 button");
  check(await page.getByRole("button", { name: "查看创作点余额 1,280" }).count() === 1, "顶部展示可聚焦余额");
  check(await page.getByRole("button", { name: "去充值" }).count() === 1, "顶部展示充值入口");
  check(await page.getByRole("button", { name: "账户中心" }).count() >= 1, "顶部展示账户入口");
  check(
    (await page.locator(".dashboard-sidebar__group-title").allTextContents()).join(",") === "工具,账户",
    "侧栏分组标题使用真实文本节点",
  );
  check(await page.getByText("上传素材，跟随引导完成专业出片", { exact: true }).count() === 1, "创建说明使用真实文本");
  check(await page.locator(".recent-projects__credits").filter({ hasText: /^消耗 \d+$/ }).count() === 3, "项目消耗使用真实文本");
  check(await page.getByText("影创工坊 · 让 AI 创作更简单", { exact: true }).count() === 1, "桌面存在品牌 Footer");
  const membershipEntry = page.getByRole("button", { name: /升级会员/ });
  await membershipEntry.focus();
  check(await membershipEntry.evaluate((element) => document.activeElement === element), "会员入口可获得键盘焦点");
  for (const accountAction of [
    page.getByRole("button", { name: "查看创作点余额 1,280" }),
    page.getByRole("button", { name: "去充值" }),
    page.locator(".dashboard-account__avatar"),
  ]) {
    await accountAction.focus();
    check(await accountAction.evaluate((element) => document.activeElement === element), "账户区操作可获得键盘焦点");
  }

  for (const width of [1280, 1025]) {
    await page.setViewportSize({ width, height: 1058 });
    const responsiveMetrics = await page.evaluate(() => {
      const sidebar = document.querySelector(".dashboard-sidebar").getBoundingClientRect();
      const main = document.querySelector(".dashboard-main").getBoundingClientRect();
      const creation = document.querySelector(".creation-entry-card").getBoundingClientRect();
      const tools = [...document.querySelectorAll(".tool-quick-start__card")].map((element) =>
        element.getBoundingClientRect().width,
      );
      return {
        pageWidth: document.documentElement.scrollWidth,
        viewportWidth: innerWidth,
        sidebarWidth: sidebar.width,
        mainLeft: main.left,
        creationWidth: creation.width,
        minimumToolWidth: Math.min(...tools),
        mobileNavDisplay: getComputedStyle(document.querySelector(".dashboard-mobile-nav")).display,
      };
    });
    check(
      responsiveMetrics.pageWidth <= responsiveMetrics.viewportWidth + 1,
      `${width} 桌面不得横向溢出`,
    );
    check(responsiveMetrics.sidebarWidth >= 220, `${width} 保留可用桌面侧栏`);
    check(responsiveMetrics.mainLeft >= responsiveMetrics.sidebarWidth, `${width} 主内容避让侧栏`);
    check(responsiveMetrics.creationWidth >= 280, `${width} 新建创作卡保持可读宽度`);
    check(responsiveMetrics.minimumToolWidth >= 120, `${width} 工具卡保持可读宽度`);
    check(responsiveMetrics.mobileNavDisplay === "none", `${width} 桌面隐藏移动底栏`);
  }

  for (const viewport of [
    { width: 390, height: 844 },
    { width: 320, height: 720 },
    { width: 768, height: 1024 },
    { width: 1024, height: 1058 },
  ]) {
    await page.setViewportSize(viewport);
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    const mobileMetrics = await page.evaluate(() => {
      const sidebar = document.querySelector(".dashboard-sidebar");
      const mobileNav = document.querySelector(".dashboard-mobile-nav");
      const tools = document.querySelector(".tool-quick-start__grid");
      const main = document.querySelector(".dashboard-main");
      const navTargets = [...mobileNav.querySelectorAll("a, button")].map((element) => {
        const rect = element.getBoundingClientRect();
        return { width: rect.width, height: rect.height };
      });
      const visiblePageTargets = [
        ...document.querySelectorAll(
          ".dashboard-header a, .dashboard-header button, .dashboard-main a, .dashboard-main button, .dashboard-mobile-nav a, .dashboard-mobile-nav button",
        ),
      ]
        .filter((element) => {
          const rect = element.getBoundingClientRect();
          const style = getComputedStyle(element);
          return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden";
        })
        .map((element) => {
          const rect = element.getBoundingClientRect();
          return {
            label: element.getAttribute("aria-label") || element.textContent.trim() || element.className,
            width: rect.width,
            height: rect.height,
          };
        });
      const creditActionIcon = document
        .querySelector(".credits-overview__action svg")
        .getBoundingClientRect();
      const lastContent = document.querySelector(".credits-overview").getBoundingClientRect();
      const navRect = mobileNav.getBoundingClientRect();
      return {
        pageWidth: document.documentElement.scrollWidth,
        viewportWidth: innerWidth,
        sidebarDisplay: getComputedStyle(sidebar).display,
        mobileNavDisplay: getComputedStyle(mobileNav).display,
        toolsClient: tools.clientWidth,
        toolsScroll: tools.scrollWidth,
        toolsOverflow: getComputedStyle(tools).overflowX,
        toolsTemplate: getComputedStyle(tools).gridTemplateColumns,
        toolWidths: [...tools.children].map((element) => element.getBoundingClientRect().width),
        bodyPaddingBottom: parseFloat(getComputedStyle(main).paddingBottom),
        navHeight: navRect.height,
        navTargets,
        visiblePageTargets,
        creditActionIcon: { width: creditActionIcon.width, height: creditActionIcon.height },
        inspirationDisplay: getComputedStyle(document.querySelector(".inspiration-panel")).display,
        creditsRingDisplay: document.querySelector(".credits-ring")
          ? getComputedStyle(document.querySelector(".credits-ring")).display
          : "missing",
        lastContentBottom: lastContent.bottom,
        navTop: navRect.top,
      };
    });
    const size = `${viewport.width}×${viewport.height}`;
    check(mobileMetrics.pageWidth <= mobileMetrics.viewportWidth + 1, `${size} 移动页面无横向溢出`);
    check(mobileMetrics.sidebarDisplay === "none", `${size} 移动隐藏桌面侧栏`);
    check(mobileMetrics.mobileNavDisplay !== "none", `${size} 移动显示底部导航`);
    check(
      mobileMetrics.toolsScroll > mobileMetrics.toolsClient && ["auto", "scroll"].includes(mobileMetrics.toolsOverflow),
      `${size} 工具只在内部横向滚动（client=${mobileMetrics.toolsClient}, scroll=${mobileMetrics.toolsScroll}, overflow=${mobileMetrics.toolsOverflow}, template=${mobileMetrics.toolsTemplate}, cards=${mobileMetrics.toolWidths.join("/")}）`,
    );
    check(mobileMetrics.bodyPaddingBottom >= mobileMetrics.navHeight, `${size} 底部 padding 覆盖固定导航`);
    check(
      mobileMetrics.navTargets.every(({ width, height }) => width >= 44 && height >= 44),
      `${size} 移动导航触控目标至少 44px`,
    );
    const undersizedTarget = mobileMetrics.visiblePageTargets.find(({ width, height }) => width < 44 || height < 44);
    check(
      !undersizedTarget,
      `${size} 页面内主要可见交互目标至少 44px${
        undersizedTarget
          ? `（${undersizedTarget.label}: ${undersizedTarget.width}×${undersizedTarget.height}）`
          : ""
      }`,
    );
    check(
      mobileMetrics.creditActionIcon.width >= 18 && mobileMetrics.creditActionIcon.height >= 18,
      `${size} 月耗操作箭头清晰可见`,
    );
    check(mobileMetrics.inspirationDisplay === "none", `${size} 移动隐藏创作灵感`);
    check(mobileMetrics.creditsRingDisplay === "none", `${size} 移动隐藏完整创作点圆环`);
    check(mobileMetrics.lastContentBottom <= mobileMetrics.navTop, `${size} 最后一项不被固定底栏遮挡`);
    check(
      (await page.locator(".dashboard-mobile-nav a[aria-current='page']").textContent()).includes("概览"),
      `${size} 移动概览标记当前页面`,
    );
    await page.getByText("处理中 66%", { exact: true }).waitFor({ state: "visible" });
  }

  await page.setViewportSize({ width: 390, height: 844 });
  check(
    await page.locator("a.dashboard-header--mobile[aria-label='影创工坊'][href='/']").count() === 1,
    "移动 Header Logo 使用具名首页 Link",
  );
  const unlabeledIconButtons = await page.locator("button").evaluateAll((buttons) =>
    buttons.filter((button) => !button.textContent.trim() && !button.getAttribute("aria-label")).length,
  );
  check(unlabeledIconButtons === 0, "纯图标按钮均有 aria-label");

  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.getByRole("button", { name: /新建创作/ }).first().click();
  await page.getByRole("status").filter({ hasText: "新建创作功能建设中" }).waitFor();
  const reducedMotion = await page.evaluate(() =>
    ["[data-dashboard-banner]", ".dashboard-toast", ".tool-quick-start__card"].map((selector) => {
      const element = document.querySelector(selector);
      if (!element) return null;
      const style = getComputedStyle(element);
      return { animationName: style.animationName, transitionDuration: style.transitionDuration };
    }),
  );
  check(
    reducedMotion.length === 3 && reducedMotion.every(Boolean),
    "减少动态效果采样完整覆盖 Banner、Toast 与工具卡",
  );
  check(
    reducedMotion.every(({ animationName }) => animationName === "none"),
    "减少动态效果时 Banner、Toast 与卡片不播放动画",
  );
  check(
    reducedMotion.every(({ transitionDuration }) => parseFloat(transitionDuration) <= 0.01),
    "减少动态效果时过渡降级为近静态",
  );
  await page.getByRole("button", { name: "关闭提示" }).click();
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.setViewportSize({ width: 1487, height: 1058 });
  check(await page.locator("h1").count() === 1, "Dashboard 只有一个 h1");
  check(await page.getByRole("navigation", { name: "工作台主导航" }).count() === 1, "桌面主导航存在");
  check(await page.getByRole("link", { name: "影创工坊" }).getAttribute("href") === "/", "品牌链接返回官网");
  const projectStatuses = await page.locator("[data-project-status]").evaluateAll((elements) =>
    elements.map((element) => element.dataset.projectStatus).sort(),
  );
  check(projectStatuses.join(",") === "complete,draft,processing", "最近项目精确覆盖 complete、processing、draft 三态");
  check(await page.getByText("1,280", { exact: true }).count() >= 1, "余额为 1,280");
  check(await page.getByText(/本月.*240.*创作点/).count() >= 1, "月耗为 240");
  check(await page.locator("progress[value='66'][max='100']").count() === 1, "处理中进度有原生语义");
  await page.getByText("处理中 66%", { exact: true }).waitFor({ state: "visible" });

  const failedProject = page.locator("[data-project-status='draft']");
  await failedProject.scrollIntoViewIfNeeded();
  await page.getByRole("img", { name: "视频翻译缩略图不可用" }).waitFor();
  check(thumbnail404Observed, "缩略图请求真实返回 404");
  check(await failedProject.locator("img").count() === 0, "图片 404 后移除破图 img");

  const before = page.url();
  await page.getByRole("button", { name: /新建创作/ }).first().click();
  await page.getByRole("status").filter({ hasText: "新建创作功能建设中" }).waitFor();
  check(page.url() === before, "未实现功能不得改路由");

  const repeatedEntry = page.getByRole("button", { name: /新建创作/ }).first();
  const previousToast = await page.getByRole("status").elementHandle();
  await page.waitForTimeout(1600);
  const repeatedAt = Date.now();
  await repeatedEntry.click();
  await page.waitForFunction((element) => !element.isConnected, previousToast);
  await page.getByRole("status").filter({ hasText: "新建创作功能建设中" }).waitFor();
  await page.getByRole("status").waitFor({ state: "detached", timeout: 4500 });
  const repeatedLifetime = Date.now() - repeatedAt;
  check(
    repeatedLifetime >= 2900 && repeatedLifetime <= 4200,
    `同入口重复点击后 Toast 应约 3200ms 自动关闭，实际 ${repeatedLifetime}ms`,
  );

  await expectToast(page.getByRole("button", { name: "视频翻译" }).first(), "视频翻译功能建设中");
  await expectToast(page.getByRole("button", { name: "短剧解说" }).first(), "短剧解说功能建设中");
  await expectToast(membershipEntry, "升级会员功能建设中");
  await expectToast(page.getByRole("button", { name: "查看创作点余额 1,280" }), "创作点明细功能建设中");
  await expectToast(page.getByRole("button", { name: "去充值" }), "充值功能建设中");
  await expectToast(page.locator(".dashboard-account__avatar"), "账户中心功能建设中");
  await page.getByRole("button", { name: "关闭提示" }).click();
  check(await page.getByRole("status").count() === 0, "关闭提示后 Toast 移除 DOM");

  await page.getByRole("button", { name: "关闭促销信息" }).click();
  check(await page.locator("[data-dashboard-banner]").count() === 0, "Banner 关闭后移除 DOM");

  await page.getByRole("link", { name: "影创工坊" }).click();
  await page.waitForURL(`${baseUrl}/`);
  await page.goBack();
  await page.waitForURL(`${baseUrl}/dashboard`);
  await page.getByRole("heading", { name: "工作台概览" }).waitFor();

  if (failures.length > 0) throw new Error(`工作台访问存在浏览器错误:\n${failures.join("\n")}`);
} finally {
  await browser.close();
}

console.log("工作台结构与交互验收通过");
