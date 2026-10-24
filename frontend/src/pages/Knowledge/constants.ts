/**
 * 天链 V3 - 知识库页面常量与纯函数
 */

export const FAQ_CATEGORIES = [
  { label: '全部', value: '' },
  { label: '设备类', value: '设备类' },
  { label: '告警类', value: '告警类' },
  { label: '工单类', value: '工单类' },
  { label: '系统类', value: '系统类' },
];

export const getTagColor = (category: string) => {
  const colorMap: Record<string, string> = {
    '维修指南': 'blue', '故障诊断': 'red', '操作手册': 'green',
    '专家经验': 'purple', '安全规范': 'orange', 'general': 'default',
  };
  return colorMap[category] || 'default';
};
