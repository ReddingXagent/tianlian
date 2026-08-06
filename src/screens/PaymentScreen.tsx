import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
  ScrollView,
} from 'react-native';
import { useRoute, RouteProp, useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { paymentApi } from '../services/api';
import { RootStackParamList, PaymentMethod } from '../types';
import { formatMoney } from '../utils/format';

type PaymentRouteProp = RouteProp<RootStackParamList, 'Payment'>;
type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const PAYMENT_METHODS: { key: PaymentMethod; label: string; icon: string }[] = [
  { key: 'wechat', label: '微信支付', icon: '💚' },
  { key: 'alipay', label: '支付宝', icon: '💙' },
  { key: 'balance', label: '余额支付', icon: '💰' },
];

const PaymentScreen: React.FC = () => {
  const route = useRoute<PaymentRouteProp>();
  const navigation = useNavigation<NavigationProp>();
  const { orderId, amount } = route.params;
  const [selectedMethod, setSelectedMethod] = useState<PaymentMethod>('wechat');
  const [paying, setPaying] = useState(false);

  const handlePay = async () => {
    setPaying(true);
    try {
      const response = await paymentApi.pay({
        orderId,
        method: selectedMethod,
      });
      if (response.data.success) {
        Alert.alert('支付成功', `已支付 ¥${formatMoney(response.data.paidAmount)}`, [
          {
            text: '完成',
            onPress: () => {
              navigation.popToTop();
            },
          },
        ]);
      } else {
        Alert.alert('支付失败', response.data.message || '请重试');
      }
    } catch (err: unknown) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { data?: { message?: string } } };
        Alert.alert('支付失败', axiosErr.response?.data?.message || '支付请求失败');
      } else {
        Alert.alert('支付失败', '网络错误，请检查网络连接');
      }
    } finally {
      setPaying(false);
    }
  };

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* 金额展示 */}
      <View style={styles.amountCard}>
        <Text style={styles.amountLabel}>待支付金额</Text>
        <Text style={styles.amountValue}>
          <Text style={styles.amountSymbol}>¥</Text>
          {formatMoney(amount)}
        </Text>
      </View>

      {/* 支付方式 */}
      <Text style={styles.sectionTitle}>选择支付方式</Text>
      <View style={styles.methodCard}>
        {PAYMENT_METHODS.map((method, index) => (
          <TouchableOpacity accessibilityRole="button"
            key={method.key}
            style={[
              styles.methodItem,
              index < PAYMENT_METHODS.length - 1 && styles.methodItemBorder,
              selectedMethod === method.key && styles.methodItemSelected,
            ]}
            onPress={() => setSelectedMethod(method.key)}
            activeOpacity={0.7}
          >
            <Text style={styles.methodIcon}>{method.icon}</Text>
            <Text style={styles.methodLabel}>{method.label}</Text>
            <View
              style={[
                styles.radio,
                selectedMethod === method.key && styles.radioSelected,
              ]}
            >
              {selectedMethod === method.key && <View style={styles.radioInner} />}
            </View>
          </TouchableOpacity>
        ))}
      </View>

      {/* 支付按钮 */}
      <TouchableOpacity accessibilityRole="button"
        style={[styles.payBtn, paying && styles.payBtnDisabled]}
        onPress={handlePay}
        disabled={paying}
        activeOpacity={0.7}
      >
        {paying ? (
          <ActivityIndicator color="#fff" size="small" />
        ) : (
          <Text style={styles.payBtnText}>
            确认支付 ¥{formatMoney(amount)}
          </Text>
        )}
      </TouchableOpacity>

      {/* 提示 */}
      <Text style={styles.tipText}>
        支付即表示同意《充电服务协议》
      </Text>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f6fa',
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  amountCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 24,
    alignItems: 'center',
    marginBottom: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 8,
    elevation: 4,
  },
  amountLabel: {
    fontSize: 14,
    color: '#999',
    marginBottom: 8,
  },
  amountValue: {
    fontSize: 40,
    fontWeight: '700',
    color: '#e65100',
  },
  amountSymbol: {
    fontSize: 24,
    fontWeight: '600',
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    marginBottom: 10,
  },
  methodCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    marginBottom: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  methodItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 16,
  },
  methodItemBorder: {
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  methodItemSelected: {
    backgroundColor: 'rgba(26, 115, 232, 0.03)',
  },
  methodIcon: {
    fontSize: 24,
    marginRight: 12,
  },
  methodLabel: {
    flex: 1,
    fontSize: 15,
    color: '#333',
    fontWeight: '500',
  },
  radio: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    borderColor: '#ddd',
    justifyContent: 'center',
    alignItems: 'center',
  },
  radioSelected: {
    borderColor: '#1a73e8',
  },
  radioInner: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: '#1a73e8',
  },
  payBtn: {
    backgroundColor: '#1a73e8',
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
    marginBottom: 12,
  },
  payBtnDisabled: {
    opacity: 0.6,
  },
  payBtnText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
  },
  tipText: {
    textAlign: 'center',
    fontSize: 12,
    color: '#ccc',
  },
});

export default PaymentScreen;