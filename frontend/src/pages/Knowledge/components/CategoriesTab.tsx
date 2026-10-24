/**
 * 天链 V3 - 知识库：分类管理 Tab
 */
import React from 'react';
import {
  Card, Space, Button, Empty, List, Modal, Input, InputNumber, Popconfirm,
} from 'antd';
import {
  FolderOutlined, PlusOutlined, EditOutlined, DeleteOutlined,
} from '@ant-design/icons';
import type { KnowledgeBase } from '../hooks/useKnowledgeBase';

const CategoriesTab: React.FC<{ kb: KnowledgeBase }> = ({ kb }) => {
  const {
    categoryItems, catEditVisible, setCatEditVisible,
    editingCategory, setEditingCategory,
    newCatName, setNewCatName, newCatIcon, setNewCatIcon,
    newCatDesc, setNewCatDesc, newCatSort, setNewCatSort, catSaving,
    handleCreateCategory, handleUpdateCategory, handleDeleteCategory,
    openEditCategory, openCreateCategory,
  } = kb;

  return (
    <Card
      title={
        <Space>
          <FolderOutlined />
          <span>分类管理</span>
        </Space>
      }
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreateCategory}>
          添加分类
        </Button>
      }
    >
      {categoryItems.length === 0 ? (
        <Empty description="暂无分类，点击上方按钮添加" />
      ) : (
        <List
          dataSource={categoryItems}
          renderItem={(item) => (
            <List.Item
              key={item.id}
              actions={[
                <a key="edit" onClick={() => openEditCategory(item)}>
                  <EditOutlined /> 编辑
                </a>,
                <Popconfirm
                  key="delete"
                  title={`确认删除分类"${item.name}"？`}
                  description={item.article_count > 0 ? `该分类下有 ${item.article_count} 篇文章，无法删除` : undefined}
                  onConfirm={() => handleDeleteCategory(item.id)}
                  okText="删除"
                  cancelText="取消"
                  disabled={item.article_count > 0}
                >
                  <a style={{ color: item.article_count > 0 ? '#ccc' : '#ea4335' }}>
                    <DeleteOutlined /> 删除
                  </a>
                </Popconfirm>,
              ]}
            >
              <List.Item.Meta
                avatar={<span style={{ fontSize: 24 }}>{item.icon || '📁'}</span>}
                title={<strong>{item.name}</strong>}
                description={
                  <Space split="|">
                    <span>{item.description || '无描述'}</span>
                    <span>排序: {item.sort_order}</span>
                    <span>文章数: {item.article_count}</span>
                  </Space>
                }
              />
            </List.Item>
          )}
        />
      )}

      {/* 分类编辑/创建弹窗 */}
      <Modal
        title={editingCategory ? '编辑分类' : '添加分类'}
        open={catEditVisible}
        onOk={editingCategory ? handleUpdateCategory : handleCreateCategory}
        onCancel={() => { setCatEditVisible(false); setEditingCategory(null); }}
        confirmLoading={catSaving}
        okText={editingCategory ? '更新' : '创建'}
        cancelText="取消"
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <div style={{ marginBottom: 4, fontWeight: 500 }}>分类名称 *</div>
            <Input
              value={newCatName}
              onChange={e => setNewCatName(e.target.value)}
              placeholder="例如：维修指南、故障诊断"
            />
          </div>
          <div>
            <div style={{ marginBottom: 4, fontWeight: 500 }}>图标（Emoji）</div>
            <Input
              value={newCatIcon}
              onChange={e => setNewCatIcon(e.target.value)}
              placeholder="例如：🔧📚⚡"
            />
          </div>
          <div>
            <div style={{ marginBottom: 4, fontWeight: 500 }}>描述</div>
            <Input
              value={newCatDesc}
              onChange={e => setNewCatDesc(e.target.value)}
              placeholder="分类描述"
            />
          </div>
          <div>
            <div style={{ marginBottom: 4, fontWeight: 500 }}>排序</div>
            <InputNumber
              value={newCatSort}
              onChange={v => setNewCatSort(v || 0)}
              min={0}
              style={{ width: '100%' }}
            />
          </div>
        </Space>
      </Modal>
    </Card>
  );
};

export default CategoriesTab;
