/**
 * MessageList - 消息列表组件
 */

import React, { useEffect, useRef, useState } from 'react';
import ArtifactRenderer, { parseArtifacts, Artifact } from './ArtifactRenderer';

interface Message {
    id: string;
    role: 'user' | 'assistant' | 'system';
    content: string;
    timestamp: Date;
    artifacts?: Artifact[];
}

interface MessageListProps {
    messages: Message[];
}

const MessageList: React.FC<MessageListProps> = ({ messages }) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const [processedMessages, setProcessedMessages] = useState<Message[]>([]);

    useEffect(() => {
        // 处理消息，解析 artifacts
        const processed = messages.map((msg) => {
            if (msg.role === 'assistant' && !msg.artifacts) {
                const { text, artifacts } = parseArtifacts(msg.content);
                return {
                    ...msg,
                    content: text,
                    artifacts: artifacts.length > 0 ? artifacts : undefined,
                };
            }
            return msg;
        });
        setProcessedMessages(processed);
    }, [messages]);

    useEffect(() => {
        // 自动滚动到底部
        if (containerRef.current) {
            containerRef.current.scrollTop = containerRef.current.scrollHeight;
        }
    }, [processedMessages]);

    const renderMessageContent = (content: string) => {
        // 支持简单的 Markdown 渲染
        const lines = content.split('\n');
        return lines.map((line, idx) => {
            // 代码块
            if (line.startsWith('```')) {
                return null; // 代码块由 artifact 处理
            }
            // 粗体
            if (line.includes('**')) {
                const parts = line.split('**');
                return (
                    <p key={idx}>
                        {parts.map((part, i) =>
                            i % 2 === 1 ? <strong key={i}>{part}</strong> : part
                        )}
                    </p>
                );
            }
            // 斜体
            if (line.includes('_') && !line.startsWith('_')) {
                const parts = line.split('_');
                return (
                    <p key={idx}>
                        {parts.map((part, i) =>
                            i % 2 === 1 ? <em key={i}>{part}</em> : part
                        )}
                    </p>
                );
            }
            // 普通文本
            return line ? <p key={idx}>{line}</p> : <br key={idx} />;
        });
    };

    return (
        <div className="messages-container" ref={containerRef}>
            {processedMessages.map((message) => (
                <div key={message.id} className={`message ${message.role}`}>
                    <div className="message-content">
                        {renderMessageContent(message.content)}
                    </div>
                    {message.artifacts && message.artifacts.length > 0 && (
                        <div className="message-artifacts">
                            {message.artifacts.map((artifact) => (
                                <ArtifactRenderer key={artifact.id} artifact={artifact} />
                            ))}
                        </div>
                    )}
                </div>
            ))}
        </div>
    );
};

export default MessageList;
