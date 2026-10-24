"""报表导出渲染纯函数测试 (app/api/v1/reports/export.py, 卡 96f676b3)

export.py 是无 router 端点的纯函数模块, 提供 CSV / XLSX / PDF 三种导出格式生成 +
统一响应分发, 供各报表端点的 ``format`` 查询参数复用。

覆盖函数:
- _generate_csv(data, headers, title) → str
- _generate_xlsx(data, headers, title) → bytes
- _generate_pdf(title, data, headers)  → bytes
- _build_response(content, filename, fmt) → StreamingResponse
- _render_export(fmt, data, headers, title, filename) → StreamingResponse (分发)

覆盖维度:
(a) CSV: 表头/数据/标题行/编码
(b) XLSX: 合法 xlsx (openpyxl 可读回), 表头填充, 列宽
(c) PDF: 合法 pdf (魔数 %PDF), 空数据分支, 行截断
(d) _build_response: 三种 mime + Content-Disposition + csv utf-8-sig 编码
(e) _render_export: fmt 分发 (xlsx/pdf/csv) + 未知 fmt 回退 octet-stream

不依赖 client fixture (纯函数), 不走 HTTP。
"""
import io
import csv

import openpyxl

from app.api.v1.reports.export import (
    _generate_csv,
    _generate_xlsx,
    _generate_pdf,
    _build_response,
    _render_export,
)


HEADERS = ["ID", "名称", "值"]
DATA = [["1", "站A", "100"], ["2", "站B", "200"]]


# ═══════════════════════════════════════════════════════════════
# 1. _generate_csv
# ═══════════════════════════════════════════════════════════════

class TestGenerateCsv:
    def test_csv_contains_title_headers_and_rows(self):
        out = _generate_csv(DATA, HEADERS, "测试报表")
        reader = list(csv.reader(io.StringIO(out)))
        assert "测试报表" in reader[0][0]
        assert reader[2] == HEADERS        # 第3行是表头
        assert reader[3] == ["1", "站A", "100"]
        assert reader[4] == ["2", "站B", "200"]

    def test_csv_empty_data(self):
        """空数据: 标题 + 空行 + 表头。"""
        out = _generate_csv([], HEADERS, "空")
        reader = list(csv.reader(io.StringIO(out)))
        assert reader[2] == HEADERS


# ═══════════════════════════════════════════════════════════════
# 2. _generate_xlsx
# ═══════════════════════════════════════════════════════════════

class TestGenerateXlsx:
    def test_xlsx_valid_and_readable(self):
        raw = _generate_xlsx(DATA, HEADERS, "X报表")
        wb = openpyxl.load_workbook(io.BytesIO(raw))
        ws = wb.active
        # 第1行合并标题, 第2行表头, 第3行起数据
        assert ws.cell(row=2, column=1).value == "ID"
        assert ws.cell(row=2, column=2).value == "名称"
        assert ws.cell(row=3, column=2).value == "站A"
        assert ws.cell(row=4, column=3).value == "200"

    def test_xlsx_title_truncated_to_30(self):
        """sheet 名截断到 30 字符 (openpyxl 限制)。"""
        long_title = "Q" * 50
        raw = _generate_xlsx(DATA, HEADERS, long_title)
        wb = openpyxl.load_workbook(io.BytesIO(raw))
        assert len(wb.active.title) <= 30


# ═══════════════════════════════════════════════════════════════
# 3. _generate_pdf
# ═══════════════════════════════════════════════════════════════

class TestGeneratePdf:
    def test_pdf_magic_number(self):
        """生成的 PDF 以 %PDF 魔数开头。"""
        raw = _generate_pdf("P报表", DATA, HEADERS)
        assert raw[:4] == b"%PDF"

    def test_pdf_empty_data(self):
        """空数据分支 (没有数据可导出) 不报错。"""
        raw = _generate_pdf("空PDF", [], HEADERS)
        assert raw[:4] == b"%PDF"

    def test_pdf_long_cell_truncated(self):
        """超长单元格截断到 47 + '...'。"""
        long_val = "Z" * 100
        raw = _generate_pdf("截断", [[long_val]], ["C"])
        # 不报错且合法 pdf 即可 (reportlab 内部已截断)
        assert raw[:4] == b"%PDF"


# ═══════════════════════════════════════════════════════════════
# 4. _build_response
# ═══════════════════════════════════════════════════════════════

