"""
预测性维护 AI 服务 - 基于 LSTM 的设备故障预测
Phase10 #56

功能:
- LSTM 时序模型：基于遥测数据预测设备故障
- 健康度评分：实时计算设备 RUL (Remaining Useful Life)
- 异常检测：基于统计阈值的早期预警
- 模型训练/推理 API：支持在线训练和批量预测
"""
import os
import threading

from app.services.predictive_maintenance.lstm_predictor import PredictiveMaintenanceService

_service_instance = None
_lock = threading.Lock()


def get_service() -> PredictiveMaintenanceService:
    """获取预测性维护服务单例"""
    global _service_instance
    if _service_instance is None:
        with _lock:
            if _service_instance is None:
                model_dir = os.path.join(os.path.dirname(__file__), "..", "..", "data", "predictive_models")
                model_dir = os.path.abspath(model_dir)
                os.makedirs(model_dir, exist_ok=True)
                _service_instance = PredictiveMaintenanceService(model_dir)
    return _service_instance
