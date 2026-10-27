"""
WebSocket 统一路由
路由前缀: /ws/v1/
整合三个现有WebSocket端点
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json
import logging
from datetime import datetime, timezone

from app.ws import ws_manager
from app.ws.auth import authenticate_websocket
from app.ws.authorize import (
    authorize_station,
    authorize_device,
    authorize_enterprise,
    device_in_scope,
    _is_platform_admin_role,
)

logger = logging.getLogger(__name__)


def _aggregate_team_id(user: dict):
    """聚合频道团队作用域 (卡 a579f89e): 平台管理员 → None (不过滤, 全量);
    团队级用户 → 本 team_id。与 HTTP /stats/* team_scope 语义一致,
    是范围过滤而非拒绝访问, 不新增授权 close 码。"""
    if _is_platform_admin_role(user.get("role")):
        return None
    return user.get("team_id")

def _conn_metadata(user: dict):
    """连接元数据 (卡 434f741a): 供 ws_manager.broadcast_team_scoped 按 team 过滤。

    team_id 用 _aggregate_team_id 归一 (平台 admin → None, 语义=收全量广播),
    避免下游过滤逻辑各处重复判断 admin 角色。
    """
    return {"team_id": _aggregate_team_id(user), "role": user.get("role")}


from app.ws.schemas import (
    WebSocketMessage,
    create_connected_message,
    create_data_message,
)
from app.ws.realtime_handler import RealtimeDataHandler
from app.ws.digital_twin_handler import DigitalTwinHandler
from app.ws.fleet_handler import FleetRealtimeHandler

router = APIRouter(prefix="/ws/v1", tags=["WebSocket"])


# ========== 1. 实时数据推送 (整合 websocket.py + websocket_realtime.py) ==========

@router.websocket("/realtime")
async def websocket_realtime(websocket: WebSocket):
    """实时数据推送 - 全局实时数据"""
    user = await authenticate_websocket(websocket)
    if user is None:
        return
    # 团队作用域 (卡 a579f89e): 聚合推送按 team 过滤, admin 全量
    team_id = _aggregate_team_id(user)
    await ws_manager.connect(websocket, channel="realtime", metadata=_conn_metadata(user))

    try:
        # 发送连接成功消息
        connected_msg = create_connected_message("realtime", "实时数据WebSocket连接成功")
        await ws_manager.send_personal_message(connected_msg, websocket)

        # 创建数据处理器
        handler = RealtimeDataHandler()
        
        # 处理客户端消息
        async def handle_client_messages():
            try:
                while True:
                    data = await websocket.receive_json()
                    message_type = data.get("type")
                    
                    if message_type == "ping":
                        ws_manager.record_heartbeat(websocket)
                        await ws_manager.send_personal_message(
                            WebSocketMessage(type="heartbeat", channel="realtime", payload={"ping": "pong"}),
                            websocket
                        )
                    elif message_type == "subscribe":
                        # 处理订阅请求
                        channel = data.get("channel")
                        if channel:
                            await ws_manager.send_personal_message(
                                WebSocketMessage(type="subscribed", channel=channel, message=f"已订阅{channel}频道"),
                                websocket
                            )
                    
            except Exception as e:
                logger.warning("处理客户端消息失败: %s", e)
        
        # 定时推送实时数据
        async def push_realtime_data():
            while True:
                try:
                    # Dashboard统计数据 (卡8035bd65: 同步DB查询经 to_thread 卸载到线程池)
                    dashboard_data = await asyncio.to_thread(handler.get_dashboard_stats, team_id)
                    await ws_manager.send_personal_message(
                        create_data_message("dashboard", dashboard_data),
                        websocket
                    )
                    
                    # 设备状态
                    device_data = await asyncio.to_thread(handler.get_device_status, team_id)
                    top_devices = device_data[:10]  # 前10个设备
                    await ws_manager.send_personal_message(
                        create_data_message(
                            "devices", {"devices": top_devices, "count": len(top_devices)}
                        ),
                        websocket
                    )

                    # 告警更新
                    alarm_data = await asyncio.to_thread(handler.get_alarm_updates, team_id)
                    if alarm_data:
                        top_alarms = alarm_data[:5]  # 前5个告警
                        await ws_manager.send_personal_message(
                            create_data_message(
                                "alerts", {"alerts": top_alarms, "count": len(top_alarms)}
                            ),
                            websocket
                        )
                    
                    # 工单更新
                    workorder_data = await asyncio.to_thread(handler.get_workorder_updates, team_id)
                    await ws_manager.send_personal_message(
                        create_data_message("workorders", workorder_data),
                        websocket
                    )
                    
                    await asyncio.sleep(5)  # 每5秒推送
                    
                except WebSocketDisconnect:
                    raise
                except Exception as e:
                    logger.warning("推送实时数据失败: %s", e)
                    await asyncio.sleep(5)

        # 并行运行
        client_task = asyncio.create_task(handle_client_messages())
        push_task = asyncio.create_task(push_realtime_data())
        
        done, pending = await asyncio.wait(
            [client_task, push_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        for task in pending:
            task.cancel()
            
    finally:
        ws_manager.disconnect(websocket)


# ========== 2. Dashboard实时数据 ==========

@router.websocket("/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    """Dashboard实时数据推送"""
    user = await authenticate_websocket(websocket)
    if user is None:
        return
    team_id = _aggregate_team_id(user)
    await ws_manager.connect(websocket, channel="dashboard", metadata=_conn_metadata(user))
    
    try:
        connected_msg = create_connected_message("dashboard", "Dashboard WebSocket连接成功")
        await ws_manager.send_personal_message(connected_msg, websocket)
        
        handler = RealtimeDataHandler()

        # 定时推送 Dashboard 数据
        async def push_dashboard_data():
            while True:
                try:
                    stats = await asyncio.to_thread(handler.get_dashboard_stats, team_id)
                    await ws_manager.send_personal_message(
                        create_data_message("dashboard", stats),
                        websocket,
                    )
                    await asyncio.sleep(5)
                except WebSocketDisconnect:
                    raise
                except Exception as e:
                    logger.warning("推送Dashboard数据失败: %s", e)
                    await asyncio.sleep(5)

        # 断连感知: 纯 send-only 循环无法察觉客户端断开, 用 receive 作为断连传感器,
        # 客户端关闭时 receive 抛出异常使任务结束, 避免 handler 成为僵尸任务导致 teardown 挂起
        # (卡 0bef02bc) 吞 ping 改为响应心跳, 防止连接被心跳驱逐
        async def wait_disconnect():
            try:
                while True:
                    raw = await websocket.receive_text()
                    try:
                        data = json.loads(raw)
                    except (ValueError, TypeError):
                        continue
                    if data.get("type") == "ping":
                        ws_manager.record_heartbeat(websocket)
                        await ws_manager.send_personal_message(
                            WebSocketMessage(
                                type="heartbeat", channel="dashboard", payload={"ping": "pong"}
                            ),
                            websocket,
                        )
            except Exception:
                return

        push_task = asyncio.create_task(push_dashboard_data())
        disconnect_task = asyncio.create_task(wait_disconnect())

        done, pending = await asyncio.wait(
            [push_task, disconnect_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    finally:
        ws_manager.disconnect(websocket)


# ========== 3. 设备状态实时推送 ==========

@router.websocket("/devices")
async def websocket_devices(websocket: WebSocket):
    """设备状态实时推送"""
    user = await authenticate_websocket(websocket)
    if user is None:
        return
    team_id = _aggregate_team_id(user)
    await ws_manager.connect(websocket, channel="devices", metadata=_conn_metadata(user))
    
    try:
        connected_msg = create_connected_message("devices", "设备状态 WebSocket连接成功")
        await ws_manager.send_personal_message(connected_msg, websocket)
        
        handler = RealtimeDataHandler()

        # 定时推送设备状态
        async def push_device_data():
            while True:
                try:
                    devices = await asyncio.to_thread(handler.get_device_status, team_id)
                    await ws_manager.send_personal_message(
                        create_data_message("devices", {"devices": devices, "count": len(devices)}),
                        websocket,
                    )
                    await asyncio.sleep(10)
                except WebSocketDisconnect:
                    raise
                except Exception as e:
                    logger.warning("推送设备状态失败: %s", e)
                    await asyncio.sleep(5)

        # 断连感知 (同 dashboard, 卡 0bef02bc: ping 记心跳)
        async def wait_disconnect():
            try:
                while True:
                    raw = await websocket.receive_text()
                    try:
                        data = json.loads(raw)
                    except (ValueError, TypeError):
                        continue
                    if data.get("type") == "ping":
                        ws_manager.record_heartbeat(websocket)
                        await ws_manager.send_personal_message(
                            WebSocketMessage(
                                type="heartbeat", channel="devices", payload={"ping": "pong"}
                            ),
                            websocket,
                        )
            except Exception:
                return

        push_task = asyncio.create_task(push_device_data())
        disconnect_task = asyncio.create_task(wait_disconnect())

        done, pending = await asyncio.wait(
            [push_task, disconnect_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    finally:
        ws_manager.disconnect(websocket)


# ========== 4. 告警实时推送 ==========

@router.websocket("/alerts")
async def websocket_alerts(websocket: WebSocket):
    """告警实时推送"""
    user = await authenticate_websocket(websocket)
    if user is None:
        return
    team_id = _aggregate_team_id(user)
    await ws_manager.connect(websocket, channel="alerts", metadata=_conn_metadata(user))
    
    try:
        connected_msg = create_connected_message("alerts", "告警 WebSocket连接成功")
        await ws_manager.send_personal_message(connected_msg, websocket)
        
        handler = RealtimeDataHandler()

        # 定时推送告警更新
        async def push_alarm_data():
            while True:
                try:
                    alarms = await asyncio.to_thread(handler.get_alarm_updates, team_id)
                    await ws_manager.send_personal_message(
                        create_data_message("alerts", {"alarms": alarms, "count": len(alarms)}),
                        websocket,
                    )
                    await asyncio.sleep(30)
                except WebSocketDisconnect:
                    raise
                except Exception as e:
                    logger.warning("推送告警数据失败: %s", e)
                    await asyncio.sleep(5)

        # 断连感知 (同 dashboard, 卡 0bef02bc: ping 记心跳)
        async def wait_disconnect():
            try:
                while True:
                    raw = await websocket.receive_text()
                    try:
                        data = json.loads(raw)
                    except (ValueError, TypeError):
                        continue
                    if data.get("type") == "ping":
                        ws_manager.record_heartbeat(websocket)
                        await ws_manager.send_personal_message(
                            WebSocketMessage(
                                type="heartbeat", channel="alerts", payload={"ping": "pong"}
                            ),
                            websocket,
                        )
            except Exception:
                return

        push_task = asyncio.create_task(push_alarm_data())
        disconnect_task = asyncio.create_task(wait_disconnect())

        done, pending = await asyncio.wait(
            [push_task, disconnect_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    finally:
        ws_manager.disconnect(websocket)


# ========== 5. 工单实时推送 ==========

@router.websocket("/workorders")
async def websocket_workorders(websocket: WebSocket):
    """工单实时推送"""
    user = await authenticate_websocket(websocket)
    if user is None:
        return
    team_id = _aggregate_team_id(user)
    await ws_manager.connect(websocket, channel="workorders", metadata=_conn_metadata(user))
    
    try:
        connected_msg = create_connected_message("workorders", "工单 WebSocket连接成功")
        await ws_manager.send_personal_message(connected_msg, websocket)
        
        handler = RealtimeDataHandler()

        # 定时推送工单更新
        async def push_workorder_data():
            while True:
                try:
                    workorders = await asyncio.to_thread(handler.get_workorder_updates, team_id)
                    await ws_manager.send_personal_message(
                        create_data_message("workorders", workorders),
                        websocket,
                    )
                    await asyncio.sleep(10)
                except WebSocketDisconnect:
                    raise
                except Exception as e:
                    logger.warning("推送工单数据失败: %s", e)
                    await asyncio.sleep(5)

        # 断连感知 (同 dashboard, 卡 0bef02bc: ping 记心跳)
        async def wait_disconnect():
            try:
                while True:
                    raw = await websocket.receive_text()
                    try:
                        data = json.loads(raw)
                    except (ValueError, TypeError):
                        continue
                    if data.get("type") == "ping":
                        ws_manager.record_heartbeat(websocket)
                        await ws_manager.send_personal_message(
                            WebSocketMessage(
                                type="heartbeat", channel="workorders", payload={"ping": "pong"}
                            ),
                            websocket,
                        )
            except Exception:
                return

        push_task = asyncio.create_task(push_workorder_data())
        disconnect_task = asyncio.create_task(wait_disconnect())

        done, pending = await asyncio.wait(
            [push_task, disconnect_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    finally:
        ws_manager.disconnect(websocket)


# ========== 6. 数字孪生实时推送 (整合 websocket_digital_twin.py) ==========

@router.websocket("/digital-twin/station/{station_id}")
async def websocket_digital_twin_station(websocket: WebSocket, station_id: int):
    """数字孪生站点级实时推送"""
    user = await authenticate_websocket(websocket)
    if user is None:
        return
    # 授权作用域 (卡 e2ad0b7d): HTTP 层 _check_station_team 的 WS 变体, 跨团队/不存在 → close 4003
    if not await authorize_station(websocket, user, station_id):
        return
    await ws_manager.connect(websocket, channel="digital_twin", station_id=station_id)
    
    try:
        connected_msg = create_connected_message(
            "digital_twin", 
            f"数字孪生站点{station_id} WebSocket连接成功",
            station_id=station_id
        )
        await ws_manager.send_personal_message(connected_msg, websocket)
        
        handler = DigitalTwinHandler()
        
        # 发送初始数据
        initial_data = await asyncio.to_thread(handler.get_station_digital_twin_data, station_id)
        await ws_manager.send_personal_message(
            WebSocketMessage(type="initial_data", channel="digital_twin", payload=initial_data, station_id=station_id),
            websocket
        )
        
        # 处理客户端消息
        async def handle_client_messages():
            try:
                while True:
                    data = await websocket.receive_json()
                    message_type = data.get("type")
                    
                    if message_type == "subscribe_device":
                        device_id = data.get("device_id")
                        if device_id:
                            # 消息级设备归属校验 (卡 e2ad0b7d): 越权订阅发 error 并跳过, 不断连
                            if not await device_in_scope(user, device_id):
                                await ws_manager.send_personal_message(
                                    WebSocketMessage(
                                        type="error",
                                        channel="device",
                                        device_id=device_id,
                                        message=f"无权订阅设备{device_id}"
                                    ),
                                    websocket
                                )
                                continue
                            ws_manager.subscribe_device(websocket, device_id)
                            await ws_manager.send_personal_message(
                                WebSocketMessage(
                                    type="subscribed", 
                                    channel="device", 
                                    device_id=device_id,
                                    message=f"已订阅设备{device_id}"
                                ),
                                websocket
                            )
                    
                    elif message_type == "unsubscribe_device":
                        device_id = data.get("device_id")
                        if device_id:
                            ws_manager.unsubscribe_device(websocket, device_id)
                            await ws_manager.send_personal_message(
                                WebSocketMessage(
                                    type="unsubscribed", 
                                    channel="device", 
                                    device_id=device_id,
                                    message=f"已取消订阅设备{device_id}"
                                ),
                                websocket
                            )
                    
                    elif message_type == "ping":
                        ws_manager.record_heartbeat(websocket)
                        await ws_manager.send_personal_message(
                            WebSocketMessage(type="heartbeat", channel="digital_twin", payload={"ping": "pong"}),
                            websocket
                        )
                    
            except Exception as e:
                logger.warning("处理客户端消息失败: %s", e)
        
        # 定时推送实时数据
        async def push_realtime_updates():
            while True:
                try:
                    station_update = await asyncio.to_thread(
                        handler.get_station_digital_twin_data, station_id
                    )
                    await ws_manager.send_personal_message(
                        WebSocketMessage(type="update", channel="station", payload=station_update, station_id=station_id),
                        websocket
                    )
                    
                    # 推送设备级更新
                    devices = station_update.get("devices", [])
                    for device_data in devices:
                        device_id = device_data["device"]["id"]
                        device_update = await asyncio.to_thread(
                            handler.get_device_realtime_update, device_id
                        )
                        await ws_manager.broadcast_device_subscribers(
                            device_id,
                            WebSocketMessage(type="update", channel="device", payload=device_update, device_id=device_id)
                        )
                    
                    await asyncio.sleep(3)
                    
                except Exception as e:
                    logger.warning("推送实时更新失败: %s", e)
                    await asyncio.sleep(5)
        
        # 并行运行
        client_task = asyncio.create_task(handle_client_messages())
        push_task = asyncio.create_task(push_realtime_updates())
        
        done, pending = await asyncio.wait(
            [client_task, push_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        for task in pending:
            task.cancel()
            
    finally:
        ws_manager.disconnect(websocket)


@router.websocket("/digital-twin/device/{device_id}")
async def websocket_digital_twin_device(websocket: WebSocket, device_id: int):
    """数字孪生设备级实时推送"""
    user = await authenticate_websocket(websocket)
    if user is None:
        return
    # 授权作用域 (卡 e2ad0b7d): HTTP 层 _check_device_team 的 WS 变体, 跨团队/不存在 → close 4003
    if not await authorize_device(websocket, user, device_id):
        return
    # 卡 6c62e375: 走统一 WebSocketManager (限额/心跳/超时驱逐/get_status 可见),
    # connect 内部完成 accept; 被 1013 拒绝时不进入推送循环
    if (await ws_manager.connect(websocket, channel="digital_twin")).get("rejected"):
        return

    try:
        connected_msg = create_connected_message(
            "digital_twin",
            f"设备{device_id}数字孪生 WebSocket连接成功",
            device_id=device_id
        )
        await ws_manager.send_personal_message(connected_msg, websocket)

        handler = DigitalTwinHandler()

        # 发送初始数据
        initial_data = await asyncio.to_thread(handler.get_device_realtime_update, device_id)
        await ws_manager.send_personal_message(
            WebSocketMessage(type="initial_data", channel="device", payload=initial_data, device_id=device_id), websocket
        )

        # 定时推送设备实时数据
        async def push_device_twin_data():
            while True:
                update_data = await asyncio.to_thread(
                    handler.get_device_realtime_update, device_id
                )
                await ws_manager.send_personal_message(
                    WebSocketMessage(type="update", channel="device", payload=update_data, device_id=device_id), websocket
                )
                await asyncio.sleep(1)

        # 断连感知 (同 dashboard): 纯 send-only 循环无法察觉客户端断开,
        # 用 receive 作为断连传感器, 客户端关闭时 receive 抛异常使任务结束,
        # 避免 handler 成为僵尸任务导致 teardown 挂起
        async def wait_disconnect():
            try:
                while True:
                    await websocket.receive_text()
            except Exception:
                return

        push_task = asyncio.create_task(push_device_twin_data())
        disconnect_task = asyncio.create_task(wait_disconnect())

        done, pending = await asyncio.wait(
            [push_task, disconnect_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    finally:
        ws_manager.disconnect(websocket)
        logger.info("设备%d数字孪生WebSocket连接断开", device_id)


# ========== 7. 大屏独立展示模式实时推送 ==========

@router.websocket("/dashboard/large-screen")
async def websocket_large_screen(websocket: WebSocket):
    """数据大屏独立展示模式实时推送
    
    每5秒推送聚合仪表盘数据：
    - 核心指标（设备总数、在线率、告警数、工单数）
    - 站点健康分布
    - 最近告警
    - 工单状态统计
    """
    # 大屏无人值守场景: 当前复用统一 token 鉴权闭合 P1 缺口。
    # TODO: 后续支持 ?api_key=<系统配置表 key> 免 token 认证 (大屏无登录态),
    #       从 system_configs 读取有效 key 校验, 降低大屏部署 token 续期成本。
    user = await authenticate_websocket(websocket)
    if user is None:
        return
    team_id = _aggregate_team_id(user)
    await ws_manager.connect(websocket, channel="large_screen", metadata=_conn_metadata(user))
    
    try:
        connected_msg = create_connected_message("large_screen", "数据大屏 WebSocket 连接成功")
        await ws_manager.send_personal_message(connected_msg, websocket)
        
        handler = RealtimeDataHandler()
        
        async def handle_client_messages():
            try:
                while True:
                    data = await websocket.receive_json()
                    message_type = data.get("type")
                    
                    if message_type == "ping":
                        ws_manager.record_heartbeat(websocket)
                        await ws_manager.send_personal_message(
                            WebSocketMessage(type="heartbeat", channel="large_screen", payload={"ping": "pong"}),
                            websocket
                        )
            except Exception as e:
                logger.warning("大屏客户端消息处理失败: %s", e)
        
        async def push_large_screen_data():
            while True:
                try:
                    # 推送聚合仪表盘数据
                    stats = await asyncio.to_thread(handler.get_dashboard_stats, team_id)
                    await ws_manager.send_personal_message(
                        create_data_message("large_screen", stats),
                        websocket
                    )
                    
                    # 推送设备状态概览
                    device_status = await asyncio.to_thread(handler.get_device_status, team_id)
                    await ws_manager.send_personal_message(
                        WebSocketMessage(
                            type="data",
                            channel="large_screen",
                            payload={"devices_summary": device_status[:10]},
                            timestamp=datetime.now(timezone.utc).isoformat(),
                        ),
                        websocket
                    )
                    
                    # 推送告警更新
                    alarm_data = await asyncio.to_thread(handler.get_alarm_updates, team_id)
                    if alarm_data:
                        await ws_manager.send_personal_message(
                            WebSocketMessage(
                                type="notification",
                                channel="large_screen",
                                payload={"alerts": alarm_data[:5]},
                                timestamp=datetime.now(timezone.utc).isoformat(),
                            ),
                            websocket
                        )
                    
                    await asyncio.sleep(5)
                    
                except Exception as e:
                    logger.warning("大屏数据推送失败: %s", e)
                    await asyncio.sleep(5)
        
        client_task = asyncio.create_task(handle_client_messages())
        push_task = asyncio.create_task(push_large_screen_data())
        
        done, pending = await asyncio.wait(
            [client_task, push_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        for task in pending:
            task.cancel()
            
    finally:
        ws_manager.disconnect(websocket)


# ========== 8. 全局数字孪生数据推送 ==========

@router.websocket("/digital-twin/global")
async def websocket_digital_twin_global(websocket: WebSocket):
    """全局数字孪生数据推送(所有站点)"""
    user = await authenticate_websocket(websocket)
    if user is None:
        return
    await ws_manager.connect(websocket, channel="digital_twin")
    
    try:
        connected_msg = create_connected_message("digital_twin", "全局数字孪生 WebSocket连接成功")
        await ws_manager.send_personal_message(connected_msg, websocket)

        # 断连感知: 原纯 sleep 循环无法察觉客户端断开 → handler 永不退出 → 连接泄漏。
        # 用 receive 作断连传感器, 客户端关闭时 receive 抛异常使 handler 退出。
        async def wait_disconnect():
            try:
                while True:
                    raw = await websocket.receive_text()
                    try:
                        data = json.loads(raw)
                    except (ValueError, TypeError):
                        continue
                    if data.get("type") == "ping":
                        ws_manager.record_heartbeat(websocket)
                        await ws_manager.send_personal_message(
                            WebSocketMessage(
                                type="heartbeat", channel="digital_twin", payload={"ping": "pong"}
                            ),
                            websocket,
                        )
            except Exception:
                return

        await wait_disconnect()

    finally:
        ws_manager.disconnect(websocket)


# ========== 导出路由 ==========

# 用于其他API调用的广播接口
async def broadcast_workorder_to_all(workorder_data: dict, team_id=None):
    """广播工单更新到所有客户端 (卡 434f741a: 按 team 作用域过滤)

    team_id=None 表示工单无归属站点 → 只发平台 admin 连接; 团队匹配逻辑见
    ws_manager.broadcast_team_scoped。
    """
    await ws_manager.broadcast_team_scoped(
        WebSocketMessage(type="notification", channel="workorders", payload=workorder_data),
        team_id=team_id,
    )


# ========== 9. 车队充电排队队列实时推送 ==========

@router.websocket("/fleet/queue/{station_id}")
async def websocket_fleet_queue(websocket: WebSocket, station_id: int):
    """车队充电排队队列实时推送

    连接后推送初始快照，之后每 5 秒推送该电站的队列状态快照
    (总数 / 各状态计数 / 平均等待)。前端收到后拉取完整明细。
    """
    user = await authenticate_websocket(websocket)
    if user is None:
        return
    # 授权作用域 (卡 e2ad0b7d): 站点归属校验, 跨团队/不存在 → close 4003
    if not await authorize_station(websocket, user, station_id):
        return
    await ws_manager.connect(websocket, channel="fleet_queue")

    try:
        await ws_manager.send_personal_message(
            create_connected_message("fleet_queue", f"车队排队队列 WebSocket连接成功 (station={station_id})"),
            websocket,
        )

        handler = FleetRealtimeHandler()

        # 发送初始快照
        initial = await asyncio.to_thread(handler.get_charging_queue_snapshot, station_id)
        await ws_manager.send_personal_message(
            create_data_message("fleet_queue", initial),
            websocket,
        )

        # 处理客户端消息 (心跳 / 订阅)，同时作为断连感知通道
        async def handle_client_messages():
            try:
                while True:
                    data = await websocket.receive_json()
                    if data.get("type") == "ping":
                        ws_manager.record_heartbeat(websocket)
                        await ws_manager.send_personal_message(
                            WebSocketMessage(type="heartbeat", channel="fleet_queue", payload={"ping": "pong"}),
                            websocket,
                        )
            except WebSocketDisconnect:
                raise
            except Exception as e:
                logger.warning("fleet_queue 客户端消息处理失败: %s", e)

        # 定时推送快照
        async def push_snapshot():
            while True:
                try:
                    await asyncio.sleep(5)
                    snapshot = await asyncio.to_thread(
                        handler.get_charging_queue_snapshot, station_id
                    )
                    await ws_manager.send_personal_message(
                        create_data_message("fleet_queue", snapshot),
                        websocket,
                    )
                except WebSocketDisconnect:
                    raise
                except Exception as e:
                    logger.warning("fleet_queue 推送失败: %s", e)
                    await asyncio.sleep(5)

        client_task = asyncio.create_task(handle_client_messages())
        push_task = asyncio.create_task(push_snapshot())

        done, pending = await asyncio.wait(
            [client_task, push_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    finally:
        ws_manager.disconnect(websocket)


# ========== 10. 车队 V2G 计划状态实时推送 ==========

@router.websocket("/fleet/v2g/{enterprise_id}")
async def websocket_fleet_v2g(websocket: WebSocket, enterprise_id: int):
    """车队 V2G 计划状态实时推送

    连接后推送初始快照，之后每 5 秒推送该企业的 V2G 计划状态快照
    (计划总数 / 各状态计数)。前端收到后拉取完整明细。
    """
    user = await authenticate_websocket(websocket)
    if user is None:
        return
    # 授权作用域 (卡 e2ad0b7d): HTTP 层 assert_enterprise_team_access 的 WS 变体,
    # 跨团队/不存在 → close 4003
    if not await authorize_enterprise(websocket, user, enterprise_id):
        return
    await ws_manager.connect(websocket, channel="fleet_v2g")

    try:
        await ws_manager.send_personal_message(
            create_connected_message("fleet_v2g", f"车队V2G WebSocket连接成功 (enterprise={enterprise_id})"),
            websocket,
        )

        handler = FleetRealtimeHandler()

        # 发送初始快照
        initial = await asyncio.to_thread(handler.get_v2g_snapshot, enterprise_id)
        await ws_manager.send_personal_message(
            create_data_message("fleet_v2g", initial),
            websocket,
        )

        # 处理客户端消息 (心跳 / 订阅)，同时作为断连感知通道
        async def handle_client_messages():
            try:
                while True:
                    data = await websocket.receive_json()
                    if data.get("type") == "ping":
                        ws_manager.record_heartbeat(websocket)
                        await ws_manager.send_personal_message(
                            WebSocketMessage(type="heartbeat", channel="fleet_v2g", payload={"ping": "pong"}),
                            websocket,
                        )
            except WebSocketDisconnect:
                raise
            except Exception as e:
                logger.warning("fleet_v2g 客户端消息处理失败: %s", e)

        # 定时推送快照
        async def push_snapshot():
            while True:
                try:
                    await asyncio.sleep(5)
                    snapshot = await asyncio.to_thread(handler.get_v2g_snapshot, enterprise_id)
                    await ws_manager.send_personal_message(
                        create_data_message("fleet_v2g", snapshot),
                        websocket,
                    )
                except WebSocketDisconnect:
                    raise
                except Exception as e:
                    logger.warning("fleet_v2g 推送失败: %s", e)
                    await asyncio.sleep(5)

        client_task = asyncio.create_task(handle_client_messages())
        push_task = asyncio.create_task(push_snapshot())

        done, pending = await asyncio.wait(
            [client_task, push_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

    finally:
        ws_manager.disconnect(websocket)

