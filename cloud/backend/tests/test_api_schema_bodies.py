"""
P2 API 质量守护：mutation 端点必须用 Pydantic schema（结构化 requestBody）

任务卡 7011daeb：healing.py / report_mgmt.py 等路由曾用 `data: dict` 接收请求体，
导致无 schema 校验、无 OpenAPI 字段文档（FastAPI 对 dict 形参只生成
`{"type":"object","additionalProperties":true}` 的空 schema）。

本测试守护 Pydantic 化成果——确认核心 mutation 端点的 requestBody 是结构化的，
含具体字段 properties，而非空 object。
"""
from app.main import app


def _resolve(spec: dict, schema: dict) -> dict:
    """解析 $ref / anyOf($ref) 到 components/schemas 下的实际模型定义。"""
    if "$ref" in schema:
        node = spec
        for part in schema["$ref"][2:].split("/"):  # 去掉 "#/" 前缀
            node = node[part]
        return node
    if "anyOf" in schema:  # Optional body → anyOf[{$ref}, {type:null}]
        for sub in schema["anyOf"]:
            if "$ref" in sub:
                return _resolve(spec, sub)
    return schema


def _body_props(path: str, method: str) -> dict:
    """提取某端点 requestBody 的 schema properties；无 requestBody 时返回 {}。"""
    spec = app.openapi()
    op = spec["paths"].get(path, {}).get(method, {})
    body = op.get("requestBody")
    if not body:
        return {}
    schema = body.get("content", {}).get("application/json", {}).get("schema", {})
    return _resolve(spec, schema).get("properties", {})


class TestHealingSchemaBodies:
    """自愈规则 / 执行审批的请求体必须有结构化字段。"""

    def test_create_rule_has_typed_body(self):
        props = _body_props("/api/v1/healing/rules", "post")
        assert "name" in props
        assert "alarm_pattern" in props
        assert "priority" in props

    def test_update_rule_has_typed_body(self):
        props = _body_props("/api/v1/healing/rules/{rule_id}", "put")
        assert "name" in props
        assert "enabled" in props

    def test_reject_execution_has_typed_body(self):
        props = _body_props("/api/v1/healing/executions/{execution_id}/reject", "post")
        assert "reason" in props


class TestReportMgmtSchemaBodies:
    """报告 CRUD 的请求体必须有结构化字段。"""

    def test_create_report_has_typed_body(self):
        props = _body_props("/api/v1/report-mgmt", "post")
        assert "title" in props
        assert "type" in props
        assert "station_id" in props

    def test_update_report_has_typed_body(self):
        props = _body_props("/api/v1/report-mgmt/{report_id}", "put")
        assert "title" in props
