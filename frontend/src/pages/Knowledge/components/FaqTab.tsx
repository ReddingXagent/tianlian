/**
 * 天链 V3 - 知识库：FAQ 问答 Tab
 */
import React from 'react';
import {
  Card, Space, Button, Input, Select, Empty, Tag, Collapse, Spin, Modal,
} from 'antd';
import {
  QuestionCircleOutlined, ExpandAltOutlined, CompressOutlined,
  PlusOutlined, SearchOutlined, EyeOutlined, LikeOutlined,
} from '@ant-design/icons';
import Highlight from './Highlight';
import { FAQ_CATEGORIES } from '../constants';
import type { FaqState } from '../hooks/useFaq';

const { Panel } = Collapse;
const { TextArea } = Input;

const FaqTab: React.FC<{ faq: FaqState }> = ({ faq }) => {
  const {
    faqList, faqLoading, faqCategory, setFaqCategory,
    faqSearch, setFaqSearch,
    activeFaqPanels, setActiveFaqPanels,
    faqCreateVisible, setFaqCreateVisible,
    newFaqQuestion, setNewFaqQuestion,
    newFaqAnswer, setNewFaqAnswer,
    newFaqCategory, setNewFaqCategory, faqCreateLoading,
    fetchFAQList, handleFAQLike, handleFaqCreate, toggleAllFaqPanels,
  } = faq;

  return (
    <Card
      title={
        <Space>
          <QuestionCircleOutlined />
          <span>FAQ 常见问题</span>
        </Space>
      }
      extra={
        <Space>
          <Button icon={<ExpandAltOutlined />} onClick={() => toggleAllFaqPanels(true)}>展开全部</Button>
          <Button icon={<CompressOutlined />} onClick={() => toggleAllFaqPanels(false)}>收起全部</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setFaqCreateVisible(true)}>
            添加FAQ
          </Button>
        </Space>
      }
    >
      {/* FAQ 搜索和分类筛选 */}
      <Space style={{ marginBottom: 24, width: '100%' }} size="large">
        <Input.Search
          placeholder="搜索FAQ问题或答案"
          value={faqSearch}
          onChange={(e) => setFaqSearch(e.target.value)}
          onSearch={fetchFAQList}
          enterButton={<SearchOutlined />}
          style={{ width: 300 }}
        />
        <Select
          placeholder="按分类筛选"
          value={faqCategory}
          onChange={(value) => { setFaqCategory(value); setTimeout(() => fetchFAQList(), 0); }}
          allowClear
          style={{ width: 200 }}
        >
          {FAQ_CATEGORIES.filter(c => c.value).map(c => (
            <Select.Option key={c.value} value={c.value}>{c.label}</Select.Option>
          ))}
        </Select>
        <Button onClick={fetchFAQList}>刷新</Button>
      </Space>

      {/* FAQ 分类标签 */}
      <Space style={{ marginBottom: 16 }} wrap>
        {FAQ_CATEGORIES.map(c => (
          <Tag
            key={c.value}
            color={faqCategory === c.value ? '#ff5a36' : 'default'}
            style={{ cursor: 'pointer', padding: '2px 12px' }}
            onClick={() => { setFaqCategory(c.value); setTimeout(() => fetchFAQList(), 0); }}
          >
            {c.label || '全部'}
          </Tag>
        ))}
      </Space>

      {faqLoading ? (
        <div style={{ padding: 40, textAlign: 'center' }}><Spin /></div>
      ) : faqList.length === 0 ? (
        <Empty description="暂无FAQ数据" />
      ) : (
        <Collapse
          activeKey={activeFaqPanels}
          onChange={(keys) => setActiveFaqPanels(keys as string[])}
          expandIconPosition="right"
        >
          {faqList.map((faqItem, index) => (
            <Panel
              key={String(index)}
              header={
                <Space>
                  <QuestionCircleOutlined style={{ color: '#ff5a36' }} />
                  <strong><Highlight text={faqItem.question} keyword={faqSearch} /></strong>
                  <Tag color="default">{faqItem.category}</Tag>
                  {faqItem.tags && faqItem.tags.split(',').filter(t => t.trim()).slice(0, 2).map(t => (
                    <Tag key={t} color="geekblue" style={{ fontSize: 11 }}>{t.trim()}</Tag>
                  ))}
                </Space>
              }
              extra={
                <Space size="small" style={{ cursor: 'default' }} onClick={e => e.stopPropagation()}>
                  <span style={{ fontSize: 12, color: '#999' }}><EyeOutlined /> {faqItem.views}</span>
                  <Button
                    type="text"
                    size="small"
                    icon={<LikeOutlined />}
                    onClick={(e) => { e.stopPropagation(); handleFAQLike(faqItem.id); }}
                  >
                    {faqItem.helpful_count}
                  </Button>
                </Space>
              }
            >
              <div style={{ lineHeight: 1.8, whiteSpace: 'pre-wrap', color: '#555' }}>
                <Highlight text={faqItem.answer} keyword={faqSearch} />
              </div>
            </Panel>
          ))}
        </Collapse>
      )}

      {/* 新建FAQ弹窗 */}
      <Modal
        title="添加FAQ"
        open={faqCreateVisible}
        onOk={handleFaqCreate}
        onCancel={() => setFaqCreateVisible(false)}
        confirmLoading={faqCreateLoading}
        okText="创建"
        cancelText="取消"
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <div>
            <div style={{ marginBottom: 4, fontWeight: 500 }}>分类</div>
            <Select value={newFaqCategory} onChange={setNewFaqCategory} style={{ width: '100%' }}>
              {FAQ_CATEGORIES.filter(c => c.value).map(c => (
                <Select.Option key={c.value} value={c.value}>{c.label}</Select.Option>
              ))}
            </Select>
          </div>
          <div>
            <div style={{ marginBottom: 4, fontWeight: 500 }}>问题</div>
            <Input
              value={newFaqQuestion}
              onChange={e => setNewFaqQuestion(e.target.value)}
              placeholder="请输入常见问题"
            />
          </div>
          <div>
            <div style={{ marginBottom: 4, fontWeight: 500 }}>答案</div>
            <TextArea
              value={newFaqAnswer}
              onChange={e => setNewFaqAnswer(e.target.value)}
              placeholder="请输入答案"
              rows={4}
            />
          </div>
        </Space>
      </Modal>
    </Card>
  );
};

export default FaqTab;
