import { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
} from 'react-native';
import { diagnosisApi } from '../services/api';
import { DiagnosisResult } from '../types';

const FAULT_CODE_EXAMPLES = [
  { code: 'E001', label: 'E001-过压' },
  { code: 'E002', label: 'E002-过流' },
  { code: 'E003', label: 'E003-过热' },
  { code: 'E004', label: 'E004-通信故障' },
  { code: 'E005', label: 'E005-绝缘异常' },
];

const SEVERITY_CONFIG: Record<string, { label: string; color: string }> = {
  low: { label: '低', color: '#2e7d32' },
  medium: { label: '中', color: '#f57f17' },
  high: { label: '高', color: '#e65100' },
  critical: { label: '严重', color: '#c62828' },
};

const DiagnosisScreen: React.FC = () => {
  const [codeInput, setCodeInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<DiagnosisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = useCallback(async () => {
    const code = codeInput.trim();
    if (!code) {
      setError('请输入故障码');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const response = await diagnosisApi.getDiagnosis(code);
      setResult(response.data);
      setCodeInput('');
    } catch {
      setError('未找到该故障码，请确认故障码是否正确');
    } finally {
      setLoading(false);
    }
  }, [codeInput]);

  const handleQuickInput = (code: string) => {
    setCodeInput(code);
    setError(null);
  };

  const severityConfig = result
    ? SEVERITY_CONFIG[result.severity] || { label: result.severity, color: '#999' }
    : null;

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      {/* 搜索区域 */}
      <View style={styles.searchCard}>
        <Text style={styles.searchTitle}>🔍 故障码诊断</Text>
        <Text style={styles.searchHint}>
          输入设备故障码，获取故障原因和解决方案
        </Text>
        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            placeholder="输入故障码（如 E001）"
            placeholderTextColor="#999"
            value={codeInput}
            onChangeText={(text) => {
              setCodeInput(text);
              setError(null);
            }}
            autoCapitalize="characters"
            autoCorrect={false}
            editable={!loading}
            returnKeyType="search"
            onSubmitEditing={handleSearch}
          />
          <TouchableOpacity
            style={[styles.searchBtn, loading && styles.searchBtnDisabled]}
            onPress={handleSearch}
            disabled={loading}
            activeOpacity={0.7}
           accessibilityRole="button">
            {loading ? (
              <ActivityIndicator color="#fff" size="small" />
            ) : (
              <Text style={styles.searchBtnText}>查询</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>

      {/* 常见故障码 */}
      <View style={styles.examplesCard}>
        <Text style={styles.examplesTitle}>常见故障码:</Text>
        <View style={styles.examplesRow}>
          {FAULT_CODE_EXAMPLES.map((item) => (
            <TouchableOpacity
              key={item.code}
              style={styles.exampleBtn}
              onPress={() => handleQuickInput(item.code)}
             accessibilityRole="button">
              <Text style={styles.exampleBtnText}>{item.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* 错误提示 */}
      {error && (
        <View style={styles.errorContainer}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}

      {/* 诊断结果 */}
      {result && (
        <View style={styles.resultContainer}>
          <Text style={styles.resultTitle}>诊断结果</Text>

          {/* 故障码信息 */}
          <View style={styles.resultCard}>
            <View style={styles.resultHeader}>
              <Text style={styles.faultCode}>{result.faultCode}</Text>
              {severityConfig && (
                <View
                  style={[
                    styles.severityBadge,
                    { backgroundColor: severityConfig.color },
                  ]}
                >
                  <Text style={styles.severityText}>
                    {severityConfig.label}
                  </Text>
                </View>
              )}
            </View>
            <Text style={styles.faultDesc}>{result.description}</Text>
            {result.deviceType && (
              <Text style={styles.deviceType}>
                设备类型: {result.deviceType}
              </Text>
            )}
          </View>

          {/* 可能原因 */}
          {result.possibleCauses.length > 0 && (
            <View style={styles.sectionCard}>
              <Text style={styles.sectionLabel}>📋 可能原因</Text>
              {result.possibleCauses.map((cause, index) => (
                <View key={index} style={styles.listItem}>
                  <Text style={styles.listNumber}>{index + 1}.</Text>
                  <Text style={styles.listText}>{cause}</Text>
                </View>
              ))}
            </View>
          )}

          {/* 解决方案 */}
          {result.solutions.length > 0 && (
            <View style={styles.sectionCard}>
              <Text style={styles.sectionLabel}>💡 解决方案</Text>
              {result.solutions.map((solution, index) => (
                <View key={index} style={styles.listItem}>
                  <Text style={styles.listNumber}>{index + 1}.</Text>
                  <Text style={styles.listText}>{solution}</Text>
                </View>
              ))}
            </View>
          )}

          {/* AI 建议入口 */}
          <View style={styles.aiCard}>
            <Text style={styles.aiIcon}>🤖</Text>
            <View style={styles.aiContent}>
              <Text style={styles.aiTitle}>需要更多帮助？</Text>
              <Text style={styles.aiHint}>
                使用 AI 助手获取更详细的故障分析和处理建议
              </Text>
            </View>
            <TouchableOpacity style={styles.aiBtn} activeOpacity={0.7}>
              <Text style={styles.aiBtnText}>咨询AI</Text>
            </TouchableOpacity>
          </View>

          {/* 关联文章 */}
          {result.relatedArticles && result.relatedArticles.length > 0 && (
            <View style={styles.sectionCard}>
              <Text style={styles.sectionLabel}>📚 相关知识库文章</Text>
              {result.relatedArticles.map((article) => (
                <TouchableOpacity
                  key={article.id}
                  style={styles.articleItem}
                  activeOpacity={0.7}
                >
                  <Text style={styles.articleTitle} numberOfLines={1}>
                    {article.title}
                  </Text>
                  <Text style={styles.articleMeta}>
                    {article.authorName} · {article.viewCount}次浏览
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          )}
        </View>
      )}

      {/* 空状态 */}
      {!result && !error && !loading && (
        <View style={styles.emptyContainer}>
          <Text style={styles.emptyIcon}>🔍</Text>
          <Text style={styles.emptyTitle}>故障码诊断</Text>
          <Text style={styles.emptyMessage}>
            输入设备上显示的故障码，获取故障原因、解决方案和相关知识库文章
          </Text>
        </View>
      )}
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
  searchCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  searchTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#333',
    marginBottom: 4,
  },
  searchHint: {
    fontSize: 13,
    color: '#999',
    marginBottom: 12,
  },
  inputRow: {
    flexDirection: 'row',
    gap: 10,
  },
  input: {
    flex: 1,
    backgroundColor: '#f5f6fa',
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    color: '#333',
    borderWidth: 1,
    borderColor: '#ddd',
  },
  searchBtn: {
    backgroundColor: '#1a73e8',
    borderRadius: 8,
    paddingHorizontal: 24,
    justifyContent: 'center',
    alignItems: 'center',
  },
  searchBtnDisabled: {
    opacity: 0.6,
  },
  searchBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  examplesCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 14,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  examplesTitle: {
    fontSize: 13,
    color: '#999',
    marginBottom: 8,
  },
  examplesRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  exampleBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: '#e3f2fd',
    borderRadius: 8,
  },
  exampleBtnText: {
    fontSize: 13,
    color: '#1565c0',
    fontWeight: '500',
  },
  errorContainer: {
    backgroundColor: '#fce4ec',
    borderRadius: 8,
    padding: 12,
    marginBottom: 12,
  },
  errorText: {
    color: '#c62828',
    fontSize: 14,
    textAlign: 'center',
  },
  resultContainer: {
    marginTop: 4,
  },
  resultTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    marginBottom: 10,
  },
  resultCard: {
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
  resultHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  faultCode: {
    fontSize: 20,
    fontWeight: '700',
    color: '#333',
  },
  severityBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 4,
  },
  severityText: {
    fontSize: 12,
    color: '#fff',
    fontWeight: '600',
  },
  faultDesc: {
    fontSize: 14,
    color: '#666',
    lineHeight: 20,
    marginBottom: 8,
  },
  deviceType: {
    fontSize: 12,
    color: '#999',
  },
  sectionCard: {
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
  sectionLabel: {
    fontSize: 15,
    fontWeight: '600',
    color: '#333',
    marginBottom: 10,
  },
  listItem: {
    flexDirection: 'row',
    marginBottom: 8,
    paddingRight: 8,
  },
  listNumber: {
    fontSize: 14,
    color: '#1a73e8',
    fontWeight: '500',
    marginRight: 6,
    width: 20,
  },
  listText: {
    fontSize: 14,
    color: '#666',
    lineHeight: 20,
    flex: 1,
  },
  aiCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  aiIcon: {
    fontSize: 32,
    marginRight: 12,
  },
  aiContent: {
    flex: 1,
  },
  aiTitle: {
    fontSize: 15,
    fontWeight: '600',
    color: '#333',
    marginBottom: 2,
  },
  aiHint: {
    fontSize: 12,
    color: '#999',
    lineHeight: 16,
  },
  aiBtn: {
    backgroundColor: '#1a73e8',
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  aiBtnText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '600',
  },
  articleItem: {
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
  },
  articleTitle: {
    fontSize: 14,
    color: '#1a73e8',
    fontWeight: '500',
    marginBottom: 2,
  },
  articleMeta: {
    fontSize: 12,
    color: '#999',
  },
  emptyContainer: {
    alignItems: 'center',
    paddingVertical: 60,
    paddingHorizontal: 40,
  },
  emptyIcon: {
    fontSize: 48,
    marginBottom: 16,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '600',
    color: '#333',
    marginBottom: 8,
  },
  emptyMessage: {
    fontSize: 14,
    color: '#999',
    textAlign: 'center',
    lineHeight: 22,
  },
});

export default DiagnosisScreen;
