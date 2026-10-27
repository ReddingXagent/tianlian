import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  TextInput,
  RefreshControl,
  Alert,
} from 'react-native';
import { CompositeScreenProps } from '@react-navigation/native';
import { BottomTabScreenProps } from '@react-navigation/bottom-tabs';
import { NativeStackScreenProps } from '@react-navigation/native-stack';
import { MainTabParamList, RootStackParamList } from '../navigation/AppNavigator';
import { knowledgeApi } from '../services/api';
import type { KnowledgeItem, KnowledgeCategory } from '../types';

type Props = CompositeScreenProps<
  BottomTabScreenProps<MainTabParamList, 'Knowledge'>,
  NativeStackScreenProps<RootStackParamList>
>;

const KnowledgeScreen: React.FC<Props> = () => {
  const [activeTab, setActiveTab] = useState<KnowledgeCategory>('fault_case');
  const [searchKeyword, setSearchKeyword] = useState('');
  const [faultCases, setFaultCases] = useState<KnowledgeItem[]>([]);
  const [manuals, setManuals] = useState<KnowledgeItem[]>([]);
  const [loading, setLoading] = useState(false);

  // 加载知识库数据
  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const [casesData, manualsData] = await Promise.all([
        knowledgeApi.getFaultCases(searchKeyword),
        knowledgeApi.getManuals(searchKeyword),
      ]);
      setFaultCases(casesData);
      setManuals(manualsData);
    } catch (error: any) {
      console.error('Load knowledge error:', error);
      // 使用模拟数据
      setFaultCases(getMockFaultCases());
      setManuals(getMockManuals());
    } finally {
      setLoading(false);
    }
  }, [searchKeyword]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // 搜索
  const handleSearch = () => {
    loadData();
  };

  // 模拟数据
  const getMockFaultCases = (): KnowledgeItem[] => [
    {
      id: '1',
      category: 'fault_case',
      title: '充电桩充电枪无法连接故障处理',
      content: '故障现象：充电枪插入后无法识别，显示屏无响应...',
      tags: ['充电桩', '充电枪', '通信故障'],
      viewCount: 128,
      createdAt: '2026-05-10',
      updatedAt: '2026-05-12',
    },
    {
      id: '2',
      category: 'fault_case',
      title: '储能柜温度异常告警处理方案',
      content: '故障现象：储能柜温度传感器告警，温度显示异常...',
      tags: ['储能柜', '温度', '传感器'],
      viewCount: 95,
      createdAt: '2026-05-08',
      updatedAt: '2026-05-09',
    },
    {
      id: '3',
      category: 'fault_case',
      title: '光伏逆变器效率下降检修指南',
      content: '故障现象：逆变器转换效率明显下降，发电量降低...',
      tags: ['光伏', '逆变器', '效率'],
      viewCount: 67,
      createdAt: '2026-05-05',
      updatedAt: '2026-05-06',
    },
  ];

  const getMockManuals = (): KnowledgeItem[] => [
    {
      id: '4',
      category: 'manual',
      title: '充电桩设备维护手册 V2.1',
      content: '充电桩日常维护、检修流程、安全注意事项...',
      tags: ['充电桩', '维护手册'],
      viewCount: 234,
      createdAt: '2026-04-15',
      updatedAt: '2026-05-01',
    },
    {
      id: '5',
      category: 'manual',
      title: '储能系统操作手册',
      content: '储能柜启动、停止、参数设置、故障排查...',
      tags: ['储能柜', '操作手册'],
      viewCount: 156,
      createdAt: '2026-04-10',
      updatedAt: '2026-04-20',
    },
    {
      id: '6',
      category: 'manual',
      title: '光伏逆变器技术规格书',
      content: '逆变器技术参数、安装要求、调试方法...',
      tags: ['光伏', '逆变器', '规格书'],
      viewCount: 89,
      createdAt: '2026-04-05',
      updatedAt: '2026-04-15',
    },
  ];

  // 知识条目卡片
  const KnowledgeCard = ({ item }: { item: KnowledgeItem }) => (
    <TouchableOpacity style={styles.card} onPress={() => Alert.alert('提示', '详情页面开发中')}>
      <View style={styles.cardHeader}>
        <Text style={styles.cardTitle}>{item.title}</Text>
        <Text style={styles.cardViews}>👁 {item.viewCount}</Text>
      </View>
      <Text style={styles.cardContent} numberOfLines={2}>
        {item.content}
      </Text>
      <View style={styles.cardFooter}>
        {item.tags?.map((tag) => (
          <View key={tag} style={styles.tag}>
            <Text style={styles.tagText}>{tag}</Text>
          </View>
        ))}
      </View>
      <Text style={styles.cardDate}>更新时间: {item.updatedAt}</Text>
    </TouchableOpacity>
  );

  const currentList = activeTab === 'fault_case' ? faultCases : manuals;

  return (
    <View style={styles.container}>
      {/* 搜索栏 */}
      <View style={styles.searchBar}>
        <TextInput
          style={styles.searchInput}
          placeholder="搜索故障案例、维修手册..."
          value={searchKeyword}
          onChangeText={setSearchKeyword}
          onSubmitEditing={handleSearch}
          placeholderTextColor="#999"
          returnKeyType="search"
        />
        <TouchableOpacity style={styles.searchButton} onPress={handleSearch}>
          <Text style={styles.searchButtonText}>🔍</Text>
        </TouchableOpacity>
      </View>

      {/* Tab切换 */}
      <View style={styles.tabContainer}>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'fault_case' && styles.tabActive]}
          onPress={() => setActiveTab('fault_case')}
        >
          <Text style={[styles.tabText, activeTab === 'fault_case' && styles.tabTextActive]}>
            故障案例 ({faultCases.length})
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, activeTab === 'manual' && styles.tabActive]}
          onPress={() => setActiveTab('manual')}
        >
          <Text style={[styles.tabText, activeTab === 'manual' && styles.tabTextActive]}>
            维修手册 ({manuals.length})
          </Text>
        </TouchableOpacity>
      </View>

      {/* 列表 */}
      <ScrollView
        style={styles.listContainer}
        refreshControl={
          <RefreshControl refreshing={loading} onRefresh={loadData} colors={['#1890ff']} />
        }
      >
        {currentList.length > 0 ? (
          currentList.map((item) => (
            <KnowledgeCard key={item.id} item={item} />
          ))
        ) : (
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyIcon}>📚</Text>
            <Text style={styles.emptyText}>
              {searchKeyword ? '未找到相关内容' : '暂无内容'}
            </Text>
          </View>
        )}
      </ScrollView>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  searchBar: {
    flexDirection: 'row',
    padding: 16,
    paddingBottom: 12,
    backgroundColor: '#fff',
  },
  searchInput: {
    flex: 1,
    height: 40,
    borderWidth: 1,
    borderColor: '#e0e0e0',
    borderRadius: 8,
    paddingHorizontal: 12,
    fontSize: 14,
    backgroundColor: '#fafafa',
  },
  searchButton: {
    width: 40,
    height: 40,
    backgroundColor: '#1890ff',
    borderRadius: 8,
    marginLeft: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },
  searchButtonText: {
    fontSize: 18,
  },
  tabContainer: {
    flexDirection: 'row',
    padding: 16,
    paddingBottom: 12,
    backgroundColor: '#fff',
  },
  tab: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
    borderRadius: 8,
    marginHorizontal: 4,
    backgroundColor: '#f5f5f5',
  },
  tabActive: {
    backgroundColor: '#e6f7ff',
    borderWidth: 1,
    borderColor: '#1890ff',
  },
  tabText: {
    fontSize: 14,
    color: '#666',
  },
  tabTextActive: {
    color: '#1890ff',
    fontWeight: '600',
  },
  listContainer: {
    flex: 1,
    padding: 16,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.05,
    shadowRadius: 8,
    elevation: 2,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#1a1a2e',
    flex: 1,
  },
  cardViews: {
    fontSize: 12,
    color: '#999',
    marginLeft: 12,
  },
  cardContent: {
    fontSize: 14,
    color: '#666',
    lineHeight: 20,
    marginBottom: 12,
  },
  cardFooter: {
    flexDirection: 'row',
    marginBottom: 8,
  },
  tag: {
    backgroundColor: '#f0f0f0',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 4,
    marginRight: 8,
  },
  tagText: {
    fontSize: 12,
    color: '#666',
  },
  cardDate: {
    fontSize: 12,
    color: '#999',
  },
  emptyContainer: {
    padding: 60,
    alignItems: 'center',
  },
  emptyIcon: {
    fontSize: 48,
    marginBottom: 16,
  },
  emptyText: {
    fontSize: 14,
    color: '#999',
  },
});

export default KnowledgeScreen;