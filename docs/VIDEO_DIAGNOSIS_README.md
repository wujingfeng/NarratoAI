# 视频诊断与智能剪辑功能

## 概述

视频诊断功能可以对上传的视频进行多维度AI分析,生成专业的诊断报告,并提供一键智能剪辑能力。

## 核心功能

### 1. 五维度质量评估

- **一致性检查**: 评估色调、构图、人物形象的连续性
- **连贯度评估**: 分析镜头转场自然度和叙事逻辑
- **重复镜头检测**: 使用pHash + VLM双重验证识别重复内容
- **节奏分析**: 统计镜头时长分布,识别节奏异常区间
- **废片识别**: 检测黑屏、无效内容等需要删除的片段

### 2. 逐镜分析与建议

- 为每个镜头生成内容描述
- 标注问题状态(通过/注意/警告)
- 提供具体的修改建议

### 3. 智能剪辑方案

- 基于诊断结果自动生成可执行的剪辑脚本
- 支持保守模式(仅删除废片)和激进模式(积极裁剪)
- 兼容现有clip_video.py格式,可直接执行

### 4. 多格式输出

- **PDF诊断报告**: 包含雷达图、分维度详情、逐镜建议表
- **JSON结构化数据**: 便于程序化处理
- **WebUI可视化**: 交互式展示诊断结果

## 快速开始

### 方式1: WebUI使用

1. 启动Web应用:
   ```bash
   python webui.py
   ```

2. 在侧边栏点击 "🎬 视频诊断"

3. 上传视频文件(支持mp4/mov/avi,最多5个)

4. 可选: 上传字幕文件(srt格式)

5. 选择诊断模式和剪辑模式

6. 点击 " 开始诊断"

7. 等待诊断完成,查看结果并可选择:
   - 🔄 再测一次
   - 📄 导出PDF
   - ️ 一键智能剪辑

### 方式2: 命令行测试

```bash
# 基本用法
python tests/test_video_diagnosis.py resource/videos/古墓迷宫震全球.mp4

# 查看帮助
python tests/test_video_diagnosis.py --help
```

## 技术架构

### 核心模块

```
app/services/video_diagnosis/
├── __init__.py                 # 模块导出
├── preprocessor.py             # 视频预处理(场景检测+关键帧提取)
├── quality_analyzer.py         # 五维度质量评估
├── shot_analyzer.py            # 逐镜分析与建议生成
├── editing_planner.py          # 智能剪辑方案生成
├── service.py                  # 主服务(流水线编排)
└── pdf_reporter.py             # PDF报告生成

app/models/
└── diagnosis_schema.py         # 数据模型定义

app/services/prompts/video_diagnosis/
├── consistency_check.txt       # 一致性检查Prompt
├── coherence_check.txt         # 连贯度评估Prompt
── duplicate_check.txt         # 重复镜头确认Prompt
├── rhythm_check.txt            # 节奏分析Prompt
├── waste_check.txt             # 废片识别Prompt
├── shot_analysis.txt           # 逐镜分析Prompt
└── summary_generation.txt      # 总结文案生成Prompt

webui/components/
└── video_diagnosis.py          # WebUI组件
```

### 处理流程

```
用户上传视频
    ↓
Phase 1: 视频预处理 (0-20%)
  ├─ 获取视频元信息
  ├─ FFmpeg场景切换检测
  └─ 提取关键帧
    ↓
Phase 2: 多维度质量评估 (20-50%)
  ├─ 一致性检查 (VLM批量分析)
  ├─ 连贯度评估 (滑动窗口+时长统计)
  ├─ 重复镜头检测 (pHash初筛+VLM确认)
  ├─ 节奏分析 (统计+VLM主观评价)
  └─ 废片识别 (FFmpeg滤镜+VLM确认)
    ↓
Phase 3: 逐镜分析与建议 (50-75%)
  ├─ 批量VLM生成镜头描述
  ├─ 结合质量评估结果打标签
  ─ TextModel生成修改建议
    ↓
Phase 4: 智能剪辑方案生成 (75-85%)
  ├─ 计算裁剪区间
  ├─ 建议转场效果
  └─ 输出兼容clip_video.py的JSON脚本
    ↓
Phase 5: 结果输出 (85-100%)
  ├─ 保存JSON结构化数据
  ├─ 生成PDF诊断报告
  └─ WebUI可视化展示
```

