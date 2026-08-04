import React, { useEffect, useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  Alert,
  Modal,
  TextInput,
  ActivityIndicator,
  RefreshControl,
  KeyboardAvoidingView,
  Platform,
} from 'react-native';
import { useIsFocused } from '@react-navigation/native';
import { vehicleApi } from '../services/api';
import { Vehicle } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';

const VehicleScreen: React.FC = () => {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalVisible, setModalVisible] = useState(false);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // 表单
  const [plate, setPlate] = useState('');
  const [brand, setBrand] = useState('');
  const [model, setModel] = useState('');
  const [color, setColor] = useState('');
  const [vin, setVin] = useState('');
  const [isDefault, setIsDefault] = useState(false);

  const loadVehicles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await vehicleApi.getList();
      setVehicles(response.data);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '获取车辆列表失败';
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  // 回焦静默刷新: 与订单/首页/钱包等屏对齐(F170/F209交互一致性模式);
  // 默认车辆/车辆状态可能在支付/充电流程后变化。
  const isFocused = useIsFocused();

  useEffect(() => {
    if (isFocused) {
      loadVehicles();
    }
  }, [isFocused, loadVehicles]);

  // 下拉刷新: 与订单/优惠券/钱包等列表屏对齐(F209模式)。
  const handleRefresh = async () => {
    setRefreshing(true);
    await loadVehicles();
    setRefreshing(false);
  };

  const handleAdd = async () => {
    if (!plate.trim()) {
      Alert.alert('提示', '请输入车牌号');
      return;
    }
    setSaving(true);
    try {
      await vehicleApi.add({
        plate: plate.trim(),
        brand: brand.trim(),
        model: model.trim(),
        color: color.trim(),
        vin: vin.trim(),
        isDefault,
      });
      setModalVisible(false);
      resetForm();
      loadVehicles();
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { message?: string } } };
        Alert.alert('添加失败', axiosErr.response?.data?.message || '请重试');
      } else {
        Alert.alert('添加失败', '网络错误');
      }
    } finally {
      setSaving(false);
    }
  };

  const handleRemove = (vehicle: Vehicle) => {
    Alert.alert('删除车辆', `确定要删除 ${vehicle.plate} 吗？`, [
      { text: '取消', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: async () => {
          try {
            await vehicleApi.remove(vehicle.id);
            loadVehicles();
          } catch {
            Alert.alert('删除失败', '请重试');
          }
        },
      },
    ]);
  };

  const handleSetDefault = async (vehicle: Vehicle) => {
    try {
      await vehicleApi.setDefault(vehicle.id);
      loadVehicles();
    } catch {
      Alert.alert('设置失败', '请重试');
    }
  };

  const resetForm = () => {
    setPlate('');
    setBrand('');
    setModel('');
    setColor('');
    setVin('');
    setIsDefault(false);
  };

  const renderVehicleItem = ({ item }: { item: Vehicle }) => (
    <View style={styles.vehicleCard}>
      <View style={styles.vehicleHeader}>
        <Text style={styles.vehiclePlate}>{item.plate}</Text>
        {item.isDefault && (
          <View style={styles.defaultBadge}>
            <Text style={styles.defaultBadgeText}>默认</Text>
          </View>
        )}
      </View>
      <View style={styles.vehicleInfo}>
        <Text style={styles.vehicleDetail}>
          {item.brand} {item.model}
        </Text>
        <Text style={styles.vehicleDetail}>颜色: {item.color}</Text>
        <Text style={styles.vehicleDetail}>VIN: {item.vin}</Text>
      </View>
      <View style={styles.vehicleActions}>
        {!item.isDefault && (
          <TouchableOpacity
            style={styles.actionBtn}
            onPress={() => handleSetDefault(item)}
          >
            <Text style={styles.actionBtnText}>设为默认</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity
          style={[styles.actionBtn, styles.actionBtnDanger]}
          onPress={() => handleRemove(item)}
        >
          <Text style={[styles.actionBtnText, styles.actionBtnTextDanger]}>删除</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  // 仅首屏(无数据)才切整屏spinner/错误页; 回焦重拉/刷新失败时保留已有列表不闪屏(F209模式)
  if (loading && vehicles.length === 0) {
    return <LoadingSpinner text="加载车辆列表..." />;
  }

  if (error && vehicles.length === 0) {
    return (
      <EmptyState
        icon="⚠️"
        title="加载失败"
        message={error}
        actionLabel="重试"
        onAction={loadVehicles}
      />
    );
  }

  return (
    <View style={styles.container}>
      <FlatList
        data={vehicles}
        keyExtractor={(item) => String(item.id)}
        renderItem={renderVehicleItem}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            colors={["#1a73e8"]}
            tintColor="#1a73e8"
          />
        }
        ListEmptyComponent={
          <EmptyState
            icon="🚗"
            title="暂无车辆"
            message="添加您的爱车，方便充电时快速选择"
          />
        }
      />

      {/* 添加按钮 */}
      <TouchableOpacity
        style={styles.addBtn}
        onPress={() => setModalVisible(true)}
        activeOpacity={0.7}
      >
        <Text style={styles.addBtnText}>+ 添加车辆</Text>
      </TouchableOpacity>

      {/* 添加弹窗 */}
      <Modal
        visible={modalVisible}
        animationType="slide"
        transparent
        onRequestClose={() => setModalVisible(false)}
      >
        {/* F271: 底部弹出表单(justifyContent:flex-end)键盘遮挡修复——
            Modal内TextInput聚焦时软键盘直接覆盖下半部输入项与保存按钮,
            KAV behavior分平台(iOS padding/Android height), 与LoginScreen同惯例 */}
        <KeyboardAvoidingView
          style={styles.modalOverlay}
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        >
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>添加车辆</Text>

            <TextInput
              style={styles.modalInput}
              placeholder="车牌号 *"
              placeholderTextColor="#999"
              value={plate}
              onChangeText={setPlate}
            />
            <TextInput
              style={styles.modalInput}
              placeholder="品牌"
              placeholderTextColor="#999"
              value={brand}
              onChangeText={setBrand}
            />
            <TextInput
              style={styles.modalInput}
              placeholder="型号"
              placeholderTextColor="#999"
              value={model}
              onChangeText={setModel}
            />
            <TextInput
              style={styles.modalInput}
              placeholder="颜色"
              placeholderTextColor="#999"
              value={color}
              onChangeText={setColor}
            />
            <TextInput
              style={styles.modalInput}
              placeholder="VIN码"
              placeholderTextColor="#999"
              value={vin}
              onChangeText={setVin}
            />

            <TouchableOpacity
              style={styles.defaultCheck}
              onPress={() => setIsDefault(!isDefault)}
            >
              <View style={[styles.checkbox, isDefault && styles.checkboxChecked]}>
                {isDefault && <Text style={styles.checkmark}>✓</Text>}
              </View>
              <Text style={styles.defaultCheckLabel}>设为默认车辆</Text>
            </TouchableOpacity>

            <View style={styles.modalActions}>
              <TouchableOpacity
                style={styles.modalCancelBtn}
                onPress={() => {
                  setModalVisible(false);
                  resetForm();
                }}
              >
                <Text style={styles.modalCancelText}>取消</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modalSaveBtn, saving && styles.modalSaveBtnDisabled]}
                onPress={handleAdd}
                disabled={saving}
              >
                {saving ? (
                  <ActivityIndicator color="#fff" size="small" />
                ) : (
                  <Text style={styles.modalSaveText}>保存</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f6fa',
  },
  listContent: {
    padding: 16,
    paddingBottom: 100,
  },
  vehicleCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  vehicleHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
  },
  vehiclePlate: {
    fontSize: 18,
    fontWeight: '700',
    color: '#333',
    marginRight: 8,
  },
  defaultBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    backgroundColor: '#e3f2fd',
    borderRadius: 4,
  },
  defaultBadgeText: {
    fontSize: 11,
    color: '#1565c0',
    fontWeight: '500',
  },
  vehicleInfo: {
    marginBottom: 10,
  },
  vehicleDetail: {
    fontSize: 13,
    color: '#999',
    marginBottom: 2,
  },
  vehicleActions: {
    flexDirection: 'row',
    gap: 10,
  },
  actionBtn: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 6,
    backgroundColor: '#e3f2fd',
  },
  actionBtnDanger: {
    backgroundColor: '#fce4ec',
  },
  actionBtnText: {
    fontSize: 13,
    color: '#1565c0',
    fontWeight: '500',
  },
  actionBtnTextDanger: {
    color: '#c62828',
  },
  addBtn: {
    position: 'absolute',
    bottom: 20,
    left: 16,
    right: 16,
    backgroundColor: '#1a73e8',
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
  },
  addBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 24,
    paddingBottom: 40,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#333',
    marginBottom: 20,
    textAlign: 'center',
  },
  modalInput: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    color: '#333',
    backgroundColor: '#fafafa',
    marginBottom: 12,
  },
  defaultCheck: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 20,
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 4,
    borderWidth: 2,
    borderColor: '#ddd',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 8,
  },
  checkboxChecked: {
    backgroundColor: '#1a73e8',
    borderColor: '#1a73e8',
  },
  checkmark: {
    color: '#fff',
    fontSize: 14,
    fontWeight: 'bold',
  },
  defaultCheckLabel: {
    fontSize: 14,
    color: '#333',
  },
  modalActions: {
    flexDirection: 'row',
    gap: 12,
  },
  modalCancelBtn: {
    flex: 1,
    paddingVertical: 12,
    alignItems: 'center',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#ddd',
  },
  modalCancelText: {
    fontSize: 15,
    color: '#666',
    fontWeight: '500',
  },
  modalSaveBtn: {
    flex: 1,
    paddingVertical: 12,
    alignItems: 'center',
    borderRadius: 8,
    backgroundColor: '#1a73e8',
  },
  modalSaveBtnDisabled: {
    opacity: 0.6,
  },
  modalSaveText: {
    fontSize: 15,
    color: '#fff',
    fontWeight: '600',
  },
});

export default VehicleScreen;