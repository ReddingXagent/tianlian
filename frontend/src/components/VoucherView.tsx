/**
 * 凭证鉴权查看 (卡 554bb70b)
 *
 * /uploads 静态裸挂已移除, 凭证文件改经鉴权端点
 * GET /api/v1/fleet/recharge/{id}/voucher 下发 (带 Bearer + X-Team-Id)。
 * <img>/<a> 无法带 Authorization 头, 故用 blob 拉取后转 objectURL。
 */
import React, { useEffect, useState } from 'react';
import { Image } from 'antd';
import { FileOutlined } from '@ant-design/icons';
import api from '../api';

interface VoucherViewProps {
  record: { id: number; voucher_url?: string };
  /** 列表内嵌缩略图 (图片类凭证); false 时渲染"查看"链接 */
  thumbnail?: boolean;
}

const VoucherView: React.FC<VoucherViewProps> = ({ record, thumbnail = false }) => {
  const [objectUrl, setObjectUrl] = useState('');

  useEffect(() => {
    let url = '';
    let cancelled = false;
    api
      .get(`/fleet/recharge/${record.id}/voucher`, { responseType: 'blob' })
      .then((res) => {
        if (cancelled) return;
        url = URL.createObjectURL(res.data as Blob);
        setObjectUrl(url);
      })
      .catch(() => {
        /* 加载失败保持占位图标 */
      });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [record.id]);

  if (!record.voucher_url) return '-';
  if (!objectUrl) return <FileOutlined />;
  const isImage = /\.(jpg|jpeg|png|webp)$/i.test(record.voucher_url);
  if (thumbnail && isImage) {
    return (
      <Image
        src={objectUrl}
        width={40}
        height={40}
        style={{ objectFit: 'cover', borderRadius: 4 }}
      />
    );
  }
  return (
    <a href={objectUrl} target="_blank" rel="noopener noreferrer">
      <FileOutlined /> 查看
    </a>
  );
};

export default VoucherView;
