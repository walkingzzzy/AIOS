/**
 * ChatView - 主对话界面
 */

import React, { useState, useRef, useEffect } from 'react';
import MessageList from '../components/MessageList';
import InputBox from '../components/InputBox';
import { VoiceInput } from '../components/voice';
import TaskBoard from '../components/TaskBoard';
import { useTaskBoard } from '../hooks/useTaskBoard';
import { api } from '../utils/api';

interface Message {
    id: string;
    role: 'user' | 'assistant' | 'system';
    content: string;
    timestamp: Date;
}

interface ChatViewProps {
    quickLauncherOpen: boolean;
    onQuickLauncherClose: () => void;
}

const ChatView: React.FC<ChatViewProps> = ({ quickLauncherOpen, onQuickLauncherClose }) => {
    const [messages, setMessages] = useState<Message[]>([
        {
            id: '1',
            role: 'system',
            content: '欢迎使用 AIOS! 我可以帮助您控制系统设置、管理应用程序、操作文件等。',
            timestamp: new Date(),
        },
    ]);
    const [isLoading, setIsLoading] = useState(false);
    const [showTaskBoard, setShowTaskBoard] = useState(false);
    const quickLauncherRef = useRef<HTMLInputElement>(null);
    const { tasks, cancelTask, retryTask, clearCompleted } = useTaskBoard();

    useEffect(() => {
        if (quickLauncherOpen && quickLauncherRef.current) {
            quickLauncherRef.current.focus();
        }
    }, [quickLauncherOpen]);

    const handleSendMessage = async (content: string) => {
        if (!content.trim()) return;

        const userMessage: Message = {
            id: Date.now().toString(),
            role: 'user',
            content,
            timestamp: new Date(),
        };

        setMessages((prev) => [...prev, userMessage]);
        setIsLoading(true);

        try {
            // 使用三层 AI 协调
            const response = await api.smartChat(content);

            // 构建响应内容，包含执行信息
            let responseContent = response.response;
            const tierLabels: Record<string, string> = {
                direct: '⚡ 直达',
                fast: '🚀 Fast',
                vision: '👁️ Vision',
                smart: '🧠 Smart',
            };
            const tierInfo = tierLabels[response.tier] || response.tier;
            const timeInfo = `${response.executionTime}ms`;

            const assistantMessage: Message = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: `${responseContent}\n\n_${tierInfo} · ${timeInfo}${response.model ? ` · ${response.model}` : ''}_`,
                timestamp: new Date(),
            };

            setMessages((prev) => [...prev, assistantMessage]);
        } catch (error) {
            const errorMessage: Message = {
                id: (Date.now() + 1).toString(),
                role: 'system',
                content: error instanceof Error ? `错误: ${error.message}` : '发生错误，请稍后重试。',
                timestamp: new Date(),
            };
            setMessages((prev) => [...prev, errorMessage]);
        } finally {
            setIsLoading(false);
        }
    };

    const handleQuickLauncherSubmit = (e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter') {
            const value = (e.target as HTMLInputElement).value;
            if (value.trim()) {
                handleSendMessage(value);
                (e.target as HTMLInputElement).value = '';
            }
            onQuickLauncherClose();
        } else if (e.key === 'Escape') {
            onQuickLauncherClose();
        }
    };

    // 自动显示任务板
    useEffect(() => {
        if (tasks.length > 0 && tasks.some(t => t.status === 'running')) {
            setShowTaskBoard(true);
        }
    }, [tasks]);

    return (
        <div className="chat-view">
            <header className="chat-header">
                <h2>AI 助手</h2>
                {tasks.length > 0 && (
                    <button
                        className="task-board-toggle"
                        onClick={() => setShowTaskBoard(!showTaskBoard)}
                        title={showTaskBoard ? '隐藏任务板' : '显示任务板'}
                    >
                        📋 {tasks.filter(t => t.status === 'running').length > 0 && (
                            <span className="task-badge">
                                {tasks.filter(t => t.status === 'running').length}
                            </span>
                        )}
                    </button>
                )}
            </header>

            <div className="chat-content">
                <MessageList messages={messages} />

                {showTaskBoard && tasks.length > 0 && (
                    <div className="task-board-container">
                        <TaskBoard
                            tasks={tasks}
                            onCancel={cancelTask}
                            onRetry={retryTask}
                        />
                        {tasks.filter(t => t.status === 'completed' || t.status === 'failed').length > 0 && (
                            <button
                                className="clear-completed-btn"
                                onClick={clearCompleted}
                            >
                                清除已完成
                            </button>
                        )}
                    </div>
                )}
            </div>

            <InputBox
                onSend={handleSendMessage}
                disabled={isLoading}
                voiceButton={<VoiceInput onTranscript={handleSendMessage} disabled={isLoading} />}
            />

            {quickLauncherOpen && (
                <div className="quick-launcher-overlay" onClick={onQuickLauncherClose}>
                    <div className="quick-launcher" onClick={(e) => e.stopPropagation()}>
                        <input
                            ref={quickLauncherRef}
                            type="text"
                            className="quick-launcher-input"
                            placeholder="输入命令..."
                            onKeyDown={handleQuickLauncherSubmit}
                        />
                    </div>
                </div>
            )}
        </div>
    );
};

export default ChatView;
