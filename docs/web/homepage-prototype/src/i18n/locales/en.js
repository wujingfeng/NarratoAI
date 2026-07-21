import { zhCN } from "./zh-CN.js";

const translations = new Map([
  ["影创工坊", "影创工坊"], ["语言", "Language"], ["简体中文", "English"], ["登录", "Log in"], ["打开菜单", "Open menu"], ["关闭菜单", "Close menu"],
  ["返回首页", "Back to home"], ["主导航", "Primary navigation"], ["移动端导航", "Mobile navigation"], ["产品能力", "Capabilities"], ["案例 Demo", "Demo"], ["价格", "Pricing"],
  ["价格页待接入", "Pricing page coming soon"], ["登录流程待接入", "Login flow coming soon"], ["登录影创工坊", "Log in to 影创工坊"],
  ["AI 视频创作 · 小白也能做专业视频", "AI video creation · Professional results for beginners"], ["专为自媒体小白打造的", "Built for first-time creators"], ["AI 出片工作台", "AI Video Workspace"],
  ["上传素材，AI 自动完成剪辑、文案、配音、字幕与合成。短剧解说、视频翻译、智能混剪，一个工作台搞定。", "Upload your footage and let AI handle editing, scripts, voice-over, subtitles, and production. Narration, translation, and remixing—all in one workspace."],
  ["上传素材，AI 自动完成剪辑、文案、配音、字幕与合成。", "Upload footage and let AI handle editing, scripts, voice-over, subtitles, and production."], ["开始创作", "Start creating"], ["查看案例", "View demos"],
  ["AI 处理流程", "AI workflow"], ["处理中", "Processing"], ["预计还需 30 秒完成", "About 30 seconds remaining"], ["识别剧情冲突", "Detect story conflicts"], ["分析剧情与节奏点", "Analyze plot and pacing"],
  ["提取高光片段", "Extract highlights"], ["定位高能情绪瞬间", "Find emotional peaks"], ["生成解说文案", "Generate narration"], ["匹配风格与配音", "Match style and voice"], ["配音字幕合成", "Synthesize voice and captions"], ["声音与字幕自动对齐", "Auto-align voice and captions"],
  ["都市短剧成片预览", "Urban short-drama preview"], ["命运的", "A Twist of"], ["反转", "Fate"], ["这一刻，他终于", "At this moment, he finally"], ["发现自己爱上了她", "realized he had fallen for her"],
  ["短剧解说", "Short-drama narration"], ["加旁白讲剧情", "Tell the story with voice-over"], ["视频翻译", "Video translation"], ["多语言翻译配音", "Multilingual dubbing"], ["短剧混剪", "Short-drama remix"], ["智能提取高能片段", "Smart highlight extraction"],
  ["AI 智能提取", "AI extraction"], ["高能片段", "Highlights"], ["自动配音字幕", "Auto voice and captions"], ["一键合成", "One-click production"], ["节奏快不拖沓", "Fast, focused pacing"], ["适配平台算法", "Optimized for platforms"], ["多格式导出", "Multi-format export"], ["高清无水印", "HD without watermarks"],
  ["视频片段", "Video clips"], ["解说文案", "Narration script"], ["配音音频", "Voice-over"], ["背景音乐", "Background music"], ["这场相遇…", "This encounter…"], ["命运的反转", "A twist of fate"], ["真相揭开", "Truth revealed"], ["新的开始", "A new beginning"],
  ["AI 视频出片工作台预览", "AI video workspace preview"], ["创作点", "Credits"], ["充值", "Top up"],
  ["看见", "See"], ["如何把素材变成成片", "turn footage into finished video"], ["小白不用懂剪辑，跟着流程就能完成", "No editing experience needed—just follow the workflow"], ["选择创作工具", "Choose a creation tool"],
  ["拖动查看{before}与{after}", "Drag to compare {before} and {after}"], ["播放案例：{title}", "Play demo: {title}"], ["{title}案例封面", "Cover for {title}"], ["使用相同模板创作", "Create with this template"],
  ["00:00–00:03", "00:00–00:03"], ["播放解说案例", "Play narration demo"], ["原始素材", "Original footage"], ["最终成片", "Final video"], ["原始剧情素材", "Original story footage"], ["AI 生成的短剧解说成片", "AI-generated narrated short drama"],
  ["跨越语言", "Across languages"], ["自然表达", "Natural expression"], ["保留人物语气", "Preserve each character's tone"], ["英文对白自然流畅", "Natural, fluent English dialogue"], ["高能", "Highlights"], ["混剪", "Remix"], ["保留原声 · 卡点转场", "Original audio · Beat transitions"], ["节奏与 BGM 自动匹配", "Automatic pacing and BGM matching"],
  ["上传剧集", "Upload episodes"], ["3 集素材已进入队列", "3 episodes added to the queue"], ["ASR/剧情拆解", "ASR / story analysis"], ["识别人物、对白与剧情冲突", "Identify characters, dialogue, and conflict"], ["筛选高光", "Select highlights"], ["按反转与情绪强度选出 8 段", "Select 8 clips by twists and emotion"], ["生成/润色解说词", "Generate / polish narration"], ["口语化重写并校准叙事节奏", "Rewrite naturally and refine pacing"], ["配音、字幕与画面自动对齐", "Auto-align voice, captions, and video"],
  ["中文 → EN", "Chinese → EN"], ["播放翻译案例", "Play translation demo"], ["中文原片", "Chinese original"], ["英文成片", "English version"], ["待翻译的中文原片", "Chinese source video"], ["完成英语本地化的视频成片", "English-localized final video"],
  ["识别中文对白", "Recognize Chinese dialogue"], ["区分角色并还原对白时间轴", "Identify speakers and restore timing"], ["翻译与本地化", "Translate and localize"], ["优化称谓、语气与文化表达", "Adapt names, tone, and cultural context"], ["角色声线映射", "Map character voices"], ["为每位角色匹配目标语音色", "Match each character to a target voice"], ["英文配音+双语字幕", "English dubbing + bilingual captions"], ["配音与双语字幕自动对齐", "Auto-align dubbing and bilingual captions"],
  ["12 个片段", "12 clips"], ["播放混剪案例", "Play remix demo"], ["原始剧集", "Original episodes"], ["高光混剪", "Highlight remix"], ["待处理的原始短剧片段", "Original short-drama clips"], ["保留原声并完成节奏转场的高光混剪", "Highlight remix with original audio and rhythmic transitions"],
  ["导入多集", "Import episodes"], ["12 集素材已建立镜头索引", "Shot index created for 12 episodes"], ["选择高光", "Choose highlights"], ["按冲突、反转与情绪强度排序", "Rank by conflict, twists, and emotion"], ["卡点拼接与混音", "Beat editing and mixing"], ["保留原声并匹配节拍与 BGM", "Keep original audio and match beats and BGM"],
  ["解说创作流程", "Narration workflow"], ["剧情理解完成 · 正在润色文案", "Story analysis complete · Polishing narration"], ["已上传素材队列", "Uploaded footage queue"], ["素材队列", "Footage queue"], ["3 集 · 08:46", "3 episodes · 08:46"], ["第 {number} 集", "Episode {number}"], ["已分析", "Analyzed"],
  ["剧情高点已定位", "Story peaks located"], ["反转 3 · 冲突 4 · 情绪峰值 5", "3 twists · 4 conflicts · 5 emotional peaks"], ["剧情与解说文案编辑", "Story and narration editor"], ["剧情理解", "Story analysis"], ["强钩子 · 00:00–00:03", "Strong hook · 00:00–00:03"], ["推荐", "Recommended"], ["96 字 · 预计 23 秒", "96 words · About 23 sec"], ["AI 润色", "AI polish"],
  ["视频输出摘要", "Video output summary"], ["视频输出", "Video output"], ["接近完成", "Almost done"], ["专业度评分", "Quality score"], ["节奏与钩子表现优秀", "Excellent pacing and hook"], ["前 3 秒强钩子", "Strong first-3-second hook"], ["冲突信息已前置", "Conflict moved up front"], ["自然女声 · 1.05x", "Natural female voice · 1.05x"], ["情绪强度已匹配", "Emotional intensity matched"], ["动态高亮字幕", "Dynamic highlighted captions"], ["安全区与断句已校准", "Safe area and line breaks calibrated"], ["BGM 自动闪避", "Automatic BGM ducking"], ["对白区域降低 8dB", "Dialogue sections lowered by 8 dB"],
  ["冷静女声", "Calm female voice"], ["低沉男声", "Deep male voice"], ["多语言本地化", "Multilingual localization"], ["已识别 3 位角色 · 86 条对白", "3 characters recognized · 86 lines"], ["翻译语言设置", "Translation language settings"], ["源语言", "Source language"], ["目标语言", "Target language"], ["视频翻译流程", "Video translation workflow"], ["双语视频预览", "Bilingual video preview"], ["中文短剧英文配音预览", "English-dubbed Chinese short-drama preview"], ["双语对白编辑", "Bilingual dialogue editor"], ["编辑{role}的译文", "Edit {role}'s translation"], ["3 / 3 已匹配", "3 / 3 matched"], ["试听{role}的英文声线", "Preview {role}'s English voice"], ["本地化检查完成", "Localization check complete"], ["专有名词、称谓和语气已优化", "Names, forms of address, and tone optimized"],
  ["高光混剪控制台", "Highlight remix console"], ["12 集 · 36:40 · 已选 8 个高能镜头", "12 episodes · 36:40 · 8 highlights selected"], ["短剧混剪流程", "Short-drama remix workflow"], ["高光片段池", "Highlight pool"], ["按强度排序", "Sorted by intensity"], ["冲突爆发", "Conflict erupts"], ["身份揭晓", "Identity revealed"], ["绝地反击", "Comeback"], ["情绪顶点", "Emotional peak"], ["高光混剪成片预览", "Highlight remix preview"], ["高光混剪 · 9:16", "Highlight remix · 9:16"], ["播放高光混剪", "Play highlight remix"], ["多轨混剪时间线", "Multitrack remix timeline"], ["画面", "Video"], ["原声", "Original audio"], ["BGM 与节拍控制", "BGM and beat controls"], ["BGM / 节拍", "BGM / Beats"], ["已同步", "Synced"], ["电子氛围 · 128 BPM", "Electronic ambience · 128 BPM"], ["播放背景音乐", "Play background music"], ["卡点强度", "Beat intensity"], ["原声音量", "Original volume"], ["BGM 音量", "BGM volume"], ["18 个节拍点", "18 beat points"], ["6 处转场", "6 transitions"], ["0 空拍", "0 empty beats"],
  ["霸总反转", "CEO twist"], ["反转密集", "Twist-packed"], ["情绪拉满", "High emotion"], ["高完播", "High completion"], ["悬疑真相局", "Suspense reveal"], ["强钩子", "Strong hook"], ["层层递进", "Rising tension"], ["沉浸旁白", "Immersive narration"], ["都市逆袭录", "Urban comeback"], ["冲突前置", "Conflict first"], ["节奏紧凑", "Tight pacing"], ["反转收尾", "Twist ending"], ["多语言出海", "Global multilingual launch"], ["多语翻译", "Multilingual"], ["本地配音", "Localized dubbing"], ["全球发行", "Global release"], ["短剧英语版", "English short drama"], ["英语配音", "English dubbing"], ["双语字幕", "Bilingual captions"], ["角色声线", "Character voices"], ["都市剧日语版", "Japanese urban drama"], ["日语本地化", "Japanese localization"], ["口型节奏", "Lip-sync timing"], ["字幕校准", "Caption calibration"], ["都市逆袭混剪", "Urban comeback remix"], ["燃点爆发", "Explosive energy"], ["高能混剪", "High-energy remix"], ["心动名场面", "Romantic highlights"], ["情绪峰值", "Emotional peaks"], ["保留原声", "Original audio"], ["氛围 BGM", "Atmospheric BGM"], ["电影感卡点", "Cinematic beat edit"], ["镜头卡点", "Beat-matched shots"], ["节奏转场", "Rhythmic transitions"], ["高光合集", "Highlight collection"],
  ["一个工作台，搞定", "One workspace for"], ["三种视频创作", "three video workflows"], ["选择目标，剩下的交给 AI 流程", "Choose your goal and let AI handle the workflow"], ["立即体验", "Try now"], ["小白也能做短剧号", "Launch a short-drama channel with ease"], ["高光片段 · 解说文案 · AI 配音 · 字幕 · BGM", "Highlights · Narration · AI voice · Captions · BGM"], ["让内容跨越语言", "Take content across languages"], ["字幕翻译 · 重新配音 · 双语字幕", "Caption translation · Redubbing · Bilingual captions"], ["不用懂剪辑", "No editing skills needed"], ["高光片段 · 保留原声 · BGM", "Highlights · Original audio · BGM"], ["上传素材", "Upload footage"], ["AI 分析", "AI analysis"], ["用户审核", "Review"], ["自动合成", "Auto production"], ["导出发布", "Export and publish"], ["小白可以沿用 AI 推荐，", "Beginners can follow AI recommendations,"], ["有经验也能逐步调整", "while experts can fine-tune every step"],
  ["常见问题", "Frequently asked questions"], ["没有字幕文件也能用吗？", "Can I use it without a subtitle file?"], ["可以。影创工坊会自动识别视频中的对白并生成时间轴字幕，你仍可在合成前校对。", "Yes. 影创工坊 recognizes dialogue and builds timed captions automatically, and you can review them before rendering."], ["生成前可以修改片段和文案吗？", "Can I edit clips and scripts before generation?"], ["可以。AI 先给出推荐片段、文案和节奏，你可以逐项替换、改写或调整顺序。", "Yes. AI recommends clips, narration, and pacing, and you can replace, rewrite, or reorder each item."], ["创作点如何计费？", "How are credits charged?"], ["原型中暂不接入真实计费；正式版本会在生成前透明展示预计创作点消耗。", "This prototype does not charge real credits. The production version will show the estimated cost before generation."], ["生成失败会扣费吗？", "Will failed generations use credits?"], ["失败任务不会按成功成片计费，正式规则会在任务记录中清晰展示。", "Failed tasks will not be billed as completed videos. The final policy will appear clearly in task history."],
  ["准备好完成你的第一条", "Ready to create your first"], ["AI 成片", "AI video"], ["了吗？", "?"], ["真实生成前会透明展示预计消耗", "Estimated usage is shown clearly before generation"], ["页脚导航", "Footer navigation"], ["用户协议", "Terms of service"], ["用户协议待接入", "Terms of service coming soon"], ["隐私政策", "Privacy policy"], ["隐私政策待接入", "Privacy policy coming soon"], ["关闭案例播放", "Close demo playback"], ["关闭案例", "Close demo"], ["播放", "Play"], ["暂停", "Pause"], ["{title}视频案例", "Video demo: {title}"], ["关闭提示", "Close notification"], ["常见问题与开始创作", "FAQ and start creating"],
  ["页面未找到", "Page not found"], ["你访问的页面不存在。", "The page you requested does not exist."], ["错误页面导航", "Error page navigation"], ["返回官网", "Back to website"], ["前往工作台", "Go to workspace"],
  ["影创工坊｜AI 出片工作台", "影创工坊 | AI Video Workspace"], ["工作台概览｜影创工坊", "Workspace overview | 影创工坊"], ["新建创作｜影创工坊", "New creation | 影创工坊"], ["我的项目｜影创工坊", "My projects | 影创工坊"], ["霸总短剧解说 01｜影创工坊", "CEO short-drama narration 01 | 影创工坊"], ["短剧解说设置｜影创工坊", "Narration settings | 影创工坊"], ["AI 分析｜影创工坊", "AI analysis | 影创工坊"], ["解说编辑器｜影创工坊", "Narration editor | 影创工坊"], ["页面未找到｜影创工坊", "Page not found | 影创工坊"],
]);

