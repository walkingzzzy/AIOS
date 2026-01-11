/**
 * MessageList - 消息列表组件
 */

import React, { useEffect, useRef } from 'react';

interface Message {
    id: string;
    role: 'user' | 'assistant' | 'system';
    content: string;
    timestamp: Date;
}

interface MessageListProps {
    messages: Message[];
}

const MessageList: React.FC<MessageListProps> = ({ messages }) => {
    const containerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        // 自动滚动到底部
        if (containerRef.current) {
            containerRef.current.scrollTop = containerRef.current.scrollHeight;
        }
    }, [messages]);

    return (
        <div className="messages-container" ref={containerRef}>
            {messages.map((message) => (
                <div key={message.id} className={`message ${message.role}`}>
                    {message.content}
                </div>
            ))}
        </div>
    );
};

export default MessageList;
