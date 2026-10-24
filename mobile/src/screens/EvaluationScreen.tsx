import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  RefreshControl,
  ActivityIndicator,
  TouchableOpacity,
} from 'react-native';
import { useOffline } from '../store/OfflineContext';
import { evaluationApi } from '../services/api';
import { cache } from '../services/cache';

interface TeamRating {
  responseSpeed: number;
  repairQuality: number;
  serviceAttitude: number;
  overall: number;
}

interface EngineerEvaluation {
  id: string;
  engineerId: string;
  engineerName: string;
  avatar?: string;
  stationName: string;
  rating: number;
  commentCount: number;
  latestComment?: string;
  latestCommentTime?: string;
}

interface EvaluationData {
  teamRating: TeamRating;
  engineerEvaluations: EngineerEvaluation[];
}

const EvaluationScreen = () => {
  const [data, setData] = useState<EvaluationData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const { isConnected, triggerSync, getCachedData } = useOffline();

  const loadData = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    try {
      if (isConnected) {
        const response = await evaluationApi.getOverview();
        const evaluationData = response.data;
        setData(evaluationData);

        // 缓存数据
        await cache.set('evaluation_overview', evaluationData);
      } else {
        // 离线模式
        const cachedData = await getCachedData<EvaluationData>('evaluation_overview');
        if (cachedData) {
          setData(cachedData);
        }
      }
    } catch (error: any) {
      console.error('[Evaluation] Load error:', error.message);
      // 尝试从缓存加载
      const cachedData = await getCachedData<EvaluationData>('evaluation_overview');
      if (cachedData) {
        setData(cachedData);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [isConnected, getCachedData]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRefresh = async () => {
    if (isConnected) {
      await triggerSync();
      await loadData(true);
    }
  };

  const renderRatingStars = (rating: number) => {
    return (
      <View style={styles.starsContainer}>
        {[1, 2, 3, 4, 5].map((star) => (
          <Text key={star} style={[styles.star, star <= Math.round(rating) ? styles.starActive : null]}>
            ★
          </Text>
        ))}
        <Text style={styles.ratingNumber}>{rating.toFixed(1)}</Text>
      </View>
    );
  };

  const getRatingColor = (rating: number) => {
    if (rating >= 4) return '#52c41a';
    if (rating >= 3) return '#faad14';
    return '#ff4d4f';
  };

  const renderEngineerItem = ({ item }: { item: EngineerEvaluation }) => (
    <TouchableOpacity style={styles.engineerItem}>
      <View style={styles.engineerLeft}>
        <View style={styles.avatarPlaceholder}>
          <Text style={styles.avatarText}>
            {item.engineerName.charAt(0)}
          </Text>
        </View>
        <View style={styles.engineerInfo}>
          <Text style={styles.engineerName}>{item.engineerName}</Text>
          <Text style={styles.stationName}>{item.stationName}</Text>
          {item.latestComment && (
            <Text style={styles.latestComment} numberOfLines={2}>
              "{item.latestComment}"
            </Text>
          )}
        </View>
      </View>
      <View style={styles.engineerRight}>
        {renderRatingStars(item.rating)}
        <Text style={styles.commentCount}>{item.commentCount} 条评价</Text>
        {item.latestCommentTime && (
          <Text style={styles.commentTime}>{item.latestCommentTime}</Text>
        )}
      </View>
    </TouchableOpacity>
  );

  if (loading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#1890ff" />
        <Text style={styles.loadingText}>加载评价数据...</Text>
      </View>
    );
  }

  if (!data) {
    return (
      <View style={styles.centerContainer}>
        <Text style={styles.emptyIcon}>📭</Text>
        <Text style={styles.emptyText}>暂无数据</Text>
        {!isConnected && <Text style={styles.emptySubtext}>请连接网络后刷新</Text>}
      </View>
    );
  }

  return (
    <FlatList
      data={data.engineerEvaluations}
      renderItem={renderEngineerItem}
      keyExtractor={(item) => item.id}
      contentContainerStyle={styles.container}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          onRefresh={handleRefresh}
          enabled={isConnected}
          colors={['#1890ff']}
        />
      }
      ListHeaderComponent={
        <>
          {/* 团队评分 */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>运维团队评分</Text>
            <View style={styles.teamRatingCard}>
              <View style={styles.overallRating}>
                <Text style={[styles.overallScore, { color: getRatingColor(data.teamRating.overall) }]}>
                  {data.teamRating.overall.toFixed(1)}
                </Text>
                <Text style={styles.overallLabel}>综合评分</Text>
                {renderRatingStars(data.teamRating.overall)}
              </View>
              <View style={styles.ratingBreakdown}>
                <View style={styles.ratingRow}>
                  <Text style={styles.ratingLabel}>响应速度</Text>
                  {renderRatingStars(data.teamRating.responseSpeed)}
                </View>
                <View style={styles.ratingRow}>
                  <Text style={styles.ratingLabel}>维修质量</Text>
                  {renderRatingStars(data.teamRating.repairQuality)}
                </View>
                <View style={styles.ratingRow}>
                  <Text style={styles.ratingLabel}>服务态度</Text>
                  {renderRatingStars(data.teamRating.serviceAttitude)}
                </View>
              </View>
            </View>
          </View>

          {/* 工程师评价列表 */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>工程师评价</Text>
          </View>
        </>
      }
      ListEmptyComponent={
        !isConnected && data.engineerEvaluations.length === 0 ? (
          <View style={styles.emptyCard}>
            <Text style={styles.emptyText}>离线且无缓存数据</Text>
            <Text style={styles.emptySubtext}>请连接网络后刷新</Text>
          </View>
        ) : (
          <View style={styles.emptyCard}>
            <Text style={styles.emptyText}>暂无工程师评价</Text>
          </View>
        )
      }
    />
  );
};

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    backgroundColor: '#f5f5f5',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 32,
  },
  section: {
    padding: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#333',
    marginBottom: 12,
  },
  teamRatingCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 20,
  },
  overallRating: {
    alignItems: 'center',
    marginBottom: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#f0f0f0',
    paddingBottom: 16,
  },
  overallScore: {
    fontSize: 48,
    fontWeight: 'bold',
  },
  overallLabel: {
    fontSize: 14,
    color: '#666',
    marginTop: 8,
  },
  ratingBreakdown: {
    marginTop: 12,
  },
  ratingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
  },
  ratingLabel: {
    fontSize: 14,
    color: '#666',
    flex: 1,
  },
  starsContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  star: {
    fontSize: 16,
    color: '#d9d9d9',
    marginRight: 2,
  },
  starActive: {
    color: '#faad14',
  },
  ratingNumber: {
    fontSize: 14,
    color: '#666',
    marginLeft: 8,
    fontWeight: '500',
  },
  engineerItem: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  engineerLeft: {
    flexDirection: 'row',
    flex: 1,
  },
  avatarPlaceholder: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: '#1890ff',
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#fff',
  },
  engineerInfo: {
    marginLeft: 12,
    flex: 1,
  },
  engineerName: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#333',
    marginBottom: 4,
  },
  stationName: {
    fontSize: 12,
    color: '#666',
    marginBottom: 8,
  },
  latestComment: {
    fontSize: 14,
    color: '#999',
    fontStyle: 'italic',
    marginTop: 4,
  },
  engineerRight: {
    alignItems: 'flex-end',
  },
  commentCount: {
    fontSize: 12,
    color: '#666',
    marginTop: 8,
  },
  commentTime: {
    fontSize: 12,
    color: '#999',
    marginTop: 4,
  },
  emptyCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 32,
    alignItems: 'center',
    margin: 16,
  },
  loadingText: {
    marginTop: 16,
    color: '#999',
    fontSize: 14,
  },
  emptyIcon: {
    fontSize: 48,
    marginBottom: 16,
  },
  emptyText: {
    fontSize: 16,
    color: '#999',
    marginBottom: 8,
  },
  emptySubtext: {
    fontSize: 14,
    color: '#ccc',
  },
});

export default EvaluationScreen;