"""
机器学习模型服务 - 设备故障预测和健康度评分模型

功能:
1. 时序预测模型 (LSTM/GRU) - 预测设备故障
2. 分类模型 (XGBoost/RandomForest) - 故障分类
3. 异常检测模型 (Isolation Forest/AutoEncoder)
4. 回归模型 - 健康度评分预测
5. 模型训练/推理/评估/部署
"""
import os
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from typing import Dict, List, Any
import joblib
from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
import logging


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MLModelService:
    """机器学习模型服务"""
    
    def __init__(self, model_dir: str = None):
        self.model_dir = model_dir or os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "ml_models"
        )
        os.makedirs(self.model_dir, exist_ok=True)
        
        self.models = {}  # 内存中加载的模型
        self.scalers = {}  # 特征缩放器
        
    def _get_model_path(self, model_type: str, device_id: int = None, model_name: str = None) -> str:
        """获取模型文件路径"""
        if model_name:
            filename = f"{model_name}.joblib"
        elif device_id:
            filename = f"{model_type}_device_{device_id}.joblib"
        else:
            filename = f"{model_type}_global.joblib"
        
        return os.path.join(self.model_dir, filename)
    
    def _get_scaler_path(self, model_type: str, device_id: int = None) -> str:
        """获取缩放器文件路径"""
        if device_id:
            filename = f"scaler_{model_type}_device_{device_id}.joblib"
        else:
            filename = f"scaler_{model_type}_global.joblib"
        
        return os.path.join(self.model_dir, filename)
    
    def load_model(self, model_type: str, device_id: int = None, model_name: str = None):
        """加载模型"""
        model_key = f"{model_type}_{device_id if device_id else 'global'}_{model_name if model_name else 'default'}"
        
        if model_key in self.models:
            return self.models[model_key]
        
        model_path = self._get_model_path(model_type, device_id, model_name)
        if os.path.exists(model_path):
            try:
                model = joblib.load(model_path)
                self.models[model_key] = model
                logger.info("加载模型: %s", model_key)
                return model
            except Exception as e:
                logger.error("加载模型失败 %s: %s", model_path, e)
        
        return None
    
    def load_scaler(self, model_type: str, device_id: int = None):
        """加载特征缩放器"""
        scaler_key = f"{model_type}_{device_id if device_id else 'global'}"
        
        if scaler_key in self.scalers:
            return self.scalers[scaler_key]
        
        scaler_path = self._get_scaler_path(model_type, device_id)
        if os.path.exists(scaler_path):
            try:
                scaler = joblib.load(scaler_path)
                self.scalers[scaler_key] = scaler
                logger.info("加载缩放器: %s", scaler_key)
                return scaler
            except Exception as e:
                logger.error("加载缩放器失败 %s: %s", scaler_path, e)
        
        return None
    
    def save_model(self, model, model_type: str, device_id: int = None, model_name: str = None):
        """保存模型"""
        model_path = self._get_model_path(model_type, device_id, model_name)
        joblib.dump(model, model_path)
        
        model_key = f"{model_type}_{device_id if device_id else 'global'}_{model_name if model_name else 'default'}"
        self.models[model_key] = model
        logger.info("保存模型: %s", model_key)
        
        return model_path
    
    def save_scaler(self, scaler, model_type: str, device_id: int = None):
        """保存特征缩放器"""
        scaler_path = self._get_scaler_path(model_type, device_id)
        joblib.dump(scaler, scaler_path)
        
        scaler_key = f"{model_type}_{device_id if device_id else 'global'}"
        self.scalers[scaler_key] = scaler
        logger.info("保存缩放器: %s", scaler_key)
        
        return scaler_path
    
    # ============ 特征工程 ============

    @staticmethod
    def _sanitize_matrix(X: np.ndarray) -> np.ndarray:
        """清洗特征矩阵中的 NaN/Inf -> 0.0。

        真实遥测脏数据可能混入非有限值 (pandas dropna 不剔除 inf -> mean=inf/std=nan),
        直接喂给 sklearn (StandardScaler.fit_transform / IsolationForest.fit) 会抛
        ValueError: "Input X contains infinity or a value too large for dtype('float64')"。
        训练前统一清洗为 0.0 (中性值), 保证 fit 不因脏值崩溃。
        """
        return np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    def extract_features(self, telemetry_data: List[Dict]) -> pd.DataFrame:
        """从遥测数据提取特征 (异常守卫: 脏数据导致提取失败均降级为空 DataFrame,
        调用方据此跳过该样本, 不向 API 层抛 500)。"""
        if not telemetry_data:
            return pd.DataFrame()
        try:
            return self._extract_features_impl(telemetry_data)
        except Exception:
            logger.warning("特征提取失败, 返回空 DataFrame", exc_info=True)
            return pd.DataFrame()

    def _extract_features_impl(self, telemetry_data: List[Dict]) -> pd.DataFrame:
        """特征提取实现内核 (由 extract_features 异常守卫调用)。"""
        df = pd.DataFrame(telemetry_data)
        
        # 基础特征
        features = {}
        
        # 数值特征
        numeric_cols = [
            'battery_soc', 'battery_soh', 'battery_temperature',
            'battery_voltage', 'battery_current', 'battery_power',
            'grid_voltage_a', 'grid_voltage_b', 'grid_voltage_c',
            'grid_current_a', 'grid_current_b', 'grid_current_c',
            'grid_power_total', 'grid_power_factor',
            'inv_temperature', 'internal_temperature', 'pv_temperature',
            'charger_power', 'charger_voltage', 'charger_current',
            'gun_temperature'
        ]
        
        for col in numeric_cols:
            if col in df.columns:
                # 基础统计
                col_data = df[col].dropna()
                if len(col_data) > 0:
                    features[f'{col}_mean'] = col_data.mean()
                    features[f'{col}_std'] = col_data.std()
                    features[f'{col}_min'] = col_data.min()
                    features[f'{col}_max'] = col_data.max()
                    features[f'{col}_range'] = col_data.max() - col_data.min()
        
        # 时间序列特征
        if 'timestamp' in df.columns and len(df) > 1:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp')
            
            # 时间间隔统计
            time_diffs = df['timestamp'].diff().dt.total_seconds()
            if len(time_diffs.dropna()) > 0:
                features['time_interval_mean'] = time_diffs.mean()
                features['time_interval_std'] = time_diffs.std()
                features['time_interval_cv'] = time_diffs.std() / max(time_diffs.mean(), 0.001)
        
        # 复合特征
        if 'battery_voltage' in df.columns and 'battery_current' in df.columns:
            voltage = df['battery_voltage'].dropna()
            current = df['battery_current'].dropna()
            if len(voltage) > 0 and len(current) > 0:
                features['battery_resistance_est'] = voltage.mean() / max(current.mean(), 0.001)
        
        if 'grid_voltage_a' in df.columns and 'grid_current_a' in df.columns:
            va = df['grid_voltage_a'].dropna()
            ia = df['grid_current_a'].dropna()
            if len(va) > 0 and len(ia) > 0:
                features['grid_impedance_a'] = va.mean() / max(ia.mean(), 0.001)
        
        # 温度相关特征
        temp_cols = [col for col in df.columns if 'temperature' in col]
        if temp_cols:
            all_temps = []
            for col in temp_cols:
                temps = df[col].dropna()
                if len(temps) > 0:
                    all_temps.extend(temps.tolist())
            
            if all_temps:
                all_temps = np.array(all_temps)
                features['temperature_mean'] = all_temps.mean()
                # 温度点数 >= 2 才能做一次多项式拟合; 单点时降级为 0.0 (常量, 无梯度),
                # 避免 numpy polyfit(deg=1) 抛 LinAlgError (SVD 不收敛)。
                if len(all_temps) >= 2:
                    features['temperature_gradient'] = np.polyfit(range(len(all_temps)), all_temps, 1)[0]
                else:
                    features['temperature_gradient'] = 0.0
        
        # 告警相关特征
        if 'bms_alarm_word' in df.columns:
            alarm_data = df['bms_alarm_word'].dropna()
            if len(alarm_data) > 0:
                alarm_counts = (alarm_data != 0).sum()
                features['alarm_frequency'] = alarm_counts / len(alarm_data)
                features['has_alarms'] = 1 if alarm_counts > 0 else 0
        
        return pd.DataFrame([features])
    
    # ============ 故障分类模型 ============
    
    def train_fault_classifier(self, device_id: int, telemetry_data: List[Dict], 
                               alarm_labels: List[int]) -> Dict[str, Any]:
        """
        训练故障分类模型
        
        Args:
            device_id: 设备ID
            telemetry_data: 遥测数据列表
            alarm_labels: 对应的告警标签 (0=正常, 1=故障)
        
        Returns:
            训练结果字典
        """
        logger.info("训练故障分类模型, 设备: %s, 样本数: %d", device_id, len(telemetry_data))
        
        if len(telemetry_data) < 50:
            return {
                'status': 'error',
                'error': '训练数据不足，至少需要50个样本',
                'samples': len(telemetry_data)
            }
        
        # 提取特征
        X_list = []
        for data in telemetry_data:
            features_df = self.extract_features([data])
            if not features_df.empty:
                X_list.append(features_df.iloc[0].tolist())
        
        X = np.array(X_list)
        y = np.array(alarm_labels[:len(X)])  # 对齐长度
        
        if len(X) < 10:
            return {
                'status': 'error',
                'error': '有效特征太少，无法训练',
                'samples': len(X)
            }
        
        # fit 前校验: 标签对齐 + 单类检测 (基于 y, 在清洗 X 之前判定)
        if len(y) != len(X):
            return {
                'status': 'error',
                'error': '训练标签数量与样本数不匹配',
                'samples': len(X)
            }
        if len(np.unique(y)) < 2:
            return {
                'status': 'error',
                'error': '训练标签仅含单一类别，无法训练有效分类模型',
                'samples': len(X)
            }

        try:
            # NaN/Inf 清洗 + 特征缩放
            X = self._sanitize_matrix(X)
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            # 划分训练测试集
            X_train, X_test, y_train, y_test = train_test_split(
                X_scaled, y, test_size=0.2, random_state=42
            )

            # 训练模型
            model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                n_jobs=-1
            )

            model.fit(X_train, y_train)

            # 评估
            y_pred = model.predict(X_test)
            accuracy = accuracy_score(y_test, y_pred)
            precision = precision_score(y_test, y_pred, zero_division=0)
            recall = recall_score(y_test, y_pred, zero_division=0)
            f1 = f1_score(y_test, y_pred, zero_division=0)

            # 特征重要性
            feature_importance = model.feature_importances_.tolist()

            # 保存模型和缩放器
            model_path = self.save_model(model, 'fault_classifier', device_id)
            scaler_path = self.save_scaler(scaler, 'fault_classifier', device_id)
        except Exception:
            logger.exception("故障分类模型训练失败, device_id=%s", device_id)
            return {
                'status': 'error',
                'error': '模型训练失败，请检查数据质量',
                'samples': len(X)
            }

        return {
            'status': 'success',
            'device_id': device_id,
            'model_type': 'RandomForestClassifier',
            'accuracy': round(accuracy, 4),
            'precision': round(precision, 4),
            'recall': round(recall, 4),
            'f1_score': round(f1, 4),
            'training_samples': len(X_train),
            'test_samples': len(X_test),
            'feature_count': X.shape[1],
            'feature_importance': feature_importance,
            'model_path': model_path,
            'scaler_path': scaler_path,
            'trained_at': datetime.now(timezone.utc).isoformat()
        }
    
    def predict_fault(self, device_id: int, telemetry_data: List[Dict]) -> Dict[str, Any]:
        """
        预测设备故障
        
        Args:
            device_id: 设备ID
            telemetry_data: 遥测数据列表
        
        Returns:
            预测结果字典
        """
        # 加载模型
        model = self.load_model('fault_classifier', device_id)
        if model is None:
            return {
                'device_id': device_id,
                'prediction': 'unknown',
                'confidence': 0.0,
                'error': '模型未训练'
            }
        
        # 加载缩放器
        scaler = self.load_scaler('fault_classifier', device_id)
        if scaler is None:
            return {
                'device_id': device_id,
                'prediction': 'unknown',
                'confidence': 0.0,
                'error': '特征缩放器未找到'
            }
        
        # 提取特征
        X_list = []
        for data in telemetry_data[-10:]:  # 使用最近10个点
            features_df = self.extract_features([data])
            if not features_df.empty:
                X_list.append(features_df.iloc[0].tolist())
        
        if not X_list:
            return {
                'device_id': device_id,
                'prediction': 'unknown',
                'confidence': 0.0,
                'error': '无法提取特征'
            }
        
        try:
            X = np.array(X_list)
            X_scaled = scaler.transform(X)

            # 预测
            predictions = model.predict(X_scaled)
            probabilities = model.predict_proba(X_scaled)
        except Exception:
            logger.exception("故障预测失败, device_id=%s", device_id)
            return {
                'device_id': device_id,
                'prediction': 'unknown',
                'confidence': 0.0,
                'error': '故障预测失败'
            }

        # 综合结果
        fault_count = np.sum(predictions == 1)
        fault_prob_mean = np.mean(probabilities[:, 1]) if len(probabilities.shape) > 1 else 0.0
        
        is_fault = fault_count > len(predictions) / 2  # 多数投票
        confidence = fault_prob_mean if is_fault else 1 - fault_prob_mean
        
        return {
            'device_id': device_id,
            'prediction': 'fault' if is_fault else 'normal',
            'confidence': float(confidence),
            'fault_probability': float(fault_prob_mean),
            'fault_samples': int(fault_count),
            'total_samples': len(predictions),
            'probabilities': probabilities.tolist() if len(probabilities.shape) > 1 else [],
            'predictions': predictions.tolist()
        }
    
    # ============ 异常检测模型 ============
    
    def train_anomaly_detector(self, device_id: int, telemetry_data: List[Dict]) -> Dict[str, Any]:
        """
        训练异常检测模型
        
        Args:
            device_id: 设备ID
            telemetry_data: 遥测数据列表
        
        Returns:
            训练结果字典
        """
        logger.info("训练异常检测模型, 设备: %s, 样本数: %d", device_id, len(telemetry_data))
        
        if len(telemetry_data) < 100:
            return {
                'status': 'error',
                'error': '训练数据不足，至少需要100个样本',
                'samples': len(telemetry_data)
            }
        
        # 提取特征
        X_list = []
        for data in telemetry_data:
            features_df = self.extract_features([data])
            if not features_df.empty:
                X_list.append(features_df.iloc[0].tolist())
        
        X = np.array(X_list)
        
        if len(X) < 20:
            return {
                'status': 'error',
                'error': '有效特征太少，无法训练',
                'samples': len(X)
            }
        
        try:
            # NaN/Inf 清洗 + 特征缩放
            X = self._sanitize_matrix(X)
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            # 训练Isolation Forest模型
            model = IsolationForest(
                contamination=0.1,  # 假设10%的异常率
                random_state=42,
                n_jobs=-1
            )

            model.fit(X_scaled)

            # 在训练集上评估
            train_pred = model.predict(X_scaled)
            anomaly_count = np.sum(train_pred == -1)
            anomaly_rate = anomaly_count / len(train_pred)

            # 保存模型和缩放器
            model_path = self.save_model(model, 'anomaly_detector', device_id)
            scaler_path = self.save_scaler(scaler, 'anomaly_detector', device_id)
        except Exception:
            logger.exception("异常检测模型训练失败, device_id=%s", device_id)
            return {
                'status': 'error',
                'error': '模型训练失败，请检查数据质量',
                'samples': len(X)
            }

        return {
            'status': 'success',
            'device_id': device_id,
            'model_type': 'IsolationForest',
            'training_samples': len(X),
            'anomaly_count': int(anomaly_count),
            'anomaly_rate': round(anomaly_rate, 4),
            'feature_count': X.shape[1],
            'model_path': model_path,
            'scaler_path': scaler_path,
            'trained_at': datetime.now(timezone.utc).isoformat()
        }
    
    def detect_anomalies(self, device_id: int, telemetry_data: List[Dict]) -> Dict[str, Any]:
        """
        检测异常
        
        Args:
            device_id: 设备ID
            telemetry_data: 遥测数据列表
        
        Returns:
            检测结果字典
        """
        # 加载模型
        model = self.load_model('anomaly_detector', device_id)
        if model is None:
            return {
                'device_id': device_id,
                'anomalies': [],
                'anomaly_score': 0.0,
                'error': '模型未训练'
            }
        
        # 加载缩放器
        scaler = self.load_scaler('anomaly_detector', device_id)
        if scaler is None:
            return {
                'device_id': device_id,
                'anomalies': [],
                'anomaly_score': 0.0,
                'error': '特征缩放器未找到'
            }
        
        # 提取特征
        X_list = []
        timestamps = []
        for data in telemetry_data:
            features_df = self.extract_features([data])
            if not features_df.empty:
                X_list.append(features_df.iloc[0].tolist())
                timestamps.append(data.get('timestamp', ''))
        
        if not X_list:
            return {
                'device_id': device_id,
                'anomalies': [],
                'anomaly_score': 0.0,
                'error': '无法提取特征'
            }
        
        try:
            X = np.array(X_list)
            X_scaled = scaler.transform(X)

            # 检测异常
            predictions = model.predict(X_scaled)
            anomaly_scores = model.decision_function(X_scaled)
        except Exception:
            logger.exception("异常检测失败, device_id=%s", device_id)
            return {
                'device_id': device_id,
                'anomalies': [],
                'anomaly_score': 0.0,
                'error': '异常检测失败'
            }

        # 分析结果
        anomalies = []
        for i, (pred, score, ts) in enumerate(zip(predictions, anomaly_scores, timestamps)):
            if pred == -1:  # 异常
                anomalies.append({
                    'index': i,
                    'timestamp': ts,
                    'anomaly_score': float(score),
                    'severity': 'high' if score < -0.5 else 'medium' if score < 0 else 'low'
                })
        
        # 计算总体异常分数 (越低表示异常程度越高)
        overall_score = np.mean(anomaly_scores) if len(anomaly_scores) > 0 else 0.0
        
        return {
            'device_id': device_id,
            'anomalies': anomalies,
            'total_samples': len(predictions),
            'anomaly_count': len(anomalies),
            'anomaly_rate': len(anomalies) / len(predictions) if len(predictions) > 0 else 0.0,
            'anomaly_score': float(overall_score),
            'predictions': predictions.tolist(),
            'anomaly_scores': anomaly_scores.tolist()
        }
    
    # ============ 健康度评分模型 ============
    
    def train_health_scorer(self, device_id: int, telemetry_data: List[Dict], 
                            health_scores: List[float]) -> Dict[str, Any]:
        """
        训练健康度评分模型
        
        Args:
            device_id: 设备ID
            telemetry_data: 遥测数据列表
            health_scores: 对应的健康度评分 (0-100)
        
        Returns:
            训练结果字典
        """
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.metrics import mean_absolute_error, r2_score
        
        logger.info("训练健康度评分模型, 设备: %s, 样本数: %d", device_id, len(telemetry_data))
        
        if len(telemetry_data) < 50:
            return {
                'status': 'error',
                'error': '训练数据不足，至少需要50个样本',
                'samples': len(telemetry_data)
            }
        
        # 提取特征
        X_list = []
        for data in telemetry_data:
            features_df = self.extract_features([data])
            if not features_df.empty:
                X_list.append(features_df.iloc[0].tolist())
        
        X = np.array(X_list)
        y = np.array(health_scores[:len(X)])  # 对齐长度
        
        if len(X) < 10:
            return {
                'status': 'error',
                'error': '有效特征太少，无法训练',
                'samples': len(X)
            }

        # fit 前校验: 评分数量须与样本数一致, 否则 train_test_split 抛 ValueError
        if len(y) != len(X):
            return {
                'status': 'error',
                'error': '健康度评分数量与样本数不匹配',
                'samples': len(X)
            }

        try:
            # NaN/Inf 清洗 + 特征缩放
            X = self._sanitize_matrix(X)
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            # 划分训练测试集
            X_train, X_test, y_train, y_test = train_test_split(
                X_scaled, y, test_size=0.2, random_state=42
            )

            # 训练回归模型
            model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                random_state=42,
                n_jobs=-1
            )

            model.fit(X_train, y_train)

            # 评估
            y_pred = model.predict(X_test)
            mae = mean_absolute_error(y_test, y_pred)
            r2 = r2_score(y_test, y_pred)

            # 特征重要性
            feature_importance = model.feature_importances_.tolist()

            # 保存模型和缩放器
            model_path = self.save_model(model, 'health_scorer', device_id)
            scaler_path = self.save_scaler(scaler, 'health_scorer', device_id)
        except Exception:
            logger.exception("健康度评分模型训练失败, device_id=%s", device_id)
            return {
                'status': 'error',
                'error': '模型训练失败，请检查数据质量',
                'samples': len(X)
            }

        return {
            'status': 'success',
            'device_id': device_id,
            'model_type': 'RandomForestRegressor',
            'mae': round(mae, 4),
            'r2_score': round(r2, 4),
            'training_samples': len(X_train),
            'test_samples': len(X_test),
            'feature_count': X.shape[1],
            'feature_importance': feature_importance,
            'model_path': model_path,
            'scaler_path': scaler_path,
            'trained_at': datetime.now(timezone.utc).isoformat()
        }
    
    def predict_health_score(self, device_id: int, telemetry_data: List[Dict]) -> Dict[str, Any]:
        """
        预测健康度评分
        
        Args:
            device_id: 设备ID
            telemetry_data: 遥测数据列表
        
        Returns:
            预测结果字典
        """
        # 加载模型
        model = self.load_model('health_scorer', device_id)
        if model is None:
            return {
                'device_id': device_id,
                'health_score': 70.0,  # 默认值
                'confidence': 0.0,
                'error': '模型未训练，使用默认值'
            }
        
        # 加载缩放器
        scaler = self.load_scaler('health_scorer', device_id)
        if scaler is None:
            return {
                'device_id': device_id,
                'health_score': 70.0,
                'confidence': 0.0,
                'error': '特征缩放器未找到，使用默认值'
            }
        
        # 提取特征
        X_list = []
        for data in telemetry_data[-5:]:  # 使用最近5个点
            features_df = self.extract_features([data])
            if not features_df.empty:
                X_list.append(features_df.iloc[0].tolist())
        
        if not X_list:
            return {
                'device_id': device_id,
                'health_score': 70.0,
                'confidence': 0.0,
                'error': '无法提取特征，使用默认值'
            }
        
        try:
            X = np.array(X_list)
            X_scaled = scaler.transform(X)

            # 预测
            predictions = model.predict(X_scaled)
        except Exception:
            logger.exception("健康度评分预测失败, device_id=%s", device_id)
            return {
                'device_id': device_id,
                'health_score': 70.0,
                'confidence': 0.0,
                'error': '健康度评分预测失败，使用默认值'
            }

        health_score = np.mean(predictions)
        confidence = 1.0 - (np.std(predictions) / 100)  # 预测一致性作为置信度
        
        # 确保分数在0-100范围内
        health_score = max(0, min(100, health_score))
        
        return {
            'device_id': device_id,
            'health_score': float(health_score),
            'confidence': float(confidence),
            'prediction_samples': len(predictions),
            'score_std': float(np.std(predictions)),
            'predictions': predictions.tolist()
        }
    
    # ============ 模型管理 ============
    
    def get_model_status(self, device_id: int = None) -> Dict[str, Any]:
        """获取模型状态"""
        models = {}
        
        if device_id:
            # 检查特定设备的模型
            model_types = ['fault_classifier', 'anomaly_detector', 'health_scorer']
            for model_type in model_types:
                model_path = self._get_model_path(model_type, device_id)
                scaler_path = self._get_scaler_path(model_type, device_id)
                
                models[model_type] = {
                    'has_model': os.path.exists(model_path),
                    'has_scaler': os.path.exists(scaler_path),
                    'model_path': model_path,
                    'scaler_path': scaler_path
                }
        else:
            # 检查全局模型状态
            model_files = [f for f in os.listdir(self.model_dir) if f.endswith('.joblib')]
            
            device_models = {}
            for filename in model_files:
                parts = filename.replace('.joblib', '').split('_')
                if len(parts) >= 3 and parts[0] in ['fault', 'anomaly', 'health']:
                    model_type = '_'.join(parts[:2])
                    device_part = parts[2] if len(parts) > 2 else 'global'
                    
                    if device_part not in device_models:
                        device_models[device_part] = {}
                    
                    device_models[device_part][model_type] = {
                        'filename': filename,
                        'size_kb': os.path.getsize(os.path.join(self.model_dir, filename)) / 1024
                    }
            
            models = device_models
        
        return {
            'model_dir': self.model_dir,
            'total_models': len([f for f in os.listdir(self.model_dir) if f.endswith('.joblib')]),
            'models': models,
            'loaded_models': list(self.models.keys()),
            'loaded_scalers': list(self.scalers.keys())
        }
    
    def delete_model(self, model_type: str, device_id: int = None, model_name: str = None) -> bool:
        """删除模型"""
        model_path = self._get_model_path(model_type, device_id, model_name)
        scaler_path = self._get_scaler_path(model_type, device_id)
        
        deleted = False
        
        if os.path.exists(model_path):
            os.remove(model_path)
            deleted = True
            
            # 从内存中移除
            model_key = f"{model_type}_{device_id if device_id else 'global'}_{model_name if model_name else 'default'}"
            if model_key in self.models:
                del self.models[model_key]
        
        if os.path.exists(scaler_path):
            os.remove(scaler_path)
            
            scaler_key = f"{model_type}_{device_id if device_id else 'global'}"
            if scaler_key in self.scalers:
                del self.scalers[scaler_key]
        
        return deleted


# 全局服务实例
ml_model_service = MLModelService()


def predict_fault(device_id: int, temperature: float = None, voltage: float = None, **kwargs) -> dict:
    """Standalone predict_fault function for tests"""
    telemetry = []
    if temperature is not None or voltage is not None:
        entry = {}
        if temperature is not None:
            entry['temperature'] = temperature
        if voltage is not None:
            entry['voltage'] = voltage
        entry.update(kwargs)
        telemetry.append(entry)
    return ml_model_service.predict_fault(device_id, telemetry)


def detect_anomaly(telemetry_data: dict = None) -> dict:
    """Standalone detect_anomaly function for tests"""
    data = [telemetry_data] if telemetry_data else []
    result = ml_model_service.detect_anomalies(device_id=0, telemetry_data=data)
    return {
        'is_anomaly': len(result.get('anomalies', [])) > 0,
        'anomaly_score': result.get('anomaly_score', 0),
        'anomalies': result.get('anomalies', []),
    }