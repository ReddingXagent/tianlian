"""告警升级链 (卡 8d98ebe3)

AlarmEscalationTracker: 告警触发即时通知 → 超时未确认逐级升级。

升级层级:
  ① 触发即时: IM/企微群通知 (level 1)
  ② 经 sms_escalate_min (settings.ALARM_SMS_ESCALATE_MIN, 默认 15min) 未确认: 短信通知 on_call 值班人 (level 2)
  ③ 再经同样时长 (voice_escalate_min = 2×sms) 未确认: 语音外呼桩 (level 3)

POST /api/v1/alerts/{alarm_id}/ack 确认 → ack() 终止升级链。

调度: 本模块只提供状态机与辅助函数, 不自带 celery/cron —— 由调用方 (告警触发流程 /
定时巡检) 调度 trigger() 与 check_escalation()。状态内存态 (单进程); 持久化由调用方
按需扩展。时钟可注入 (now=) 做确定性测试。
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from app.services.channel_providers import dispatch_real_channel

logger = logging.getLogger(__name__)

# ack 后状态保留时长: 超过则 check_escalation 清理 (避免 _states 无限增长, BUG1)
ACK_RETENTION = timedelta(hours=24)


def _get_setting(name: str, default: Any) -> Any:
    """懒读 settings 字段, 取不到/异常回退 default。"""
    try:
        from app.core.config import settings
        val = getattr(settings, name, default)
        return default if val is None else val
    except Exception:
        return default


class AlarmEscalationTracker:
    """告警升级链状态机 (内存态, 单进程)。

    Args:
        notifier: 发送回调 ``notifier(level, channel, alarm_id, message, receiver)``,
                  None 时走默认实现 (调 channel_providers.dispatch_real_channel)。
        oncall_resolver: 解析 on_call 值班人 ``resolver(team_id) -> receiver dict``,
                  供 level 2/3 (短信/语音) 取接收人。None → 无接收人。
        sms_escalate_min: level ② 阈值 (分钟), None 读 settings.ALARM_SMS_ESCALATE_MIN。
        voice_escalate_min: level ③ 阈值 (分钟), None = 2 × sms_escalate_min。
    """

    def __init__(
        self,
        *,
        notifier: Optional[Callable] = None,
        oncall_resolver: Optional[Callable] = None,
        sms_escalate_min: Optional[int] = None,
        voice_escalate_min: Optional[int] = None,
    ):
        self._notifier = notifier
        self._oncall_resolver = oncall_resolver
        self._states: Dict[Any, Dict[str, Any]] = {}
        self._lock = threading.Lock()  # _states 读写锁 (BUG2 线程安全)
        if sms_escalate_min is None:
            sms_escalate_min = int(_get_setting("ALARM_SMS_ESCALATE_MIN", 15))
        self.sms_escalate_min = sms_escalate_min
        if voice_escalate_min is None:
            voice_escalate_min = 2 * self.sms_escalate_min
        self.voice_escalate_min = voice_escalate_min

    # ─── 内部 ───

    def _notify(self, level, channel, alarm_id, message, receiver):
        """统一发送入口: 注入式 notifier 优先, 否则默认 (真实 dispatch_real_channel)。"""
        if self._notifier is not None:
            self._notifier(level, channel, alarm_id, message, receiver)
        else:
            self._default_notifier(level, channel, alarm_id, message, receiver)

    def _default_notifier(self, level, channel, alarm_id, message, receiver=None):
        """默认发送: 走 channel_providers 真实路径, 读 state 内 team_id/db。"""
        st = self._states.get(alarm_id) or {}
        try:
            dispatch_real_channel(
                channel, st.get("team_id"), st.get("db"),
                receiver or {}, message, None,
            )
        except Exception as e:
            logger.error(
                "升级链默认发送失败 (alarm=%s level=%s ch=%s): %s",
                alarm_id, level, channel, e,
            )

    def _resolve_oncall(self, team_id) -> Optional[Dict[str, Any]]:
        if self._oncall_resolver is None:
            return None
        try:
            return self._oncall_resolver(team_id)
        except Exception:
            return None

    # ─── 公开 API ───

    def trigger(
        self, alarm_id, *, message, team_id=None, receiver=None,
        now=None, db=None, immediate_channels=("im", "wecom"),
    ) -> List[Dict[str, Any]]:
        """告警触发: 记录状态并发送 ① 即时通知 (IM/企微)。

        Returns: 本次发送的 level-1 动作列表 [{level, channel, alarm_id, receiver}]。
        """
        if now is None:
            now = datetime.now(timezone.utc)
        actions: List[Dict[str, Any]] = []
        with self._lock:
            self._states[alarm_id] = {
                "triggered_at": now,
                "acked": False,
                "acked_at": None,
                "level": 1,
                "message": message,
                "team_id": team_id,
                "receiver": receiver,
                "db": db,
            }
            for ch in immediate_channels:
                self._notify(1, ch, alarm_id, message, receiver)
                actions.append({
                    "level": 1, "channel": ch, "alarm_id": alarm_id, "receiver": receiver,
                })
        return actions

    def check_escalation(self, *, now=None) -> List[Dict[str, Any]]:
        """巡检所有未确认告警, 对超时未 ack 的逐级升级 (② 短信 / ③ 语音)。

        每级仅触发一次 (level 守卫)。voice 阈值优先判定; 跨级 (sms+voice 同时超阈值)
        时 voice 升级同时补发一条 sms, 不跳过 sms 层 (BUG3)。已 ack 超 ACK_RETENTION
        的状态在此清理 (BUG1)。负 elapsed (clock skew) 钳位 0 (BUG4)。
        Returns: 本次升级动作列表。"""
        if now is None:
            now = datetime.now(timezone.utc)
        actions: List[Dict[str, Any]] = []
        with self._lock:
            for alarm_id, st in list(self._states.items()):
                # 已 ack: 超 ACK_RETENTION 则清理, 否则跳过
                if st["acked"]:
                    acked_at = st.get("acked_at")
                    if acked_at is not None and (now - acked_at) >= ACK_RETENTION:
                        del self._states[alarm_id]
                    continue
                # BUG4: clock skew 防护, 时钟回拨时 elapsed 钳位 0 不误升级
                elapsed_min = max(
                    0.0, (now - st["triggered_at"]).total_seconds() / 60.0
                )
                receiver = self._resolve_oncall(st.get("team_id"))
                message = st["message"]
                # ③ 语音 (elapsed >= voice 阈值, 未到 level 3)
                if elapsed_min >= self.voice_escalate_min and st["level"] < 3:
                    # BUG3: 跨级补发 — sms 尚未发过 (level<2) 时, voice 升级同时补一条 sms
                    if st["level"] < 2:
                        self._notify(2, "sms", alarm_id, message, receiver)
                        actions.append({
                            "level": 2, "channel": "sms", "alarm_id": alarm_id,
                            "receiver": receiver,
                        })
                    self._notify(3, "voice", alarm_id, message, receiver)
                    st["level"] = 3
                    actions.append({
                        "level": 3, "channel": "voice", "alarm_id": alarm_id,
                        "receiver": receiver,
                    })
                # ② 短信 (elapsed >= sms 阈值, 未到 level 2)
                elif elapsed_min >= self.sms_escalate_min and st["level"] < 2:
                    self._notify(2, "sms", alarm_id, message, receiver)
                    st["level"] = 2
                    actions.append({
                        "level": 2, "channel": "sms", "alarm_id": alarm_id,
                        "receiver": receiver,
                    })
        return actions

    def ack(self, alarm_id, *, now=None) -> bool:
        """确认告警 → 终止升级链。已确认/无状态返回 False, 首次确认返回 True。"""
        with self._lock:
            st = self._states.get(alarm_id)
            if st is None or st["acked"]:
                return False
            if now is None:
                now = datetime.now(timezone.utc)
            st["acked"] = True
            st["acked_at"] = now
            level = st["level"]
        logger.info("告警 %s 已确认, 升级链终止 (达到 level %s)", alarm_id, level)
        return True

    def get_state(self, alarm_id) -> Optional[Dict[str, Any]]:
        """返回告警升级状态 (triggered_at/acked/level/...)。"""
        with self._lock:
            return self._states.get(alarm_id)


# 模块级单例 (由 ack 端点与告警触发流程共享, 调度由调用方驱动)
alarm_escalation_tracker = AlarmEscalationTracker()