## 依赖安装

新增依赖已添加到 `requirements.txt`:

```bash
pip install -r requirements.txt
```

主要新增包:
- `imagehash>=4.3.0` - pHash感知哈希算法
- `reportlab>=4.0.0` - PDF报告生成
- `matplotlib>=3.7.0` - 可视化图表

## API使用示例

```python
import asyncio
from app.services.video_diagnosis.service import VideoDiagnosisService

async def diagnose_video():
    service = VideoDiagnosisService()
    
    result = await service.diagnose(
        video_path="path/to/video.mp4",
        task_id="unique-task-id",
        subtitle_path=None,  # 可选
        mode="full",  # "full" 或 "fast"
        editing_mode="conservative"  # "conservative" 或 "aggressive"
    )
    
    # 访问诊断结果
    print(f"总体评级: {result.overall_grade}")
    print(f"镜头总数: {result.total_shots}")
    print(f"总结: {result.summary}")
    
    # 访问逐镜详情
    for shot in result.shot_details:
        print(f"镜头#{shot.shot_id}: {shot.content_description}")
        if shot.issues:
            print(f"  问题: {shot.issues}")
        if shot.suggestions:
            print(f"  建议: {shot.suggestions[0]}")
    
    # 访问剪辑方案
    if result.editing_plan:
        print(f"保留镜头数: {len(result.editing_plan['video_clips'])}")

asyncio.run(diagnose_video())
```

## 存储结构

诊断结果保存在 `storage/tasks/{task_id}/` 目录下:

```
storage/tasks/{task_id}/
├── diagnosis_result.json       # 结构化诊断结果
├── report.pdf                  # PDF诊断报告
├── keyframes/                  # 关键帧图片
│   ├── shot_001.jpg
│   ├── shot_002.jpg
│   └── ...
└── editing_plan.json           # 智能剪辑方案(可选)
```

## 性能优化建议

1. **快速模式 vs 全量模式**:
   - 快速模式: 抽样分析,减少LLM调用次数,适合长视频
   - 全量模式: 完整分析,精度更高,适合短视频(<5分钟)

2. **缓存机制**:
   - 系统会自动缓存相同视频的LLM分析结果
   - 基于关键帧pHash去重,避免重复调用

3. **并发处理**:
   - 5个维度的评估并行执行
   - 关键帧分批处理(每批10张)

## 常见问题

### Q: 场景切换检测不准确怎么办?

A: 可以调整 `ShotDetector` 的 `threshold` 参数(默认0.4):
- 值越小越敏感(检测到更多切换点)
- 值越大越保守(只检测明显的切换)

### Q: LLM API调用失败怎么办?

A: 系统有完善的降级机制:
- 超时自动重试(最多3次)
- 失败后返回合理的默认值
- 不会中断整个诊断流程

### Q: 如何自定义诊断维度?

A: 可以在 `quality_analyzer.py` 中新增维度分析器:
1. 继承 `DimensionAnalyzer` 基类
2. 实现 `analyze()` 方法
3. 在 `MultiDimensionAnalyzer` 中注册

### Q: 智能剪辑方案不符合预期怎么办?

A: 可以尝试:
- 切换到"保守模式"(仅删除明确的废片)
- 手动编辑生成的剪辑脚本(JSON格式)
- 使用WebUI中的"再测一次"重新诊断

## 后续扩展方向

1. **多视频对比分析**: 支持上传多个版本进行对比
2. **风格迁移建议**: 基于参考视频给出调色、配乐建议
3. **实时诊断**: 视频播放过程中实时显示诊断信息
4. **A/B测试**: 生成多个剪辑方案供用户选择
5. **学习优化**: 收集用户反馈,训练专用诊断模型

## 技术支持

如有问题或建议,欢迎提交Issue或PR。
