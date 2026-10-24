"""
预测性维护AI模型 - 基于LSTM的设备故障预测
Phase10 - 天链维护管理系统

核心功能:
1. 基于历史遥测数据的LSTM故障预测模型
2. 设备健康度趋势预测
3. 剩余使用寿命(RUL)估计
4. 异常检测与预警
5. 模型训练与推理服务
"""

import numpy as np
import json
import os
import logging
import zipfile
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

# ============ 数据结构 ============

@dataclass
class PredictionResult:
    """预测结果"""
    device_id: int
    device_name: str
    prediction_time: str
    failure_probability: float  # 故障概率 0-1
    health_trend: str  # improving/stable/degrading/critical
    rul_hours: Optional[float]  # 剩余使用寿命(小时)
    risk_level: str  # low/medium/high/critical
    anomaly_score: float  # 异常分数 0-1
    key_indicators: List[Dict]  # 关键指标
    recommended_actions: List[str]  # 建议措施
    confidence: float  # 预测置信度

@dataclass
class TrainingConfig:
    """训练配置"""
    sequence_length: int = 24  # 输入序列长度（小时）
    prediction_horizon: int = 6  # 预测未来多少小时
    lstm_units: int = 64
    lstm_layers: int = 2
    dropout_rate: float = 0.2
    learning_rate: float = 0.001
    batch_size: int = 32
    epochs: int = 50
    validation_split: float = 0.2
    feature_columns: List[str] = None
    
    def __post_init__(self):
        if self.feature_columns is None:
            self.feature_columns = [
                'battery_soc', 'battery_soh', 'battery_temperature',
                'battery_voltage', 'battery_current', 'battery_power',
                'grid_voltage_a', 'grid_current_a', 'grid_frequency',
                'inv_temperature', 'internal_temperature',
                'grid_power_total', 'charger_power',
                'bms_alarm_word', 'system_status'
            ]


# ============ 数据预处理 ============

