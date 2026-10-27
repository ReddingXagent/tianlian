/**
 * 语言切换组件
 * 支持中文和英文切换，切换后所有UI文字立即更新
 */
import React from 'react';
import { Button, Dropdown, Space } from 'antd';
import { GlobalOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

const LanguageSwitcher: React.FC = () => {
  const { t, i18n } = useTranslation();
  const currentLang = i18n.language || 'zh-CN';

  const switchLanguage = (lng: string) => {
    i18n.changeLanguage(lng);
    // 同步更新 Ant Design 本地化（可选）
    localStorage.setItem('i18nextLng', lng);
  };

  const items = [
    {
      key: 'zh-CN',
      label: (
        <Space>
          <span role="img" aria-label="Chinese">🇨🇳</span>
          <span>{currentLang === 'zh-CN' ? '✓ ' : ''}{t('language.zh_CN')}</span>
        </Space>
      ),
      onClick: () => switchLanguage('zh-CN'),
    },
    {
      key: 'en',
      label: (
        <Space>
          <span role="img" aria-label="English">🇬🇧</span>
          <span>{currentLang === 'en' ? '✓ ' : ''}{t('language.en_US')}</span>
        </Space>
      ),
      onClick: () => switchLanguage('en'),
    },
  ];

  return (
    <Dropdown menu={{ items }} placement="bottomRight" trigger={['click']}>
      <Button
        type="text"
        icon={<GlobalOutlined />}
        style={{ fontSize: 16 }}
        title={t('language.select')}
      >
        {currentLang === 'en' ? 'EN' : '中'}
      </Button>
    </Dropdown>
  );
};

export default LanguageSwitcher;