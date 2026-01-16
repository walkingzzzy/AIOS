/**
 * ArtifactRenderer - 构件渲染器
 * 用于渲染 AI 生成的各种构件类型 (HTML, Markdown, React, SVG 等)
 */

import React, { useState, useMemo } from 'react';
import './ArtifactRenderer.css';

export interface Artifact {
    id: string;
    type: 'html' | 'markdown' | 'react' | 'svg' | 'code' | 'text' | 'image';
    title?: string;
    content: string;
    language?: string;
}

interface ArtifactRendererProps {
    artifact: Artifact;
    onClose?: () => void;
    onCopy?: () => void;
    className?: string;
}

const ArtifactRenderer: React.FC<ArtifactRendererProps> = ({
    artifact,
    onClose,
    onCopy,
    className = '',
}) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const [copySuccess, setCopySuccess] = useState(false);

    const handleCopy = async () => {
        try {
            await navigator.clipboard.writeText(artifact.content);
            setCopySuccess(true);
            setTimeout(() => setCopySuccess(false), 2000);
            onCopy?.();
        } catch (error) {
            console.error('Failed to copy:', error);
        }
    };

    const renderedContent = useMemo(() => {
        switch (artifact.type) {
            case 'html':
                return (
                    <div
                        className="artifact-html"
                        dangerouslySetInnerHTML={{ __html: artifact.content }}
                    />
                );

            case 'svg':
                return (
                    <div
                        className="artifact-svg"
                        dangerouslySetInnerHTML={{ __html: artifact.content }}
                    />
                );

            case 'markdown':
                return (
                    <div className="artifact-markdown">
                        <pre>{artifact.content}</pre>
                    </div>
                );

            case 'code':
                return (
                    <div className="artifact-code">
                        <div className="code-header">
                            <span className="language">{artifact.language || 'code'}</span>
                        </div>
                        <pre>
                            <code>{artifact.content}</code>
                        </pre>
                    </div>
                );

            case 'image':
                return (
                    <div className="artifact-image">
                        <img src={artifact.content} alt={artifact.title || 'Image'} />
                    </div>
                );

            case 'text':
            default:
                return (
                    <div className="artifact-text">
                        <pre>{artifact.content}</pre>
                    </div>
                );
        }
    }, [artifact]);

    return (
        <div className={`artifact-renderer ${isExpanded ? 'expanded' : ''} ${className}`}>
            <div className="artifact-header">
                <div className="artifact-title">
                    <span className="artifact-type-badge">{artifact.type.toUpperCase()}</span>
                    {artifact.title && <span className="title-text">{artifact.title}</span>}
                </div>
                <div className="artifact-actions">
                    <button
                        className="action-btn"
                        onClick={handleCopy}
                        title="复制内容"
                    >
                        {copySuccess ? '✓' : '📋'}
                    </button>
                    <button
                        className="action-btn"
                        onClick={() => setIsExpanded(!isExpanded)}
                        title={isExpanded ? '收起' : '展开'}
                    >
                        {isExpanded ? '⬆️' : '⬇️'}
                    </button>
                    {onClose && (
                        <button
                            className="action-btn close-btn"
                            onClick={onClose}
                            title="关闭"
                        >
                            ✕
                        </button>
                    )}
                </div>
            </div>
            <div className="artifact-content">{renderedContent}</div>
        </div>
    );
};

/**
 * 从 AI 输出中解析 artifact 标签
 */
export function parseArtifacts(text: string): { text: string; artifacts: Artifact[] } {
    const artifactRegex = /<artifact\s+type="([^"]+)"(?:\s+title="([^"]*)")?(?:\s+language="([^"]*)")?>([\s\S]*?)<\/artifact>/g;
    const artifacts: Artifact[] = [];
    let cleanText = text;
    let match;
    let idx = 0;

    while ((match = artifactRegex.exec(text)) !== null) {
        artifacts.push({
            id: `artifact-${Date.now()}-${idx++}`,
            type: match[1] as Artifact['type'],
            title: match[2] || undefined,
            language: match[3] || undefined,
            content: match[4].trim(),
        });
        cleanText = cleanText.replace(match[0], `[构件: ${match[2] || match[1]}]`);
    }

    return { text: cleanText, artifacts };
}

export default ArtifactRenderer;
