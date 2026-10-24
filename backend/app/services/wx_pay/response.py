"""用户端云端契约响应包装 (code=0, 工作卡 280c85ee — 云端配套④)

契约 §6 通用约定: 响应包裹 {code, message, data}, code=0 成功, code!=0 失败。
与现有 app.core.response.success_response (code=200) 区分 —— 用户端云端契约统一 code=0,
端侧 (user-mp / user-app) 按 code===0 判断。

业务错误: HTTP 200 + code!=0 + message=契约原因码 + data=null (端侧按 code 处理)。
认证/权限/校验错误仍走 FastAPI HTTPException (401/403/422), 与全平台一致。
"""
from typing import Any, Optional

CODE_OK = 0

# 业务错误码 (code != 0; message 为契约原因码)
CODE_BIZ_ERROR = 1                # 通用业务错误
CODE_SUB_MCH_NOT_READY = 10001    # 子商户未就绪 (进件未 FINISH / merchant_status=PENDING)
CODE_SUB_MCH_FROZEN = 10002       # 子商户冻结 (merchant_status=FROZEN)
CODE_ORDER_CLOSED = 10003         # 订单已关闭
CODE_ORDER_NOT_FOUND = 10004      # 业务订单不存在
CODE_ORDER_ALREADY_PAID = 10005   # 订单已支付 (重复 prepay 拒绝, 工作卡 16209d26)
CODE_STATION_NOT_FOUND = 10006    # 场站不存在 (C端建单/详情, 工作卡 418a675a)
CODE_DEVICE_NOT_FOUND = 10007     # 充电设备不存在 (C端建单, 工作卡 418a675a)
CODE_INVOICE_NOT_FOUND = 10008    # 开票申请不存在 (C端开票, 工作卡 418a675a)

BIZ_MESSAGES = {
    CODE_SUB_MCH_NOT_READY: "SUB_MCH_NOT_READY",
    CODE_SUB_MCH_FROZEN: "SUB_MCH_FROZEN",
    CODE_ORDER_CLOSED: "ORDER_CLOSED",
    CODE_ORDER_NOT_FOUND: "ORDER_NOT_FOUND",
    CODE_ORDER_ALREADY_PAID: "ORDER_ALREADY_PAID",
    CODE_STATION_NOT_FOUND: "STATION_NOT_FOUND",
    CODE_DEVICE_NOT_FOUND: "DEVICE_NOT_FOUND",
    CODE_INVOICE_NOT_FOUND: "INVOICE_REQUEST_NOT_FOUND",
    CODE_BIZ_ERROR: "BIZ_ERROR",
}


def ok(data: Any = None, message: str = "ok") -> dict:
    """成功响应: {code:0, message, data}"""
    return {"code": CODE_OK, "message": message, "data": data}


def biz_error(code: int = CODE_BIZ_ERROR, message: Optional[str] = None) -> dict:
    """业务错误响应: {code:非0, message:契约原因码, data:null}"""
    return {
        "code": code,
        "message": message or BIZ_MESSAGES.get(code, "BIZ_ERROR"),
        "data": None,
    }