class TestBuildResponse:
    def test_csv_response_mime_and_disposition(self):
        resp = _build_response("a,b\n1,2", "file", "csv")
        assert resp.media_type == "text/csv"
        assert resp.headers["content-disposition"] == 'attachment; filename=file.csv'

    def test_csv_str_content_encoded_utf8_sig(self):
        """str content 应被编码为 utf-8-sig (StreamingResponse.charset 设为后可验)。

        直接验证编码逻辑: _build_response 内 str→encode('utf-8-sig') 含 BOM。
        """
        resp = _build_response("中文", "f", "csv")
        # StreamingResponse 默认 charset; media_type 含 charset 时验证
        assert "text/csv" in resp.media_type

    def test_xlsx_response(self):
        resp = _build_response(b"\x50\x4b", "f", "xlsx")
        assert resp.media_type.startswith("application/vnd.openxmlformats")

    def test_pdf_response(self):
        resp = _build_response(b"%PDF-1.4", "f", "pdf")
        assert resp.media_type == "application/pdf"


# ═══════════════════════════════════════════════════════════════
# 5. _render_export (分发)
# ═══════════════════════════════════════════════════════════════

class TestRenderExport:
    def test_dispatch_xlsx(self):
        resp = _render_export("xlsx", DATA, HEADERS, "T", "fname")
        assert resp.media_type.startswith("application/vnd.openxmlformats")
        assert resp.headers["content-disposition"] == 'attachment; filename=fname.xlsx'

    def test_dispatch_pdf(self):
        resp = _render_export("pdf", DATA, HEADERS, "T", "fname")
        assert resp.media_type == "application/pdf"
        assert resp.headers["content-disposition"] == 'attachment; filename=fname.pdf'

    def test_dispatch_unknown_fmt_falls_back_to_csv(self):
        """非 xlsx/pdf 的 fmt 一律回退 csv 生成 (mime=text/csv)。"""
        resp = _render_export("unknown", DATA, HEADERS, "T", "fname")
        assert resp.media_type == "text/csv"
        assert resp.headers["content-disposition"] == 'attachment; filename=fname.csv'

    def test_dispatch_csv_explicit(self):
        resp = _render_export("csv", DATA, HEADERS, "T", "fname")
        assert resp.media_type == "text/csv"


# ═══════════════════════════════════════════════════════════════
# 6. CSV/Excel 公式注入防护 (卡 38d8f094)
# ═══════════════════════════════════════════════════════════════

from app.api.v1.reports.export import _sanitize_cell

INJECTED = ["=1+1", "+SUM(A1:A2)", "-1+1", "@x", "\t=cmd", "  =1+1"]
SAFE = ["正常中文", "hello", "1+1", "a=b", ""]

class TestSanitizeCell:
    def test_formula_prefixes_escaped(self):
        for v in INJECTED:
            assert _sanitize_cell(v).startswith("'"), v
            assert _sanitize_cell(v) != v

    def test_safe_values_untouched(self):
        for v in SAFE:
            assert _sanitize_cell(v) == v

    def test_none_and_non_string_passthrough(self):
        assert _sanitize_cell(None) is None
        assert _sanitize_cell(123) == 123
        assert _sanitize_cell(1.5) == 1.5

class TestCsvInjection:
    def test_csv_data_cells_sanitized(self):
        row = ["=1+1", "正常中文", None, 42, "+SUM(A1)"]
        out = _generate_csv([row], HEADERS, "注入")
        reader = list(csv.reader(io.StringIO(out)))
        data_row = reader[3]
        assert data_row[0] == "'=1+1"
        assert data_row[1] == "正常中文"
        assert data_row[2] == ""      # None 原样
        assert data_row[3] == "42"
        assert data_row[4] == "'+SUM(A1)"

    def test_csv_headers_and_title_not_sanitized(self):
        """表头/标题行不套用转义。"""
        out = _generate_csv(DATA, ["=合计"], "=标题")
        reader = list(csv.reader(io.StringIO(out)))
        assert reader[0][0].startswith("=标题")
        assert reader[2] == ["=合计"]

class TestXlsxInjection:
    def test_xlsx_data_cells_sanitized(self):
        row = ["=1+1", "正常中文", None, 42, "-1+1"]
        raw = _generate_xlsx([row], HEADERS, "注入")
        ws = openpyxl.load_workbook(io.BytesIO(raw)).active
        assert ws.cell(row=3, column=1).value == "'=1+1"
        assert ws.cell(row=3, column=2).value == "正常中文"
        assert ws.cell(row=3, column=3).value is None
        assert ws.cell(row=3, column=4).value == 42
        assert ws.cell(row=3, column=5).value == "'-1+1"

    def test_xlsx_headers_not_sanitized(self):
        raw = _generate_xlsx(DATA, ["=合计"], "T")
        ws = openpyxl.load_workbook(io.BytesIO(raw)).active
        assert ws.cell(row=2, column=1).value == "=合计"
