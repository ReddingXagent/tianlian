"""数据分析报表导出渲染（拆分自原 reports.py）。

CSV / XLSX / PDF 三种导出格式的生成与统一分发，供各报表端点的 ``format`` 查询参数复用。
"""
import csv
import io
from datetime import datetime, timezone

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from fastapi.responses import StreamingResponse

# PDF generation
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# 公式注入危险前缀: Excel/Sheets 将以这些字符开头的单元格解析为公式
_FORMULA_PREFIXES = ('=', '+', '-', '@', '\t', '\r')


def _sanitize_cell(value):
    """防 CSV/Excel 公式注入: 字符串 lstrip 后以 = + - @ \t \r 开头则加单引号前缀转义。

    None / 非字符串原样返回; 仅用于数据单元格, 标题行/表头行不套用。
    """
    if not isinstance(value, str):
        return value
    if value.lstrip()[:1] in _FORMULA_PREFIXES:
        return "'" + value
    return value


def _generate_csv(data: list, headers: list, title: str) -> str:
    """生成 CSV 内容"""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([f"{title} - 导出时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}"])
    writer.writerow([])
    writer.writerow(headers)
    for row in data:
        writer.writerow([_sanitize_cell(v) for v in row])
    return output.getvalue()


def _generate_xlsx(data: list, headers: list, title: str) -> bytes:
    """生成 XLSX 内容"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title[:30]

    title_font = Font(bold=True, size=14, color='1677FF')
    header_fill = PatternFill(start_color='1677FF', end_color='1677FF', fill_type='solid')
    header_font = Font(bold=True, color='FFFFFF', size=11)
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    ws.cell(row=1, column=1, value=f'{title} - {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")}')
    ws.cell(row=1, column=1).font = title_font
    ws.row_dimensions[1].height = 30

    for ci, h in enumerate(headers, 1):
        cell = ws.cell(row=2, column=ci, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border

    for ri, row in enumerate(data, 3):
        for ci, val in enumerate(row, 1):
            cell = ws.cell(row=ri, column=ci, value=_sanitize_cell(val))
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='center')

    for ci in range(1, len(headers) + 1):
        max_len = len(str(headers[ci - 1]))
        for row_data in data:
            if ci <= len(row_data):
                max_len = max(max_len, len(str(row_data[ci - 1])))
        ws.column_dimensions[openpyxl.utils.get_column_letter(ci)].width = min(max_len + 4, 40)

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


def _build_response(content, filename: str, fmt: str) -> StreamingResponse:
    """根据格式返回对应响应"""
    mime_map = {
        'csv': 'text/csv',
        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'pdf': 'application/pdf'
    }
    if isinstance(content, str):
        content = content.encode('utf-8-sig')
    return StreamingResponse(
        io.BytesIO(content),
        media_type=mime_map.get(fmt, 'application/octet-stream'),
        headers={'Content-Disposition': f'attachment; filename={filename}.{fmt}'},
    )


def _generate_pdf(title: str, data: list, headers: list) -> bytes:
    """生成 PDF 内容"""
    buffer = io.BytesIO()

    # 尝试注册中文字体，如果失败则使用默认字体
    try:
        pdfmetrics.registerFont(TTFont('SimSun', '/System/Library/Fonts/PingFang.ttc', 'R'))
        default_font = 'SimSun'
    except Exception:
        default_font = 'Helvetica'

    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()

    # 自定义标题样式
    title_style = ParagraphStyle(
        name='CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        alignment=1,  # 居中
        spaceAfter=20
    )

    # 自定义普通文本样式
    normal_style = ParagraphStyle(
        name='CustomNormal',
        parent=styles['Normal'],
        fontSize=10,
        alignment=0,
        spaceAfter=10
    )

    # 标题
    story = []
    story.append(Paragraph(title, title_style))
    story.append(Paragraph(f"导出时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}", normal_style))
    story.append(Spacer(1, 20))

    # 创建表格
    if data:
        table_data = [headers]
        for row in data:
            # 确保每行数据长度与表头一致
            table_row = []
            for i, cell in enumerate(row):
                cell_str = str(cell)
                if len(cell_str) > 50:  # 截断过长的单元格
                    cell_str = cell_str[:47] + "..."
                table_row.append(cell_str)
            table_data.append(table_row)

        # 限制表格行数，避免内存问题
        max_rows = 100
        if len(table_data) > max_rows + 1:
            table_data = table_data[:max_rows + 1]
            story.append(Paragraph(f"注：显示前{max_rows-1}行，共{len(data)}条记录", normal_style))

        table = Table(table_data)

        # 表格样式
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1677FF')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, -1), default_font),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))

        story.append(table)
    else:
        story.append(Paragraph("没有数据可导出", normal_style))

    # 构建文档
    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def _render_export(fmt: str, data: list, headers: list, title: str, filename: str) -> StreamingResponse:
    """统一导出渲染分发"""
    if fmt == 'xlsx':
        return _build_response(_generate_xlsx(data, headers, title), filename, 'xlsx')
    elif fmt == 'pdf':
        return _build_response(_generate_pdf(title, data, headers), filename, 'pdf')
    return _build_response(_generate_csv(data, headers, title), filename, 'csv')
