/**
 * StreamingText - 流式文本显示组件
 * 支持打字机效果和 Markdown 实时渲染
 */

import React, { useMemo } from 'react';
import type { StreamingStatus } from '../hooks/useStreamingChat';
import './StreamingText.css';

interface StreamingTextProps {
    /** 文本内容 */
    text: string;
    /** 推理内容（可选） */
    reasoningContent?: string;
    /** 当前状态 */
    status: StreamingStatus;
    /** 是否显示光标 */
    showCursor?: boolean;
    /** 自定义类名 */
    className?: string;
}

/**
 * 简单的 Markdown 解析器
 */
function parseMarkdown(text: string): React.ReactNode[] {
    const lines = text.split('\n');
    const elements: React.ReactNode[] = [];

    let inCodeBlock = false;
    let codeBlockContent = '';
    let codeBlockLang = '';

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i];

        // 代码块开始/结束
        if (line.startsWith('```')) {
            if (inCodeBlock) {
                // 结束代码块
                elements.push(
                    <pre key={`code-${i}`} className={`code-block lang-${codeBlockLang}`}>
                        <code>{codeBlockContent}</code>
                    </pre>
                );
                codeBlockContent = '';
                codeBlockLang = '';
                inCodeBlock = false;
            } else {
                // 开始代码块
                inCodeBlock = true;
                codeBlockLang = line.slice(3).trim() || 'text';
            }
            continue;
        }

        if (inCodeBlock) {
            codeBlockContent += (codeBlockContent ? '\n' : '') + line;
            continue;
        }

        // 标题
        if (line.startsWith('### ')) {
            elements.push(<h3 key={i}>{line.slice(4)}</h3>);
            continue;
        }
        if (line.startsWith('## ')) {
            elements.push(<h2 key={i}>{line.slice(3)}</h2>);
            continue;
        }
        if (line.startsWith('# ')) {
            elements.push(<h1 key={i}>{line.slice(2)}</h1>);
            continue;
        }

        // 列表项
        if (line.match(/^[-*]\s/)) {
            elements.push(
                <li key={i}>{parseInlineMarkdown(line.slice(2))}</li>
            );
            continue;
        }

        // 有序列表
        if (line.match(/^\d+\.\s/)) {
            const content = line.replace(/^\d+\.\s/, '');
            elements.push(
                <li key={i} className="ordered">{parseInlineMarkdown(content)}</li>
            );
            continue;
        }

        // 空行
        if (line.trim() === '') {
            elements.push(<br key={i} />);
            continue;
        }

        // 普通段落
        elements.push(
            <p key={i}>{parseInlineMarkdown(line)}</p>
        );
    }

    // 处理未闭合的代码块
    if (inCodeBlock && codeBlockContent) {
        elements.push(
            <pre key="code-unclosed" className={`code-block lang-${codeBlockLang}`}>
                <code>{codeBlockContent}</code>
            </pre>
        );
    }

    return elements;
}

/**
 * 解析行内 Markdown（粗体、斜体、代码）
 */
function parseInlineMarkdown(text: string): React.ReactNode {
    const parts: React.ReactNode[] = [];
    let remaining = text;
    let key = 0;

    while (remaining) {
        // 行内代码
        const codeMatch = remaining.match(/`([^`]+)`/);
        if (codeMatch) {
            const before = remaining.slice(0, codeMatch.index);
            if (before) parts.push(before);
            parts.push(<code key={key++} className="inline-code">{codeMatch[1]}</code>);
            remaining = remaining.slice((codeMatch.index || 0) + codeMatch[0].length);
            continue;
        }

        // 粗体
        const boldMatch = remaining.match(/\*\*([^*]+)\*\*/);
        if (boldMatch) {
            const before = remaining.slice(0, boldMatch.index);
            if (before) parts.push(before);
            parts.push(<strong key={key++}>{boldMatch[1]}</strong>);
            remaining = remaining.slice((boldMatch.index || 0) + boldMatch[0].length);
            continue;
        }

        // 斜体
        const italicMatch = remaining.match(/\*([^*]+)\*/);
        if (italicMatch) {
            const before = remaining.slice(0, italicMatch.index);
            if (before) parts.push(before);
            parts.push(<em key={key++}>{italicMatch[1]}</em>);
            remaining = remaining.slice((italicMatch.index || 0) + italicMatch[0].length);
            continue;
        }

        // 没有更多匹配
        parts.push(remaining);
        break;
    }

    return parts.length === 1 ? parts[0] : <>{parts}</>;
}

/**
 * 流式文本显示组件
 */
const StreamingText: React.FC<StreamingTextProps> = ({
    text,
    reasoningContent,
    status,
    showCursor = true,
    className = '',
}) => {
    // 解析 Markdown
    const parsedContent = useMemo(() => parseMarkdown(text), [text]);
    const parsedReasoning = useMemo(
        () => reasoningContent ? parseMarkdown(reasoningContent) : null,
        [reasoningContent]
    );

    const isStreaming = status === 'streaming';

    return (
        <div className={`streaming-text ${className} ${isStreaming ? 'is-streaming' : ''}`}>
            {/* 推理内容（折叠显示） */}
            {parsedReasoning && (
                <details className="reasoning-content">
                    <summary>💭 推理过程</summary>
                    <div className="reasoning-body">
                        {parsedReasoning}
                    </div>
                </details>
            )}

            {/* 主要内容 */}
            <div className="text-content">
                {parsedContent}
                {showCursor && isStreaming && (
                    <span className="streaming-cursor" aria-hidden="true">▌</span>
                )}
            </div>

            {/* 状态指示 */}
            {status === 'error' && (
                <div className="streaming-error">
                    ⚠️ 响应出错
                </div>
            )}
        </div>
    );
};

export default StreamingText;
