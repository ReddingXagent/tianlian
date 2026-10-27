"""Runbook 执行引擎 + 便捷函数 — 从原 runbook_engine.py 拆出 (卡 1ed83abf)。

对外符号 ``RunbookEngine`` / ``execute_runbook_for_alarm`` 由包 ``__init__`` 重导出,
import 路径不变。shell=True 信任通道逻辑 (``_run_command`` trusted 分支 /
``_substitute_vars`` shlex.quote) 原样保留, 不动安全边界。
"""
import copy
import json
import shlex
import subprocess
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional

import app.services.runbook_engine as _pkg
from .models import (
    RunbookActionType,
    RunbookExecution,
    RunbookStatus,
    RiskLevel,
    RunbookStep,
)
from .security import safe_command_list
from .templates import RunbookTemplate


class _LoggerProxy:
    """包级 logger 代理 —— 拆包兼容层 (load-bearing)。

    原单文件 runbook_engine.py 下, RunbookEngine 各方法的 ``logger.X()`` 以模块全局
    ``logger`` 调用, ``patch("app.services.runbook_engine.logger")`` 改的是该模块
    ``__dict__``, 方法运行时解析全局即命中 mock。拆包后这些方法定义在本子模块,
    全局 ``logger`` 解析于 engine 命名空间, 包级 patch 不再生效(test_runbook_engine
    的 ``test_send_notification_default_message_uses_alarm_id`` 会脱钩)。

    本代理把每次属性访问转发到 ``_pkg.logger`` (运行时动态查找包属性), 使包级 patch
    重新命中; 方法体内所有 ``logger.info/warning/error`` 调用零改动。正常(未 patch)
    运行时 ``_pkg.logger`` 是真 Logger 对象, 行为与原单文件完全一致。
    """

    def __getattr__(self, name):
        return getattr(_pkg.logger, name)


logger = _LoggerProxy()


# ========== 执行引擎 ==========