class DataPreprocessor:
    """遥测数据预处理器"""
    
    def __init__(self, config: TrainingConfig):
        self.config = config
        self.feature_stats = {}  # 均值/标准差，用于归一化
    
    def fit(self, data: List[Dict]):
        """计算归一化参数"""
        import collections
        all_values = collections.defaultdict(list)
        for row in data:
            for col in self.config.feature_columns:
                val = row.get(col)
                if val is not None:
                    all_values[col].append(float(val))
        
        for col, values in all_values.items():
            if len(values) > 1:
                self.feature_stats[col] = {
                    'mean': float(np.mean(values)),
                    'std': float(np.std(values)) if np.std(values) > 0 else 1.0,
                    'min': float(np.min(values)),
                    'max': float(np.max(values))
                }
            else:
                self.feature_stats[col] = {'mean': 0, 'std': 1.0, 'min': 0, 'max': 1}
        
        logger.info("Preprocessor fitted with %d features", len(self.feature_stats))
    
    def transform(self, data: List[Dict]) -> np.ndarray:
        """归一化变换"""
        result = []
        for row in data:
            features = []
            for col in self.config.feature_columns:
                val = row.get(col)
                if val is None:
                    features.append(0.0)
                else:
                    stats = self.feature_stats.get(col, {'mean': 0, 'std': 1.0})
                    std = stats['std'] or 1.0
                    normalized = (float(val) - stats['mean']) / std
                    features.append(np.clip(normalized, -5, 5))
            result.append(features)
        return np.array(result, dtype=np.float32)
    
    def create_sequences(self, data: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """创建时序序列和标签"""
        X, y = [], []
        seq_len = self.config.sequence_length
        horizon = self.config.prediction_horizon
        
        for i in range(len(data) - seq_len - horizon):
            X.append(data[i:i+seq_len])
            # 标签：未来horizon步内是否出现异常（基于温度/SOC等异常判断）
            future_window = data[i+seq_len:i+seq_len+horizon]
            label = self._compute_fault_label(future_window)
            y.append(label)
        
        return np.array(X), np.array(y)
    
    def _compute_fault_label(self, future_window: np.ndarray) -> float:
        """基于未来窗口数据计算故障标签"""
        # 简化的故障判定逻辑
        # 基于电池温度异常、SOC骤降、电压异常等
        anomaly_signals = 0
        total_checks = 0
        
        for step in future_window:
            # 检查是否有明显的异常模式
            for val in step:
                if abs(val) > 3.0:  # 超过3个标准差
                    anomaly_signals += 1
                total_checks += 1
        
        if total_checks == 0:
            return 0.0
        return min(1.0, anomaly_signals / (total_checks * 0.1))
    
    def save_stats(self, path: str):
        """保存归一化参数。写入失败(只读目录/磁盘满/不可序列化)不抛, 记 warning。"""
        try:
            with open(path, 'w') as f:
                json.dump(self.feature_stats, f, indent=2)
        except (OSError, TypeError, ValueError) as e:
            logger.warning("Failed to save preprocessor stats to %s: %s", path, e)
    
    def load_stats(self, path: str):
        """加载归一化参数。文件缺失/损坏 → 不抛, 降级为空 stats(transform 用默认值)。"""
        try:
            with open(path, 'r') as f:
                self.feature_stats = json.load(f)
        except (OSError, ValueError) as e:
            logger.warning("Failed to load preprocessor stats from %s: %s", path, e)
            self.feature_stats = {}


# ============ LSTM模型 ============

class LSTMPredictor:
    """LSTM故障预测模型 - 支持PyTorch和轻量回退"""
    
    def __init__(self, config: TrainingConfig):
        self.config = config
        self.model = None
        self.preprocessor = DataPreprocessor(config)
        self.use_pytorch = False
        self._weights = None  # 轻量模式的权重
        self.trained = False
        self.training_history = []
    
    def _try_import_pytorch(self):
        """尝试导入PyTorch"""
        try:
            import torch
            import torch.nn as nn
            self.use_pytorch = True
            self.torch = torch
            self.nn = nn
            logger.info("PyTorch available, using GPU-accelerated LSTM")
            return True
        except ImportError:
            self.use_pytorch = False
            logger.info("PyTorch not available, using lightweight LSTM")
            return False
    
    def _build_pytorch_model(self, input_size: int):
        """构建PyTorch LSTM模型"""
        class FaultPredictorLSTM(self.nn.Module):
            def __init__(selfself, input_size, hidden_size, num_layers, dropout):
                super().__init__()
                selfself.lstm = self.nn.LSTM(
                    input_size=input_size,
                    hidden_size=hidden_size,
                    num_layers=num_layers,
                    batch_first=True,
                    dropout=dropout if num_layers > 1 else 0
                )
                selfself.attention = self.nn.Linear(hidden_size, 1)
                selfself.fc1 = self.nn.Linear(hidden_size, 32)
                selfself.relu = self.nn.ReLU()
                selfself.dropout = self.nn.Dropout(dropout)
                selfself.fc2 = self.nn.Linear(32, 1)
                selfself.sigmoid = self.nn.Sigmoid()
            
            def forward(selfself, x):
                lstm_out, (h_n, c_n) = selfself.lstm(x)
                # Attention mechanism
                attn_weights = self.nn.functional.softmax(
                    selfself.attention(lstm_out).squeeze(-1), dim=1
                )
                context = self.torch.bmm(
                    attn_weights.unsqueeze(1), lstm_out
                ).squeeze(1)
                out = selfself.fc1(context)
                out = selfself.relu(out)
                out = selfself.dropout(out)
                out = selfself.fc2(out)
                return selfself.sigmoid(out).squeeze(-1)
        
        model = FaultPredictorLSTM(
            input_size=input_size,
            hidden_size=self.config.lstm_units,
            num_layers=self.config.lstm_layers,
            dropout=self.config.dropout_rate
        )
        return model
    
    def _build_lightweight_model(self, input_size: int):
        """构建轻量级LSTM（numpy实现）"""
        # 使用简单的权重矩阵模拟LSTM前向传播
        # 对于生产环境，建议安装PyTorch
        hidden_size = self.config.lstm_units
        
        self._weights = {
            'Wi': np.random.randn(input_size, hidden_size).astype(np.float32) * 0.1,
            'Wf': np.random.randn(input_size, hidden_size).astype(np.float32) * 0.1,
            'Wo': np.random.randn(input_size, hidden_size).astype(np.float32) * 0.1,
            'Wc': np.random.randn(input_size, hidden_size).astype(np.float32) * 0.1,
            'Ui': np.random.randn(hidden_size, hidden_size).astype(np.float32) * 0.1,
            'Uf': np.random.randn(hidden_size, hidden_size).astype(np.float32) * 0.1,
            'Uo': np.random.randn(hidden_size, hidden_size).astype(np.float32) * 0.1,
            'Uc': np.random.randn(hidden_size, hidden_size).astype(np.float32) * 0.1,
            'bi': np.zeros(hidden_size, dtype=np.float32),
            'bf': np.ones(hidden_size, dtype=np.float32),  # forget gate bias=1
            'bo': np.zeros(hidden_size, dtype=np.float32),
            'bc': np.zeros(hidden_size, dtype=np.float32),
            'W_out': np.random.randn(hidden_size, 1).astype(np.float32) * 0.1,
            'b_out': np.zeros(1, dtype=np.float32),
        }
    
    def _sigmoid(self, x):
        return 1.0 / (1.0 + np.exp(-np.clip(x, -500, 500)))
    
    def _lstm_forward(self, X: np.ndarray) -> np.ndarray:
        """轻量LSTM前向传播"""
        batch_size, seq_len, input_size = X.shape
        h = np.zeros((batch_size, self.config.lstm_units), dtype=np.float32)
        c = np.zeros((batch_size, self.config.lstm_units), dtype=np.float32)
        w = self._weights
        
        for t in range(seq_len):
            x_t = X[:, t, :]
            i = self._sigmoid(x_t @ w['Wi'] + h @ w['Ui'] + w['bi'])
            f = self._sigmoid(x_t @ w['Wf'] + h @ w['Uf'] + w['bf'])
            o = self._sigmoid(x_t @ w['Wo'] + h @ w['Uo'] + w['bo'])
            c_tilde = np.tanh(x_t @ w['Wc'] + h @ w['Uc'] + w['bc'])
            c = f * c + i * c_tilde
            h = o * np.tanh(c)
        
        # 输出层
        out = self._sigmoid(h @ w['W_out'] + w['b_out'])
        return out.squeeze(-1)
    
    def train(self, raw_data: List[Dict], device_id: int = None) -> Dict:
        """训练模型"""
        logger.info("Starting training with %d records", len(raw_data))
        
        # 数据预处理
        self.preprocessor.fit(raw_data)
        normalized = self.preprocessor.transform(raw_data)
        X, y = self.preprocessor.create_sequences(normalized)
        
        if len(X) < 10:
            logger.warning("Not enough sequences (%d), generating synthetic data", len(X))
            X, y = self._generate_synthetic_data()
        
        logger.info("Training data: X=%s, y=%s, positive_rate=%.3f", X.shape, y.shape, y.mean())
        
        # 构建模型
        input_size = X.shape[2]
        
        if self._try_import_pytorch():
            return self._train_pytorch(X, y, input_size)
        else:
            return self._train_lightweight(X, y, input_size)
    
    def _train_pytorch(self, X: np.ndarray, y: np.ndarray, input_size: int) -> Dict:
        """PyTorch训练"""
        torch = self.torch
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        model = self._build_pytorch_model(input_size).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=self.config.learning_rate)
        criterion = self.nn.BCELoss()
        
        # 数据加载
        X_tensor = torch.FloatTensor(X).to(device)
        y_tensor = torch.FloatTensor(y).to(device)
        
        dataset = torch.utils.data.TensorDataset(X_tensor, y_tensor)
        loader = torch.utils.data.DataLoader(
            dataset, batch_size=self.config.batch_size, shuffle=True
        )
        
        # 训练循环
        self.training_history = []
        for epoch in range(self.config.epochs):
            model.train()
            total_loss = 0
            for batch_X, batch_y in loader:
                optimizer.zero_grad()
                pred = model(batch_X)
                loss = criterion(pred, batch_y)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()
            
            avg_loss = total_loss / len(loader) if len(loader) > 0 else 0.0
            self.training_history.append({'epoch': epoch + 1, 'loss': avg_loss})
            
            if (epoch + 1) % 10 == 0:
                logger.info("Epoch %d/%d, Loss: %.4f", epoch+1, self.config.epochs, avg_loss)
        
        self.model = model
        self.trained = True
        
        return {
            'status': 'success',
            'framework': 'pytorch',
            'epochs': self.config.epochs,
            'final_loss': self.training_history[-1]['loss'] if self.training_history else 0,
            'samples': len(X),
            'device': str(device)
        }
    
    def _train_lightweight(self, X: np.ndarray, y: np.ndarray, input_size: int) -> Dict:
        """轻量级训练（梯度近似）"""
        self._build_lightweight_model(input_size)
        
        lr = self.config.learning_rate
        best_loss = float('inf')
        self.training_history = []
        
        for epoch in range(self.config.epochs):
            # 前向传播
            pred = self._lstm_forward(X)
            
            # BCE Loss
            eps = 1e-7
            pred_clipped = np.clip(pred, eps, 1 - eps)
            loss = -np.mean(y * np.log(pred_clipped) + (1 - y) * np.log(1 - pred_clipped))
            
            # 简化梯度更新（数值扰动法）
            if loss < best_loss:
                best_loss = loss
                best_weights = {k: v.copy() for k, v in self._weights.items()}
            
            # 随机扰动优化
            if epoch % 5 == 0:
                for key in self._weights:
                    perturbation = np.random.randn(*self._weights[key].shape).astype(np.float32) * lr * 0.1
                    self._weights[key] += perturbation
            
            self.training_history.append({'epoch': epoch + 1, 'loss': float(loss)})
            
            if (epoch + 1) % 10 == 0:
                logger.info("Epoch %d/%d, Loss: %.4f", epoch+1, self.config.epochs, loss)
        
        # 恢复最佳权重
        if best_loss < self.training_history[-1]['loss']:
            self._weights = best_weights
        
        self.trained = True
        
        return {
            'status': 'success',
            'framework': 'lightweight_numpy',
            'epochs': self.config.epochs,
            'final_loss': best_loss,
            'samples': len(X),
            'note': 'For production use, install PyTorch for better accuracy'
        }
    
    def predict(self, recent_data: List[Dict], device_id: int, device_name: str = "") -> PredictionResult:
        """预测设备故障概率"""
        if not self.trained:
            raise RuntimeError("Model not trained. Call train() first.")
        
        # 预处理
        normalized = self.preprocessor.transform(recent_data)
        
        if len(normalized) < self.config.sequence_length:
            # 数据不足时用零填充
            pad = np.zeros((self.config.sequence_length - len(normalized), normalized.shape[1]), dtype=np.float32)
            normalized = np.concatenate([pad, normalized])
        
        # 取最近的sequence_length个数据点
        X = normalized[-self.config.sequence_length:].reshape(1, self.config.sequence_length, -1)
        
        # 推理
        if self.use_pytorch and self.model is not None:
            with self.torch.no_grad():
                X_tensor = self.torch.FloatTensor(X)
                if self.torch.cuda.is_available():
                    X_tensor = X_tensor.cuda()
                failure_prob = self.model(X_tensor).cpu().item()
        else:
            failure_prob = float(self._lstm_forward(X)[0])
        
        # 计算辅助指标
        anomaly_score = self._compute_anomaly_score(normalized[-self.config.sequence_length:])
        health_trend = self._compute_health_trend(normalized[-self.config.sequence_length:])
        risk_level = self._compute_risk_level(failure_prob, anomaly_score)
        rul_hours = self._estimate_rul(failure_prob, recent_data)
        key_indicators = self._extract_key_indicators(recent_data[-1] if recent_data else {})
        recommendations = self._generate_recommendations(risk_level, failure_prob, key_indicators)
        
        return PredictionResult(
            device_id=device_id,
            device_name=device_name,
            prediction_time=datetime.now(timezone.utc).isoformat(),
            failure_probability=round(failure_prob, 4),
            health_trend=health_trend,
            rul_hours=round(rul_hours, 1) if rul_hours else None,
            risk_level=risk_level,
            anomaly_score=round(anomaly_score, 4),
            key_indicators=key_indicators,
            recommended_actions=recommendations,
            confidence=round(min(0.95, 0.5 + abs(failure_prob - 0.5)), 3)
        )
    
    def _compute_anomaly_score(self, data: np.ndarray) -> float:
        """计算异常分数"""
        # 基于数据偏离统计特征的程度
        anomaly_count = 0
        total = 0
        for step in data:
            for val in step:
                if abs(val) > 2.5:
                    anomaly_count += 1
                total += 1
        return min(1.0, anomaly_count / max(total * 0.05, 1))
    
    def _compute_health_trend(self, data: np.ndarray) -> str:
        """计算健康趋势"""
        if len(data) < 4:
            return "stable"
        
        # 看后半段数据是否异常增多
        first_half = data[:len(data)//2]
        second_half = data[len(data)//2:]
        
        first_anomaly = np.mean(np.abs(first_half) > 2.0)
        second_anomaly = np.mean(np.abs(second_half) > 2.0)
        
        if second_anomaly > 0.3:
            return "critical"
        elif second_anomaly > first_anomaly * 1.5:
            return "degrading"
        elif first_anomaly > second_anomaly * 1.5:
            return "improving"
        else:
            return "stable"
    
    def _compute_risk_level(self, failure_prob: float, anomaly_score: float) -> str:
        """计算风险等级"""
        combined = failure_prob * 0.7 + anomaly_score * 0.3
        if combined > 0.8:
            return "critical"
        elif combined > 0.5:
            return "high"
        elif combined > 0.3:
            return "medium"
        else:
            return "low"
    
    def _estimate_rul(self, failure_prob: float, data: List[Dict]) -> Optional[float]:
        """估计剩余使用寿命"""
        if not data:
            return None
        
        latest = data[-1] if data else {}
        soh = latest.get('battery_soh', 90)
        
        # 基于SOH和故障概率的简化RUL估计
        if soh and soh < 20:
            return soh * 10  # 非常低SOH
        
        base_rul = (soh or 80) * 100  # 基准RUL
        adjusted = base_rul * (1 - failure_prob)
        return max(0, adjusted)
    
    def _extract_key_indicators(self, latest: Dict) -> List[Dict]:
        """提取关键指标"""
        indicators = []
        indicator_map = {
            'battery_soc': {'name': '电池SOC', 'unit': '%', 'thresholds': [20, 40, 60, 80]},
            'battery_soh': {'name': '电池SOH', 'unit': '%', 'thresholds': [50, 70, 85, 95]},
            'battery_temperature': {'name': '电池温度', 'unit': '℃', 'thresholds': [45, 40, 35, 30]},
            'internal_temperature': {'name': '机内温度', 'unit': '℃', 'thresholds': [60, 50, 40, 35]},
            'inv_temperature': {'name': '逆变温度', 'unit': '℃', 'thresholds': [65, 55, 45, 40]},
            'grid_frequency': {'name': '电网频率', 'unit': 'Hz', 'thresholds': [49.0, 49.5, 50.2, 50.5]},
            'battery_voltage': {'name': '电池电压', 'unit': 'V', 'thresholds': None},
            'grid_power_total': {'name': '总有功功率', 'unit': 'kW', 'thresholds': None},
        }
        
        for key, info in indicator_map.items():
            val = latest.get(key)
            if val is not None:
                status = "normal"
                if info['thresholds']:
                    thresholds = info['thresholds']
                    if thresholds[0] > thresholds[3]:
                        # 降序阈值（温度类）：thresholds=[最高, 次高, ...]，
                        # 仅高温判定异常，常温/低温属正常工作区间。
                        # 如 [45,40,35,30]：>45 critical，>40 warning，其余 normal。
                        if val > thresholds[0]:
                            status = "critical"
                        elif val > thresholds[1]:
                            status = "warning"
                    else:
                        # 升序阈值（SOC/SOH/电网频率）：双向区间判定，
                        # 偏离 [t0, t3] 外侧 critical、[t1, t2] 外侧 warning。
                        if val < thresholds[0] or val > thresholds[3]:
                            status = "critical"
                        elif val < thresholds[1] or val > thresholds[2]:
                            status = "warning"
                
                indicators.append({
                    'key': key,
                    'name': info['name'],
                    'value': round(float(val), 2),
                    'unit': info['unit'],
                    'status': status
                })
        
        return indicators[:8]  # 最多8个关键指标
    
    def _generate_recommendations(self, risk_level: str, failure_prob: float, 
                                   key_indicators: List[Dict]) -> List[str]:
        """生成维护建议"""
        recs = []
        
        if risk_level == "critical":
            recs.append("🚨 紧急：设备故障风险极高，建议立即停机检查")
            recs.append("联系运维团队进行现场排查")
        elif risk_level == "high":
            recs.append("⚠️ 设备故障风险较高，建议48小时内安排检修")
            recs.append("加强监控频率，每30分钟检查一次")
        elif risk_level == "medium":
            recs.append("📋 设备存在潜在风险，建议一周内安排维护")
            recs.append("关注关键指标变化趋势")
        else:
            recs.append("✅ 设备运行正常，按常规周期维护即可")
        
        # 基于具体指标的针对性建议
        for indicator in key_indicators:
            if indicator['status'] == 'critical':
                if '温度' in indicator['name']:
                    recs.append(f"🌡️ {indicator['name']}异常({indicator['value']}{indicator['unit']})，检查散热系统")
                elif 'SOC' in indicator['name']:
                    recs.append(f"🔋 {indicator['name']}过低({indicator['value']}{indicator['unit']})，检查充电系统")
                elif 'SOH' in indicator['name']:
                    recs.append(f"📊 {indicator['name']}严重衰减({indicator['value']}{indicator['unit']})，建议更换电池")
            elif indicator['status'] == 'warning':
                if '温度' in indicator['name']:
                    recs.append(f"🌡️ {indicator['name']}偏高({indicator['value']}{indicator['unit']})，注意通风")
        
        return recs[:6]  # 最多6条建议
    
    def _generate_synthetic_data(self) -> Tuple[np.ndarray, np.ndarray]:
        """生成合成训练数据"""
        n_samples = 500
        seq_len = self.config.sequence_length
        n_features = len(self.config.feature_columns)
        
        X = np.random.randn(n_samples, seq_len, n_features).astype(np.float32) * 0.5
        y = np.zeros(n_samples, dtype=np.float32)
        
        # 正常样本 (70%)
        for i in range(int(n_samples * 0.7)):
            X[i] = np.random.randn(seq_len, n_features).astype(np.float32) * 0.3
            y[i] = 0.0
        
        # 异常样本 (30%)
        for i in range(int(n_samples * 0.7), n_samples):
            anomaly_step = np.random.randint(seq_len // 2, seq_len)
            X[i, anomaly_step:] += np.random.randn(seq_len - anomaly_step, n_features).astype(np.float32) * 2.0
            y[i] = 1.0
        
        return X, y
    
    def save(self, path: str):
        """保存模型。任意写入失败(只读目录/磁盘满)不炸调用方, best-effort 持久化。"""
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            logger.warning("Failed to create model dir %s: %s", path, e)
            return
        
        # 保存预处理参数
        self.preprocessor.save_stats(os.path.join(path, 'preprocessor_stats.json'))
        
        # 保存配置
        try:
            with open(os.path.join(path, 'config.json'), 'w') as f:
                json.dump(asdict(self.config), f, indent=2)
        except (OSError, TypeError, ValueError) as e:
            logger.warning("Failed to save config to %s: %s", path, e)
        
        if self.use_pytorch and self.model is not None:
            try:
                self.torch.save(self.model.state_dict(), os.path.join(path, 'model.pt'))
            except (OSError, RuntimeError) as e:
                logger.warning("Failed to save pytorch model to %s: %s", path, e)
        elif self._weights is not None:
            try:
                np.savez(os.path.join(path, 'weights.npz'), **self._weights)
            except (OSError, ValueError) as e:
                logger.warning("Failed to save numpy weights to %s: %s", path, e)
        
        # 保存元数据
        meta = {
            'trained': self.trained,
            'use_pytorch': self.use_pytorch,
            'training_history': self.training_history[-10:] if self.training_history else [],
            'saved_at': datetime.now(timezone.utc).isoformat()
        }
        try:
            with open(os.path.join(path, 'meta.json'), 'w') as f:
                json.dump(meta, f, indent=2)
        except (OSError, TypeError, ValueError) as e:
            logger.warning("Failed to save meta to %s: %s", path, e)
        
        logger.info("Model saved to %s", path)
    
    def load(self, path: str):
        """加载模型"""
        # 加载配置: 失败则无法继续, 保持默认 config + 未训练, 直接返回
        try:
            with open(os.path.join(path, 'config.json'), 'r') as f:
                config_dict = json.load(f)
                self.config = TrainingConfig(**config_dict)
        except (OSError, ValueError, TypeError) as e:
            logger.warning("Failed to load model config from %s, keeping default: %s", path, e)
            self.trained = False
            return
        
        # 加载预处理参数
        self.preprocessor = DataPreprocessor(self.config)
        self.preprocessor.load_stats(os.path.join(path, 'preprocessor_stats.json'))
        
        # 加载权重: 失败则 _weights/model=None + weights_loaded=False, 防 predict 撞 None
        weights_loaded = False
        if os.path.exists(os.path.join(path, 'model.pt')):
            if self._try_import_pytorch():
                try:
                    input_size = len(self.config.feature_columns)
                    self.model = self._build_pytorch_model(input_size)
                    self.model.load_state_dict(self.torch.load(os.path.join(path, 'model.pt'), map_location='cpu'))
                    self.model.eval()
                    self.use_pytorch = True
                    weights_loaded = True
                except (OSError, ValueError, RuntimeError, EOFError) as e:
                    logger.warning("Failed to load pytorch weights from %s: %s", path, e)
                    self.model = None
                    self.use_pytorch = False
        elif os.path.exists(os.path.join(path, 'weights.npz')):
            try:
                data = np.load(os.path.join(path, 'weights.npz'))
                self._weights = {k: data[k] for k in data.files}
                self.use_pytorch = False
                weights_loaded = True
            except (OSError, ValueError, zipfile.BadZipFile) as e:
                # 损坏/截断 npz: 垃圾字节→ValueError, 截断→BadZipFile
                logger.warning("Failed to load numpy weights from %s: %s", path, e)
                self._weights = None
        
        # 加载元数据: trained 必须 AND weights_loaded, 防 meta 撒谎导致 predict 撞 _weights=None → TypeError
        try:
            with open(os.path.join(path, 'meta.json'), 'r') as f:
                meta = json.load(f)
                self.trained = meta.get('trained', False) and weights_loaded
        except (OSError, ValueError) as e:
            logger.warning("Failed to load model meta from %s: %s", path, e)
            self.trained = False
        
        logger.info("Model loaded from %s, pytorch=%s, trained=%s", path, self.use_pytorch, self.trained)


# ============ 预测服务 ============

class PredictiveMaintenanceService:
    """预测性维护服务 - 管理模型生命周期"""
    
    def __init__(self, model_dir: str = "/opt/tianlian-v3/backend/app/data/predictive_models"):
        self.model_dir = model_dir
        self.models: Dict[int, LSTMPredictor] = {}  # device_id -> predictor
        self.default_config = TrainingConfig()
        self._ensure_dirs()
    
    def _ensure_dirs(self):
        os.makedirs(self.model_dir, exist_ok=True)
    
    def get_or_create_predictor(self, device_id: int) -> LSTMPredictor:
        """获取或创建设备的预测器"""
        if device_id not in self.models:
            predictor = LSTMPredictor(self.default_config)
            model_path = os.path.join(self.model_dir, str(device_id))
            if os.path.exists(model_path):
                predictor.load(model_path)
            self.models[device_id] = predictor
        return self.models[device_id]
    
    async def train_device_model(self, device_id: int, data: List[Dict]) -> Dict:
        """训练设备模型"""
        predictor = self.get_or_create_predictor(device_id)
        result = predictor.train(data, device_id)
        
        # 保存模型
        model_path = os.path.join(self.model_dir, str(device_id))
        predictor.save(model_path)
        
        return result
    
    async def predict_failure(self, device_id: int, recent_data: List[Dict], 
                               device_name: str = "") -> PredictionResult:
        """预测设备故障"""
        predictor = self.get_or_create_predictor(device_id)
        
        if not predictor.trained:
            # 如果模型未训练，先训练
            logger.info("Model for device %s not trained, training with provided data...", device_id)
            await self.train_device_model(device_id, recent_data)
        
        return predictor.predict(recent_data, device_id, device_name)
    
    async def batch_predict(self, predictions_request: List[Dict]) -> List[PredictionResult]:
        """批量预测"""
        results = []
        for req in predictions_request:
            device_id = req['device_id']
            recent_data = req.get('recent_data', [])
            device_name = req.get('device_name', '')
            try:
                result = await self.predict_failure(device_id, recent_data, device_name)
                results.append(result)
            except Exception as e:
                logger.error("Prediction failed for device %s: %s", device_id, e)
        return results
    
    def get_model_status(self) -> Dict:
        """获取所有模型状态"""
        status = {}
        for device_id, predictor in self.models.items():
            status[str(device_id)] = {
                'trained': predictor.trained,
                'framework': 'pytorch' if predictor.use_pytorch else 'numpy',
                'features': len(predictor.config.feature_columns),
                'sequence_length': predictor.config.sequence_length,
            }
        
        # 扫描磁盘上的模型
        if os.path.exists(self.model_dir):
            for d in os.listdir(self.model_dir):
                if d.isdigit() and int(d) not in self.models:
                    meta_path = os.path.join(self.model_dir, d, 'meta.json')
                    if os.path.exists(meta_path):
                        try:
                            with open(meta_path) as f:
                                meta = json.load(f)
                        except (OSError, ValueError) as e:
                            # 损坏的 meta.json 跳过该设备, 不上报脏数据误导运维
                            logger.warning("Failed to read model meta %s: %s", meta_path, e)
                            continue
                        status[d] = {
                            'trained': meta.get('trained', False),
                            'framework': 'pytorch' if meta.get('use_pytorch') else 'numpy',
                            'on_disk': True
                        }
        
        return status


# ============ 工具函数 ============

def format_prediction_for_display(result: PredictionResult) -> Dict:
    """格式化预测结果用于API返回"""
    risk_emoji = {
        'low': '🟢',
        'medium': '🟡',
        'high': '🟠',
        'critical': '🔴'
    }
    
    trend_emoji = {
        'improving': '📈',
        'stable': '➡️',
        'degrading': '📉',
        'critical': '⬇️'
    }
    
    return {
        'device_id': result.device_id,
        'device_name': result.device_name,
        'prediction_time': result.prediction_time,
        'failure_probability': result.failure_probability,
        'failure_probability_display': f"{result.failure_probability * 100:.1f}%",
        'risk_level': result.risk_level,
        'risk_emoji': risk_emoji.get(result.risk_level, '⚪'),
        'health_trend': result.health_trend,
        'trend_emoji': trend_emoji.get(result.health_trend, '➡️'),
        'rul_hours': result.rul_hours,
        'rul_display': f"{result.rul_hours:.0f}h" if result.rul_hours else "N/A",
        'anomaly_score': result.anomaly_score,
        'key_indicators': result.key_indicators,
        'recommended_actions': result.recommended_actions,
        'confidence': result.confidence
    }
