# 视频诊断功能 - 快速上手指南

## 🚀 5分钟快速体验

### 步骤1: 启动应用

```bash
cd /Users/wujingfeng/project/ai/codex/NarratoAI
python webui.py
```

浏览器会自动打开 http://localhost:8501

### 步骤2: 进入诊断页面

在左侧边栏找到并点击 **"🎬 视频诊断"**

### 步骤3: 上传视频

- 点击"上传视频"区域,选择你的视频文件(mp4/mov/avi)
- 可选: 如果有字幕文件(srt),也可以一并上传
- 支持同时上传最多5个视频

### 步骤4: 选择模式

**诊断模式**:
- ✅ **全量分析 (推荐)**: 完整分析所有镜头,精度高,耗时稍长
- ⚡ **快速模式**: 抽样分析,速度快,适合长视频

**剪辑模式**:
- 🛡️ **保守模式**: 仅删除明确的废片,保留更多内容
- ️ **激进模式**: 积极裁剪节奏慢、重复的镜头

### 步骤5: 开始诊断

点击 **"🚀 开始诊断"** 按钮

系统会显示实时进度:
1. 🔍 场景检测 (0-20%)
2.  质量评估 (20-50%)
3. 🎞️ 逐镜分析 (50-75%)
4. 📝 方案生成 (75-85%)
5. 📄 报告生成 (85-100%)

### 步骤6: 查看结果

诊断完成后,你会看到:

#### 📈 概览卡片
- 总体评级 (A/B/C/D)
- 镜头总数
- 视频时长

#### 🎯 六维评分
5个维度的评分卡片,带状态标识:
- ✅ **通过** (绿色): 表现良好
- ⚠️ **注意** (黄色): 需要改进
- ❌ **警告** (红色): 问题严重

维度包括:
- 一致性
- 连贯度
- 重复镜
- 节奏
- 废片

#### 💡 整体评价
AI生成的总结文案,包括:
- 总体评价
- 优点亮点
- 主要问题
- 核心建议

#### 🎞️ 逐镜建议
可折叠的镜头列表,每个镜头显示:
- 镜头编号和时长
- 关键帧缩略图
- 内容描述
- 问题标签(如有)
- 修改建议(如有)

### 步骤7: 执行操作

底部有3个按钮:

1. **🔄 再测一次**: 清除当前结果,重新诊断
2. **📄 导出PDF**: 下载完整的PDF诊断报告
3. **✂️ 一键智能剪辑**: 基于诊断结果自动执行剪辑(需配置LLM API)

---

##  命令行快速测试

如果你想快速验证功能是否正常,可以使用测试脚本:

```bash
# 使用项目中的示例视频
python tests/test_video_diagnosis.py resource/videos/古墓迷宫震全球.mp4

# 或使用你自己的视频
python tests/test_video_diagnosis.py /path/to/your/video.mp4
```

测试脚本会输出:
- 总体评级
- 各维度评分
- 前5个镜头的建议
- 存储位置信息

---

## 📁 结果在哪里?

诊断结果保存在 `storage/tasks/{task_id}/` 目录下:

```
storage/tasks/abc123-def456-.../
├── diagnosis_result.json    # 结构化数据(JSON格式)
├── report.pdf               # PDF诊断报告
├── keyframes/               # 关键帧图片
│   ├── shot_001.jpg
│   ├── shot_002.jpg
│   └── ...
└── editing_plan.json        # 智能剪辑方案
```

你可以通过以下方式访问:
- **WebUI**: 直接在线查看
- **文件系统**: 打开上述目录查看原始文件
- **API**: 读取JSON文件进行程序化处理

---

## ❓ 常见问题

### Q1: 诊断需要多长时间?

**A**: 取决于视频长度和模式选择:
- 1分钟视频 + 全量模式: 约1-2分钟
- 5分钟视频 + 全量模式: 约3-5分钟
- 10分钟视频 + 快速模式: 约2-3分钟

### Q2: 为什么有些维度显示"警告"?

**A**: "警告"表示该维度存在问题,但不影响整体可用性。例如:
- **一致性警告**: 某些镜头色调略有差异
- **节奏警告**: 部分镜头时长偏长或偏短
- **重复镜警告**: 检测到相似但未完全重复的镜头

建议根据具体提示进行优化。

### Q3: 智能剪辑安全吗?会不会删掉重要内容?

**A**: 非常安全!
- **保守模式**: 只删除明确的黑屏、无效内容
- **激进模式**: 会裁剪节奏慢的部分,但保留核心内容
- 执行前可以预览剪辑方案
- 原始视频不会被修改,剪辑结果是新文件

### Q4: 如何调整诊断的敏感度?

**A**: 目前有两个可调参数:
1. **诊断模式**: 全量 vs 快速
2. **剪辑模式**: 保守 vs 激进

未来版本会开放更多参数(如场景检测阈值、重复判定标准等)。

### Q5: LLM API费用高吗?

**A**: 取决于使用频率和视频长度:
- 单个短视频(1-3分钟): 约$0.01-0.05
- 中等视频(5-10分钟): 约$0.05-0.15
- 长视频(>10分钟): 建议使用快速模式降低成本

系统有缓存机制,相同视频不会重复计费。

---

## 🎓 进阶使用

### 自定义Prompt模板

如果你希望调整诊断标准,可以编辑Prompt模板:

```bash
# 例如调整一致性检查的标准
vim app/services/prompts/video_diagnosis/consistency_check.txt
```

修改后重启应用即可生效。

### 批量处理多个视频

目前WebUI支持最多5个视频同时上传。如果需要处理更多:

```python
import asyncio
from app.services.video_diagnosis.service import VideoDiagnosisService

async def batch_diagnose(video_paths: list):
    service = VideoDiagnosisService()
    
    for i, video_path in enumerate(video_paths):
        task_id = f"batch_{i}_{uuid.uuid4()}"
        result = await service.diagnose(
            video_path=video_path,
            task_id=task_id,
            mode="fast"  # 批量处理建议使用快速模式
        )
        print(f"视频{i+1}完成: {result.overall_grade}")

# 使用
video_list = ["video1.mp4", "video2.mp4", "video3.mp4"]
asyncio.run(batch_diagnose(video_list))
```

### 集成到你的工作流

诊断结果以JSON格式存储,可以轻松集成到其他系统:

```python
import json

# 读取诊断结果
with open("storage/tasks/{task_id}/diagnosis_result.json") as f:
    result = json.load(f)

# 提取关键信息
grade = result["overall_grade"]
issues = [s for s in result["shot_details"] if s["quality_status"] == "error"]

# 自动化处理
if grade == "D":
    send_alert("视频质量较差,需要人工审核")
elif len(issues) > 10:
    auto_edit(result["editing_plan"])
```

---

## 📚 相关文档

- [完整技术文档](VIDEO_DIAGNOSIS_README.md)
- [实施报告](IMPLEMENTATION_REPORT.md)
- [系统设计计划](../../Library/Application\ Support/QoderCN/SharedClientCache/cache/plans/视频诊断与智能剪辑系统_141da625.md)

---

## 🆘 获取帮助

遇到问题?试试以下步骤:

1. **查看日志**: `logs/app.log` 中有详细错误信息
2. **检查依赖**: 确保已安装所有依赖 `pip install -r requirements.txt`
3. **重启应用**: 有时重启能解决临时问题
4. **提交Issue**: 在GitHub仓库提交问题,附上错误日志

---

## 🎉 开始体验吧!

现在你已经了解了所有基础知识,快去试试视频诊断功能吧!

```bash
python webui.py
```

祝你使用愉快! 🚀
