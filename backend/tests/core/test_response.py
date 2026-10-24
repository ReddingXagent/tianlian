"""app/core/response.py 统一响应包装单测

四个纯函数: success_response / paginated_response / error_response / action_response。
统一契约: {code, message, data, timestamp(UTC int)}; action_response success=False → code 500。
"""
from datetime import datetime, timezone

from app.core import response


# ────────────────────────────────────────────────────────────────────
# success_response
# ────────────────────────────────────────────────────────────────────
class TestSuccessResponse:
    def test_defaults(self):
        r = response.success_response()
        assert r["code"] == 200
        assert r["message"] == "success"
        assert r["data"] is None
        assert isinstance(r["timestamp"], int)

    def test_with_data_and_message(self):
        r = response.success_response(data={"id": 1}, message="created")
        assert r["code"] == 200
        assert r["data"] == {"id": 1}
        assert r["message"] == "created"

    def test_data_can_be_list(self):
        r = response.success_response(data=[1, 2, 3])
        assert r["data"] == [1, 2, 3]

    def test_timestamp_is_recent_utc_seconds(self):
        before = int(datetime.now(timezone.utc).timestamp())
        r = response.success_response()
        after = int(datetime.now(timezone.utc).timestamp())
        assert before <= r["timestamp"] <= after


# ────────────────────────────────────────────────────────────────────
# paginated_response
# ────────────────────────────────────────────────────────────────────
class TestPaginatedResponse:
    def test_structure(self):
        r = response.paginated_response([{"id": 1}], total=100, page=3, page_size=20)
        assert r["code"] == 200
        assert r["message"] == "success"
        assert r["data"] == {
            "items": [{"id": 1}],
            "total": 100,
            "page": 3,
            "page_size": 20,
        }

    def test_empty_page(self):
        r = response.paginated_response([], 0, 1, 20)
        assert r["data"]["items"] == []
        assert r["data"]["total"] == 0
        assert r["data"]["page"] == 1
        assert r["data"]["page_size"] == 20

    def test_custom_message(self):
        r = response.paginated_response([], 0, 1, 20, message="list ok")
        assert r["message"] == "list ok"

    def test_timestamp_int(self):
        assert isinstance(
            response.paginated_response([], 0, 1, 1)["timestamp"], int
        )


# ────────────────────────────────────────────────────────────────────
# error_response
# ────────────────────────────────────────────────────────────────────
class TestErrorResponse:
    def test_structure(self):
        r = response.error_response(404, "not found")
        assert r["code"] == 404
        assert r["message"] == "not found"
        assert r["data"] is None
        assert isinstance(r["timestamp"], int)

    def test_with_data(self):
        r = response.error_response(400, "bad request", data={"field": "name"})
        assert r["data"] == {"field": "name"}

    def test_code_passthrough(self):
        """error_response 透传任意 code, 不做成功/失败映射。"""
        assert response.error_response(500, "x")["code"] == 500
        assert response.error_response(422, "y")["code"] == 422


# ────────────────────────────────────────────────────────────────────
# action_response — success → 200, failure → 500
# ────────────────────────────────────────────────────────────────────
class TestActionResponse:
    def test_success_default(self):
        r = response.action_response()
        assert r["code"] == 200
        assert r["message"] == "操作成功"
        assert r["data"] is None

    def test_failure_maps_to_500(self):
        r = response.action_response(success=False, message="失败")
        assert r["code"] == 500
        assert r["message"] == "失败"

    def test_with_data(self):
        r = response.action_response(success=True, data={"rows": 5})
        assert r["data"] == {"rows": 5}

    def test_timestamp_int(self):
        assert isinstance(response.action_response()["timestamp"], int)
