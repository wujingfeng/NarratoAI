import { chromium } from "playwright";

const baseUrl = process.env.BASE_URL || "http://127.0.0.1:4173/";
const executablePath = process.env.CHROME_PATH || "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await chromium.launch({ executablePath, headless: true });
const failures = [];

function check(condition, message, details = "") {
  if (!condition) failures.push(`${message}${details ? ` — ${details}` : ""}`);
}

async function ready(page, viewport) {
  await page.setViewportSize(viewport);
  await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
  await page.evaluate(() => document.fonts?.ready);
  await page.waitForTimeout(450);
}

async function inspectDesktop(width, height) {
  const page = await browser.newPage();
  await ready(page, { width, height });

  const metrics = await page.evaluate(() => {
    const copy = document.querySelector(".hero-copy").getBoundingClientRect();
    const titleLines = [...document.querySelectorAll(".hero-copy h1 > *")]
      .map((node) => node.getBoundingClientRect());
    const workbench = document.querySelector(".hero-workbench").getBoundingClientRect();
    const reflection = document.querySelector(".hero-workbench__reflection").getBoundingClientRect();
    const reflectionStyle = getComputedStyle(document.querySelector(".hero-workbench__reflection"));
    const wrap = document.querySelector(".hero-workbench-wrap");
    const wrapStyle = getComputedStyle(wrap);
    const mirrorFloor = document.querySelector(".hero-mirror-floor");
    const mirrorFloorStyle = mirrorFloor ? getComputedStyle(mirrorFloor) : null;
    const virtualFrame = getComputedStyle(wrap, "::before");
    const projectionGlow = getComputedStyle(wrap, "::after");
    const titleStyle = getComputedStyle(document.querySelector(".hero-copy h1 span"));
    const workbenchStyle = getComputedStyle(document.querySelector(".hero-workbench"));
    const rootStyle = getComputedStyle(document.documentElement);
    const floorStyle = getComputedStyle(document.querySelector(".hero-grid-floor"));
    const loader = document.querySelector(".analysis-step__loader");
    const loaderStyle = loader ? getComputedStyle(loader) : null;
    let authoredWorkbenchTransform = "";
    for (const sheet of document.styleSheets) {
      for (const rule of sheet.cssRules) {
        if (rule.selectorText === ".hero-workbench-wrap") {
          authoredWorkbenchTransform = rule.style.transform;
          break;
        }
      }
      if (authoredWorkbenchTransform) break;
    }

    return {
      copyRight: copy.right,
      copyTop: copy.top,
      copyBottom: copy.bottom,
      titleRight: Math.max(...titleLines.map((line) => line.right)),
      workbenchLeft: workbench.left,
      workbenchRight: workbench.right,
      workbenchTop: workbench.top,
      workbenchBottom: workbench.bottom,
      reflectionHeight: reflection.height,
      reflectionBackground: reflectionStyle.backgroundImage,
      reflectionFilter: reflectionStyle.filter,
      pageWidth: document.documentElement.scrollWidth,
      viewportWidth: innerWidth,
      titleAnimationName: titleStyle.animationName,
      titleAnimationDuration: titleStyle.animationDuration,
      virtualFrameContent: virtualFrame.content,
      virtualFramePadding: virtualFrame.paddingTop,
      virtualFrameBackground: virtualFrame.backgroundImage,
      virtualFrameBackgroundColor: virtualFrame.backgroundColor,
      virtualFrameBorder: virtualFrame.borderTopWidth,
      projectionBorder: projectionGlow.borderTopWidth,
      projectionFilter: projectionGlow.filter,
      transformStyle: wrapStyle.transformStyle,
      tiltY: wrapStyle.getPropertyValue("--hero-tilt-y").trim(),
      boxReflect: workbenchStyle.webkitBoxReflect,
      mirrorFloorExists: Boolean(mirrorFloor),
      mirrorFloorHeight: mirrorFloor?.getBoundingClientRect().height || 0,
      mirrorFloorBackground: mirrorFloorStyle?.backgroundImage || "none",
      mirrorLayerCount: mirrorFloor?.children.length || 0,
      workbenchShadow: workbenchStyle.boxShadow,
      authoredWorkbenchTransform,
      floorBackground: floorStyle.backgroundImage,
      floorTransform: floorStyle.transform,
      loaderAnimationName: loaderStyle?.animationName || "",
      loaderAnimationDuration: loaderStyle?.animationDuration || "",
      loaderBorderTopColor: loaderStyle?.borderTopColor || "",
      pageBackground: rootStyle.getPropertyValue("--bg-page").trim(),
      blueToken: rootStyle.getPropertyValue("--blue").trim(),
      violetToken: rootStyle.getPropertyValue("--violet").trim(),
      orangeToken: rootStyle.getPropertyValue("--orange").trim(),
    };
  });

  const minimumGap = width >= 1600 ? 36 : 20;
  const overlapsVertically = Math.max(metrics.copyTop, metrics.workbenchTop)
    < Math.min(metrics.copyBottom, metrics.workbenchBottom);
  if (overlapsVertically) {
    check(
      metrics.titleRight + minimumGap <= metrics.workbenchLeft,
      `${width}px 标题与工作台需要至少 ${minimumGap}px 间距`,
      `titleRight=${metrics.titleRight.toFixed(1)}, workbenchLeft=${metrics.workbenchLeft.toFixed(1)}`,
    );
    check(
      metrics.copyRight <= metrics.workbenchLeft,
      `${width}px 文案布局盒不得侵入工作台`,
      `copyRight=${metrics.copyRight.toFixed(1)}, workbenchLeft=${metrics.workbenchLeft.toFixed(1)}`,
    );
  } else {
    check(
      metrics.workbenchTop >= metrics.copyBottom + 12,
      `${width}px 堆叠布局需保留纵向间距`,
      `copyBottom=${metrics.copyBottom.toFixed(1)}, workbenchTop=${metrics.workbenchTop.toFixed(1)}`,
    );
  }
  check(metrics.pageWidth <= metrics.viewportWidth + 1, `${width}px 页面不得出现横向溢出`);
  check(
    metrics.workbenchRight <= metrics.viewportWidth - 12,
    `${width}px 工作台主体必须完整显示`,
    `workbenchRight=${metrics.workbenchRight.toFixed(1)}, viewport=${metrics.viewportWidth}`,
  );

  if (width >= 1600) {
    check(metrics.titleAnimationName.includes("hero-title-sweep"), "标题必须启用 hero-title-sweep 扫光动画");
    check(metrics.titleAnimationDuration === "5s", "标题扫光周期必须为 5s", metrics.titleAnimationDuration);
    check(metrics.virtualFrameContent !== "none" && metrics.virtualFrameContent !== "normal", "工作台必须具有结构化虚拟边框");
    check(metrics.virtualFramePadding === "2px", "虚拟边框必须使用 2px 渐变描边", metrics.virtualFramePadding);
    check(metrics.virtualFrameBackground !== "none", "虚拟边框必须具有渐变光色");
    check(metrics.virtualFrameBackgroundColor === "rgba(0, 0, 0, 0)", "虚拟边框不得使用实体背板", metrics.virtualFrameBackgroundColor);
    check(metrics.virtualFrameBorder === "0px", "虚拟边框不得通过第二层矩形边框伪造堆叠", metrics.virtualFrameBorder);
    check(metrics.projectionBorder === "0px", "投影层不得绘制第二块面板边框", metrics.projectionBorder);
    check(metrics.projectionFilter !== "none", "单面板 3D 必须具有体积投影", metrics.projectionFilter);
    check(metrics.transformStyle === "preserve-3d", "工作台容器必须保留 3D 层级", metrics.transformStyle);
    check(metrics.tiltY === "-11deg", "桌面工作台 Y 轴倾角必须增强至 -11deg", metrics.tiltY || "unset");
    check(metrics.reflectionHeight >= 70, "地面镜面反射可见高度不得小于 70px", `${metrics.reflectionHeight.toFixed(1)}px`);
    check(metrics.reflectionBackground.includes("repeating-linear-gradient"), "镜面反射必须包含可辨识的时间线纹理");
    check(metrics.reflectionFilter.includes("blur(2px)"), "镜面主体必须保持清晰轮廓，不能退化为模糊光斑", metrics.reflectionFilter);
    check(metrics.boxReflect && metrics.boxReflect !== "none", "工作台必须具有真实渐隐镜像反射");
    check(metrics.mirrorFloorExists, "Hero 必须具有整区赛博镜面地台");
    check(metrics.mirrorFloorHeight >= 280, "Hero 镜面地台高度不得小于 280px", `${metrics.mirrorFloorHeight.toFixed(1)}px`);
    check(metrics.mirrorFloorBackground !== "none", "Hero 镜面地台必须具有镜面渐变");
    check(metrics.mirrorLayerCount >= 2, "Hero 镜面地台必须包含文案与工作台反射层", `${metrics.mirrorLayerCount}`);
    check(metrics.pageBackground === "#10131c", "页面背景色必须严格使用 #10131c", metrics.pageBackground);
    check(metrics.blueToken === "#4096ff", "蓝色 token 必须严格使用 #4096ff", metrics.blueToken);
    check(metrics.violetToken === "#992bff", "紫色 token 必须严格使用 #992bff", metrics.violetToken);
    check(metrics.orangeToken === "#ff9922", "橙色 token 必须严格使用 #ff9922", metrics.orangeToken);
    check(metrics.authoredWorkbenchTransform.includes("perspective(1200px)"), "工作台透视必须使用 perspective(1200px)", metrics.authoredWorkbenchTransform);
    check(metrics.authoredWorkbenchTransform.includes("rotateY(-7deg)"), "工作台主倾角必须使用 rotateY(-7deg)", metrics.authoredWorkbenchTransform);
    check(metrics.workbenchShadow.includes("64, 150, 255"), "霓虹阴影必须包含 #4096ff 蓝光");
    check(metrics.workbenchShadow.includes("153, 43, 255"), "霓虹阴影必须包含 #992bff 紫光");
    check(metrics.workbenchShadow.includes("0px 0px 8px"), "霓虹阴影必须具有近距离光晕层", metrics.workbenchShadow);
    check(metrics.workbenchShadow.includes("0px 0px 22px"), "霓虹阴影必须具有中距离扩散层", metrics.workbenchShadow);
    check(metrics.workbenchShadow.includes("0px 0px 48px"), "霓虹阴影必须具有远距离扩散层", metrics.workbenchShadow);
    check(metrics.floorBackground.includes("64, 150, 255"), "透视网格必须使用 #4096ff 蓝色线条");
    check(metrics.loaderAnimationName.includes("analysis-loader-spin"), "加载环必须使用 CSS keyframes 动画", metrics.loaderAnimationName);
    check(metrics.loaderAnimationDuration === "1.1s", "加载环动画周期必须为 1.1s", metrics.loaderAnimationDuration);
    check(metrics.loaderBorderTopColor === "rgb(64, 150, 255)", "加载环主色必须为 #4096ff", metrics.loaderBorderTopColor);
  }

  await page.close();
  return metrics;
}

