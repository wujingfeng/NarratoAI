import { zhCN } from "./zh-CN.js";

const translations = new Map([
  ["影创工坊", "影创工坊"], ["语言", "言語"], ["简体中文", "日本語"], ["登录", "ログイン"], ["打开菜单", "メニューを開く"], ["关闭菜单", "メニューを閉じる"],
  ["返回首页", "ホームに戻る"], ["主导航", "メインナビゲーション"], ["移动端导航", "モバイルナビゲーション"], ["产品能力", "製品機能"], ["案例 Demo", "事例 Demo"], ["价格", "料金"], ["价格页待接入", "料金ページは準備中です"], ["登录流程待接入", "ログイン機能は準備中です"], ["登录影创工坊", "影创工坊にログイン"],
  ["AI 视频创作 · 小白也能做专业视频", "AI 動画制作 · 初心者でもプロ品質"], ["专为自媒体小白打造的", "動画制作初心者のための"], ["AI 出片工作台", "AI 動画制作ワークスペース"],
  ["上传素材，AI 自动完成剪辑、文案、配音、字幕与合成。短剧解说、视频翻译、智能混剪，一个工作台搞定。", "素材をアップロードするだけで、AI が編集・台本・音声・字幕・合成を自動化。ショートドラマ解説、動画翻訳、スマートリミックスを一つのワークスペースで完結できます。"],
  ["上传素材，AI 自动完成剪辑、文案、配音、字幕与合成。", "素材をアップロードするだけで、AI が編集・台本・音声・字幕・合成を自動化します。"], ["开始创作", "制作を始める"], ["查看案例", "事例を見る"],
  ["AI 处理流程", "AI 処理フロー"], ["处理中", "処理中"], ["预计还需 30 秒完成", "完了まで約30秒"], ["识别剧情冲突", "物語の対立を検出"], ["分析剧情与节奏点", "物語とテンポを分析"], ["提取高光片段", "ハイライトを抽出"], ["定位高能情绪瞬间", "感情のピークを特定"], ["生成解说文案", "解説台本を生成"], ["匹配风格与配音", "スタイルと音声を最適化"], ["配音字幕合成", "音声と字幕を合成"], ["声音与字幕自动对齐", "音声と字幕を自動同期"],
  ["都市短剧成片预览", "都市ショートドラマの完成プレビュー"], ["命运的", "運命の"], ["反转", "逆転"], ["这一刻，他终于", "この瞬間、彼はついに"], ["发现自己爱上了她", "彼女を愛していると気づいた"],
  ["短剧解说", "ショートドラマ解説"], ["加旁白讲剧情", "ナレーションで物語を伝える"], ["视频翻译", "動画翻訳"], ["多语言翻译配音", "多言語翻訳と吹き替え"], ["短剧混剪", "ショートドラマリミックス"], ["智能提取高能片段", "見せ場をスマート抽出"], ["AI 智能提取", "AI スマート抽出"], ["高能片段", "ハイライト"], ["自动配音字幕", "音声・字幕を自動生成"], ["一键合成", "ワンクリック合成"], ["节奏快不拖沓", "無駄のないテンポ"], ["适配平台算法", "プラットフォームに最適化"], ["多格式导出", "多形式で書き出し"], ["高清无水印", "高画質・透かしなし"],
  ["视频片段", "映像クリップ"], ["解说文案", "解説台本"], ["配音音频", "ナレーション音声"], ["背景音乐", "BGM"], ["这场相遇…", "この出会い…"], ["命运的反转", "運命の逆転"], ["真相揭开", "真実が明らかに"], ["新的开始", "新たな始まり"], ["AI 视频出片工作台预览", "AI 動画制作ワークスペースのプレビュー"], ["创作点", "制作クレジット"], ["充值", "チャージ"],
  ["看见", "見る"], ["如何把素材变成成片", "が素材を完成動画に変える方法"], ["小白不用懂剪辑，跟着流程就能完成", "編集経験がなくても、フローに沿うだけで完成"], ["选择创作工具", "制作ツールを選択"], ["拖动查看{before}与{after}", "ドラッグして{before}と{after}を比較"], ["播放案例：{title}", "事例を再生：{title}"], ["{title}案例封面", "{title}の事例カバー"], ["使用相同模板创作", "同じテンプレートで制作"],
  ["播放解说案例", "解説事例を再生"], ["原始素材", "元素材"], ["最终成片", "完成動画"], ["原始剧情素材", "元の物語素材"], ["AI 生成的短剧解说成片", "AI が生成したショートドラマ解説動画"], ["上传剧集", "エピソードをアップロード"], ["3 集素材已进入队列", "3話をキューに追加済み"], ["ASR/剧情拆解", "ASR / 物語分析"], ["识别人物、对白与剧情冲突", "登場人物・セリフ・対立を認識"], ["筛选高光", "ハイライトを選定"], ["按反转与情绪强度选出 8 段", "逆転と感情の強さから8クリップを選定"], ["生成/润色解说词", "解説を生成・推敲"], ["口语化重写并校准叙事节奏", "自然な話し言葉に直しテンポを調整"], ["配音、字幕与画面自动对齐", "音声・字幕・映像を自動同期"],
  ["中文 → EN", "中国語 → EN"], ["播放翻译案例", "翻訳事例を再生"], ["中文原片", "中国語の元動画"], ["英文成片", "英語版"], ["待翻译的中文原片", "翻訳前の中国語動画"], ["完成英语本地化的视频成片", "英語ローカライズ済み動画"], ["识别中文对白", "中国語のセリフを認識"], ["区分角色并还原对白时间轴", "話者を判別しタイムラインを復元"], ["翻译与本地化", "翻訳とローカライズ"], ["优化称谓、语气与文化表达", "呼称・口調・文化表現を最適化"], ["角色声线映射", "キャラクター音声の割り当て"], ["为每位角色匹配目标语音色", "各キャラクターに対象音声を割り当て"], ["英文配音+双语字幕", "英語吹き替え＋二言語字幕"], ["配音与双语字幕自动对齐", "吹き替えと二言語字幕を自動同期"],
  ["12 个片段", "12クリップ"], ["播放混剪案例", "リミックス事例を再生"], ["原始剧集", "元エピソード"], ["高光混剪", "ハイライトリミックス"], ["待处理的原始短剧片段", "処理前のショートドラマ素材"], ["保留原声并完成节奏转场的高光混剪", "原音を残しテンポよく切り替えるハイライトリミックス"], ["导入多集", "複数話を読み込む"], ["12 集素材已建立镜头索引", "12話のショット索引を作成済み"], ["选择高光", "ハイライトを選択"], ["按冲突、反转与情绪强度排序", "対立・逆転・感情の強さで並べ替え"], ["卡点拼接与混音", "ビート編集とミックス"], ["保留原声并匹配节拍与 BGM", "原音を残してビートとBGMに同期"],
  ["解说创作流程", "解説制作フロー"], ["剧情理解完成 · 正在润色文案", "物語分析完了 · 台本を推敲中"], ["已上传素材队列", "アップロード済み素材キュー"], ["素材队列", "素材キュー"], ["3 集 · 08:46", "3話 · 08:46"], ["第 {number} 集", "第{number}話"], ["已分析", "分析済み"], ["剧情高点已定位", "物語のピークを特定済み"], ["反转 3 · 冲突 4 · 情绪峰值 5", "逆転 3 · 対立 4 · 感情ピーク 5"], ["剧情与解说文案编辑", "物語と解説台本の編集"], ["剧情理解", "物語分析"], ["强钩子 · 00:00–00:03", "強いフック · 00:00–00:03"], ["推荐", "おすすめ"], ["96 字 · 预计 23 秒", "96文字 · 約23秒"], ["AI 润色", "AI 推敲"], ["视频输出摘要", "動画出力サマリー"], ["视频输出", "動画出力"], ["接近完成", "まもなく完了"], ["专业度评分", "品質スコア"], ["节奏与钩子表现优秀", "テンポとフックが優秀"], ["前 3 秒强钩子", "冒頭3秒の強いフック"], ["冲突信息已前置", "対立情報を前方に配置"], ["自然女声 · 1.05x", "自然な女性音声 · 1.05x"], ["情绪强度已匹配", "感情の強さを調整済み"], ["动态高亮字幕", "動的ハイライト字幕"], ["安全区与断句已校准", "セーフエリアと改行を調整済み"], ["BGM 自动闪避", "BGM 自動ダッキング"], ["对白区域降低 8dB", "セリフ区間を8dB低減"],
  ["冷静女声", "落ち着いた女性音声"], ["低沉男声", "低音の男性音声"], ["多语言本地化", "多言語ローカライズ"], ["已识别 3 位角色 · 86 条对白", "3人を認識 · 86行のセリフ"], ["翻译语言设置", "翻訳言語の設定"], ["源语言", "元の言語"], ["目标语言", "対象言語"], ["视频翻译流程", "動画翻訳フロー"], ["双语视频预览", "二言語動画プレビュー"], ["中文短剧英文配音预览", "中国語ショートドラマの英語吹き替えプレビュー"], ["双语对白编辑", "二言語セリフ編集"], ["编辑{role}的译文", "{role}の訳文を編集"], ["3 / 3 已匹配", "3 / 3 割り当て済み"], ["试听{role}的英文声线", "{role}の英語音声を試聴"], ["本地化检查完成", "ローカライズ確認完了"], ["专有名词、称谓和语气已优化", "固有名詞・呼称・口調を最適化済み"],
  ["高光混剪控制台", "ハイライトリミックスコンソール"], ["12 集 · 36:40 · 已选 8 个高能镜头", "12話 · 36:40 · 8ショット選択済み"], ["短剧混剪流程", "ショートドラマリミックスフロー"], ["高光片段池", "ハイライトプール"], ["按强度排序", "強度順"], ["冲突爆发", "対立の勃発"], ["身份揭晓", "正体判明"], ["绝地反击", "逆転の反撃"], ["情绪顶点", "感情の頂点"], ["高光混剪成片预览", "ハイライトリミックスのプレビュー"], ["高光混剪 · 9:16", "ハイライトリミックス · 9:16"], ["播放高光混剪", "ハイライトリミックスを再生"], ["多轨混剪时间线", "マルチトラックリミックスタイムライン"], ["画面", "映像"], ["原声", "原音"], ["BGM 与节拍控制", "BGMとビートの調整"], ["BGM / 节拍", "BGM / ビート"], ["已同步", "同期済み"], ["电子氛围 · 128 BPM", "エレクトロニック · 128 BPM"], ["播放背景音乐", "BGMを再生"], ["卡点强度", "ビート強度"], ["原声音量", "原音音量"], ["BGM 音量", "BGM音量"], ["18 个节拍点", "18ビートポイント"], ["6 处转场", "6トランジション"], ["0 空拍", "空拍0"],
  ["霸总反转", "CEOの逆転"], ["反转密集", "逆転満載"], ["情绪拉满", "感情全開"], ["高完播", "高い完視聴率"], ["悬疑真相局", "サスペンスの真相"], ["强钩子", "強いフック"], ["层层递进", "高まる緊張"], ["沉浸旁白", "没入感のある語り"], ["都市逆袭录", "都会の逆転劇"], ["冲突前置", "対立を冒頭に"], ["节奏紧凑", "引き締まったテンポ"], ["反转收尾", "逆転エンド"], ["多语言出海", "多言語グローバル展開"], ["多语翻译", "多言語翻訳"], ["本地配音", "現地向け吹き替え"], ["全球发行", "世界配信"], ["短剧英语版", "ショートドラマ英語版"], ["英语配音", "英語吹き替え"], ["双语字幕", "二言語字幕"], ["角色声线", "キャラクター音声"], ["都市剧日语版", "都市ドラマ日本語版"], ["日语本地化", "日本語ローカライズ"], ["口型节奏", "リップシンク"], ["字幕校准", "字幕調整"], ["都市逆袭混剪", "都会の逆転リミックス"], ["燃点爆发", "熱量全開"], ["高能混剪", "高エネルギーリミックス"], ["心动名场面", "胸キュン名場面"], ["情绪峰值", "感情のピーク"], ["保留原声", "原音を保持"], ["氛围 BGM", "雰囲気BGM"], ["电影感卡点", "シネマティックビート編集"], ["镜头卡点", "ショットをビート同期"], ["节奏转场", "リズミカルな切り替え"], ["高光合集", "ハイライト集"],
  ["一个工作台，搞定", "一つのワークスペースで"], ["三种视频创作", "3つの動画制作"], ["选择目标，剩下的交给 AI 流程", "目的を選んだら、あとはAIフローにお任せ"], ["立即体验", "今すぐ試す"], ["小白也能做短剧号", "初心者でもショートドラマ運営"], ["高光片段 · 解说文案 · AI 配音 · 字幕 · BGM", "ハイライト · 解説台本 · AI音声 · 字幕 · BGM"], ["让内容跨越语言", "コンテンツを言語の壁の向こうへ"], ["字幕翻译 · 重新配音 · 双语字幕", "字幕翻訳 · 再吹き替え · 二言語字幕"], ["不用懂剪辑", "編集スキル不要"], ["高光片段 · 保留原声 · BGM", "ハイライト · 原音保持 · BGM"], ["上传素材", "素材をアップロード"], ["AI 分析", "AI分析"], ["用户审核", "ユーザー確認"], ["自动合成", "自動合成"], ["导出发布", "書き出して公開"], ["小白可以沿用 AI 推荐，", "初心者はAIのおすすめをそのまま使い、"], ["有经验也能逐步调整", "経験者は各工程を調整できます"],
  ["常见问题", "よくある質問"], ["没有字幕文件也能用吗？", "字幕ファイルがなくても使えますか？"], ["可以。影创工坊会自动识别视频中的对白并生成时间轴字幕，你仍可在合成前校对。", "はい。影创工坊が動画内のセリフを認識してタイムライン字幕を生成し、合成前に確認できます。"], ["生成前可以修改片段和文案吗？", "生成前にクリップや台本を修正できますか？"], ["可以。AI 先给出推荐片段、文案和节奏，你可以逐项替换、改写或调整顺序。", "はい。AIが提案したクリップ、台本、テンポを個別に差し替え、書き換え、並べ替えできます。"], ["创作点如何计费？", "制作クレジットはどのように消費されますか？"], ["原型中暂不接入真实计费；正式版本会在生成前透明展示预计创作点消耗。", "このプロトタイプでは実際の課金は行いません。正式版では生成前に予想消費量を明示します。"], ["生成失败会扣费吗？", "生成に失敗した場合も課金されますか？"], ["失败任务不会按成功成片计费，正式规则会在任务记录中清晰展示。", "失敗したタスクは完成動画として課金されません。正式なルールはタスク履歴に明示されます。"],
  ["准备好完成你的第一条", "最初の"], ["AI 成片", "AI動画"], ["了吗？", "を作る準備はできましたか？"], ["真实生成前会透明展示预计消耗", "生成前に予想消費量を明確に表示します"], ["页脚导航", "フッターナビゲーション"], ["用户协议", "利用規約"], ["用户协议待接入", "利用規約は準備中です"], ["隐私政策", "プライバシーポリシー"], ["隐私政策待接入", "プライバシーポリシーは準備中です"], ["关闭案例播放", "事例再生を閉じる"], ["关闭案例", "事例を閉じる"], ["播放", "再生"], ["暂停", "一時停止"], ["{title}视频案例", "{title}の動画事例"], ["关闭提示", "通知を閉じる"], ["常见问题与开始创作", "よくある質問と制作開始"],
  ["页面未找到", "ページが見つかりません"], ["你访问的页面不存在。", "指定されたページは存在しません。"], ["错误页面导航", "エラーページナビゲーション"], ["返回官网", "公式サイトに戻る"], ["前往工作台", "ワークスペースへ"],
  ["影创工坊｜AI 出片工作台", "影创工坊｜AI 動画制作ワークスペース"], ["登录｜影创工坊", "ログイン｜影创工坊"], ["注册｜影创工坊", "アカウント登録｜影创工坊"], ["重置密码｜影创工坊", "パスワード再設定｜影创工坊"], ["工作台概览｜影创工坊", "ワークスペース概要｜影创工坊"], ["新建创作｜影创工坊", "新規制作｜影创工坊"], ["我的项目｜影创工坊", "マイプロジェクト｜影创工坊"], ["项目结果｜影创工坊", "プロジェクト結果｜影创工坊"], ["编辑项目｜影创工坊", "プロジェクト編集｜影创工坊"], ["短剧解说设置｜影创工坊", "ショートドラマ解説設定｜影创工坊"], ["AI 分析｜影创工坊", "AI分析｜影创工坊"], ["解说编辑器｜影创工坊", "解説エディター｜影创工坊"], ["生成视频｜影创工坊", "動画生成｜影创工坊"], ["导出完成｜影创工坊", "書き出し完了｜影创工坊"], ["页面未找到｜影创工坊", "ページが見つかりません｜影创工坊"],
]);

