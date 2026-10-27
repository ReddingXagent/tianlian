import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TextInput,
  TouchableOpacity,
  RefreshControl,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';
import { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useKnowledge } from '../hooks/useKnowledge';
import { KnowledgeArticle, RootStackParamList } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';
import { useTheme } from '../hooks/useTheme';

type NavigationProp = NativeStackNavigationProp<RootStackParamList>;

const CATEGORIES: { key: string; label: string; icon: string }[] = [
  { key: 'all', label: '全部', icon: '📚' },
  { key: 'operation', label: '操作', icon: '📖' },
  { key: 'maintenance', label: '维护', icon: '🔧' },
  { key: 'troubleshooting', label: '故障', icon: '🛠️' },
  { key: 'safety', label: '安全', icon: '🛡️' },
  { key: 'regulation', label: '规范', icon: '📋' },
];

const KnowledgeScreen: React.FC = () => {
  const { colors } = useTheme();
  const navigation = useNavigation<NavigationProp>();
  const {
    articles,
    loading,
    refreshing,
    error,
    searchQuery,
    activeCategory,
    setSearchQuery,
    setActiveCategory,
    fetchArticles,
  } = useKnowledge();

  const handleArticlePress = (article: KnowledgeArticle) => {
    navigation.navigate('KnowledgeDetail', { articleId: article.id });
  };

  const renderArticleItem = ({ item }: { item: KnowledgeArticle }) => (
    <TouchableOpacity
      testID={`knowledge-card-${item.id}`}
      style={[styles.articleCard, { backgroundColor: colors.cardBg }]}
      onPress={() => handleArticlePress(item)}
      activeOpacity={0.7}
     accessibilityRole="button">
      <View style={styles.articleHeader}>
        <Text style={[styles.articleTitle, { color: colors.textPrimary }]} numberOfLines={1}>
          {item.title}
        </Text>
        <View style={[styles.categoryBadge, { backgroundColor: colors.infoBg }]}>
          <Text style={[styles.categoryText, { color: colors.info }]}>
            {CATEGORIES.find((c) => c.key === item.category)?.label || item.category}
          </Text>
        </View>
      </View>
      <Text style={[styles.articleSummary, { color: colors.textSecondary }]} numberOfLines={2}>
        {item.summary || '暂无摘要'}
      </Text>
      <View style={[styles.articleFooter, { borderTopColor: colors.divider }]}>
        <Text style={[styles.articleMeta, { color: colors.textSecondary }]}>
          {item.authorName} · {item.viewCount}次浏览
        </Text>
        <Text style={[styles.articleDate, { color: colors.textMuted }]}>
          {new Date(item.createdAt).toLocaleDateString('zh-CN')}
        </Text>
      </View>
    </TouchableOpacity>
  );

  if (loading && articles.length === 0) {
    return <LoadingSpinner text="加载知识库..." />;
  }

  return (
    <View style={[styles.container, { backgroundColor: colors.pageBg }]}>
      {/* 搜索栏 */}
      <View style={[styles.searchContainer, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>
        <TextInput
          testID="knowledge-search-input"
          style={[styles.searchInput, { backgroundColor: colors.pageBg, color: colors.textPrimary }]}
          placeholder="搜索知识库..."
          placeholderTextColor={colors.textSecondary}
          value={searchQuery}
          onChangeText={setSearchQuery}
          clearButtonMode="while-editing"
        />
      </View>

      {/* 分类筛选 */}
      <View style={[styles.categoryContainer, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>
        {CATEGORIES.map((cat) => (
          <TouchableOpacity
            key={cat.key}
            style={[
              styles.categoryBtn,
              activeCategory === cat.key && styles.categoryBtnActive,
            ]}
            onPress={() => setActiveCategory(cat.key)}
           accessibilityRole="button">
            <Text style={styles.categoryIcon}>{cat.icon}</Text>
            <Text
              style={[
                styles.categoryLabel,
                { color: colors.textSecondary },
                activeCategory === cat.key && { color: colors.primary, fontWeight: '600' },
              ]}
            >
              {cat.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {error && articles.length === 0 ? (
        <EmptyState
          icon="⚠️"
          title="加载失败"
          message={error}
          actionLabel="重新加载"
          onAction={() => fetchArticles()}
        />
      ) : (
        <FlatList
          testID="knowledge-list"
          data={articles}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderArticleItem}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => fetchArticles(true)}
              colors={[colors.primary]}
              tintColor={colors.primary}
            />
          }
          ListEmptyComponent={
            <EmptyState
              icon="📚"
              title={searchQuery ? '未找到文章' : '暂无文章'}
              message={
                searchQuery
                  ? `未找到包含"${searchQuery}"的文章`
                  : '当前分类下暂无知识库文章'
              }
            />
          }
        />
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  searchContainer: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderBottomWidth: 1,
  },
  searchInput: {
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
  },
  categoryContainer: {
    flexDirection: 'row',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderBottomWidth: 1,
  },
  categoryBtn: {
    alignItems: 'center',
    marginRight: 16,
    paddingHorizontal: 4,
  },
  categoryBtnActive: {
    opacity: 1,
  },
  categoryIcon: {
    fontSize: 18,
    marginBottom: 2,
  },
  categoryLabel: {
    fontSize: 11,
    fontWeight: '500',
  },
  listContent: {
    padding: 16,
    paddingBottom: 32,
  },
  articleCard: {
    borderRadius: 12,
    padding: 16,
    marginBottom: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 4,
    elevation: 2,
  },
  articleHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  articleTitle: {
    fontSize: 16,
    fontWeight: '600',
    flex: 1,
    marginRight: 8,
  },
  categoryBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
  },
  categoryText: {
    fontSize: 11,
    fontWeight: '500',
  },
  articleSummary: {
    fontSize: 13,
    lineHeight: 18,
    marginBottom: 10,
  },
  articleFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 8,
    borderTopWidth: 1,
  },
  articleMeta: {
    fontSize: 12,
  },
  articleDate: {
    fontSize: 12,
  },
});

export default KnowledgeScreen;
