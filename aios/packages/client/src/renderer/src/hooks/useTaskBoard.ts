/**
 * useTaskBoard - 任务板 Hook
 * 监听并管理任务执行状态
 */

import { useState, useEffect, useCallback } from 'react';
import type { TaskGroup } from '../components/TaskBoard';

export interface UseTaskBoardResult {
    /** 任务组列表 */
    tasks: TaskGroup[];
    /** 取消任务 */
    cancelTask: (taskId: string) => Promise<void>;
    /** 重试任务 */
    retryTask: (taskId: string) => Promise<void>;
    /** 清除已完成的任务 */
    clearCompleted: () => void;
}

export function useTaskBoard(): UseTaskBoardResult {
    const [tasks, setTasks] = useState<TaskGroup[]>([]);

    // 取消任务
    const cancelTask = useCallback(async (taskId: string) => {
        try {
            await window.aios.cancelTask(taskId);
            setTasks(prev => prev.map(task =>
                task.id === taskId
                    ? { ...task, status: 'failed' as const }
                    : task
            ));
        } catch (error) {
            console.error('Failed to cancel task:', error);
        }
    }, []);

    // 重试任务
    const retryTask = useCallback(async (taskId: string) => {
        try {
            await window.aios.retryTask(taskId);
            setTasks(prev => prev.map(task =>
                task.id === taskId
                    ? {
                        ...task,
                        status: 'pending' as const,
                        subTasks: task.subTasks.map(st => ({
                            ...st,
                            status: 'pending' as const,
                            error: undefined,
                            result: undefined,
                        }))
                    }
                    : task
            ));
        } catch (error) {
            console.error('Failed to retry task:', error);
        }
    }, []);

    // 清除已完成的任务
    const clearCompleted = useCallback(() => {
        setTasks(prev => prev.filter(task =>
            task.status !== 'completed' && task.status !== 'failed'
        ));
    }, []);

    // 监听任务更新
    useEffect(() => {
        const unsubscribe = window.aios?.onTaskUpdate?.((update) => {
            setTasks(prev => {
                const existingIndex = prev.findIndex(t => t.id === update.taskId);

                if (existingIndex >= 0) {
                    // 更新现有任务
                    const updated = [...prev];
                    const task = updated[existingIndex];

                    if (update.type === 'task_status') {
                        task.status = update.status;
                    } else if (update.type === 'subtask_update') {
                        const subTaskIndex = task.subTasks.findIndex(
                            st => st.id === update.subTaskId
                        );
                        if (subTaskIndex >= 0) {
                            task.subTasks[subTaskIndex] = {
                                ...task.subTasks[subTaskIndex],
                                ...update.data,
                            };
                        }
                    }

                    return updated;
                } else if (update.type === 'task_created') {
                    // 创建新任务
                    return [...prev, update.task];
                }

                return prev;
            });
        });

        return unsubscribe;
    }, []);

    return {
        tasks,
        cancelTask,
        retryTask,
        clearCompleted,
    };
}
