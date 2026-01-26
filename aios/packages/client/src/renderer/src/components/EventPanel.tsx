/**
 * EventPanel - 事件可视化面板组件
 * 实时显示系统事件流，支持过滤和搜索
 */

import React, { useState, useMemo } from 'react';
import { useEventStream, EventType, type StreamEvent } from '../hooks';
import './EventPanel.css';

/** 事件面板属性 */
interface EventPanelProps {
    /** 最大显示事件数 */
    maxEvents?: number;
    /** 是否显示详情 */
    showDetails?: boolean;
    /** 初始过滤类型 */
    initialFilter?: EventType[];
    /** 自定义类名 */
    className?: string;
}

/** 事件类型配置 */
const EVENT_TYPE_CONFIG: Record<EventType, { label: string; color: string; icon: string }> = {
    [EventType.TASK_START]: { label: '任务开始', color: '#4CAF50', icon: '▶️' },
    [EventType.TASK_PROGRESS]: { label: '任务进度', color: '#2196F3', icon: '⏳' },
    [EventType.TASK_COMPLETE]: { label: '任务完成', color: '#4CAF50', icon: '✅' },
    [EventType.TASK_ERROR]: { label: '任务错误', color: '#f44336', icon: '❌' },
    [EventType.TOOL_CALL]: { label: '工具调用', color: '#9C27B0', icon: '🔧' },
    [EventType.TOOL_RESULT]: { label: '工具结果', color: '#673AB7', icon: '📦' },
    [EventType.LLM_REQUEST]: { label: 'LLM 请求', color: '#FF9800', icon: '📤' },
    [EventType.LLM_RESPONSE]: { label: 'LLM 响应', color: '#FF5722', icon: '📥' },
    [EventType.LLM_STREAM_CHUNK]: { label: '流式块', color: '#795548', icon: '💬' },
    [EventType.SYSTEM_INFO]: { label: '系统信息', color: '#607D8B', icon: 'ℹ️' },
    [EventType.SYSTEM_WARNING]: { label: '系统警告', color: '#FFC107', icon: '⚠️' },
    [EventType.SYSTEM_ERROR]: { label: '系统错误', color: '#f44336', icon: '🚨' },
};

/**
 * 格式化时间戳
 */
function formatTime(timestamp: number): string {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        fractionalSecondDigits: 3,
    });
}

/**
 * 格式化相对时间
 */
function formatRelativeTime(timestamp: number): string {
    const diff = Date.now() - timestamp;
    if (diff < 1000) return '刚刚';
    if (diff < 60000) return `${Math.floor(diff / 1000)}秒前`;
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
    return `${Math.floor(diff / 3600000)}小时前`;
}

/**
 * 单个事件卡片
 */
const EventCard: React.FC<{
    event: StreamEvent;
    showDetails: boolean;
    onToggleDetails: () => void;
}> = ({ event, showDetails, onToggleDetails }) => {
    const config = EVENT_TYPE_CONFIG[event.type] ?? {
        label: event.type,
        color: '#999',
        icon: '📌',
    };

    return (
        <div
            className="event-card"
            style={{ borderLeftColor: config.color }}
            onClick={onToggleDetails}
        >
            <div className="event-header">
                <span className="event-icon">{config.icon}</span>
                <span className="event-type" style={{ color: config.color }}>
                    {config.label}
                </span>
                <span className="event-source">{event.source}</span>
                <span className="event-time" title={formatTime(event.timestamp)}>
                    {formatRelativeTime(event.timestamp)}
                </span>
            </div>

            {event.taskId && (
                <div className="event-task-id">
                    <span className="label">Task:</span>
                    <code>{event.taskId.slice(0, 12)}...</code>
                </div>
            )}

            {showDetails && (
                <div className="event-details">
                    <pre>{JSON.stringify(event.data, null, 2)}</pre>
                </div>
            )}
        </div>
    );
};

/**
 * 事件可视化面板
 */
