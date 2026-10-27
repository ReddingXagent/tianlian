"""OCPP 真下发调度 (卡 87d6f7b9, 契约 §7.1/§7.2)

配置开关 OCPP_REMOTE_DISPATCH_ENABLED (默认 False):
- False: business_orders 维持原 mock 行为 (设备在线即 accepted), 零破坏。
- True: 经 OCPPAdapter 真实下发 RemoteStartTransaction/RemoteStopTransaction,
  同步等待结果 (超时 OCPP_DISPATCH_TIMEOUT_SEC, 默认 10s — 契约 §7.1 的
  "10s 内无 StartTransaction 确认保持 pending" 语义落在超时判定上)。

结果映射 (DispatchResult):
- ACCEPTED: 桩接受, 订单照常推进
- REJECTED: 桩明确拒绝
- OFFLINE:  连接失败/设备不可达 (ConnectionError/OSError)
- TIMEOUT:  超时无响应
"""
import asyncio
import logging
import os

from sqlalchemy.orm import Session

from app.gateway.ocpp import OCPPAdapter

logger = logging.getLogger(__name__)

# 契约 §7.1: 10s 内 charger 无确认 → 视为超时。同步路由内等待此窗口。
DISPATCH_TIMEOUT_SEC = 10.0


def _dispatch_timeout() -> float:
    """超时读取: env OCPP_DISPATCH_TIMEOUT_SEC 优先, 非法或 <=0 回落 10.0。"""
    raw = os.environ.get("OCPP_DISPATCH_TIMEOUT_SEC")
    if raw is None:
        return DISPATCH_TIMEOUT_SEC
    try:
        v = float(raw)
    except ValueError:
        logger.warning("OCPP_DISPATCH_TIMEOUT_SEC 非法值 %r, 回落 %.1fs", raw, DISPATCH_TIMEOUT_SEC)
        return DISPATCH_TIMEOUT_SEC
    if v <= 0:
        logger.warning("OCPP_DISPATCH_TIMEOUT_SEC=%s <= 0, 回落 %.1fs", raw, DISPATCH_TIMEOUT_SEC)
        return DISPATCH_TIMEOUT_SEC
    return v


class DispatchResult:
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    OFFLINE = "offline"
    TIMEOUT = "timeout"


def dispatch_enabled() -> bool:
    """开关读取: 环境变量优先 (测试可 monkeypatch.setenv), 缺省走 Settings 默认 False。"""
    v = os.environ.get("OCPP_REMOTE_DISPATCH_ENABLED")
    if v is not None:
        return v not in ("0", "false", "False", "")
    from app.core.config import get_settings

    return bool(get_settings().OCPP_REMOTE_DISPATCH_ENABLED)