translations.set('{title} · 项目结果', '{title} · Project result');
translations.set('生成完成', 'Generated');
translations.set('识别视频内容', 'Recognize video content');
translations.set('开始识别视频内容', 'Started recognizing video content');
translations.set('AI 已提取 8 个高光片段', 'AI extracted 8 highlights');
translations.set('解说文案生成完成', 'Narration script generated');
translations.set('配音与字幕合成完成', 'Voice and captions synthesized');
translations.set('视频导出完成', 'Video export completed');
translations.set('AI 分析', 'AI analysis');
translations.set('文案生成', 'Script generation');
translations.set('配音合成', 'Voice synthesis');
translations.set('视频渲染', 'Video rendering');
translations.set('源视频 3 集 · 08:42', '3 source episodes · 08:42');
translations.set('成片 01:25', 'Final video 01:25');
translations.set('面包屑', 'Breadcrumb');
translations.set('导出视频', 'Export video');
translations.set('下载字幕', 'Download subtitles');
translations.set('分享项目', 'Share project');
translations.set('再次编辑', 'Edit again');
translations.set('任务步骤', 'Task steps');
translations.set('全部完成', 'All complete');
translations.set('操作日志', 'Operation log');
translations.set('创作点消耗', 'Credits used');
translations.set('总计 {count} 创作点', '{count} credits total');
translations.set('项目摘要', 'Project summary');
translations.set('项目类型', 'Project type');
translations.set('{title} 成片', 'Final video for {title}');
translations.set('播放视频', 'Play video');
translations.set('暂停视频', 'Pause video');
translations.set('视频播放进度', 'Video playback progress');
translations.set('静音', 'Mute');
translations.set('取消静音', 'Unmute');
translations.set('全屏播放', 'Play fullscreen');
translations.set('当前浏览器暂不支持全屏播放', 'Fullscreen playback is not supported in this browser');
translations.set('分享链接已准备（原型）', 'Share link is ready (prototype)');
translations.set('再次编辑流程建设中', 'Editing again is coming soon');
translations.set('短剧解说设置参数', 'Short-drama narration settings');
translations.set('返回短剧解说', 'Back to short-drama narration');
translations.set('重命名项目', 'Rename project');
translations.set('已自动保存', 'Autosaved');
translations.set('短剧解说制作进度', 'Short-drama narration progress');
translations.set('设置参数', 'Set parameters');
translations.set('编辑片段', 'Edit clips');
translations.set('配音字幕', 'Voice and captions');
translations.set('高能反转', 'High-impact twists');
translations.set('节奏紧凑，反转不断\n抓住观众注意力', 'Fast-paced with constant twists\nKeep viewers engaged');
translations.set('悬疑推进', 'Building suspense');
translations.set('层层递进，悬念引导\n保持观众好奇心', 'Layered suspense and intrigue\nKeep viewers curious');
translations.set('情感共鸣', 'Emotional resonance');
translations.set('情感饱满，代入共情\n引发观众共鸣', 'Rich emotion and empathy\nConnect with viewers');
translations.set('轻松吐槽', 'Casual commentary');
translations.set('幽默解说，轻松有趣\n适合休闲观看', 'Humorous, light, and fun\nGreat for casual viewing');
translations.set('跟随首个视频 9:16', 'Follow first video 9:16');
translations.set('霓虹描边', 'Neon outline');
translations.set('经典白字', 'Classic white');
translations.set('黑底描边', 'Dark outline');
translations.set('解说设置', 'Narration settings');
translations.set('选择解说风格', 'Choose narration style');
translations.set('视频比例', 'Video ratio');
translations.set('配音角色', 'Voice character');
translations.set('沉稳男声 · 顾言', 'Calm male voice · Gu Yan');
translations.set('试听', 'Preview');
translations.set('更换', 'Change');
translations.set('字幕样式', 'Caption style');
translations.set('更多要求（可选）', 'More requirements (optional)');
translations.set('更多要求', 'More requirements');
translations.set('例如：开头 3 秒直接抛出反转，全程不要拖沓', 'Example: Open with the twist in the first 3 seconds and keep the pacing tight');
translations.set('效果预览', 'Effect preview');
translations.set('旁白配音中', 'Voice-over active');
translations.set('字幕已开启', 'Captions on');
translations.set('安全区', 'Safe area');
translations.set('短剧画面预览', 'Short-drama scene preview');
translations.set('他一步步', 'Step by step, he rose');
translations.set('走向权力的巅峰', 'to the pinnacle of power');
translations.set('预览轮播', 'Preview carousel');
translations.set('源视频', 'Source video');
translations.set('预计成片约', 'Estimated final video');
translations.set('预计消耗', 'Estimated usage');
translations.set('{count} 创作点', '{count} credits');
translations.set('上一步', 'Previous');
translations.set('使用当前设置，开始 AI 分析', 'Start AI analysis with current settings');
translations.set('重命名功能建设中', 'Renaming is coming soon');
translations.set('正在试听沉稳男声', 'Previewing the calm male voice');
translations.set('配音角色选择功能建设中', 'Voice selection is coming soon');
translations.set('短剧解说 AI 分析', 'Short-drama narration AI analysis');
translations.set('返回短剧解说设置', 'Back to narration settings');
translations.set('正在理解剧情并提取高光', 'Understanding the story and extracting highlights');
translations.set('AI 分析进度 {progress}%', 'AI analysis progress: {progress}%');
translations.set('预计还需约 45 秒', 'About 45 seconds remaining');
translations.set('整体进度', 'Overall progress');
translations.set('持续分析中', 'Analysis continuing');
translations.set('字幕识别', 'Caption recognition');
translations.set('剧情结构理解', 'Story structure');
translations.set('冲突与爽点定位', 'Conflict and payoff detection');
translations.set('高光片段评分', 'Highlight scoring');
translations.set('进行中', 'In progress');
translations.set('等待中', 'Waiting');
translations.set('素材概览', 'Footage overview');
translations.set('{count} 集视频', '{count} episodes');
translations.set('总时长', 'Total duration');
translations.set('视频素材列表', 'Video footage list');
translations.set('向左滚动素材', 'Scroll footage left');
translations.set('向右滚动素材', 'Scroll footage right');
translations.set('全屏播放 {episode}', 'Play {episode} fullscreen');
translations.set('已发现', 'Discovered');
translations.set('人物', 'Characters');
translations.set('剧情转折', 'Plot turns');
translations.set('候选高光', 'Highlight candidates');
translations.set('任务日志', 'Task log');
translations.set('开始读取视频素材', 'Started reading video footage');
translations.set('字幕识别完成', 'Caption recognition completed');
translations.set('已合并 3 集剧情时间线', 'Merged the timeline for 3 episodes');
translations.set('已识别主要人物关系', 'Identified main character relationships');
translations.set('正在定位剧情冲突与爽点', 'Locating story conflicts and payoffs');
translations.set('返回项目列表', 'Back to projects');
translations.set('下一步：编辑片段 →', 'Next: Edit clips →');
translations.set('{episode} 全屏播放', 'Fullscreen playback: {episode}');
translations.set('关闭全屏播放', 'Close fullscreen playback');
translations.set('播放上一个视频', 'Play previous video');
translations.set('播放下一个视频', 'Play next video');
translations.set('播放或暂停', 'Play or pause');
translations.set('{current} / {total} · 使用左右按钮切换视频', '{current} / {total} · Use the left and right buttons to switch videos');