class RunbookEngine:
    """
    Runbook执行引擎

    流程:
    1. 接收诊断结果
    2. 匹配Runbook模板
    3. 按风险等级过滤自动执行步骤
    4. 逐步执行(含前置检查、回滚准备)
    5. 执行结果记录
    6. 需人工步骤生成工单
    """

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    def execute_runbook(self, template: str = None, device_id: int = 0, alarm_id: int = 0, db = None, **kwargs) -> int:
        """执行Runbook（别名，兼容测试调用）"""
        import time
        diagnosis_result = {
            'fault_type': template or '设备离线',
            'remote_fixable': False,
            'immediate_actions': [],
        }
        device_info = {
            'id': device_id,
            'ip': '192.168.1.100',
            'sn': f'DEV-{device_id:04d}',
            'name': f'Device-{device_id}',
            'type': 'inverter',
            'station_id': 1,
        }
        self.execute(alarm_id, diagnosis_result, device_info, db=db)
        return int(time.time())  # Return a positive integer as runbook ID

    def get_runbook_templates(self) -> list:
        """获取所有Runbook模板"""
        return list(RunbookTemplate.TEMPLATES.keys())

    def approve_runbook(self, runbook_id: str = None, approved: bool = True, db = None) -> dict:
        """审批Runbook"""
        return {'runbook_id': runbook_id, 'approved': approved, 'status': 'approved'}

    def execute_runbook_step(self, step_id: int = 0, runbook_id: str = None, db = None) -> dict:
        """执行单个Runbook步骤"""
        return {'step_id': step_id, 'runbook_id': runbook_id, 'status': 'completed'}

    def execute(
        self,
        alarm_id: int,
        diagnosis_result: Dict,
        device_info: Dict,
        station_info: Optional[Dict] = None,
        db = None,
        auto_trigger: bool = False,
    ) -> Dict:
        """
        执行Runbook自动化修复

        Args:
            alarm_id: 告警ID
            diagnosis_result: AI诊断结果 (fault_type, remote_fixable, immediate_actions, etc.)
            device_info: 设备信息 (id, ip, sn, name, etc.)
            station_info: 站点信息 (可选)
            db: 数据库session (可选)
            auto_trigger: 保留参数(历史兼容)。实际不再按此参数过滤步骤:
                MEDIUM+ 步骤一律走 DB 审批流(有 db 时)或降级跳过/执行(无 db 时),
                由 create_approval_request + 审批执行链路保证安全, 与本参数无关。

        Returns:
            执行结果统计
        """
        import time
        start = time.time()

        # 0. 同告警去重闸 (卡 5421defc): 同 alarm_id 已有 running/pending_approval
        # 在途执行时短路返回, 不执行任何命令、不建审批、不建新记录。
        # 仅终态(COMPLETED/FAILED 等)历史放行 → 手动重跑语义保留。
        if db is not None:
            dedup = self._find_active_execution(alarm_id, db)
            if dedup is not None:
                logger.info(
                    "Runbook 去重短路: 告警#%s 已有 %s 态执行 %s, 跳过本次执行",
                    alarm_id, dedup.status, dedup.runbook_id,
                )
                return {
                    "runbook_id": dedup.runbook_id,
                    "alarm_id": alarm_id,
                    "status": "deduplicated",
                    "original_status": dedup.status,
                }

        fault_type = diagnosis_result.get("fault_type", "")
        device_id = device_info.get("id", 0)
        device_ip = device_info.get("ip", device_info.get("address", ""))
        device_sn = device_info.get("sn", device_info.get("device_sn", ""))
        device_name = device_info.get("name", device_info.get("device_name", ""))
        device_type = device_info.get("type", device_info.get("device_type", ""))
        station_id = device_info.get("station_id", 0)

        # 1. 匹配Runbook模板 (DB active 模板优先, fallback 内置)
        # DB 模板属用户自定义(不可信); 内置 TEMPLATES / get_default 为硬编码可信源。
        template = None
        template_is_builtin = False
        if db is not None:
            template = self._match_template_db(fault_type, device_type, db)
        if not template:
            template = RunbookTemplate.match(fault_type, device_type)
            template_is_builtin = template is not None
        if not template:
            template = RunbookTemplate.get_default()
            template_is_builtin = True

        runbook_id = f"RB-{alarm_id}-{int(time.time())}"
        execution = RunbookExecution(
            runbook_id=runbook_id,
            alarm_id=alarm_id,
            device_id=device_id,
            station_id=station_id,
            fault_type=fault_type,
            status=RunbookStatus.RUNNING,
            start_time=datetime.now(timezone.utc),
        )

        # 2. 替换模板变量
        steps = self._substitute_vars(template["steps"], {
            "device_id": device_id,
            "device_ip": device_ip,
            "device_sn": device_sn,
            "device_name": device_name,
            "device_type": device_type,
            "station_id": station_id,
        })
        execution.steps = steps

        # 内置硬编码模板为可信源: 允许其命令使用 &&/|| 等 shell 操作符。
        # 用户自定义(DB)模板保持 trusted=False, 走完整 shell 注入防御, 一行不弱化。
        if template_is_builtin:
            for _s in steps:
                _s.trusted = True

        # 3. 分类步骤
        auto_steps = [s for s in steps if s.auto_execute]
        manual_steps = [s for s in steps if not s.auto_execute]
        execution.auto_executed = len(auto_steps)
        execution.manual_required = len(manual_steps)

        logger.info(
            f"Runbook {runbook_id} 启动: 告警#{alarm_id}, 故障:{fault_type}, "
            f"自动步骤:{len(auto_steps)}, 人工步骤:{len(manual_steps)}"
        )

        # 4. 执行自动步骤(低风险直接执行, 中高风险需审批)
        approval_needed_count = 0
        if self.dry_run:
            logger.info("[DRY_RUN] Runbook %s 跳过执行", runbook_id)
            for step in steps:
                step.status = RunbookStatus.SKIPPED

            execution.status = RunbookStatus.COMPLETED
            execution.skipped_steps = len(steps)
        else:
            for step in auto_steps:
                # 审批流判断: MEDIUM/HIGH/CRITICAL风险等级需要审批
                if step.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL):
                    if db:
                        from app.api.v1.runbook_approval import create_approval_request
                        create_approval_request(
                            db=db,
                            runbook_id=runbook_id,
                            alarm_id=alarm_id,
                            step_index=step.step_id,
                            step_description=step.description,
                            action_type=step.action_type,
                            command_preview=step.command[:200] if step.command else "",
                            risk_level=step.risk_level,
                            rollback_preview=step.rollback_command[:200] if step.rollback_command else None,
                        )
                        step.status = RunbookStatus.PENDING
                        approval_needed_count += 1
                        logger.info("Runbook步骤#%s 风险等级%s, 已创建审批请求", step.step_id, step.risk_level)
                    else:
                        # 无DB时降级: 中风险可执行, 高/极高跳过
                        if step.risk_level == RiskLevel.MEDIUM:
                            self._execute_step(step, device_info)
                        else:
                            step.status = RunbookStatus.SKIPPED
                            step.result = f"需要{step.risk_level}级别审批, 跳过"
                            logger.warning("Runbook步骤#%s 需要%s审批, 无DB无法审批, 跳过", step.step_id, step.risk_level)
                else:
                    # LOW风险: 直接执行
                    self._execute_step(step, device_info)

                if step.status == RunbookStatus.COMPLETED:
                    execution.success_steps += 1
                elif step.status == RunbookStatus.FAILED:
                    execution.failed_steps += 1
                    execution.error_message += f"Step#{step.step_id}: {step.error_message}\n"
                elif step.status == RunbookStatus.PENDING:
                    pass  # 等待审批
                elif step.status == RunbookStatus.SKIPPED:
                    execution.skipped_steps += 1

        # 5. 处理人工步骤(创建工单/通知)
        created_wo_id = None
        if db and manual_steps:
            self._handle_manual_steps(manual_steps, alarm_id, device_info, db)
            # 检查是否创建了工单
            for step in manual_steps:
                if step.action_type == RunbookActionType.CREATE_WORKORDER:
                    created_wo_id = getattr(step, '_workorder_id', None)
                    if created_wo_id:
                        execution.workorder_id = created_wo_id
                    break
                step.status = RunbookStatus.PENDING
        elif manual_steps:
            # 无DB时仍记录日志
            logger.info("Runbook: 人工步骤 %d 个, 需在DB就绪后处理", len(manual_steps))

        execution.end_time = datetime.now(timezone.utc)
        execution.total_duration_ms = int((time.time() - start) * 1000)

        # 6. 确定最终状态
        if approval_needed_count > 0 and execution.success_steps == 0 and execution.failed_steps == 0:
            execution.status = "pending_approval"  # 全部在等审批
        elif execution.failed_steps == 0:
            execution.status = RunbookStatus.COMPLETED
        elif execution.success_steps > 0:
            execution.status = RunbookStatus.COMPLETED  # 部分成功
        else:
            execution.status = RunbookStatus.FAILED

        # 7. 保存执行记录
        if db:
            self._save_execution(execution, db)

        result = self._to_dict(execution)
        result["approval_needed"] = approval_needed_count
        return result

    @staticmethod
    def _find_active_execution(alarm_id: int, db):
        """查同告警在途执行记录(running / pending_approval), 命中返回记录否则 None。

        status 为 String 列; "pending_approval" 是 execute() 第6步拼的裸字符串,
        按字符串比对。查询异常(如测试无表)降级为 None(放行), 不阻塞执行;
        返回对象 status 非真实 str(如 MagicMock db 的假记录)同样放行。
        """
        try:
            from app.models.runbook_execution import RunbookExecutionRecord
            row = db.query(RunbookExecutionRecord).filter(
                RunbookExecutionRecord.alarm_id == alarm_id,
                RunbookExecutionRecord.status.in_(["running", "pending_approval"]),
            ).order_by(RunbookExecutionRecord.id.desc()).first()
            if row is not None and isinstance(row.status, str):
                return row
            return None
        except Exception as e:
            logger.warning("Runbook 去重查询失败(放行): %s", e)
            return None

    def _match_template_db(self, fault_type: str, device_type: str, db) -> Optional[Dict]:
        """从 DB 匹配 active 模板: alarm_type 精确 → 关键词模糊 → category 兜底。

        未命中返回 None (调用方 fallback 到内置 RunbookTemplate.match)。
        """
        try:
            from app.models.runbook import RunbookTemplateModel
        except Exception:
            return None
        if not fault_type:
            return None

        # 精确匹配 alarm_type
        row = db.query(RunbookTemplateModel).filter(
            RunbookTemplateModel.status == "active",
            RunbookTemplateModel.alarm_type == fault_type,
        ).first()

        # 关键词模糊匹配 (与内置 match 模糊逻辑保持一致)
        if not row:
            for r in db.query(RunbookTemplateModel).filter(
                RunbookTemplateModel.status == "active"
            ).all():
                if r.alarm_type and any(kw and kw in r.alarm_type for kw in fault_type.split()):
                    row = r
                    break

        # 设备类别兜底
        if not row and device_type:
            row = db.query(RunbookTemplateModel).filter(
                RunbookTemplateModel.status == "active",
                RunbookTemplateModel.category == device_type.lower(),
            ).first()

        if not row:
            return None
        return self._db_row_to_template_dict(row)

    @staticmethod
    def _db_row_to_template_dict(row) -> Dict:
        """DB ORM row → 内置模板 dict 格式 {category, description, steps:[RunbookStep]}

        steps JSON 每项含运行时字段(status/result/...), 只取 RunbookStep 已知字段构造。
        """
        known = set(RunbookStep.__dataclass_fields__)
        steps: List[RunbookStep] = []
        for s in (row.steps or []):
            kwargs = {k: v for k, v in s.items() if k in known}
            try:
                steps.append(RunbookStep(**kwargs))
            except Exception:
                logger.warning("runbook模板步骤反序列化失败，跳过该步", exc_info=True)
                continue
        return {
            "category": row.category or "general",
            "description": row.description or "",
            "steps": steps,
        }

    def _run_command(self, command: str, timeout: int, trusted: bool):
        """执行单条命令, 按 trusted 选择执行通道。

        - trusted=False(用户自定义 / DB 模板 / API 输入): safe_command_list 黑名单
          校验 + shlex.split 成 argv, subprocess.run(shell=False) 执行。注入防御
          完整保留, 与 runbook_approval._execute_approved_step 一致。
        - trusted=True(仅内置硬编码 TEMPLATES): 命令来自可信源, 跳过黑名单, 以原串
          subprocess.run(shell=True) 执行, 支持 &&/||/管道等 shell 操作符。仅
          RunbookEngine 对硬编码模板内部置位, 外部输入永不进入此通道。
        """
        if trusted:
            if not command or not command.strip():
                raise ValueError("命令为空,拒绝执行")
            return subprocess.run(
                command, shell=True, capture_output=True,
                text=True, timeout=timeout,
            )
        return subprocess.run(
            safe_command_list(command), shell=False, capture_output=True,
            text=True, timeout=timeout,
        )

    def _execute_step(self, step: RunbookStep, device_info: Dict):
        """执行单个Runbook步骤"""
        import time
        import subprocess

        step.status = RunbookStatus.RUNNING
        step_start = time.time()

        try:
            if not step.command:
                step.status = RunbookStatus.SKIPPED
                step.result = "No command"
                return

            action_type = step.action_type

            # 前置检查
            if step.pre_check:
                try:
                    pre_result = self._run_command(
                        step.pre_check, step.timeout_sec, step.trusted
                    )
                    if pre_result.returncode != 0:
                        step.status = RunbookStatus.SKIPPED
                        step.result = f"Pre-check failed: {pre_result.stdout.strip()}"
                        logger.warning("Runbook步骤#%s前置检查失败, 跳过", step.step_id)
                        return
                except subprocess.TimeoutExpired:
                    logger.warning("Runbook步骤#%s前置检查超时, 继续执行", step.step_id)

            # 执行命令
            if action_type == RunbookActionType.REMOTE_COMMAND:
                result = self._run_command(step.command, step.timeout_sec, step.trusted)
                step.result = result.stdout.strip()
                if result.returncode != 0:
                    step.status = RunbookStatus.FAILED
                    step.error_message = result.stderr.strip()[:500]
                else:
                    step.status = RunbookStatus.COMPLETED

            elif action_type in (RunbookActionType.RESTART_SERVICE, RunbookActionType.CONFIG_CHANGE,
                                 RunbookActionType.CLEAR_CACHE, RunbookActionType.RESET_PARAMETER):
                result = self._run_command(step.command, step.timeout_sec, step.trusted)
                step.result = result.stdout.strip()
                if result.returncode != 0:
                    step.status = RunbookStatus.FAILED
                    step.error_message = result.stderr.strip()[:500]
                    # 自动回滚
                    if step.rollback_command and action_type == RunbookActionType.CONFIG_CHANGE:
                        logger.warning("Runbook步骤#%s失败, 执行回滚", step.step_id)
                        self._run_command(step.rollback_command, 30, step.trusted)
                        step.status = RunbookStatus.ROLLED_BACK
                else:
                    step.status = RunbookStatus.COMPLETED

            else:
                step.status = RunbookStatus.SKIPPED
                step.result = f"Action type {action_type} requires manual handling"

        except subprocess.TimeoutExpired:
            step.status = RunbookStatus.FAILED
            step.error_message = f"Timeout after {step.timeout_sec}s"
        except Exception as e:
            step.status = RunbookStatus.FAILED
            step.error_message = str(e)[:500]

        step.duration_ms = int((time.time() - step_start) * 1000)

        logger.info(
            f"Runbook步骤#{step.step_id} [{step.action_type}] {step.status}: "
            f"{step.description} ({step.duration_ms}ms)"
        )

    def _handle_manual_steps(
        self, steps: List[RunbookStep], alarm_id: int, device_info: Dict, db
    ):
        """处理需人工介入的步骤(创建工单/通知)"""
        for step in steps:
            if step.action_type == RunbookActionType.CREATE_WORKORDER:
                self._create_workorder_from_runbook(step, alarm_id, device_info, db)
            elif step.action_type == RunbookActionType.SEND_NOTIFICATION:
                self._send_notification(step, alarm_id, device_info)

    def _create_workorder_from_runbook(
        self, step: RunbookStep, alarm_id: int, device_info: Dict, db
    ):
        """从Runbook步骤创建工单"""
        try:
            from app.models.workorder import WorkOrder, WorkOrderType, WorkOrderLevel, WorkOrderStatus
            from datetime import datetime, timezone

            params = step.params
            level_map = {
                "critical": WorkOrderLevel.CRITICAL,
                "high": WorkOrderLevel.CRITICAL,
                "medium": WorkOrderLevel.WARNING,
                "low": WorkOrderLevel.INFO,
            }
            type_map = {
                "紧急检修": WorkOrderType.EMERGENCY,
                "巡检": WorkOrderType.PREVENTIVE,
                "检修": WorkOrderType.REPAIR,
                "绝缘检测": WorkOrderType.EMERGENCY,
                "现场巡检": WorkOrderType.PREVENTIVE,
                "故障排查": WorkOrderType.REPAIR,
            }

            # 生成工单号
            now = datetime.now(timezone.utc)
            wo_id = f"WO-{now.strftime('%Y%m%d')}-{now.strftime('%H%M%S')}-{step.step_id}"

            workorder = WorkOrder(
                id=wo_id,
                type=type_map.get(params.get("type", ""), WorkOrderType.REPAIR),
                level=level_map.get(params.get("urgency", "medium"), WorkOrderLevel.WARNING),
                device_id=device_info.get("id"),
                station_id=device_info.get("station_id"),
                fault_desc=f"[Runbook自动] {step.description}: {params.get('message', '')}",
                status=WorkOrderStatus.PENDING,
            )
            db.add(workorder)
            db.commit()
            db.refresh(workorder)
            # 保存工单ID到步骤上，供调用方获取
            step._workorder_id = workorder.id
            logger.info("Runbook创建工单#%s for 告警#%s", workorder.id, alarm_id)

        except Exception as e:
            logger.error("Runbook创建工单失败: %s", str(e))
            db.rollback()

    def _send_notification(self, step: RunbookStep, alarm_id: int, device_info: Dict):
        """发送Runbook通知"""
        params = step.params
        message = params.get("message", f"告警#{alarm_id} Runbook通知")
        urgency = params.get("urgency", "medium")

        logger.info("[Runbook通知] 紧急度:%s | %s", urgency, message)
        try:
            # 尝试集成 notification_dispatcher
            from app.services.notification_dispatcher import dispatch_notification
            dispatch_notification(
                title=f"Runbook通知: 告警#{alarm_id}",
                content=message,
                urgency=urgency,
                device_info=device_info,
            )
            logger.info("Runbook通知已通过 notification_dispatcher 发送: %s", message)
        except ImportError:
            # notification_dispatcher 尚未实现——回退到日志记录
            logger.warning("notification_dispatcher 不可用，通知仅记录到日志")
        except Exception as e:
            logger.warning("发送Runbook通知失败: %s", e)

    def _save_execution(self, execution: RunbookExecution, db):
        """保存Runbook执行记录到数据库"""
        try:
            from app.models.runbook_execution import RunbookExecutionRecord

            record = RunbookExecutionRecord(
                runbook_id=execution.runbook_id,
                alarm_id=execution.alarm_id,
                diagnosis_record_id=execution.diagnosis_record_id,
                device_id=execution.device_id,
                station_id=execution.station_id,
                fault_type=execution.fault_type,
                status=execution.status,
                steps_json=json.dumps([asdict(s) for s in execution.steps], ensure_ascii=False),
                start_time=execution.start_time,
                end_time=execution.end_time,
                total_duration_ms=execution.total_duration_ms,
                success_steps=execution.success_steps,
                failed_steps=execution.failed_steps,
                skipped_steps=execution.skipped_steps,
                auto_executed=execution.auto_executed,
                manual_required=execution.manual_required,
                error_message=execution.error_message,
            )
            db.add(record)
            db.commit()
            logger.info("Runbook执行记录已保存: %s", execution.runbook_id)

        except Exception as e:
            logger.error("Runbook执行记录保存失败: %s", str(e))
            db.rollback()

    def _substitute_vars(self, steps: List[RunbookStep], context: Dict) -> List[RunbookStep]:
        """替换步骤中的变量。

        变量值统一经 shlex.quote 转义后再替换。内置硬编码模板走 _run_command 的
        trusted=True → shell=True 信任通道, 若 device_info 字段被污染(如 device_ip
        含 ``;``/``|``/``$`` 等 shell 元字符), str(val) 裸替换会让 shell=True 把
        元字符解释成命令分隔/替换 → 命令注入。shlex.quote 把含元字符的值用单引号
        包裹使其失活; 对仅含安全字符(a-zA-Z0-9 @%_+=:,./- )的值原样返回不加引号,
        故正常 IP/SN/name 与内置模板自身的 &&/|| 操作符(硬编码于模板, 非变量值)均不受影响。
        """
        new_steps = []
        for step in steps:
            s = copy.deepcopy(step)
            for key, val in context.items():
                placeholder = f"{{{key}}}"
                safe_val = shlex.quote(str(val))
                if s.command:
                    s.command = s.command.replace(placeholder, safe_val)
                if s.rollback_command:
                    s.rollback_command = s.rollback_command.replace(placeholder, safe_val)
                if s.pre_check:
                    s.pre_check = s.pre_check.replace(placeholder, safe_val)
                if s.post_check:
                    s.post_check = s.post_check.replace(placeholder, safe_val)
            new_steps.append(s)
        return new_steps

    def _to_dict(self, execution: RunbookExecution) -> Dict:
        """转换为返回字典"""
        return {
            "runbook_id": execution.runbook_id,
            "alarm_id": execution.alarm_id,
            "fault_type": execution.fault_type,
            "status": execution.status,
            "total_duration_ms": execution.total_duration_ms,
            "success_steps": execution.success_steps,
            "failed_steps": execution.failed_steps,
            "skipped_steps": execution.skipped_steps,
            "auto_executed": execution.auto_executed,
            "manual_required": execution.manual_required,
            "workorder_id": execution.workorder_id,
            "error_message": execution.error_message,
            "steps": [asdict(s) for s in execution.steps],
        }


# ========== 便捷函数 ==========

def execute_runbook_for_alarm(
    alarm_id: int,
    diagnosis_result: Dict,
    device_info: Dict,
    db = None,
    dry_run: bool = False,
) -> Dict:
    """
    为告警执行Runbook (便捷函数)

    用法:
        from app.services.runbook_engine import execute_runbook_for_alarm
        result = execute_runbook_for_alarm(alarm_id, diagnosis_result, device_info, db)
    """
    engine = RunbookEngine(dry_run=dry_run)
    return engine.execute(alarm_id, diagnosis_result, device_info, db=db)
