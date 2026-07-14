"""
PDF诊断报告生成器

使用 reportlab + matplotlib 生成美观的 PDF 诊断报告。
报告结构: 封面 → 六维雷达图 → 整体评价 → 分维度详情 → 逐镜建议表 → 剪辑方案预览
"""

import io
import logging
import os
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # 非交互后端，避免 GUI 弹窗
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.models.diagnosis_schema import DiagnosisResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
_FONT_NAME = "STSong-Light"

# 维度顺序（雷达图 / 表格通用）
_DIM_ORDER = ["consistency", "coherence", "duplicate", "rhythm", "waste"]
_DIM_CN = {
    "consistency": "一致性",
    "coherence": "连贯度",
    "duplicate": "重复镜头",
    "rhythm": "节奏",
    "waste": "废片识别",
}


class PDFReporter:
    """PDF报告生成器"""

    def __init__(self):
        self._register_fonts()

    # ------------------------------------------------------------------
    # 字体注册
    # ------------------------------------------------------------------

    def _register_fonts(self):
        """注册中文字体（reportlab + matplotlib）"""
        # 使用 reportlab 内置 CID 字体，无需外部字体文件
        pdfmetrics.registerFont(UnicodeCIDFont(_FONT_NAME))
        logger.info(f"已注册 PDF 中文字体: {_FONT_NAME}")

        # matplotlib 字体：尝试使用系统中文字体，找不到则用默认
        self._mpl_font = self._find_mpl_chinese_font()

    @staticmethod
    def _find_mpl_chinese_font() -> FontProperties | None:
        """查找系统中可用的中文字体供 matplotlib 使用"""
        import matplotlib.font_manager as fm

        candidates = [
            "STSong", "Songti SC", "SimSun", "Noto Sans CJK SC",
            "Source Han Sans SC", "PingFang SC", "Microsoft YaHei",
        ]
        available = {f.name for f in fm.fontManager.ttflist}
        for name in candidates:
            if name in available:
                logger.info(f"matplotlib 使用中文字体: {name}")
                return FontProperties(family=name)
        logger.warning("未找到系统中文字体，matplotlib 图表中文显示可能异常")
        return None

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    async def generate_report(
        self,
        diagnosis_result: DiagnosisResult,
        task_id: str,
    ) -> str:
        """
        生成PDF诊断报告

        Args:
            diagnosis_result: 诊断结果
            task_id: 任务ID

        Returns:
            PDF文件路径
        """
        storage_dir = f"storage/tasks/{task_id}"
        os.makedirs(storage_dir, exist_ok=True)

        pdf_path = os.path.join(storage_dir, "report.pdf")

        doc = SimpleDocTemplate(
            pdf_path,
            pagesize=landscape(A4),
            rightMargin=1 * cm,
            leftMargin=1 * cm,
            topMargin=1 * cm,
            bottomMargin=1 * cm,
        )

        elements = []

        # 1. 封面
        elements.extend(self._create_cover_page(diagnosis_result))
        elements.append(PageBreak())

        # 2. 六维雷达图
        elements.extend(self._create_radar_chart(diagnosis_result))
        elements.append(Spacer(1 * cm, 1 * cm))
        elements.append(PageBreak())

        # 3. 整体评价
        elements.extend(self._create_summary_section(diagnosis_result))
        elements.append(PageBreak())

        # 4. 分维度详情
        elements.extend(self._create_dimension_details(diagnosis_result))
        elements.append(PageBreak())

        # 5. 逐镜建议表
        elements.extend(self._create_shot_table(diagnosis_result))
        elements.append(PageBreak())

        # 6. 智能剪辑方案预览
        if diagnosis_result.editing_plan:
            elements.extend(self._create_editing_plan_preview(diagnosis_result))

        doc.build(elements)
        logger.info(f"PDF报告已生成: {pdf_path}")

        return pdf_path

    # ------------------------------------------------------------------
    # 各章节
    # ------------------------------------------------------------------

    def _create_cover_page(self, result: DiagnosisResult) -> list:
        """创建封面"""
        elements = []

        title_style = ParagraphStyle(
            "CoverTitle",
            fontName=_FONT_NAME,
            fontSize=24,
            textColor=colors.HexColor("#1a1a1a"),
            spaceAfter=30,
            alignment=1,  # 居中
        )
        elements.append(Paragraph("视频诊断报告", title_style))

        info_style = ParagraphStyle(
            "CoverInfo",
            fontName=_FONT_NAME,
            fontSize=12,
            textColor=colors.HexColor("#666666"),
            spaceAfter=10,
        )
        elements.append(Paragraph(f"视频路径: {os.path.basename(result.video_path)}", info_style))
        elements.append(Paragraph(f"总时长: {result.video_duration:.2f}秒", info_style))
        elements.append(Paragraph(f"镜头总数: {result.total_shots}个", info_style))
        elements.append(Paragraph(f"总体评级: {result.overall_grade}级", info_style))
        elements.append(Paragraph(
            f"诊断时间: {result.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            info_style,
        ))

        elements.append(Spacer(1 * cm, 2 * cm))

        if result.summary:
            summary_style = ParagraphStyle(
                "CoverSummary",
                fontName=_FONT_NAME,
                fontSize=11,
                textColor=colors.HexColor("#333333"),
                spaceAfter=10,
            )
            elements.append(Paragraph("整体评价:", summary_style))
            elements.append(Paragraph(result.summary, summary_style))

        return elements

    def _create_radar_chart(self, result: DiagnosisResult) -> list:
        """创建六维雷达图（matplotlib → 图片 → 插入 PDF）"""
        elements: list = []

        dim_labels = [_DIM_CN.get(d, d) for d in _DIM_ORDER]
        scores = []
        for dim in _DIM_ORDER:
            obj = next((s for s in result.dimension_scores if s.dimension == dim), None)
            scores.append(obj.score if obj else 50.0)

        # 闭合多边形
        n = len(dim_labels)
        angles = [i / n * 2 * 3.14159 for i in range(n)]
        closed_angles = angles + [angles[0]]
        closed_scores = scores + [scores[0]]

        fig = plt.figure(figsize=(8, 8))
        ax = fig.add_subplot(111, polar=True)

        ax.plot(closed_angles, closed_scores, linewidth=2, linestyle="solid", marker="o")
        ax.fill(closed_angles, closed_scores, alpha=0.25)
        ax.set_xticks(angles)
        if self._mpl_font:
            ax.set_xticklabels(dim_labels, fontproperties=self._mpl_font)
        else:
            ax.set_xticklabels(dim_labels)
        ax.set_ylim(0, 100)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        buf.seek(0)
        plt.close(fig)

        chart = Image(buf, width=6 * inch, height=6 * inch)
        elements.append(chart)
        return elements

    def _create_summary_section(self, result: DiagnosisResult) -> list:
        """创建整体评价部分"""
        elements = []

        heading_style = ParagraphStyle(
            "SectionHeading",
            fontName=_FONT_NAME,
            fontSize=16,
            textColor=colors.HexColor("#1a1a1a"),
            spaceAfter=15,
            borderWidth=1,
            borderColor=colors.HexColor("#cccccc"),
            borderPadding=5,
        )
        elements.append(Paragraph("整体评价", heading_style))

        if result.summary:
            body_style = ParagraphStyle(
                "Body",
                fontName=_FONT_NAME,
                fontSize=11,
                textColor=colors.HexColor("#333333"),
                spaceAfter=10,
            )
            elements.append(Paragraph(result.summary, body_style))

        return elements

    def _create_dimension_details(self, result: DiagnosisResult) -> list:
        """创建分维度详情表格"""
        elements = []

        heading_style = ParagraphStyle(
            "SectionHeading",
            fontName=_FONT_NAME,
            fontSize=16,
            textColor=colors.HexColor("#1a1a1a"),
            spaceAfter=15,
            borderWidth=1,
            borderColor=colors.HexColor("#cccccc"),
            borderPadding=5,
        )
        elements.append(Paragraph("分维度详情", heading_style))

        data = [["维度", "状态", "评分", "评分原因", "改进建议"]]
        status_map = {"pass": "通过", "warning": "注意", "error": "警告"}

        for score in result.dimension_scores:
            reason = score.reason or score.description
            if len(reason) > 60:
                reason = reason[:60] + "..."
            suggestion = score.suggestions[0] if score.suggestions else "-"
            if len(suggestion) > 60:
                suggestion = suggestion[:60] + "..."
            data.append([
                self._translate_dim_name(score.dimension),
                status_map.get(score.status, score.status),
                f"{score.score:.0f}",
                reason,
                suggestion,
            ])

        table = Table(data, colWidths=[2 * cm, 1.8 * cm, 1.3 * cm, 7 * cm, 7 * cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1a1a1a")),
            ("FONTNAME", (0, 0), (-1, -1), _FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
            ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#cccccc")),
        ]))

        elements.append(table)
        return elements

    def _create_shot_table(self, result: DiagnosisResult) -> list:
        """创建逐镜建议表"""
        elements = []

        heading_style = ParagraphStyle(
            "SectionHeading",
            fontName=_FONT_NAME,
            fontSize=16,
            textColor=colors.HexColor("#1a1a1a"),
            spaceAfter=15,
            borderWidth=1,
            borderColor=colors.HexColor("#cccccc"),
            borderPadding=5,
        )
        elements.append(Paragraph("逐镜建议", heading_style))

        max_shots = 20
        shots_to_show = result.shot_details[:max_shots]

        status_icon = {"pass": "✓", "warning": "⚠", "error": "✗"}
        data = [["镜头#", "时长", "状态", "问题", "建议"]]

        for shot in shots_to_show:
            issues_str = ", ".join(shot.issues[:2]) if shot.issues else "-"
            suggestion_str = (
                shot.suggestions[0][:30] + "..."
                if shot.suggestions and shot.suggestions[0]
                else "-"
            )
            data.append([
                f"#{shot.shot_id}",
                f"{shot.duration:.1f}s",
                status_icon.get(shot.quality_status, "?"),
                issues_str,
                suggestion_str,
            ])

        if len(result.shot_details) > max_shots:
            data.append(["...", "...", "...", "...", f"共{len(result.shot_details)}个镜头"])

        table = Table(data, colWidths=[1.5 * cm, 1.5 * cm, 1 * cm, 4 * cm, 6 * cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1a1a1a")),
            ("FONTNAME", (0, 0), (-1, -1), _FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
            ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#cccccc")),
        ]))

        elements.append(table)
        return elements

    def _create_editing_plan_preview(self, result: DiagnosisResult) -> list:
        """创建剪辑方案预览"""
        elements = []

        heading_style = ParagraphStyle(
            "SectionHeading",
            fontName=_FONT_NAME,
            fontSize=16,
            textColor=colors.HexColor("#1a1a1a"),
            spaceAfter=15,
            borderWidth=1,
            borderColor=colors.HexColor("#cccccc"),
            borderPadding=5,
        )
        elements.append(Paragraph("智能剪辑方案预览", heading_style))

        plan = result.editing_plan
        if not plan:
            return elements

        body_style = ParagraphStyle(
            "Body",
            fontName=_FONT_NAME,
            fontSize=11,
            textColor=colors.HexColor("#333333"),
            spaceAfter=10,
        )

        video_clips = plan.get("video_clips", [])
        transitions = plan.get("transitions", [])
        total_dur = self._get_editing_plan_duration(plan)

        elements.append(Paragraph(f"保留镜头数: {len(video_clips)}个", body_style))
        elements.append(Paragraph(f"转场建议数: {len(transitions)}个", body_style))
        elements.append(Paragraph(f"预计成片时长: {total_dur:.1f}秒", body_style))

        return elements

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    @staticmethod
    def _translate_dim_name(dim_name: str) -> str:
        """翻译维度名称"""
        return _DIM_CN.get(dim_name, dim_name)

    @staticmethod
    def _get_editing_plan_duration(plan: dict) -> float:
        """从不同版本的剪辑方案结构中读取预计成片时长"""
        summary = plan.get("summary", {}) if isinstance(plan, dict) else {}
        if isinstance(summary, dict) and "trimmed_duration" in summary:
            return float(summary.get("trimmed_duration") or 0)
        return float(plan.get("total_duration", 0) or 0)