const desktop1920 = await inspectDesktop(1920, 1080);
const desktop1487 = await inspectDesktop(1487, 1058);
const desktop1200 = await inspectDesktop(1200, 900);
const desktop1024 = await inspectDesktop(1024, 820);

const mobile = await browser.newPage();
await ready(mobile, { width: 390, height: 844 });
const mobileMetrics = await mobile.evaluate(() => ({
  pageWidth: document.documentElement.scrollWidth,
  viewportWidth: innerWidth,
  titleWhiteSpace: getComputedStyle(document.querySelector(".hero-copy h1 span")).whiteSpace,
}));
check(mobileMetrics.pageWidth <= mobileMetrics.viewportWidth + 1, "390px 页面不得出现横向溢出");
check(mobileMetrics.titleWhiteSpace === "nowrap", "移动端标题保持既定单行构图");
await mobile.close();

const reduced = await browser.newPage();
await reduced.emulateMedia({ reducedMotion: "reduce" });
await ready(reduced, { width: 1920, height: 1080 });
const reducedAnimation = await reduced.locator(".hero-copy h1 span").evaluate((node) => getComputedStyle(node).animationName);
check(reducedAnimation === "none", "减少动态效果模式下必须禁用标题扫光", reducedAnimation);
await reduced.close();

await browser.close();

if (failures.length) {
  console.error("Hero 验收失败：");
  failures.forEach((failure) => console.error(`- ${failure}`));
  process.exit(1);
}

console.log("Hero 验收通过：", {
  desktop1920,
  desktop1487,
  desktop1200,
  desktop1024,
  mobile: mobileMetrics,
  reducedAnimation,
});
