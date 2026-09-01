import {
  View,
  Text,
  StyleSheet,
  ScrollView,
} from 'react-native';
import { useRoute, RouteProp } from '@react-navigation/native';
import { useKnowledgeDetail } from '../hooks/useKnowledgeDetail';
import { RootStackParamList } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';
import { useTheme } from '../hooks/useTheme';

type DetailRouteProp = RouteProp<RootStackParamList, 'KnowledgeDetail'>;

const KnowledgeDetailScreen: React.FC = () => {
  const { colors } = useTheme();
  const route = useRoute<DetailRouteProp>();
  void route; // route consumed by hook
  const { article, loading, error, fetchDetail } = useKnowledgeDetail();

  if (loading) {
    return <LoadingSpinner text="加载文章详情..." />;
  }

  if (error || !article) {
    return (
      <EmptyState
        icon="⚠️"
        title="加载失败"
        message={error || '文章不存在'}
        actionLabel="重新加载"
        onAction={fetchDetail}
      />
    );
  }

  return (
    <ScrollView
      style={[styles.container, { backgroundColor: colors.pageBg }]}
      contentContainerStyle={styles.content}
    >
      {/* 文章头部 */}
      <View style={[styles.headerCard, { backgroundColor: colors.cardBg }]}>
        <Text style={[styles.title, { color: colors.textPrimary }]}>{article.title}</Text>
        <View style={styles.meta}>
          <Text style={[styles.metaText, { color: colors.textSecondary }]}>{article.authorName}</Text>
          <Text style={[styles.metaDot, { color: colors.textMuted }]}>·</Text>
          <Text style={[styles.metaText, { color: colors.textSecondary }]}>
            {new Date(article.createdAt).toLocaleDateString('zh-CN')}
          </Text>
          <Text style={[styles.metaDot, { color: colors.textMuted }]}>·</Text>
          <Text style={[styles.metaText, { color: colors.textSecondary }]}>{article.viewCount}次浏览</Text>
        </View>
      </View>

      {/* 标签 */}
      {article.tags.length > 0 && (
        <View style={styles.tagRow}>
          {article.tags.map((tag, index) => (
            <View key={index} style={[styles.tag, { backgroundColor: colors.successBg }]}>
              <Text style={[styles.tagText, { color: colors.success }]}>{tag}</Text>
            </View>
          ))}
        </View>
      )}

      {/* 摘要 */}
      {article.summary ? (
        <View style={[styles.summaryCard, { backgroundColor: colors.infoBg }]}>
          <Text style={[styles.summaryLabel, { color: colors.info }]}>📝 摘要</Text>
          <Text style={[styles.summaryText, { color: colors.textPrimary }]}>{article.summary}</Text>
        </View>
      ) : null}

      {/* 正文 */}
      <View style={[styles.contentCard, { backgroundColor: colors.cardBg }]}>
        <Text style={[styles.contentTitle, { color: colors.textPrimary }]}>📄 正文</Text>
        <Text style={[styles.contentText, { color: colors.textPrimary }]}>
          {article.content || '暂无详细内容'}
        </Text>
      </View>
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
  headerCard: {
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    marginBottom: 10,
    lineHeight: 28,
  },
  meta: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  metaText: {
    fontSize: 13,
  },
  metaDot: {
    fontSize: 13,
    marginHorizontal: 6,
  },
  tagRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginBottom: 12,
    gap: 6,
  },
  tag: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 4,
  },
  tagText: {
    fontSize: 12,
  },
  summaryCard: {
    borderRadius: 10,
    padding: 14,
    marginBottom: 12,
  },
  summaryLabel: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 6,
  },
  summaryText: {
    fontSize: 14,
    lineHeight: 22,
  },
  contentCard: {
    borderRadius: 12,
    padding: 16,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  contentTitle: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 12,
  },
  contentText: {
    fontSize: 15,
    lineHeight: 26,
  },
});

export default KnowledgeDetailScreen;
