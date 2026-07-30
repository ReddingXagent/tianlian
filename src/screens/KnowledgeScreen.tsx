import React, { useEffect, useState, useCallback } from 'react';
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
import { knowledgeApi } from '../services/api';
import { KnowledgeArticle, RootStackParamList } from '../types';
import LoadingSpinner from '../components/LoadingSpinner';
import EmptyState from '../components/EmptyState';

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
  const navigation = useNavigation<NavigationProp>();
  const [articles, setArticles] = useState<KnowledgeArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('all');
  const [searchTimeout, setSearchTimeout] = useState<ReturnType<typeof setTimeout> | null>(null);

  const fetchArticles = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      let response;
      if (searchQuery.trim()) {
        response = await knowledgeApi.search(searchQuery.trim());
        setArticles(response.data);
      } else {
        response = await knowledgeApi.getList({
          category: activeCategory !== 'all' ? activeCategory : undefined,
          pageSize: 50,
        });
        setArticles(response.data.items);
      }
    } catch {
      setError('加载知识库失败，请下拉刷新重试');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [searchQuery, activeCategory]);

  useEffect(() => {
    fetchArticles();
  }, [activeCategory]);

  const handleSearch = (text: string) => {
    setSearchQuery(text);
    if (searchTimeout) clearTimeout(searchTimeout);
    const timeout = setTimeout(() => {
      fetchArticles();
    }, 500);
    setSearchTimeout(timeout);
  };

  const handleArticlePress = (article: KnowledgeArticle) => {
    navigation.navigate('KnowledgeDetail', { articleId: article.id });
  };

  const renderArticleItem = ({ item }: { item: KnowledgeArticle }) => (
    <TouchableOpacity
      style={styles.articleCard}
      onPress={() => handleArticlePress(item)}
      activeOpacity={0.7}
    >
      <View style={styles.articleHeader}>
        <Text style={styles.articleTitle} numberOfLines={1}>
          {item.title}
        </Text>
        <View style={styles.categoryBadge}>
          <Text style={styles.categoryText}>
            {CATEGORIES.find((c) => c.key === item.category)?.label || item.category}
          </Text>
        </View>
      </View>
      <Text style={styles.articleSummary} numberOfLines={2}>
        {item.summary || '暂无摘要'}
      </Text>
      <View style={styles.articleFooter}>
        <Text style={styles.articleMeta}>
          {item.authorName} · {item.viewCount}次浏览
        </Text>
        <Text style={styles.articleDate}>
          {new Date(item.createdAt).toLocaleDateString('zh-CN')}
        </Text>
      </View>
    </TouchableOpacity>
  );

  if (loading && articles.length === 0) {
    return <LoadingSpinner text="加载知识库..." />;
  }

  return (
    <View style={styles.container}>
      {/* 搜索栏 */}
      <View style={styles.searchContainer}>
        <TextInput
          style={styles.searchInput}
          placeholder="搜索知识库..."
          placeholderTextColor="#999"
          value={searchQuery}
          onChangeText={handleSearch}
          clearButtonMode="while-editing"
        />
      </View>

      {/* 分类筛选 */}
      <View style={styles.categoryContainer}>
        {CATEGORIES.map((cat) => (
          <TouchableOpacity
            key={cat.key}
            style={[
              styles.categoryBtn,
              activeCategory === cat.key && styles.categoryBtnActive,
            ]}
            onPress={() => {
              setSearchQuery('');
              setActiveCategory(cat.key);
            }}
          >
            <Text style={styles.categoryIcon}>{cat.icon}</Text>
            <Text
              style={[
                styles.categoryLabel,
                activeCategory === cat.key && styles.categoryLabelActive,
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
          data={articles}
          keyExtractor={(item) => String(item.id)}
          renderItem={renderArticleItem}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => fetchArticles(true)}
              colors={['#1a73e8']}
              tintColor="#1a73e8"
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
    backgroundColor: '#f5f6fa',
  },
  searchContainer: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: '#fff',
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  searchInput: {
    backgroundColor: '#f5f6fa',
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
    fontSize: 15,
    color: '#333',
  },
  categoryContainer: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
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
    color: '#999',
    fontWeight: '500',
  },
  categoryLabelActive: {
    color: '#1a73e8',
    fontWeight: '600',
  },
  listContent: {
    padding: 16,
    paddingBottom: 32,
  },
  articleCard: {
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
  articleHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 6,
  },
  articleTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#333',
    flex: 1,
    marginRight: 8,
  },
  categoryBadge: {
    backgroundColor: '#e3f2fd',
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
  },
  categoryText: {
    fontSize: 11,
    color: '#1565c0',
    fontWeight: '500',
  },
  articleSummary: {
    fontSize: 13,
    color: '#666',
    lineHeight: 18,
    marginBottom: 10,
  },
  articleFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 8,
    borderTopWidth: 1,
    borderTopColor: '#f0f0f0',
  },
  articleMeta: {
    fontSize: 12,
    color: '#999',
  },
  articleDate: {
    fontSize: 12,
    color: '#bbb',
  },
});

export default KnowledgeScreen;