const EventPanel: React.FC<EventPanelProps> = ({
    maxEvents = 100,
    showDetails = false,
    initialFilter,
    className = '',
}) => {
    const [selectedTypes, setSelectedTypes] = useState<EventType[]>(
        initialFilter ?? Object.values(EventType)
    );
    const [searchQuery, setSearchQuery] = useState('');
    const [expandedEvents, setExpandedEvents] = useState<Set<string>>(new Set());
    const [isPaused, setIsPaused] = useState(false);

    const { events, connected, status, clearEvents, getStats } = useEventStream({
        filter: { types: selectedTypes },
        maxEvents,
        autoConnect: true,
    });

    // 过滤和搜索
    const filteredEvents = useMemo(() => {
        if (!searchQuery) return events;
        const query = searchQuery.toLowerCase();
        return events.filter(e =>
            e.source.toLowerCase().includes(query) ||
            e.taskId?.toLowerCase().includes(query) ||
            JSON.stringify(e.data).toLowerCase().includes(query)
        );
    }, [events, searchQuery]);

    // 统计信息
    const stats = getStats();

    // 切换事件类型过滤
    const toggleType = (type: EventType) => {
        setSelectedTypes(prev => {
            if (prev.includes(type)) {
                return prev.filter(t => t !== type);
            }
            return [...prev, type];
        });
    };

    // 切换事件详情展开
    const toggleEventDetails = (eventId: string) => {
        setExpandedEvents(prev => {
            const next = new Set(prev);
            if (next.has(eventId)) {
                next.delete(eventId);
            } else {
                next.add(eventId);
            }
            return next;
        });
    };

    return (
        <div className={`event-panel ${className}`}>
            {/* 头部工具栏 */}
            <div className="event-panel-header">
                <div className="header-left">
                    <h3>📊 事件流</h3>
                    <span className={`status-indicator ${connected ? 'connected' : 'disconnected'}`}>
                        {status === 'connected' ? '● 已连接' : '○ 未连接'}
                    </span>
                </div>
                <div className="header-right">
                    <span className="event-count">{stats.total} 事件</span>
                    <button
                        className="btn-icon"
                        onClick={() => setIsPaused(!isPaused)}
                        title={isPaused ? '恢复' : '暂停'}
                    >
                        {isPaused ? '▶️' : '⏸️'}
                    </button>
                    <button
                        className="btn-icon"
                        onClick={clearEvents}
                        title="清空"
                    >
                        🗑️
                    </button>
                </div>
            </div>

            {/* 过滤器 */}
            <div className="event-filters">
                <input
                    type="text"
                    className="search-input"
                    placeholder="搜索事件..."
                    value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)}
                />
                <div className="type-filters">
                    {Object.entries(EVENT_TYPE_CONFIG).map(([type, config]) => (
                        <button
                            key={type}
                            className={`type-filter-btn ${selectedTypes.includes(type as EventType) ? 'active' : ''}`}
                            style={{
                                borderColor: config.color,
                                backgroundColor: selectedTypes.includes(type as EventType) ? config.color : 'transparent',
                            }}
                            onClick={() => toggleType(type as EventType)}
                            title={config.label}
                        >
                            {config.icon}
                        </button>
                    ))}
                </div>
            </div>

            {/* 事件列表 */}
            <div className="event-list">
                {filteredEvents.length === 0 ? (
                    <div className="empty-state">
                        <span className="empty-icon">📭</span>
                        <p>暂无事件</p>
                    </div>
                ) : (
                    filteredEvents.slice().reverse().map(event => (
                        <EventCard
                            key={event.id}
                            event={event}
                            showDetails={showDetails || expandedEvents.has(event.id)}
                            onToggleDetails={() => toggleEventDetails(event.id)}
                        />
                    ))
                )}
            </div>

            {/* 统计信息 */}
            <div className="event-panel-footer">
                <div className="stats-bar">
                    {Object.entries(stats.byType).slice(0, 5).map(([type, count]) => {
                        const config = EVENT_TYPE_CONFIG[type as EventType];
                        return (
                            <span key={type} className="stat-item" style={{ color: config?.color }}>
                                {config?.icon} {count}
                            </span>
                        );
                    })}
                </div>
            </div>
        </div>
    );
};

export default EventPanel;