translations.set('{title} · 项目结果', '{title} · プロジェクト結果');
translations.set('跨越语言', '言語を越えて');
translations.set('自然表达', '自然な表現');
translations.set('保留人物语气', '人物の口調を維持');
translations.set('英文对白自然流畅', '自然で流暢な英語セリフ');
translations.set('高能', 'ハイライト');
translations.set('混剪', 'リミックス');
translations.set('保留原声 · 卡点转场', '原音を保持 · ビート切り替え');
translations.set('节奏与 BGM 自动匹配', 'テンポと BGM を自動調整');
translations.set('生成完成', '生成完了');
translations.set('识别视频内容', '動画内容を認識');
translations.set('开始识别视频内容', '動画内容の認識を開始');
translations.set('解说文案生成完成', '解説台本の生成が完了');
translations.set('配音与字幕合成完成', '音声と字幕の合成が完了');
translations.set('视频导出完成', '動画の書き出しが完了');
translations.set('文案生成', '台本生成');
translations.set('配音合成', '音声合成');
translations.set('视频渲染', '動画レンダリング');
translations.set('面包屑', 'パンくずリスト');
translations.set('导出视频', '動画を書き出す');
translations.set('下载字幕', '字幕をダウンロード');
translations.set('分享项目', 'プロジェクトを共有');
translations.set('再次编辑', '再編集');
translations.set('任务步骤', 'タスク手順');
translations.set('全部完成', 'すべて完了');
translations.set('操作日志', '操作ログ');
translations.set('创作点消耗', 'クレジット使用量');
translations.set('总计 {count} 创作点', '合計 {count} クレジット');
translations.set('导出完成内容', 'エクスポート完了コンテンツ');
translations.set('功能操作区', '操作エリア');
translations.set('视频下载', '動画をダウンロード');
translations.set('字幕下载', '字幕をダウンロード');
translations.set('音频下载', '音声をダウンロード');
translations.set('时间线下载', 'タイムラインをダウンロード');
translations.set('预览', 'プレビュー');
translations.set('下载', 'ダウンロード');
translations.set('下载中…', 'ダウンロード中…');
translations.set('导出剪映', 'Jianying にエクスポート');
translations.set('正在导出剪映草稿…', 'Jianying 草稿をエクスポート中…');
translations.set('正在核验并读取已登记产物…', '登録成果物を確認・読み込み中…');
translations.set('项目摘要', 'プロジェクト概要');
translations.set('项目类型', 'プロジェクト種類');
translations.set('{title} 成片', '{title} の完成動画');
translations.set('播放视频', '動画を再生');
translations.set('暂停视频', '動画を一時停止');
translations.set('视频播放进度', '動画の再生進捗');
translations.set('静音', 'ミュート');
translations.set('取消静音', 'ミュート解除');
translations.set('全屏播放', '全画面再生');
translations.set('当前浏览器暂不支持全屏播放', 'このブラウザは全画面再生に対応していません');
translations.set('分享链接已准备（原型）', '共有リンクを準備しました（プロトタイプ）');
translations.set('再次编辑流程建设中', '再編集フローは準備中です');
translations.set('短剧解说设置参数', 'ショートドラマ解説の設定');
translations.set('短剧解说', 'ショートドラマ解説');
translations.set('返回短剧解说', 'ショートドラマ解説に戻る');
translations.set('重命名项目', 'プロジェクト名を変更');
translations.set('已自动保存', '自動保存済み');
translations.set('短剧解说制作进度', 'ショートドラマ解説の制作進捗');
translations.set('设置参数', 'パラメーター設定');
translations.set('编辑片段', 'クリップ編集');
translations.set('解说文案', '解説台本');
translations.set('配音字幕', '音声と字幕');
translations.set('导出', '書き出し');
translations.set('高能反转', '高インパクトな逆転');
translations.set('节奏紧凑，反转不断\n抓住观众注意力', 'テンポよく逆転を重ね\n視聴者を引きつけます');
translations.set('悬疑推进', 'サスペンス展開');
translations.set('层层递进，悬念引导\n保持观众好奇心', '段階的に謎を深め\n好奇心を維持します');
translations.set('情感共鸣', '感情への共鳴');
translations.set('情感饱满，代入共情\n引发观众共鸣', '豊かな感情と没入感で\n共感を生みます');
translations.set('轻松吐槽', '気軽なツッコミ');
translations.set('幽默解说，轻松有趣\n适合休闲观看', 'ユーモラスで楽しく\n気軽な視聴に最適です');
translations.set('跟随首个视频 9:16', '最初の動画に合わせる 9:16');
translations.set('霓虹描边', 'ネオン縁取り');
translations.set('经典白字', 'クラシック白文字');
translations.set('黑底描边', '黒背景の縁取り');
translations.set('解说设置', '解説設定');
translations.set('选择解说风格', '解説スタイルを選択');
translations.set('原片占比', '元映像の比率');
translations.set('按片段数量控制原声片段占比，默认 30%。', '元音声クリップの件数比率を指定します。既定値は30%です。');
translations.set('视频比例', '動画比率');
translations.set('配音角色', 'ナレーター');
translations.set('试听', '試聴');
translations.set('更换', '変更');
translations.set('字幕样式', '字幕スタイル');
translations.set('更多要求（可选）', '追加要件（任意）');
translations.set('更多要求', '追加要件');
translations.set('例如：开头 3 秒直接抛出反转，全程不要拖沓', '例：冒頭 3 秒で逆転を提示し、全編をテンポよくする');
translations.set('效果预览', '効果プレビュー');
translations.set('旁白配音中', 'ナレーション再生中');
translations.set('字幕已开启', '字幕オン');
translations.set('安全区', 'セーフエリア');
translations.set('短剧画面预览', 'ショートドラマ画面プレビュー');
translations.set('预览轮播', 'プレビューカルーセル');
translations.set('源视频', '元動画');
translations.set('预计成片约', '完成動画の目安');
translations.set('预计消耗', '推定消費量');
translations.set('{count} 创作点', '{count} クレジット');
translations.set('上一步', '前へ');
translations.set('使用当前设置，开始 AI 分析', '現在の設定で AI 分析を開始');
translations.set('正在保存并启动…', '保存して開始しています…');
translations.set('正在加载解说配置…', '解説設定を読み込んでいます…');
translations.set('重命名功能建设中', '名前変更機能は準備中です');
translations.set('配音角色选择功能建设中', 'ナレーター選択機能は準備中です');
translations.set('短剧解说 AI 分析', 'ショートドラマ解説 AI 分析');
translations.set('返回短剧解说设置', '解説設定に戻る');
translations.set('正在理解剧情并提取高光', 'ストーリーを理解してハイライトを抽出中');
translations.set('AI 分析进度 {progress}%', 'AI 分析進捗 {progress}%');
translations.set('预计还需约 45 秒', '残り約 45 秒');
translations.set('整体进度', '全体進捗');
translations.set('持续分析中', '分析を継続中');
translations.set('字幕识别', '字幕認識');
translations.set('剧情结构理解', 'ストーリー構造の理解');
translations.set('冲突与爽点定位', '対立と見せ場の特定');
translations.set('高光片段评分', 'ハイライト評価');
translations.set('已完成', '完了');
translations.set('进行中', '進行中');
translations.set('等待中', '待機中');
translations.set('素材概览', '素材概要');
translations.set('{count} 集视频', '動画 {count} 話');
translations.set('总时长', '合計時間');
translations.set('视频素材列表', '動画素材リスト');
translations.set('向左滚动素材', '素材を左へスクロール');
translations.set('向右滚动素材', '素材を右へスクロール');
translations.set('全屏播放 {episode}', '{episode} を全画面再生');
translations.set('已发现', '検出済み');
translations.set('人物', '登場人物');
translations.set('剧情转折', 'ストーリー転換');
translations.set('候选高光', 'ハイライト候補');
translations.set('任务日志', 'タスクログ');
translations.set('开始读取视频素材', '動画素材の読み込みを開始');
translations.set('字幕识别完成', '字幕認識が完了');
translations.set('已识别主要人物关系', '主な人物関係を特定');
translations.set('正在定位剧情冲突与爽点', 'ストーリーの対立と見せ場を特定中');
translations.set('返回项目列表', 'プロジェクト一覧に戻る');
translations.set('下一步：编辑片段 →', '次へ：クリップ編集 →');
translations.set('{episode} 全屏播放', '{episode} の全画面再生');
translations.set('关闭全屏播放', '全画面再生を閉じる');
translations.set('播放上一个视频', '前の動画を再生');
translations.set('播放下一个视频', '次の動画を再生');
translations.set('播放或暂停', '再生または一時停止');
translations.set('{current} / {total} · 使用左右按钮切换视频', '{current} / {total} · 左右のボタンで動画を切り替え');

