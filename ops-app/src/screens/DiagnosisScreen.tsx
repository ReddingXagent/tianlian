import { ScrollView, View, Text, StyleSheet, TextInput, TouchableOpacity, ActivityIndicator } from 'react-native';
import { useDiagnosis } from '../hooks/useDiagnosis';
import { useTheme } from '../hooks/useTheme';
import { ThemeColors } from '../theme/colors';

const FAULT_CODE_EXAMPLES = [
  { code: 'E001', label: 'E001-过压' },
  { code: 'E002', label: 'E002-过流' },
  { code: 'E003', label: 'E003-过热' },
  { code: 'E004', label: 'E004-通信故障' },
  { code: 'E005', label: 'E005-绝缘异常' },
];

const SEVERITY_SEMANTICS: Record<string, { label: string; color: keyof ThemeColors }> = {
  low: { label: '低', color: 'success' },
  medium: { label: '中', color: 'warningAmber' },
  high: { label: '高', color: 'warning' },
  critical: { label: '严重', color: 'error' },
};

const DiagnosisScreen: React.FC = () => {
  const {
    codeInput,
    loading,
    result,
    error,
    setCodeInput,
    clearError,
    handleSearch,
    handleQuickInput,
  } = useDiagnosis();
  const { colors } = useTheme();

  const severitySemantic = result
    ? SEVERITY_SEMANTICS[result.severity] || { label: result.severity, color: 'neutralText' as const }
    : null;

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: colors.pageBg }]}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled"
    >
      {/* 搜索区域 */}
      <View style={[styles.searchCard, { backgroundColor: colors.cardBg }]}>
        <Text style={[styles.searchTitle, { color: colors.textPrimary }]}>🔍 故障码诊断</Text>
        <Text style={[styles.searchHint, { color: colors.textSecondary }]}>
          输入设备故障码，获取故障原因和解决方案
        </Text>
        <View style={styles.inputRow}>
          <TextInput
            testID="diagnosis-code-input"
            style={[styles.input, { backgroundColor: colors.pageBg, color: colors.textPrimary, borderColor: colors.border }]}
            placeholder="输入故障码（如 E001）"
            placeholderTextColor={colors.textSecondary}
            value={codeInput}
            onChangeText={(text) => {
              setCodeInput(text);
              clearError();
            }}
            autoCapitalize="characters"
            autoCorrect={false}
            editable={!loading}
            returnKeyType="search"
            onSubmitEditing={handleSearch}
          />
          <TouchableOpacity
            testID="diagnosis-search-btn"
            style={[styles.searchBtn, { backgroundColor: colors.primary }, loading && styles.searchBtnDisabled]}
            onPress={handleSearch}
            disabled={loading}
            activeOpacity={0.7}
            accessibilityRole="button">
            {loading ? (
              <ActivityIndicator color={colors.onPrimary} size="small" />
            ) : (
              <Text style={[styles.searchBtnText, { color: colors.onPrimary }]}>查询</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>

      {/* 常见故障码 */}
      <View style={[styles.examplesCard, { backgroundColor: colors.cardBg }]}>
        <Text style={[styles.examplesTitle, { color: colors.textSecondary }]}>常见故障码:</Text>
        <View style={styles.examplesRow}>
          {FAULT_CODE_EXAMPLES.map((item) => (
            <TouchableOpacity
              key={item.code}
              style={[styles.exampleBtn, { backgroundColor: colors.infoBg }]}
              onPress={() => handleQuickInput(item.code)}
              accessibilityRole="button">
              <Text style={[styles.exampleBtnText, { color: colors.info }]}>{item.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>

      {/* 错误提示 */}
      {error && (
        <View style={[styles.errorContainer, { backgroundColor: colors.errorBg }]}>
          <Text style={[styles.errorText, { color: colors.error }]}>{error}</Text>
        </View>
      )}

      {/* 诊断结果 */}
      {result && (
        <View style={styles.resultContainer}>
          <Text style={[styles.resultTitle, { color: colors.textPrimary }]}>诊断结果</Text>

          {/* 故障码信息 */}
          <View style={[styles.resultCard, { backgroundColor: colors.cardBg }]}>
            <View style={styles.resultHeader}>
              <Text style={[styles.faultCode, { color: colors.textPrimary }]}>{result.faultCode}</Text>
              {severitySemantic && (
                <View
                  style={[
                    styles.severityBadge,
                    { backgroundColor: colors[severitySemantic.color] },
                  ]}
                >
                  <Text style={[styles.severityText, { color: colors.onPrimary }]}>
                    {severitySemantic.label}
                  </Text>
                </View>
              )}
            </View>
            <Text style={[styles.faultDesc, { color: colors.textSecondary }]}>{result.description}</Text>
            {result.deviceType && (
              <Text style={[styles.deviceType, { color: colors.textSecondary }]}>
                设备类型: {result.deviceType}
              </Text>
            )}
          </View>

          {/* 可能原因 */}
          {result.possibleCauses.length > 0 && (
            <View style={[styles.sectionCard, { backgroundColor: colors.cardBg }]}>
              <Text style={[styles.sectionLabel, { color: colors.textPrimary }]}>📋 可能原因</Text>
              {result.possibleCauses.map((cause, index) => (
                <View key={index} style={styles.listItem}>
                  <Text style={[styles.listNumber, { color: colors.primary }]}>{index + 1}.</Text>
                  <Text style={[styles.listText, { color: colors.textSecondary }]}>{cause}</Text>
                </View>
              ))}
            </View>
          )}

          {/* 解决方案 */}
          {result.solutions.length > 0 && (
            <View style={[styles.sectionCard, { backgroundColor: colors.cardBg }]}>
              <Text style={[styles.sectionLabel, { color: colors.textPrimary }]}>💡 解决方案</Text>
              {result.solutions.map((solution, index) => (
                <View key={index} style={styles.listItem}>
                  <Text style={[styles.listNumber, { color: colors.primary }]}>{index + 1}.</Text>
                  <Text style={[styles.listText, { color: colors.textSecondary }]}>{solution}</Text>
                </View>
              ))}
            </View>
          )}

          {/* AI 建议入口 */}
          <View style={[styles.aiCard, { backgroundColor: colors.cardBg }]}>
            <Text style={styles.aiIcon}>🤖</Text>
            <View style={styles.aiContent}>
              <Text style={[styles.aiTitle, { color: colors.textPrimary }]}>需要更多帮助？</Text>
              <Text style={[styles.aiHint, { color: colors.textSecondary }]}>
                使用 AI 助手获取更详细的故障分析和处理建议
              </Text>
            </View>
            <TouchableOpacity style={[styles.aiBtn, { backgroundColor: colors.primary }]} activeOpacity={0.7}>
              <Text style={[styles.aiBtnText, { color: colors.onPrimary }]}>咨询AI</Text>
            </TouchableOpacity>
          </View>

          {/* 关联文章 */}
          {result.relatedArticles && result.relatedArticles.length > 0 && (
            <View style={[styles.sectionCard, { backgroundColor: colors.cardBg }]}>
              <Text style={[styles.sectionLabel, { color: colors.textPrimary }]}>📚 相关知识库文章</Text>
              {result.relatedArticles.map((article) => (
                <TouchableOpacity
                  key={article.id}
                  style={[styles.articleItem, { borderBottomColor: colors.divider }]}
                  activeOpacity={0.7}
                >
                  <Text style={[styles.articleTitle, { color: colors.primary }]} numberOfLines={1}>
                    {article.title}
                  </Text>
                  <Text style={[styles.articleMeta, { color: colors.textSecondary }]}>
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
          <Text style={[styles.emptyTitle, { color: colors.textPrimary }]}>故障码诊断</Text>
          <Text style={[styles.emptyMessage, { color: colors.textSecondary }]}>
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
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  searchCard: {
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
    marginBottom: 4,
  },
  searchHint: {
    fontSize: 13,
    marginBottom: 12,
  },
  inputRow: {
    flexDirection: 'row',
    gap: 10,
  },
  input: {
    flex: 1,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    borderWidth: 1,
  },
  searchBtn: {
    borderRadius: 8,
    paddingHorizontal: 24,
    justifyContent: 'center',
    alignItems: 'center',
  },
  searchBtnDisabled: {
    opacity: 0.6,
  },
  searchBtnText: {
    fontSize: 16,
    fontWeight: '600',
  },
  examplesCard: {
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
    borderRadius: 8,
  },
  exampleBtnText: {
    fontSize: 13,
    fontWeight: '500',
  },
  errorContainer: {
    borderRadius: 8,
    padding: 12,
    marginBottom: 12,
  },
  errorText: {
    fontSize: 14,
    textAlign: 'center',
  },
  resultContainer: {
    marginTop: 4,
  },
  resultTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 10,
  },
  resultCard: {
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
  },
  severityBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 4,
  },
  severityText: {
    fontSize: 12,
    fontWeight: '600',
  },
  faultDesc: {
    fontSize: 14,
    lineHeight: 20,
    marginBottom: 8,
  },
  deviceType: {
    fontSize: 12,
  },
  sectionCard: {
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
    marginBottom: 10,
  },
  listItem: {
    flexDirection: 'row',
    marginBottom: 8,
    paddingRight: 8,
  },
  listNumber: {
    fontSize: 14,
    fontWeight: '500',
    marginRight: 6,
    width: 20,
  },
  listText: {
    fontSize: 14,
    lineHeight: 20,
    flex: 1,
  },
  aiCard: {
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
    marginBottom: 2,
  },
  aiHint: {
    fontSize: 12,
    lineHeight: 16,
  },
  aiBtn: {
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  aiBtnText: {
    fontSize: 13,
    fontWeight: '600',
  },
  articleItem: {
    paddingVertical: 10,
    borderBottomWidth: 1,
  },
  articleTitle: {
    fontSize: 14,
    fontWeight: '500',
    marginBottom: 2,
  },
  articleMeta: {
    fontSize: 12,
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
    marginBottom: 8,
  },
  emptyMessage: {
    fontSize: 14,
    textAlign: 'center',
    lineHeight: 22,
  },
});

export default DiagnosisScreen;
