/**
 * 天链 V3 - 知识库：FAQ 数据 hook
 */
import { useState } from 'react';
import { message } from 'antd';
import { faqAPI } from '../../../api/knowledge';
import type { FAQItem } from '../types';

export function useFaq() {
  const [faqList, setFaqList] = useState<FAQItem[]>([]);
  const [faqLoading, setFaqLoading] = useState(false);
  const [faqCategory, setFaqCategory] = useState('');
  const [faqSearch, setFaqSearch] = useState('');
  const [faqCategories, setFaqCategories] = useState<string[]>([]);
  const [activeFaqPanels, setActiveFaqPanels] = useState<string[]>([]);
  const [faqCreateVisible, setFaqCreateVisible] = useState(false);
  const [newFaqQuestion, setNewFaqQuestion] = useState('');
  const [newFaqAnswer, setNewFaqAnswer] = useState('');
  const [newFaqCategory, setNewFaqCategory] = useState('设备类');
  const [faqCreateLoading, setFaqCreateLoading] = useState(false);

  const fetchFAQCategories = async () => {
    try {
      const res: any = await faqAPI.categories();
      if (Array.isArray(res.data)) {
        setFaqCategories(res.data);
      }
    } catch {
      // 静默处理：FAQ 分类加载失败不阻塞列表
    }
  };

  const fetchFAQList = async () => {
    setFaqLoading(true);
    try {
      const params: Record<string, string> = {};
      if (faqCategory) params.category = faqCategory;
      if (faqSearch) params.q = faqSearch;
      const res: any = await faqAPI.list(params);
      const items = Array.isArray(res.data) ? res.data : [];
      setFaqList(items);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '未知错误';
      message.error('FAQ加载失败：' + msg);
    } finally {
      setFaqLoading(false);
    }
  };

  const handleFAQLike = async (faqId: number) => {
    try {
      const res: any = await faqAPI.markHelpful(faqId);
      message.success('感谢反馈！');
      fetchFAQList();
    } catch {
      // 静默处理：标记有用失败不影响列表浏览
    }
  };

  const handleFaqCreate = async () => {
    if (!newFaqQuestion.trim() || !newFaqAnswer.trim()) {
      message.warning('请输入问题和答案');
      return;
    }
    setFaqCreateLoading(true);
    try {
      await faqAPI.create({
        question: newFaqQuestion,
        answer: newFaqAnswer,
        category: newFaqCategory,
      });
      message.success('FAQ创建成功');
      setFaqCreateVisible(false);
      setNewFaqQuestion('');
      setNewFaqAnswer('');
      setNewFaqCategory('设备类');
      fetchFAQList();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '未知错误';
      message.error('创建失败：' + msg);
    } finally {
      setFaqCreateLoading(false);
    }
  };

  const toggleAllFaqPanels = (expand: boolean) => {
    if (expand) {
      setActiveFaqPanels(faqList.map((_, i) => String(i)));
    } else {
      setActiveFaqPanels([]);
    }
  };

  return {
    faqList, faqLoading, faqCategory, setFaqCategory,
    faqSearch, setFaqSearch, faqCategories,
    activeFaqPanels, setActiveFaqPanels,
    faqCreateVisible, setFaqCreateVisible,
    newFaqQuestion, setNewFaqQuestion,
    newFaqAnswer, setNewFaqAnswer,
    newFaqCategory, setNewFaqCategory, faqCreateLoading,
    fetchFAQCategories, fetchFAQList, handleFAQLike, handleFaqCreate,
    toggleAllFaqPanels,
  };
}

export type FaqState = ReturnType<typeof useFaq>;