translations.set('AI 分析｜影创工坊', 'AI 分析｜影创工坊');

translations.set('我的项目', 'マイプロジェクト');
translations.set('创建时间', '作成日時');
translations.set('制作模式', '制作モード');
translations.set('选择分析完成后是否进入人工编辑。', '分析後に手動編集へ進むか選択します。');
translations.set('手动模式', '手動モード');
translations.set('分析后进入编辑器，确认片段和文案再生成。', '分析後にエディターでクリップと台本を確認してから生成します。');
translations.set('自动模式', '自動モード');
translations.set('分析完成后自动冻结脚本、配音、字幕和音乐设置并生成成片。', '分析後に台本、音声、字幕、音楽設定を固定し、自動で動画を生成します。');
translations.set('使用当前设置，全自动生成', '現在の設定で自動生成');
translations.set('正在保存并启动自动生成…', '保存して自動生成を開始しています…');
translations.set('正在理解剧情并生成解说脚本', '物語を理解し、解説台本を生成しています');
translations.set('处理时间取决于素材总时长，可稍后返回查看。', '処理時間は素材の長さによって変わります。後で戻って確認できます。');
translations.set('生成解说文案', '解説台本を生成');
translations.set('暂未读取到可播放的视频素材', '再生できる動画素材はまだありません');
translations.set('素材与消耗', '素材と使用量');
translations.set('源视频预览', '元動画のプレビュー');
translations.set('尚未读取到可预览的源视频', 'プレビューできる元動画はまだありません');
translations.set('项目结果｜影创工坊', 'プロジェクト結果｜影创工坊');
translations.set('可用配音音色', '利用可能な音声');
translations.set('音色试听', '音声サンプル');
translations.set('该音色未提供试听', 'この音声にはサンプルがありません');
translations.set('当前浏览器不支持音频试听', 'このブラウザーでは音声サンプルを再生できません');
translations.set('解说核对｜影创工坊', '解説確認｜影创工坊');

