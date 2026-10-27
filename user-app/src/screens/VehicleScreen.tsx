import React, { useState, useMemo } from 'react';
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
import { useVehicles } from '../hooks/useVehicles';
import { Vehicle } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';
import { useTheme } from '../hooks/useTheme';
import type { ThemeColors } from '../theme/colors';

const VehicleScreen: React.FC = () => {
  const { colors } = useTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);

  const { vehicles, loading, error, refreshing, loadVehicles, handleRefresh, addVehicle, removeVehicle, setDefaultVehicle } =
    useVehicles();

  const [modalVisible, setModalVisible] = useState(false);
  const [saving, setSaving] = useState(false);

  // 表单
  const [plate, setPlate] = useState('');
  const [brand, setBrand] = useState('');
  const [model, setModel] = useState('');
  const [color, setColor] = useState('');
  const [vin, setVin] = useState('');
  const [isDefault, setIsDefault] = useState(false);

  const handleAdd = async () => {
    if (!plate.trim()) {
      Alert.alert('提示', '请输入车牌号');
      return;
    }
    setSaving(true);
    const result = await addVehicle({
      plate: plate.trim(),
      brand: brand.trim(),
      model: model.trim(),
      color: color.trim(),
      vin: vin.trim(),
      isDefault,
    });
    setSaving(false);

    if (result.success) {
      setModalVisible(false);
      resetForm();
    } else {
      Alert.alert('添加失败', result.errorMessage || (result.isNetworkError ? '网络错误' : '请重试'));
    }
  };

  const handleRemove = (vehicle: Vehicle) => {
    Alert.alert('删除车辆', `确定要删除 ${vehicle.plate} 吗？`, [
      { text: '取消', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: async () => {
          const success = await removeVehicle(vehicle.id);
          if (!success) Alert.alert('删除失败', '请重试');
        },
      },
    ]);
  };

  const handleSetDefault = async (vehicle: Vehicle) => {
    const success = await setDefaultVehicle(vehicle.id);
    if (!success) Alert.alert('设置失败', '请重试');
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
          <TouchableOpacity accessibilityRole="button"
            style={styles.actionBtn}
            onPress={() => handleSetDefault(item)}
          >
            <Text style={styles.actionBtnText}>设为默认</Text>
          </TouchableOpacity>
        )}
        <TouchableOpacity accessibilityRole="button"
          style={[styles.actionBtn, styles.actionBtnDanger]}
          onPress={() => handleRemove(item)}
        >
          <Text style={[styles.actionBtnText, styles.actionBtnTextDanger]}>删除</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

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
        testID="vehicle-list"
        keyExtractor={(item) => String(item.id)}
        renderItem={renderVehicleItem}
        contentContainerStyle={styles.listContent}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            colors={[colors.primary]}
            tintColor={colors.primary}
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
      <TouchableOpacity accessibilityRole="button"
        testID="vehicle-add-btn"
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
        <KeyboardAvoidingView
          style={styles.modalOverlay}
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        >
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>添加车辆</Text>

            <TextInput
              style={styles.modalInput}
              placeholder="车牌号 *"
              placeholderTextColor={colors.textSecondary}
              value={plate}
              onChangeText={setPlate}
            />
            <TextInput
              style={styles.modalInput}
              placeholder="品牌"
              placeholderTextColor={colors.textSecondary}
              value={brand}
              onChangeText={setBrand}
            />
            <TextInput
              style={styles.modalInput}
              placeholder="型号"
              placeholderTextColor={colors.textSecondary}
              value={model}
              onChangeText={setModel}
            />
            <TextInput
              style={styles.modalInput}
              placeholder="颜色"
              placeholderTextColor={colors.textSecondary}
              value={color}
              onChangeText={setColor}
            />
            <TextInput
              style={styles.modalInput}
              placeholder="VIN码"
              placeholderTextColor={colors.textSecondary}
              value={vin}
              onChangeText={setVin}
            />

            <TouchableOpacity
              accessibilityRole="checkbox"
              accessibilityState={{ checked: isDefault }}
              style={styles.defaultCheck}
              onPress={() => setIsDefault(!isDefault)}
            >
              <View style={[styles.checkbox, isDefault && styles.checkboxChecked]}>
                {isDefault && <Text style={styles.checkmark}>✓</Text>}
              </View>
              <Text style={styles.defaultCheckLabel}>设为默认车辆</Text>
            </TouchableOpacity>

            <View style={styles.modalActions}>
              <TouchableOpacity accessibilityRole="button"
                style={styles.modalCancelBtn}
                onPress={() => {
                  setModalVisible(false);
                  resetForm();
                }}
              >
                <Text style={styles.modalCancelText}>取消</Text>
              </TouchableOpacity>
              <TouchableOpacity accessibilityRole="button"
                style={[styles.modalSaveBtn, saving && styles.modalSaveBtnDisabled]}
                onPress={handleAdd}
                disabled={saving}
              >
                {saving ? (
                  <ActivityIndicator color={colors.onPrimary} size="small" />
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

const createStyles = (colors: ThemeColors) =>
  StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.pageBg,
  },
  listContent: {
    padding: 16,
    paddingBottom: 100,
  },
  vehicleCard: {
    backgroundColor: colors.cardBg,
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
    color: colors.textPrimary,
    marginRight: 8,
  },
  defaultBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    backgroundColor: colors.infoBg,
    borderRadius: 4,
  },
  defaultBadgeText: {
    fontSize: 11,
    color: colors.info,
    fontWeight: '500',
  },
  vehicleInfo: {
    marginBottom: 10,
  },
  vehicleDetail: {
    fontSize: 13,
    color: colors.textSecondary,
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
    backgroundColor: colors.infoBg,
  },
  actionBtnDanger: {
    backgroundColor: colors.errorBg,
  },
  actionBtnText: {
    fontSize: 13,
    color: colors.info,
    fontWeight: '500',
  },
  actionBtnTextDanger: {
    color: colors.error,
  },
  addBtn: {
    position: 'absolute',
    bottom: 20,
    left: 16,
    right: 16,
    backgroundColor: colors.primary,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
  },
  addBtnText: {
    color: colors.onPrimary,
    fontSize: 16,
    fontWeight: '600',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  modalContent: {
    backgroundColor: colors.cardBg,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 24,
    paddingBottom: 40,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: colors.textPrimary,
    marginBottom: 20,
    textAlign: 'center',
  },
  modalInput: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 15,
    color: colors.textPrimary,
    backgroundColor: colors.inputBg,
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
    borderColor: colors.border,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 8,
  },
  checkboxChecked: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  checkmark: {
    color: colors.onPrimary,
    fontSize: 14,
    fontWeight: 'bold',
  },
  defaultCheckLabel: {
    fontSize: 14,
    color: colors.textPrimary,
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
    borderColor: colors.border,
  },
  modalCancelText: {
    fontSize: 15,
    color: colors.textSecondary,
    fontWeight: '500',
  },
  modalSaveBtn: {
    flex: 1,
    paddingVertical: 12,
    alignItems: 'center',
    borderRadius: 8,
    backgroundColor: colors.primary,
  },
  modalSaveBtnDisabled: {
    opacity: 0.6,
  },
  modalSaveText: {
    fontSize: 15,
    color: colors.onPrimary,
    fontWeight: '600',
  },
});

export default VehicleScreen;
