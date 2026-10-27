/**
 * 天链 V3 - 知识库关键词高亮组件
 */
import React from 'react';

const Highlight: React.FC<{ text: string; keyword: string }> = ({ text, keyword }) => {
  if (!keyword.trim()) return <>{text}</>;
  const parts = text.split(new RegExp(`(${keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'));
  return (
    <>
      {parts.map((part, i) =>
        part.toLowerCase() === keyword.toLowerCase()
          ? <span key={i} style={{ background: '#fff3b0', padding: '0 2px', borderRadius: 2 }}>{part}</span>
          : <span key={i}>{part}</span>
      )}
    </>
  );
};

export default Highlight;
