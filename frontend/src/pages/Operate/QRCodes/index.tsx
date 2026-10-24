/**
 * 二维码管理 — 充电桩收费二维码 列表 / 批量生成 / 下载
 *
 * 字段契约: backend/app/api/v1/operate/charger_qrcode.py
 *   list        -> { items[], total, page, page_size }
 *   generate    <- { device_ids }  -> { generated, errors, total, failed }
 *   download    GET  /download/{device_id}  -> PNG
 *   batch       POST /batch-download { device_ids } -> ZIP
 *
 * 下载走 axios blob: <a href> 不带 Authorization header, 鉴权接口必须走 axios
 */
import React, { useEffect, useState, useCallback } from 'react';
import {
  Table, Tag, Button, Space, Card, Row, Col, Statistic, message, Popover,
} from 'antd';
import {
  ReloadOutlined, QrcodeOutlined, DownloadOutlined, FileZipOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import { QRCodeSVG } from 'qrcode.react';
import { chargerQRCodeAPI } from '../../../api/operate';

interface QRRow {
  device_id: number;
  device_name: string;
  device_code: string;
  device_type: string;
  station_name: string;
  pile_code: string | null;
  has_qrcode: boolean;
  is_active: boolean;
  print_count: number;
  scan_count: number;
  created_at: string | null;
}

const DEVICE_TYPE_MAP: Record<string, string> = {
  charger_dc: '直流桩',
  charger_ac: '交流桩',
  v2g_charger: 'V2G桩',
};

const QRCodesPage: React.FC = () => {
  const [rows, setRows] = useState<QRRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [generating, setGenerating] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await chargerQRCodeAPI.list({ page, page_size: pageSize });
      setRows((data as any)?.items || []);
      setTotal((data as any)?.total || 0);
    } catch {
      setRows([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => { loadData(); }, [loadData]);

  // blob 触发浏览器下载
  const triggerBlobDownload = (blob: Blob, filename: string) => {
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  };

  const handleGenerate = async () => {
    if (selectedIds.length === 0) {
      message.warning('请先勾选充电桩');
      return;
    }
    setGenerating(true);
    try {
      const { data } = await chargerQRCodeAPI.generate({ device_ids: selectedIds });
      const d = data as { total?: number; failed?: number };
      message.success(`成功生成 ${d?.total ?? 0} 张二维码${d?.failed ? `，失败 ${d.failed}` : ''}`);
      setSelectedIds([]);
      loadData(); // 生成后刷新列表
    } catch {
      message.error('生成二维码失败');
    } finally {
      setGenerating(false);
    }
  };

  const handleDownloadSingle = async (record: QRRow) => {
    try {
      const res = await chargerQRCodeAPI.downloadSingle(record.device_id);
      triggerBlobDownload(res.data as Blob, `qr_${record.pile_code || record.device_id}.png`);
      message.success('已开始下载');
    } catch {
      message.error('下载失败');
    }
  };

  const handleBatchDownload = async () => {
    if (selectedIds.length === 0) {
      message.warning('请先勾选充电桩');
      return;
    }
    try {
      const res = await chargerQRCodeAPI.batchDownload({ device_ids: selectedIds });
      triggerBlobDownload(res.data as Blob, 'charger_qrcodes.zip');
      message.success('已开始下载');
    } catch {
      message.error('批量下载失败');
    }
  };

  const stats = {
    total,
    generated: rows.filter(r => r.has_qrcode).length,
    pending: rows.filter(r => !r.has_qrcode).length,
  };

  const columns = [
    {
      title: '充电桩', dataIndex: 'device_name', key: 'device_name', width: 160,
      render: (v: string, r: QRRow) => (
        <Space>
          <QrcodeOutlined style={{ color: r.has_qrcode ? '#52c41a' : '#bfbfbf' }} />
          <span>{v || '-'}</span>
        </Space>
      ),
    },
    {
      title: '桩编号', dataIndex: 'pile_code', key: 'pile_code', width: 210,
      render: (v: string | null) => v
        ? <Tag color="blue">{v}</Tag>
        : <span style={{ color: '#bfbfbf' }}>未生成</span>,
    },
    { title: '站点', dataIndex: 'station_name', key: 'station_name', width: 140, ellipsis: true,
      render: (v: string) => v || '-' },
    { title: '类型', dataIndex: 'device_type', key: 'device_type', width: 90,
      render: (v: string) => DEVICE_TYPE_MAP[v] || v },
    {
      title: '二维码状态', dataIndex: 'has_qrcode', key: 'has_qrcode', width: 110,
      render: (v: boolean) => v
        ? <Tag color="green" icon={<QrcodeOutlined />}>已生成</Tag>
        : <Tag>未生成</Tag>,
    },
    {
      title: '预览', key: 'preview', width: 80, align: 'center' as const,
      render: (_: unknown, r: QRRow) => (r.has_qrcode && r.pile_code)
        ? (
          <Popover
            trigger="hover"
            placement="right"
            title={`扫码桩编号: ${r.pile_code}`}
            content={<QRCodeSVG value={r.pile_code} size={184} className="qr-preview-large" />}
          >
            <span style={{ cursor: 'pointer', display: 'inline-block', lineHeight: 0 }}>
              <QRCodeSVG value={r.pile_code} size={36} className="qr-preview-thumbnail" />
            </span>
          </Popover>
        )
        : <QrcodeOutlined style={{ fontSize: 26, color: '#d9d9d9' }} />,
    },
    { title: '打印次数', dataIndex: 'print_count', key: 'print_count', width: 90, align: 'right' as const },
    {
      title: '操作', key: 'action', width: 120,
      render: (_: unknown, r: QRRow) => (
        <Button
          size="small"
          icon={<DownloadOutlined />}
          disabled={!r.has_qrcode}
          onClick={() => handleDownloadSingle(r)}
        >
          下载PNG
        </Button>
      ),
    },
  ];

  return (
    <>
      {/* 统计卡片 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={8}>
          <Card><Statistic title="充电桩总数" value={stats.total} prefix={<ThunderboltOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8}>
          <Card><Statistic title="已生成二维码" value={stats.generated} valueStyle={{ color: '#52c41a' }} prefix={<QrcodeOutlined />} /></Card>
        </Col>
        <Col xs={12} sm={8}>
          <Card><Statistic title="待生成" value={stats.pending} valueStyle={{ color: '#faad14' }} /></Card>
        </Col>
      </Row>

      {/* 工具栏 */}
      <Card style={{ marginBottom: 16 }}>
        <Space wrap>
          <Button
            type="primary"
            icon={<QrcodeOutlined />}
            loading={generating}
            disabled={selectedIds.length === 0}
            onClick={handleGenerate}
          >
            批量生成二维码
          </Button>
          <Button
            icon={<FileZipOutlined />}
            disabled={selectedIds.length === 0}
            onClick={handleBatchDownload}
          >
            批量下载ZIP
          </Button>
          <span style={{ color: '#888' }}>{selectedIds.length ? `已选 ${selectedIds.length} 个` : '未勾选'}</span>
          <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
        </Space>
      </Card>

      {/* 充电桩表格 */}
      <Table
        columns={columns}
        dataSource={rows}
        rowKey="device_id"
        loading={loading}
        rowSelection={{
          selectedRowKeys: selectedIds,
          onChange: (keys) => setSelectedIds(keys as number[]),
        }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t: number) => `共 ${t} 条`,
          onChange: (p: number, ps: number) => { setPage(p); setPageSize(ps); },
        }}
        scroll={{ x: 1100 }}
      />
    </>
  );
};

export default QRCodesPage;
