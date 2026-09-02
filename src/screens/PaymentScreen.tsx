import React, { useMemo } from 'react';
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
import { usePayment } from '../hooks/usePayment';
import { RootStackParamList, PaymentMethod } from '../types';
import { formatMoney } from '../utils/format';
import { useTheme } from '../hooks/useTheme';
import type { ThemeColors } from '../theme/colors';

type PaymentRouteProp = RouteProp<RootStackParamList, 'Payment'>;
type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const PAYMENT_METHODS: { key: PaymentMethod; label: string; icon: string }[] = [
  { key: 'wechat', label: '微信支付', icon: '💚' },
  { key: 'alipay', label: '支付宝', icon: '💙' },
  { key: 'balance', label: '余额支付', icon: '💰' },
];

const PaymentScreen: React.FC = () => {
  const { colors } = useTheme();
  const styles = useMemo(() => createStyles(colors), [colors]);

  const route = useRoute<PaymentRouteProp>();
  const navigation = useNavigation<NavigationProp>();
  const { orderId, amount } = route.params;
  const { selectedMethod, setSelectedMethod, paying, pay } = usePayment();

  const handlePay = async () => {
    const result = await pay(orderId, amount);
    if (result.success) {
      Alert.alert('支付成功', `已支付 ¥${formatMoney(result.paidAmount || 0)}`, [
        {
          text: '完成',
          onPress: () => {
            navigation.popToTop();
          },
        },
      ]);
    } else {
      Alert.alert('支付失败', result.message || '请重试');
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
      <View style={styles.methodCard} testID="payment-method-card">
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
        testID="payment-pay-btn"
        style={[styles.payBtn, paying && styles.payBtnDisabled]}
        onPress={handlePay}
        disabled={paying}
        activeOpacity={0.7}
      >
        {paying ? (
          <ActivityIndicator color={colors.onPrimary} size="small" />
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

const createStyles = (colors: ThemeColors) =>
  StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.pageBg,
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  amountCard: {
    backgroundColor: colors.cardBg,
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
    color: colors.textSecondary,
    marginBottom: 8,
  },
  amountValue: {
    fontSize: 40,
    fontWeight: '700',
    color: colors.warning,
  },
  amountSymbol: {
    fontSize: 24,
    fontWeight: '600',
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: colors.textPrimary,
    marginBottom: 10,
  },
  methodCard: {
    backgroundColor: colors.cardBg,
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
    borderBottomColor: colors.divider,
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
    color: colors.textPrimary,
    fontWeight: '500',
  },
  radio: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    borderColor: colors.border,
    justifyContent: 'center',
    alignItems: 'center',
  },
  radioSelected: {
    borderColor: colors.primary,
  },
  radioInner: {
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.primary,
  },
  payBtn: {
    backgroundColor: colors.primary,
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
    marginBottom: 12,
  },
  payBtnDisabled: {
    opacity: 0.6,
  },
  payBtnText: {
    color: colors.onPrimary,
    fontSize: 18,
    fontWeight: '600',
  },
  tipText: {
    textAlign: 'center',
    fontSize: 12,
    color: colors.textMuted,
  },
});

export default PaymentScreen;
