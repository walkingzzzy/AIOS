/**
 * useEventStream - 事件流订阅 Hook
 * 用于前端订阅和显示后端事件流
 * 支持 Electron IPC 和 Web (WebSocket) 两种模式
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { isElectron } from '../utils/api';

/** 事件类型 */
export enum EventType {
    TASK_START = 'task:start',
    TASK_PROGRESS = 'task:progress',
    TASK_COMPLETE = 'task:complete',
    TASK_ERROR = 'task:error',
    TOOL_CALL = 'tool:call',
    TOOL_RESULT = 'tool:result',
    LLM_REQUEST = 'llm:request',
    LLM_RESPONSE = 'llm:response',
    LLM_STREAM_CHUNK = 'llm:stream-chunk',
    SYSTEM_INFO = 'system:info',
    SYSTEM_WARNING = 'system:warning',
    SYSTEM_ERROR = 'system:error',
}

/** 事件结构 */
export interface StreamEvent {
    id: string;
    type: EventType;
    timestamp: number;
    source: string;
    taskId?: string;
    traceId?: string;
    data: Record<string, unknown>;
}

/** 事件过滤器 */
export interface EventFilter {
    types?: EventType[];
    taskId?: string;
    source?: string;
}

/** Hook 配置 */
export interface UseEventStreamOptions {
    /** 过滤器 */
    filter?: EventFilter;
    /** 最大保留事件数 */
    maxEvents?: number;
    /** 是否自动连接 */
    autoConnect?: boolean;
}

/** Hook 返回值 */
export interface UseEventStreamReturn {
    /** 事件列表 */
    events: StreamEvent[];
    /** 是否已连接 */
    connected: boolean;
    /** 连接状态 */
    status: 'disconnected' | 'connecting' | 'connected' | 'error';
    /** 错误信息 */
    error: string | null;
    /** 清空事件 */
    clearEvents: () => void;
    /** 手动连接 */
    connect: () => void;
    /** 断开连接 */
    disconnect: () => void;
    /** 获取事件统计 */
    getStats: () => {
        total: number;
        byType: Record<string, number>;
    };
}

/**
 * 事件流订阅 Hook
 * 
 * @example
 * ```tsx
 * const { events, connected, clearEvents } = useEventStream({
 *     filter: { types: [EventType.TASK_START, EventType.TASK_COMPLETE] },
 *     maxEvents: 100,
 * });
 * 
 * return (
 *     <div>
 *         {events.map(event => (
 *             <EventCard key={event.id} event={event} />
 *         ))}
 *     </div>
 * );
 * ```
 */
export function useEventStream(options: UseEventStreamOptions = {}): UseEventStreamReturn {
    const [events, setEvents] = useState<StreamEvent[]>([]);
    const [status, setStatus] = useState<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected');
    const [error, setError] = useState<string | null>(null);

    const optionsRef = useRef(options);
    optionsRef.current = options;

    const maxEvents = options.maxEvents ?? 500;
    const unsubscribeRefs = useRef<Array<() => void>>([]);

    // 检查事件是否匹配过滤器
    const matchFilter = useCallback((event: StreamEvent, filter?: EventFilter): boolean => {
        if (!filter) return true;
        if (filter.types && filter.types.length > 0 && !filter.types.includes(event.type)) {
            return false;
        }
        if (filter.taskId && event.taskId !== filter.taskId) {
            return false;
        }
        if (filter.source && event.source !== filter.source) {
            return false;
        }
        return true;
    }, []);

    // 添加事件
    const addEvent = useCallback((event: StreamEvent) => {
        if (!matchFilter(event, optionsRef.current.filter)) {
            return;
        }

        setEvents(prev => {
            const newEvents = [...prev, event];
            // 保持最大事件数
            if (newEvents.length > maxEvents) {
                return newEvents.slice(-maxEvents);
            }
            return newEvents;
        });
    }, [matchFilter, maxEvents]);

    // 连接事件流
    const connect = useCallback(() => {
        if (status === 'connected' || status === 'connecting') return;

        setStatus('connecting');
        setError(null);

        try {
            // 仅在 Electron 模式下订阅事件
            if (!isElectron()) {
                setStatus('connected');
                return;
            }

            // 订阅任务进度
            const unsubProgress = window.aios.onTaskProgress((data) => {
                addEvent({
                    id: `evt_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
                    type: EventType.TASK_PROGRESS,
                    timestamp: Date.now(),
                    source: 'TaskScheduler',
                    taskId: data.taskId,
                    data: data as unknown as Record<string, unknown>,
                });
            });
            unsubscribeRefs.current.push(unsubProgress);

            // 订阅任务完成
            const unsubComplete = window.aios.onTaskComplete((data) => {
                addEvent({
                    id: `evt_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
                    type: EventType.TASK_COMPLETE,
                    timestamp: Date.now(),
                    source: 'TaskScheduler',
                    taskId: data.taskId,
                    data: data as unknown as Record<string, unknown>,
                });
            });
            unsubscribeRefs.current.push(unsubComplete);

            // 订阅任务错误
            const unsubError = window.aios.onTaskError((data) => {
                addEvent({
                    id: `evt_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
                    type: EventType.TASK_ERROR,
                    timestamp: Date.now(),
                    source: 'TaskScheduler',
                    taskId: data.taskId,
                    data: data as unknown as Record<string, unknown>,
                });
            });
            unsubscribeRefs.current.push(unsubError);

            // 订阅流式块
            const unsubStream = window.aios.onStreamChunk((data) => {
                addEvent({
                    id: `evt_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
                    type: EventType.LLM_STREAM_CHUNK,
                    timestamp: Date.now(),
                    source: 'TaskOrchestrator',
                    taskId: data.taskId,
                    data: data as unknown as Record<string, unknown>,
                });
            });
            unsubscribeRefs.current.push(unsubStream);

            setStatus('connected');
        } catch (err) {
            setStatus('error');
            setError(err instanceof Error ? err.message : '连接失败');
        }
    }, [status, addEvent]);

    // 断开连接
    const disconnect = useCallback(() => {
        for (const unsub of unsubscribeRefs.current) {
            unsub();
        }
        unsubscribeRefs.current = [];
        setStatus('disconnected');
    }, []);

    // 清空事件
    const clearEvents = useCallback(() => {
        setEvents([]);
    }, []);

    // 获取统计
    const getStats = useCallback(() => {
        const byType: Record<string, number> = {};
        for (const event of events) {
            byType[event.type] = (byType[event.type] ?? 0) + 1;
        }
        return {
            total: events.length,
            byType,
        };
    }, [events]);

    // 自动连接
    useEffect(() => {
        if (options.autoConnect !== false) {
            connect();
        }

        return () => {
            disconnect();
        };
    }, []);

    return {
        events,
        connected: status === 'connected',
        status,
        error,
        clearEvents,
        connect,
        disconnect,
        getStats,
    };
}

export default useEventStream;
