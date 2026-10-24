/**
 * 天链 V3 - 知识库：自动文档生成数据 hook
 */
import { useState } from 'react';
import { message } from 'antd';
import { docAPI } from '../../../api/knowledge';

export function useDocGen() {
  const [docGenVisible, setDocGenVisible] = useState(false);
  const [docType, setDocType] = useState<'manual' | 'checklist' | 'document'>('manual');
  const [docDeviceType, setDocDeviceType] = useState('');
  const [docFaultCode, setDocFaultCode] = useState('');
  const [docTitle, setDocTitle] = useState('');
  const [docResult, setDocResult] = useState('');
  const [docGenLoading, setDocGenLoading] = useState(false);

  const handleGenerateDoc = async () => {
    setDocGenLoading(true);
    setDocResult('');
    try {
      const payload: any = { doc_type: docType };
      if (docType === 'manual' && docDeviceType) payload.device_type = docDeviceType;
      if (docFaultCode) payload.fault_code = docFaultCode;
      if (docTitle) payload.title = docTitle;
      const res: any = await docAPI.generateDoc(payload);
      if (res.data?.content) {
        setDocResult(res.data.content);
        message.success('文档生成成功');
      } else {
        message.error('生成结果为空');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : '未知错误';
      message.error('文档生成失败：' + msg);
    } finally {
      setDocGenLoading(false);
    }
  };

  return {
    docGenVisible, setDocGenVisible, docType, setDocType,
    docDeviceType, setDocDeviceType, docFaultCode, setDocFaultCode,
    docTitle, setDocTitle, docResult, docGenLoading, handleGenerateDoc,
  };
}

export type DocGenState = ReturnType<typeof useDocGen>;
