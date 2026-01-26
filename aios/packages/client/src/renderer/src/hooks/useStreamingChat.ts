/**
 * useStreamingChat - 流式聊天 Hook
 * 提供流式 AI 对话功能，支持实时显示响应内容
 * 支持 Electron IPC 和 Web (WebSocket) 两种模式
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import { isElectron, api } from '../utils/api';

/** 流式聊天状态 */
export type StreamingStatus = 'idle' | 'streaming' | 'completed' | 'error';

/** 流式块回调参数 */
export interface StreamChunkEvent {
    taskId: string;
    content?: string;
    reasoningContent?: string;
    toolCalls?: Array<{
        index: number;
        id?: string;
        type?: 'function';
        function?: {
            name?: string;
            arguments?: string;
        };
    }>;
    finishReason?: 'stop' | 'tool_calls' | 'length' | 'content_filter' | null;
    usage?: {
        promptTokens: number;
        completionTokens: number;
        totalTokens: number;
    };
}

/** 流式完成事件 */
export interface StreamCompleteEvent {
    taskId: string;
    success: boolean;
    response: string;
    executionTime: number;
    tier: 'direct' | 'fast' | 'vision' | 'smart';
    model?: string;
}

/** 流式聊天 Hook 返回值 */
export interface UseStreamingChatReturn {
    /** 当前累积的响应内容 */
    content: string;
    /** 推理内容（DeepSeek 等模型） */
    reasoningContent: string;
    /** 当前状态 */
    status: StreamingStatus;
    /** 错误信息 */
    error: string | null;
    /** 当前任务 ID */
    taskId: string | null;
    /** Token 使用情况 */
    usage: StreamChunkEvent['usage'] | null;
    /** 发送流式消息 */
    sendStreamMessage: (message: string, options?: { hasScreenshot?: boolean }) => Promise<void>;
    /** 取消当前流式请求 */
    cancelStream: () => Promise<void>;
    /** 重置状态 */
    reset: () => void;
}

/**
 * 流式聊天 Hook
 * @example
 * ```tsx
 * const { content, status, sendStreamMessage } = useStreamingChat();
 * 
 * // 发送流式消息
 * await sendStreamMessage("你好");
 * 
 * // 实时显示内容
 * <StreamingText text={content} status={status} />
 * ```
 */
export function useStreamingChat(): UseStreamingChatReturn {
    const [content, setContent] = useState('');
    const [reasoningContent, setReasoningContent] = useState('');
    const [status, setStatus] = useState<StreamingStatus>('idle');
    const [error, setError] = useState<string | null>(null);
    const [taskId, setTaskId] = useState<string | null>(null);
    const [usage, setUsage] = useState<StreamChunkEvent['usage'] | null>(null);

    const currentTaskIdRef = useRef<string | null>(null);

    // 监听流式块 (仅 Electron 模式)
    useEffect(() => {
        if (!isElectron()) return;

        const unsubscribe = window.aios.onStreamChunk((event: StreamChunkEvent) => {
            // 只处理当前任务的事件
            if (currentTaskIdRef.current && event.taskId !== currentTaskIdRef.current) {
                return;
            }

            if (event.content) {
                setContent(prev => prev + event.content);
            }
            if (event.reasoningContent) {
                setReasoningContent(prev => prev + event.reasoningContent);
            }
            if (event.toolCalls) {
                // Accumulate tool calls logic could be complex (merging chunks), 
                // but for now let's just expose the latest event or append. 
                // Given the type definition, toolCalls might be partial. 
                // We'll simplisticly assume we want to track 'active tool'.
                // For a full implementation we'd need a robust merger. 
                // Let's just store the LAST seen tool call for display "Calling X...".
                // Or better, let's update a separate state.
                // NOTE: effectively we need to change the Hook signature to return toolCalls.
            }
            if (event.usage) {
                setUsage(event.usage);
            }
        });

        return unsubscribe;
    }, []);

    // 监听流式完成 (仅 Electron 模式)
    useEffect(() => {
        if (!isElectron()) return;

        const unsubscribe = window.aios.onStreamComplete((event: StreamCompleteEvent) => {
            if (currentTaskIdRef.current && event.taskId !== currentTaskIdRef.current) {
                return;
            }

            if (event.success) {
                setStatus('completed');
            } else {
                setStatus('error');
                setError('流式响应失败');
            }
            currentTaskIdRef.current = null;
        });

        return unsubscribe;
    }, []);

    // 监听任务错误 (仅 Electron 模式)
    useEffect(() => {
        if (!isElectron()) return;

        const unsubscribe = window.aios.onTaskError((event) => {
            if (currentTaskIdRef.current && event.taskId !== currentTaskIdRef.current) {
                return;
            }

            setStatus('error');
            setError(event.error);
            currentTaskIdRef.current = null;
        });

        return unsubscribe;
    }, []);

    /** 发送流式消息 */
    const sendStreamMessage = useCallback(async (
        message: string,
        options?: { hasScreenshot?: boolean }
    ): Promise<void> => {
        try {
            // 重置状态
            setContent('');
            setReasoningContent('');
            setError(null);
            setUsage(null);
            setStatus('streaming');

            if (isElectron()) {
                // Electron 模式：使用流式 API
                const result = await window.aios.smartChatStream(message, {
                    hasScreenshot: options?.hasScreenshot,
                });
                setTaskId(result.taskId);
                currentTaskIdRef.current = result.taskId;
            } else {
                // Web 模式：使用非流式 API（暂时）
                const result = await api.smartChat(message, options?.hasScreenshot);
                setContent(result.response);
                setStatus(result.success ? 'completed' : 'error');
                if (!result.success) {
                    setError(result.response);
                }
            }
        } catch (err) {
            setStatus('error');
            setError(err instanceof Error ? err.message : '发送消息失败');
            currentTaskIdRef.current = null;
        }
    }, []);

    /** 取消当前流式请求 */
    const cancelStream = useCallback(async (): Promise<void> => {
        if (currentTaskIdRef.current && isElectron()) {
            await window.aios.cancelStream(currentTaskIdRef.current);
            setStatus('idle');
            currentTaskIdRef.current = null;
        }
    }, []);

    /** 重置状态 */
    const reset = useCallback(() => {
        setContent('');
        setReasoningContent('');
        setStatus('idle');
        setError(null);
        setTaskId(null);
        setUsage(null);
        currentTaskIdRef.current = null;
    }, []);

    return {
        content,
        reasoningContent,
        status,
        error,
        taskId,
        usage,
        sendStreamMessage,
        cancelStream,
        reset,
    };
}

export default useStreamingChat;