function localize(value) {
  if (typeof value === "string") return translations.get(value) ?? value;
  return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, localize(child)]));
}

const localized = localize(zhCN);
export const ja = {
  ...localized,
  dashboard: {
    routeHeading: "ワークスペース概要", footer: "影创工坊 · AI制作をもっとシンプルに", thumbnailUnavailable: "{name}のサムネイルを表示できません", thumbnailAlt: "{name}のサムネイル", coverAlt: "{name}のカバー",
    nav: { overview: "ワークスペース概要", create: "新規制作", projects: "マイプロジェクト", narration: "ショートドラマ解説", translation: "動画翻訳", remix: "ショートドラマリミックス", credits: "制作クレジット", account: "アカウント" },
    mobile: { navigation: "モバイルワークスペースナビゲーション", overview: "概要", create: "新規", projects: "プロジェクト", account: "マイページ" },
    sidebar: { navigation: "ワークスペースナビゲーション", tools: "ツール", account: "アカウント" },
    header: { home: "影创工坊ホーム", accountActions: "アカウントのクイック操作", viewBalance: "制作クレジット残高 {balance}", recharge: "チャージ" },
    membership: { title: "メンバーシップをアップグレード", description: "機能を増やして、制作をさらに効率化" },
    creation: { eyebrow: "新しいAI制作を始める", title: "新規制作", description: "素材をアップロードしてガイドに沿って完成" },
    workspaceHero: { eyebrow: "NARRATO AI ワークスペース", title: "ひらめきを、本当の作品に", description: "最初のフレームから最後の一言まで、AI と一緒に制作します。", action: "探索を始める" },
    creationSection: { eyebrow: "CREATE WITH AI", title: "制作を始める" },
    creationEntries: { narration: { title: "ドラマ解説", description: "物語のテンポをもっと魅力的に" }, translation: { title: "動画翻訳", description: "コンテンツを言語の向こうへ" }, remix: { title: "ハイライトリミックス", description: "名場面を作品にする" } },
    featuredTools: { eyebrow: "FEATURED TOOLS", title: "AI 注目ツール", image: { title: "AI 画像", description: "一言からビジュアルを生成" }, video: { title: "AI 動画", description: "アイデアを素早く動画に" }, voice: { title: "AI 音声", description: "感情に合う自然な声" } },
    cases: { eyebrow: "FEATURED CASES", title: "注目の事例", viewAll: "すべて見る", reversal: { title: "運命の逆転", meta: "ドラマ解説 · 1.2万回制作" }, action: { title: "逆風からの逆転", meta: "ハイライトリミックス · テンプレート" }, romance: { title: "ときめきの瞬間", meta: "AI 画像 · ムードの物語" }, urban: { title: "都会の新章", meta: "AI 動画 · 完成事例" }, documentary: { title: "リアルを見る", meta: "ドキュメンタリー · ナレーション制作" }, suspense: { title: "霧の下に", meta: "サスペンス解説 · 強いフック" } },
    quickStart: { eyebrow: "ツールを選択", title: "クイックスタート" },
    tools: { narration: { title: "ショートドラマ解説", description: "物語を理解し、解説動画を効率よく生成" }, translation: { title: "動画翻訳", description: "多言語字幕と吹き替えをまとめて処理" }, remix: { title: "ショートドラマリミックス", description: "ハイライトを抽出してリミックスを自動作成" } },
    promotion: { ariaLabel: "キャンペーン情報", eyebrow: "期間限定クリエイティブブースト", title: "今週のアップグレードでクレジット20%増量", action: "詳細を見る", close: "キャンペーンを閉じる" },
    recent: { eyebrow: "最近のアクティビティ", title: "最近のプロジェクト", viewAll: "すべて表示", creditsUsed: "{count} 消費" },
    status: { complete: "完了", processing: "処理中 {progress}%", draft: "下書き" },
    credits: { resource: "アカウントリソース", title: "制作クレジット", balance: "現在の残高", monthlyUsed: "今月は {count} クレジット使用", recharge: "クレジットをチャージ" },
    inspiration: { eyebrow: "もっと見る", title: "制作のヒント" },
    inspirations: { storytelling: { title: "解説テンポガイド", description: "サスペンス・逆転・クライマックスの密度を調整" }, creativeRemix: { title: "人気リミックスのヒント", description: "最近の人気テーマから制作方向を発見" } },
    toast: { close: "通知を閉じる" },
    unavailable: { translation: "動画翻訳は準備中です", remix: "ショートドラマリミックスは準備中です", credits: "制作クレジット機能は準備中です", account: "アカウントセンターは準備中です", narration: "ショートドラマ解説は準備中です", upgrade: "メンバーシップのアップグレードは準備中です", creditDetails: "クレジット明細は準備中です", recharge: "チャージ機能は準備中です", rechargeCredits: "クレジットチャージは準備中です", promotion: "キャンペーン機能は準備中です", allProjects: "すべてのプロジェクト機能は準備中です", project: "{name}は準備中です", storytelling: "解説テンポガイドは準備中です", creativeRemix: "人気リミックスのヒントは準備中です", aiImage: "AI 画像は準備中です", aiVideo: "AI 動画は準備中です", aiVoice: "AI 音声は準備中です", allCases: "注目事例は準備中です", case: "事例詳細は準備中です" },
  },
  create: {
    routeHeading: "新しい AI 動画を作成", description: "制作タイプを選択して素材をアップロード", autosave: "アップロード進捗は自動保存されます",
    types: { narration: { title: "ショートドラマ解説", description: "ナレーションで物語を伝える" }, translation: { title: "動画翻訳", description: "多言語翻訳と吹き替え" }, remix: { title: "ショートドラマリミックス", description: "編集スキル不要でハイライトを抽出" } },
    typeSelector: { title: "制作タイプを選択", ariaLabel: "制作タイプ" },
    upload: { title: "素材をアップロード", chooseVideos: "動画ファイルを選択", addMore: "追加", dragPrefix: "動画をここにドラッグ、または", chooseFile: "ファイルを選択", limits: "MP4 / MOV / AVI、1ファイル最大5GB、最大{count}本", selectedVideos: "選択した動画", uploadingMaterials: "素材をアップロード中です。ファイルを追加しないでください。", detectingVideoSubtitles: "動画字幕を検出しています。しばらくお待ちください。", uploadSubtitle: "{name}の字幕をアップロード", removeSubtitle: "{name}を削除", reorderVideo: "{name}の順序を変更", removeVideo: "{name}を削除" },
    subtitle: { matched: "SRT割り当て済み", aiRecognition: "未アップロード・AI認識を使用", pending: "認識待ち・AI認識を使用", clickOrAi: "字幕をアップロード、またはAI認識を使用", detecting: "字幕領域を検出中（{progress}）" },
    summary: { title: "制作サマリー", duration: "元動画の合計時間", estimated: "予想消費量", balance: "現在の残高", next: "次へ：パラメータ設定", nextWaiting: "字幕を検出中…", detectingSubtitles: "{count}本の動画の字幕領域を検出中です。完了すると次へ進めます。" },
    messages: { invalidVideo: "5GB以内のMP4、MOV、AVIのみ対応しています", maxVideos: "{type}は最大{count}本までアップロードできます", tooMany: "{type}には現在{current}本あり、上限は{count}本です", settingsUnavailable: "パラメータ設定は準備中です", invalidSubtitle: "50MB以内のSRT字幕のみ対応しています", orderSaveAfterUploadFailed: "素材はアップロードされましたが、順序を保存できませんでした。ドラッグして再試行してください。", orderSaveFailed: "素材の順序を保存できませんでした。再試行してください。", orderSaveBeforeNextFailed: "素材の順序が保存されていないため、パラメータ設定を開けません。再試行してください。", waitSubtitleDetection: "{count}本の動画の字幕領域を検出中です。完了してから次へ進んでください。" },
  },
  projects: {
    routeHeading: "マイプロジェクト", heading: "マイプロジェクト", description: "すべての制作タスクと生成結果を管理", search: "プロジェクト名を検索", create: "新規制作", notice: "処理中にページを離れても進捗は自動保存されます",
    categories: { all: "すべて", narration: "ショートドラマ解説", translation: "動画翻訳", remix: "ショートドラマリミックス" },
    status: { all: "すべてのステータス", complete: "完了", processing: "処理中", processingPercent: "処理中 {progress}%", draft: "下書き", failed: "生成失敗" },
    filters: { ariaLabel: "プロジェクトフィルター", types: "プロジェクトタイプ", status: "ステータスで絞り込む" },
    table: { project: "プロジェクト", type: "タイプ", status: "ステータス", created: "作成日時", credits: "クレジット", actions: "操作", progress: "{name}の処理進捗 {progress}%" },
    actions: { result: "結果を見る", export: "書き出し", exporting: "ダウンロード中…", progress: "進捗を見る", continue: "編集を続ける", reason: "理由を見る", retry: "再生成" },
    bulkDelete: { selected: "{count} 件選択中", hint: "分析開始前、完了済み、または失敗したタスクのみ削除できます", button: "一括削除（{count}）", selectAll: "このページの削除可能なプロジェクトをすべて選択", selectAllShort: "削除可能項目を全選択", clearAll: "選択を解除", selectProject: "プロジェクト {name} を選択", unavailable: "プロジェクト {name} は処理中のため削除できません", dialogTitle: "選択したプロジェクトを削除しますか？", dialogDescription: "選択した {count} 件のプロジェクトと関連コンテンツを削除します。この操作は取り消せません。", cancel: "キャンセル", confirm: "{count} 件を削除", deleting: "削除中…" },
    empty: { title: "一致するプロジェクトがありません", description: "フィルターを変更するか新規制作を始めてください" },
    pagination: { ariaLabel: "プロジェクトのページ切り替え", previous: "前のページ", next: "次のページ", page: "{page}ページ", perPage: "1ページ{count}件" },
    messages: { unavailable: "{name}：{action}は準備中です", retryUnavailable: "{name}：再生成機能は準備中です", retryFailed: "{name}：再生成用の下書きを作成できませんでした。", retryUnsupported: "{name}：このプロジェクト種類では再生成できません", exportStarted: "{name}：生成動画のダウンロードを開始しました", exportVideoUnavailable: "{name}：ダウンロードできる動画が見つかりません", exportFailed: "{name}：動画のダウンロードに失敗しました。時間をおいて再試行してください。", pageChanged: "{page}ページに切り替えました", failureReason: "{name}：生成失敗の理由：{reason}", failureReasonUnavailable: "{name}：失敗理由を取得できませんでした", failureReasonReadFailed: "{name}：失敗理由の取得に失敗しました。時間をおいて再試行してください。", loading: "プロジェクトを読み込み中…", loadFailed: "プロジェクトを読み込めませんでした。時間をおいて再試行してください。", deleteSuccess: "{count} 件のプロジェクトの削除を受け付けました", deletePartial: "{success} 件の削除を受け付け、{failed} 件は失敗しました", deleteFailed: "{count} 件のプロジェクトを削除できませんでした。時間をおいて再試行してください。" },
  },
  editor: {
    routeHeading: "マルチトラック解説エディター", mobileNotice: "マルチトラックの詳細編集にはデスクトップをご利用ください",
    topbar: { back: "戻る", backAria: "分析ページに戻る", editing: "編集中", autosaved: "自動保存済み", credits: "制作クレジット", saveDraft: "下書きを保存", generate: "動画を生成", readOnly: "閲覧のみ", locked: "ロック済み", saving: "保存中…", saveFailed: "保存に失敗しました", generating: "生成中…", reviewMode: "表形式モード", switchingMode: "切り替え中…" },
    clips: { highlights: "ハイライト {count} 件" },
    tabs: { script: "解説台本", subtitle: "音声字幕", bgm: "背景音楽" },
    script: { current: "現在のクリップ台本", input: "現在のクリップ台本を編集", characters: "{count} 文字" },
    settings: { summary: "クイック設定の概要", voiceRole: "音声キャラクター", volume: "ボリューム {value}%", volumeControl: "音声ボリュームを調整", speed: "話速 {value}×", speedControl: "音声の話速を調整", subtitleStyle: "字幕スタイル", backgroundMusic: "背景音楽" },
    subtitle: { title: "字幕ファイルの内容", locked: "タイムライン固定・テキストのみ編集可能", cue: "{time} の字幕を編集" },
    bgm: { title: "背景音楽", currentFile: "現在のファイル：{file}", none: "未設定" },
    preview: { ariaLabel: "動画プレビュー", safeArea: "セーフエリア", progress: "プレビュー再生位置", start: "先頭へ移動", backOne: "1秒戻る", play: "再生", pause: "一時停止", forwardOne: "1秒進む", end: "末尾へ移動", fullscreen: "全画面プレビュー" },
    timeline: { ariaLabel: "マルチトラックタイムライン", noOverlap: "クリップ同士は重ねられません", zoomOut: "タイムラインを縮小", zoom: "タイムラインのズーム", zoomIn: "タイムラインを拡大", trimStart: "開始位置をトリミング", trimEnd: "終了位置をトリミング", tracks: { video: "動画クリップ", script: "解説台本", voice: "音声オーディオ", bgm: "背景音楽" } },
    waveform: { voicePreview: "音声プレビュー", bgmWaveform: "背景音楽の波形" },
    messages: { draftSaved: "下書きを保存しました", loading: "エディターの下書きを読み込み中…", readFailed: "エディターの下書きを読み込めません。", invalidDraft: "エディター API のデータが不完全です。", draftUnavailable: "このプロジェクトには編集可能な下書きがありません。分析完了後に再試行してください。", saveFailed: "下書きを保存できません。再試行してください。", saveBeforeGenerateFailed: "下書きを保存できないため、動画生成を開始していません。", switchModeFailed: "下書きを保存できなかったため、表形式モードを開いていません。" },
  },
  review: {
    routeHeading: "ショートドラマ解説の手動確認",
    eyebrow: "MANUAL REVIEW",
    heading: "解説クリップを確認",
    description: "各クリップの元動画範囲、画面説明、解説台本、原音設定を確認します。変更内容はマルチトラック下書きと同期されます。",
    contentLabel: "解説クリップ確認リスト",
    rowLabel: "解説クリップ {number}",
    sourcePreview: "{number} 行目の元動画プレビュー",
    assetSelect: "{number} 行目の元動画を選択",
    timeInput: "{number} 行目の{field}",
    pictureInput: "{number} 行目の画面説明を編集",
    scriptInput: "{number} 行目の解説台本を編集",
    originalSoundInput: "{number} 行目で元動画の音声を再生するか設定",
    columns: { sequence: "番号", source: "元動画", timecode: "タイムコード", picture: "画面説明", script: "解説台本", originalSound: "元動画を再生", actions: "操作" },
    fields: { start: "開始時間", end: "終了時間" },
    placeholders: { picture: "このクリップの画面内容を説明", script: "このクリップの解説台本を入力" },
    values: { yes: "はい", no: "いいえ" },
    actions: {
      editorMode: "エディターモード", switching: "切り替え中…", save: "下書きを保存", generate: "動画を生成", generating: "生成中…",
      delete: "削除", deleteRow: "{number} 行目を削除", moveUp: "上へ", moveUpRow: "{number} 行目を上へ移動", moveDown: "下へ", moveDownRow: "{number} 行目を下へ移動", insertAfter: "行を追加", insertAfterRow: "{number} 行目の後に新しい行を追加",
    },
    status: { locked: "ロック済み", saving: "保存中…", failed: "保存に失敗", saved: "自動保存済み" },
    validation: {
      ready: "{count} 件のクリップを確認済み", pending: "あと {count} 項目の確認が必要です", missingAsset: "再生可能な元動画を選択してください", invalidStart: "開始時間は 0 以上にしてください", invalidEnd: "終了時間は開始時間より後にしてください", outOfRange: "終了時間が元動画の長さを超えています", emptyScript: "解説台本を入力してください", duplicateRegion: "クリップ識別子が重複しています。再読み込みしてください。", emptyRows: "少なくとも 1 件のクリップを残してください", timecode: "HH:MM:SS.mmm 形式で入力してください",
    },
    messages: {
      missingProject: "プロジェクトが指定されていません。タスクフローから手動確認を開いてください。", invalidDraft: "エディター API のデータが不完全です。", draftUnavailable: "確認できる下書きがありません。AI 分析完了後に再試行してください。", readFailed: "確認用の下書きを読み込めません。", saveFailed: "下書きを保存できません。再試行してください。", loading: "確認内容を読み込み中…", fixBeforeSave: "時間または素材のエラーを修正してから保存してください。", switchFailed: "下書きを保存できなかったため、エディターモードを開いていません。", fixBeforeGenerate: "必須項目と時間のエラーをすべて修正してください。", generateFailed: "動画生成を開始できません。再試行してください。", readOnly: "動画はすでに生成処理中です。現在の内容は閲覧のみです。", previewUnavailable: "この素材には再生可能な URL がありません", noAssets: "利用できる動画素材がありません",
    },
  },
  videoTranslation: {
  "back": "ダッシュボードへ戻る",
  "name": "動画翻訳",
  "flow": "動画翻訳フロー",
  "mode": "制作モード",
  "modeHint": "Configure how the translation is produced.",
  "manual": "手動確認",
  "manualHint": "Review before rendering",
  "auto": "自動生成",
  "autoHint": "Run the whole workflow automatically",
  "language": "翻訳言語",
  "ratio": "出力比率",
  "voice": "共通ボイス",
  "originalSound": "元音声",
  "mute": "ミュート",
  "muteHint": "Translated audio only",
  "keep": "保持",
  "keepHint": "Mix original and translated audio",
  "voice_replacement": "音声を置換",
  "voice_replacementHint": "環境音・効果音・BGMを残し、話者の声だけを翻訳音声に置換します",
  "voiceReplacementSurcharge": "環境音の保持には音声分離を使用するため、{credits} クレジット/分が追加されます（全ての元動画を合算して切り上げ）。",
  "noVoiceReplacementSurcharge": "翻訳音声のみでは音声分離を使用しないため、環境音保持の追加料金はかかりません。",
  "estimatedCost": "元動画は {minutes} 分として課金されます。見積りは {credits} クレジット（環境音保持の追加分 {surcharge} クレジットを含む）です。",
  "translated_voice_only": "翻訳音声のみ",
  "translated_voice_onlyHint": "元動画の音声をすべて削除し、翻訳音声だけを残します",
  "music": "BGM",
  "musicHint": "Optional background music",
  "chooseMusic": "BGMを選択",
  "previous": "戻る",
  "saving": "Saving…",
  "start": "AI翻訳を開始",
  "subtitleLayout": "字幕とマスク設定",
  "subtitleHint": "Caption areas are detected automatically.",
  "sourceSubtitle": "元字幕",
  "targetSubtitle": "翻訳字幕",
  "keepSource": "元字幕を保持",
  "recognizing": "字幕を認識中…",
  "processing": "AI翻訳処理中",
  "edit": "翻訳セリフを編集",
  "time": "時間",
  "source": "元字幕",
  "target": "翻訳文",
  "preview": "試聴",
  "render": "動画を生成",
  "rendering": "動画を生成中",
  "complete": "エクスポート完了",
  "completeHint": "翻訳動画を利用できます。",
  "download": "ダウンロード",
  "steps": {
    "upload": "タスク作成",
    "settings": "設定",
    "translation": "AI翻訳",
    "edit": "セリフ編集",
    "render": "動画生成"
  },
  "languages": {'en': '英語', 'ja': '日本語', 'ko': '韓国語', 'de': 'ドイツ語', 'fr': 'フランス語', 'es': 'スペイン語', 'pt': 'ポルトガル語', 'ru': 'ロシア語', 'vi': 'ベトナム語', 'th': 'タイ語', 'id': 'インドネシア語', 'ar': 'アラビア語'},
  "ratios": {"original": "元の比率", "9:16": "9:16", "16:9": "16:9", "1:1": "1:1", "4:3": "4:3", "3:4": "3:4"},
  "errors": {
    "config": "Unable to load settings",
    "project": "Missing project ID",
    "save": "Unable to save settings",
    "music": "Unable to upload music",
    "progress": "Unable to load progress",
    "segments": "Unable to load lines",
    "limit": "Preview is limited to 100 characters or words",
    "preview": "Preview failed",
    "render": "Render failed",
    "result": "Unable to load the export result"
  }
}
};
translations.set('AI 视频生成｜影创工坊', 'AI動画生成｜スタジオ');
