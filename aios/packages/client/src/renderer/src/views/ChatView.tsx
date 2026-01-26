/**
 * ChatView - 主对话界面
 * 现代化设计：底部输入框 + 欢迎卡片
 */

import React, { useState, useRef, useEffect } from 'react';
import MessageList from '../components/MessageList';
import InputBox from '../components/InputBox';
import { VoiceInput } from '../components/voice';
import TaskBoard from '../components/TaskBoard';
import PlanPreview from '../components/PlanPreview';
import { usePlanApproval } from '../hooks/usePlanApproval';
import StreamingText from '../components/StreamingText';
import { useTaskBoard } from '../hooks/useTaskBoard';
import { useStreamingChat } from '../hooks/useStreamingChat';
import { api, isElectron } from '../utils/api';

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

// 欢迎卡片组件
const WelcomeCard: React.FC<{ onSuggestionClick: (text: string) => void }> = ({ onSuggestionClick }) => {
    const suggestions = [
        { icon: '🔊', text: '调节系统音量到 50%', label: '系统控制' },
        { icon: '📁', text: '打开下载文件夹', label: '文件操作' },
        { icon: '🌙', text: '开启深色模式', label: '外观设置' },
        { icon: '📱', text: '查看已安装的应用', label: '应用管理' },
    ];

    return (
        <div className="welcome-card">
            <div className="welcome-header">
                <span className="welcome-icon">👋</span>
                <div>
                    <h3>欢迎使用 AIOS</h3>
                    <p>你的智能系统助手，帮助你更高效地控制电脑</p>
                </div>
            </div>
            <div className="welcome-suggestions">
                <p className="suggestions-label">试试这些命令：</p>
                <div className="suggestions-grid">
                    {suggestions.map((item, idx) => (
                        <button
                            key={idx}
                            className="suggestion-item"
                            onClick={() => onSuggestionClick(item.text)}
                        >
                            <span className="suggestion-icon">{item.icon}</span>
                            <div className="suggestion-content">
                                <span className="suggestion-text">{item.text}</span>
                                <span className="suggestion-label">{item.label}</span>
                            </div>
                        </button>
                    ))}
                </div>
            </div>
        </div>
    );
};

const ChatView: React.FC<ChatViewProps> = ({ quickLauncherOpen, onQuickLauncherClose }) => {
    const [messages, setMessages] = useState<Message[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [showTaskBoard, setShowTaskBoard] = useState(false);
    const quickLauncherRef = useRef<HTMLInputElement>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const { tasks, cancelTask, retryTask, clearCompleted } = useTaskBoard();

    // 计划审批 Hook
    const { pendingPlan, isLoading: isPlanLoading, approvePlan, rejectPlan } = usePlanApproval();

    // 流式聊天 hook
    const {
        content: streamContent,
        reasoningContent,
        status: streamStatus,
        sendStreamMessage,
        cancelStream,
        reset: resetStream,
    } = useStreamingChat();

    // 滚动到底部
    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages]);

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

        // 在 Electron 环境下使用流式模式
        if (isElectron()) {
            resetStream();
            await sendStreamMessage(content);
        } else {
            // Web 环境使用非流式模式
            setIsLoading(true);
            try {
                const response = await api.smartChat(content);

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
        }
    };

    // 当流式响应完成时，将内容添加到消息列表
    useEffect(() => {
        if (streamStatus === 'completed' && streamContent) {
            const assistantMessage: Message = {
                id: Date.now().toString(),
                role: 'assistant',
                content: streamContent,
                timestamp: new Date(),
            };
            setMessages((prev) => [...prev, assistantMessage]);
            resetStream();
        } else if (streamStatus === 'error') {
            const errorMessage: Message = {
                id: Date.now().toString(),
                role: 'system',
                content: '流式响应出错，请稍后重试。',
                timestamp: new Date(),
            };
            setMessages((prev) => [...prev, errorMessage]);
            resetStream();
        }
    }, [streamStatus, streamContent, resetStream]);

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

    const hasMessages = messages.length > 0;

    return (
        <div className="chat-view">
            {/* 计划预览弹窗 */}
            {pendingPlan && (
                <div className="plan-preview-overlay">
                    <div className="plan-preview-modal">
                        <PlanPreview
                            plan={pendingPlan}
                            onApprove={() => approvePlan()}
                            onReject={(feedback) => rejectPlan(feedback)}
                            isLoading={isPlanLoading}
                        />
                    </div>
                </div>
            )}
            {/* 消息区域 */}
            <div className="chat-messages-area">
                {!hasMessages && streamStatus !== 'streaming' ? (
                    <div className="chat-empty-state">
                        <WelcomeCard onSuggestionClick={handleSendMessage} />
                    </div>
                ) : (
                    <div className="messages-scroll-container">
                        <MessageList messages={messages} />

                        {/* 流式响应显示 */}
                        {streamStatus === 'streaming' && (
                            <div className="message assistant streaming">
                                <div className="message-content">
                                    <StreamingText
                                        text={streamContent}
                                        reasoningContent={reasoningContent}
                                        status={streamStatus}
                                    />
                                </div>
                                <button
                                    className="cancel-stream-btn"
                                    onClick={cancelStream}
                                    title="停止生成"
                                >
                                    ⏹️ 停止生成
                                </button>
                            </div>
                        )}

                        <div ref={messagesEndRef} />
                    </div>
                )}

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

            {/* 底部固定输入区域 */}
            <div className="chat-input-area">
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
                <InputBox
                    onSend={handleSendMessage}
                    disabled={isLoading}
                    voiceButton={<VoiceInput onTranscript={handleSendMessage} disabled={isLoading} />}
                />
            </div>

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