translations.set('霸总短剧解说 01｜影创工坊', '霸总短剧解说 01 | 影创工坊');

translations.set('我的项目', 'My projects');
translations.set('创建时间', 'Created');
translations.set('导出', 'Export');
translations.set('已完成', 'Complete');

function localize(value) {
  if (typeof value === "string") return translations.get(value) ?? value;
  return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, localize(child)]));
}

const localized = localize(zhCN);
export const en = {
  ...localized,
  dashboard: {
    routeHeading: "Workspace overview", footer: "影创工坊 · Make AI creation simple", thumbnailUnavailable: "Thumbnail unavailable for {name}", thumbnailAlt: "Thumbnail for {name}", coverAlt: "Cover for {name}",
    nav: { overview: "Workspace overview", create: "New creation", projects: "My projects", narration: "Short-drama narration", translation: "Video translation", remix: "Short-drama remix", credits: "Credits", account: "Account" },
    mobile: { navigation: "Mobile workspace navigation", overview: "Overview", create: "Create", projects: "Projects", account: "Me" },
    sidebar: { navigation: "Workspace navigation", tools: "Tools", account: "Account" },
    header: { home: "影创工坊 home", accountActions: "Account quick actions", viewBalance: "View credit balance: {balance}", recharge: "Top up" },
    membership: { title: "Upgrade membership", description: "Unlock more tools and create faster" },
    creation: { eyebrow: "Start a new AI creation", title: "New creation", description: "Upload footage and follow the guided workflow" },
    workspaceHero: { eyebrow: "NARRATO AI WORKSPACE", title: "Turn every spark into a real piece of work", description: "From the first frame to the final line, create with AI at your side.", action: "Start exploring" },
    creationSection: { eyebrow: "CREATE WITH AI", title: "Start creating" },
    creationEntries: { narration: { title: "Drama narration", description: "Give every story a sharper rhythm" }, translation: { title: "Video translation", description: "Let your stories cross languages" }, remix: { title: "Highlight remix", description: "Make standout moments into work" } },
    featuredTools: { eyebrow: "FEATURED TOOLS", title: "AI featured tools", image: { title: "AI image", description: "Generate visual ideas from a sentence" }, video: { title: "AI video", description: "Turn an idea into motion quickly" }, voice: { title: "AI voice", description: "Natural voices tuned to the mood" } },
    cases: { eyebrow: "FEATURED CASES", title: "Featured cases", viewAll: "View all", reversal: { title: "A twist of fate", meta: "Drama narration · 12k creations" }, action: { title: "Against the wind", meta: "Highlight remix · Rhythm template" }, romance: { title: "A heartbeat moment", meta: "AI image · Mood storytelling" }, urban: { title: "A new city chapter", meta: "AI video · Finished case" }, documentary: { title: "Seeing the real", meta: "Documentary · Voice-over creation" }, suspense: { title: "Under the mist", meta: "Suspense narration · Strong hook" } },
    quickStart: { eyebrow: "Choose a tool", title: "Quick start" },
    tools: { narration: { title: "Short-drama narration", description: "Understand the story and generate narration efficiently" }, translation: { title: "Video translation", description: "Handle multilingual captions and dubbing in one place" }, remix: { title: "Short-drama remix", description: "Extract highlights and build a remix automatically" } },
    promotion: { ariaLabel: "Promotion", eyebrow: "Limited-time creation boost", title: "Upgrade this week and get 20% extra credits", action: "View offer", close: "Close promotion" },
    recent: { eyebrow: "Recent activity", title: "Recent projects", viewAll: "View all", creditsUsed: "Used {count}" },
    status: { complete: "Complete", processing: "Processing {progress}%", draft: "Draft" },
    credits: { resource: "Account resources", title: "Credits", balance: "Current balance", monthlyUsed: "Used {count} credits this month", recharge: "Top up credits" },
    inspiration: { eyebrow: "Explore more", title: "Creative inspiration" },
    inspirations: { storytelling: { title: "Narration pacing guide", description: "Balance suspense, twists, and climaxes" }, creativeRemix: { title: "Trending remix ideas", description: "Find directions in recent popular themes" } },
    toast: { close: "Close notification" },
    unavailable: { translation: "Video translation is coming soon", remix: "Short-drama remix is coming soon", credits: "Credits are coming soon", account: "Account center is coming soon", narration: "Short-drama narration is coming soon", upgrade: "Membership upgrades are coming soon", creditDetails: "Credit details are coming soon", recharge: "Top-up is coming soon", rechargeCredits: "Credit top-up is coming soon", promotion: "This promotion is coming soon", allProjects: "All projects is coming soon", project: "{name} is coming soon", storytelling: "The narration pacing guide is coming soon", creativeRemix: "Trending remix ideas are coming soon", aiImage: "AI image is coming soon", aiVideo: "AI video is coming soon", aiVoice: "AI voice is coming soon", allCases: "Featured cases are coming soon", case: "Case details are coming soon" },
  },
  create: {
    routeHeading: "Create a new AI video", description: "Choose a creation type and upload footage", autosave: "Upload progress is saved automatically",
    types: { narration: { title: "Short-drama narration", description: "Tell the story with voice-over" }, translation: { title: "Video translation", description: "Translate and dub in multiple languages" }, remix: { title: "Short-drama remix", description: "Extract highlights without editing skills" } },
    typeSelector: { title: "Choose creation type", ariaLabel: "Creation type" },
    upload: { title: "Upload footage", chooseVideos: "Choose video files", addMore: "Add more", dragPrefix: "Drag videos here, or", chooseFile: "choose files", limits: "MP4 / MOV / AVI, up to 5 GB each, {count} files maximum", selectedVideos: "Selected videos", uploadSubtitle: "Upload subtitles for {name}", removeVideo: "Remove {name}" },
    subtitle: { matched: "SRT matched", aiRecognition: "Not uploaded; AI recognition will be used", pending: "Pending; AI recognition will be used", clickOrAi: "Upload subtitles or use AI recognition" },
    summary: { title: "Creation summary", duration: "Total source duration", estimated: "Estimated usage", balance: "Current balance", next: "Next: Set parameters" },
    messages: { invalidVideo: "Only MP4, MOV, or AVI files up to 5 GB are supported", maxVideos: "{type} supports up to {count} videos", tooMany: "{type} currently has {current} videos; the limit is {count}", settingsUnavailable: "Parameter settings are coming soon", invalidSubtitle: "Only SRT subtitle files up to 50 MB are supported" },
  },
  projects: {
    routeHeading: "My projects", heading: "My projects", description: "Manage every creation task and result", search: "Search project names", create: "New creation", notice: "You can leave while tasks process; progress is saved automatically",
    categories: { all: "All", narration: "Short-drama narration", translation: "Video translation", remix: "Short-drama remix" },
    status: { all: "All statuses", complete: "Complete", processing: "Processing", processingPercent: "Processing {progress}%", draft: "Draft", failed: "Generation failed" },
    filters: { ariaLabel: "Project filters", types: "Project types", status: "Filter by status" },
    table: { project: "Project", type: "Type", status: "Status", created: "Created", credits: "Credits", actions: "Actions", progress: "{name} progress: {progress}%" },
    actions: { result: "View result", export: "Export", progress: "View progress", continue: "Continue editing", reason: "View reason", retry: "Generate again" },
    empty: { title: "No matching projects", description: "Change the filters or start a new creation" },
    pagination: { ariaLabel: "Project pagination", previous: "Previous page", next: "Next page", page: "Page {page}", perPage: "{count} per page" },
    messages: { unavailable: "{name}: {action} is coming soon", pageChanged: "Switched to page {page}" },
  },
  editor: {
    routeHeading: "Multitrack narration editor", mobileNotice: "Use a desktop to fine-tune the multitrack edit",
    topbar: { back: "Back", backAria: "Back to analysis", editing: "Editing", autosaved: "Autosaved", undo: "Undo", redo: "Redo", credits: "Credits", saveDraft: "Save draft", generate: "Generate video" },
    clips: { highlights: "{count} highlight clips", recommend: "Recommend again", highEnergy: "Energy", add: "Add clip" },
    tabs: { script: "Narration script", subtitle: "Voice captions", bgm: "Background music" },
    script: { current: "Current clip script", input: "Edit the current clip script", characters: "{count} characters", rewrite: "AI rewrite", style: "Script style", styles: { reversal: "High-impact twist", suspense: "Build suspense" } },
    settings: { summary: "Quick settings summary", voiceRole: "Voice role", volume: "Volume {value}%", volumeControl: "Adjust voice-over volume", speed: "Speed {value}×", speedControl: "Adjust voice-over speed", subtitleStyle: "Caption style", backgroundMusic: "Background music", edit: "Edit", editVoiceRole: "Edit voice role", editSubtitleStyle: "Edit caption style", editBackgroundMusic: "Edit background music" },
    presets: { voiceRole: "Steady male voice · Gu Yan", subtitleStyle: "Neon outline", bgmStyle: "Epic ambience" },
    subtitle: { title: "Subtitle file content", locked: "Timeline locked; text editing only", cue: "Edit the caption at {time}" },
    bgm: { title: "Background music", currentFile: "Current file: {file}", reselect: "Choose and upload music again", hint: "The prototype saves this selection; the backend reads the uploaded file on export." },
    preview: { ariaLabel: "Video preview", safeArea: "Safe area", progress: "Preview playback progress", start: "Jump to start", backOne: "Back one second", play: "Play", pause: "Pause", forwardOne: "Forward one second", end: "Jump to end", volume: "Volume", speed: "Playback speed", fullscreen: "Fullscreen preview" },
    timeline: { ariaLabel: "Multitrack timeline", noOverlap: "Clips cannot overlap", zoomOut: "Zoom timeline out", zoom: "Timeline zoom", zoomIn: "Zoom timeline in", trimStart: "Trim start", trimEnd: "Trim end", tracks: { video: "Video clips", script: "Narration script", voice: "Voice-over audio", bgm: "Background music" } },
    waveform: { voicePreview: "Voice preview", bgmWaveform: "Background music waveform" },
    messages: { draftSaved: "Draft saved", clipsRecommended: "Clips recommended again", rewriteReady: "AI rewrite generated" },
    content: { projectName: "霸总短剧解说 01", defaultCaption: "精绝古城的谜团，正在镜头中一点点揭开。" },
  },
};