def _run_with_timeout(coro, timeout: float):
    """同步执行异步下发并限时。超时 → TIMEOUT; 连接类异常 → OFFLINE。"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 同步路由线程内不会有 running loop; 防御 TestClient 异步上下文复用
            return asyncio.run_coroutine_threadsafe(
                asyncio.wait_for(coro, timeout), loop
            ).result(timeout + 1)
    except RuntimeError:
        pass
    try:
        return asyncio.run(asyncio.wait_for(coro, timeout))
    except asyncio.TimeoutError:
        return DispatchResult.TIMEOUT
    except (ConnectionError, OSError):
        return DispatchResult.OFFLINE


def remote_start(device, connector_id: int, id_tag: str) -> str:
    """经 OCPPAdapter 下发 RemoteStartTransaction。

    id_tag 传用户标识 (C 端 = user.id), charge_point_id 用设备 sn。
    """
    adapter = OCPPAdapter(charge_point_id=device.sn or f"DEV{device.id}")
    result = _run_with_timeout(
        adapter.remote_start_transaction(id_tag, connector_id), _dispatch_timeout()
    )
    if result is DispatchResult.TIMEOUT or result is DispatchResult.OFFLINE:
        return result
    return DispatchResult.ACCEPTED if result else DispatchResult.REJECTED


def _order_charge_point_id(order) -> str:
    """remote_stop 的 charge_point_id: 订单所属设备 sn (与 remote_start 同语义)。

    拿不到 device (device_id 悬空/无 DB 会话) 时兜底旧格式 ORDER{id} 并打警告 —
    真桩无法路由, 但保底行为可观测。
    """
    from app.models.device import Device

    session = (
        Session.object_session(order)
        if getattr(order, "_sa_instance_state", None) is not None
        else None
    )
    dev = None
    if session is not None and order.device_id is not None:
        dev = session.get(Device, order.device_id)
    if dev is not None and dev.sn:
        return dev.sn
    if dev is not None:
        return f"DEV{dev.id}"
    logger.warning(
        "order %s 解析不到 device (device_id=%s), remote_stop 兜底 ORDER%s",
        getattr(order, "id", "?"), order.device_id, getattr(order, "id", "?"),
    )
    return f"ORDER{order.id}"


def remote_stop(order) -> str:
    """经 OCPPAdapter 下发 RemoteStopTransaction。

    charge_point_id 用订单所属设备 sn (卡 77ca88d8 修正: 原来误用 ORDER{id},
    真 OCPP 路由无法定位桩)。
    """
    adapter = OCPPAdapter(charge_point_id=_order_charge_point_id(order))
    # TODO(卡 77ca88d8 技术债): transaction_id 此处传的是订单主键 order.id, 而非 OCPP
    # 桩侧 StartTransaction.conf 返回的 transactionId。当前适配器为模拟实现可接受;
    # 真 OCPP 落地时须建立 order ↔ 桩侧 transactionId 映射 (ChargingOrder.transaction_id
    # 列已存在), 否则 RemoteStopTransaction 无法终止桩上的真实事务。
    result = _run_with_timeout(
        adapter.remote_stop_transaction(order.id), _dispatch_timeout()
    )
    if result is DispatchResult.TIMEOUT or result is DispatchResult.OFFLINE:
        return result
    return DispatchResult.ACCEPTED if result else DispatchResult.REJECTED


def remote_stop_best_effort(order) -> None:
    """best-effort 撤销已 accepted 的 RemoteStart (卡 e18ce31e, 契约 §7.1/§7.5)。

    pending→cancelled 取消路径 (cancel_order / order_cleanup 三函数) 调用: 订单曾
    成功下发 RemoteStart (create_order §7.1 保证 pending 必经 RemoteStart accepted),
    则 best-effort 下发 RemoteStopTransaction, 防止桩物理启动充电后订单已 cancelled、
    StartTransaction 遥测到达归属悬空。

    best-effort = 下发失败/超时/离线/异常仅 logger 记录 (含订单号/充电桩/失败原因),
    不抛、不回滚、不阻塞取消流程。下发走现有 remote_stop (OCPPAdapter), 不新造轮子。

    开关 OCPP_REMOTE_DISPATCH_ENABLED=false (默认, mock 阶段): 整个下发链路天然
    no-op —— 直接返回, 不构造 adapter / 不走 asyncio, 与现状零回归。故调用方
    无需额外 if 包裹业务逻辑, 仅需在 pending→cancelled 处直接调用本函数。
    """
    if not dispatch_enabled():
        # mock 阶段: 开关 false, 下发链路 no-op, 不破坏现有行为 (卡 e18ce31e)
        return
    order_no = getattr(order, "order_no", "?")
    device_id = getattr(order, "device_id", None)
    try:
        result = remote_stop(order)
    except Exception as e:  # best-effort: 任何异常仅记录, 不阻塞取消
        logger.warning(
            "RemoteStopTransaction 撤销下发异常 order_no=%s device_id=%s 原因=%s",
            order_no, device_id, e,
        )
        return
    if result in (DispatchResult.TIMEOUT, DispatchResult.OFFLINE):
        logger.warning(
            "RemoteStopTransaction 撤销未确认 order_no=%s device_id=%s 结果=%s",
            order_no, device_id, result,
        )
        return
    logger.info(
        "RemoteStopTransaction 撤销已下发 order_no=%s device_id=%s 结果=%s",
        order_no, device_id, result,
    )
