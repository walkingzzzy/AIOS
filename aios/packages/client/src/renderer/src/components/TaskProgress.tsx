/**
 * TaskProgress - 任务进度组件
 */

import React from 'react';
import type { TaskProgressEvent, TaskStatus } from '../hooks/useTaskQueue';
import './TaskProgress.css';

interface TaskProgressProps {
    /** 当前任务列表 */
    tasks: TaskStatus[];
    /** 进度映射 */
    progress: Map<string, TaskProgressEvent>;
    /** 取消任务 */
    onCancel: (taskId: string) => void;
}

const STATUS_LABELS = {
    pending: '排队中',
    running: '执行中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
};

const STATUS_COLORS = {
    pending: '#6b7280',
    running: '#3b82f6',
    completed: '#10b981',
    failed: '#ef4444',
    cancelled: '#f59e0b',
};

export const TaskProgress: React.FC<TaskProgressProps> = ({
    tasks,
    progress,
    onCancel,
}) => {
    if (tasks.length === 0) {
        return (
            <div className="task-progress-empty">
                暂无任务
            </div>
        );
    }

    return (
        <div className="task-progress-list">
            {tasks.map(task => {
                const taskProgress = progress.get(task.taskId);
                const statusColor = STATUS_COLORS[task.status] || '#6b7280';
                const statusLabel = STATUS_LABELS[task.status] || task.status;

                return (
                    <div key={task.taskId} className="task-item">
                        <div className="task-header">
                            <span
                                className="task-status"
                                style={{ color: statusColor }}
                            >
                                {statusLabel}
                            </span>
                            {task.status === 'pending' && (
                                <button
                                    className="task-cancel"
                                    onClick={() => onCancel(task.taskId)}
                                >
                                    取消
                                </button>
                            )}
                        </div>

                        <div className="task-prompt">
                            {task.prompt.substring(0, 100)}
                            {task.prompt.length > 100 && '...'}
                        </div>

                        {task.status === 'running' && taskProgress && (
                            <div className="task-progress">
                                <div className="progress-bar">
                                    <div
                                        className="progress-fill"
                                        style={{ width: `${taskProgress.percentage}%` }}
                                    />
                                </div>
                                <div className="progress-text">
                                    {taskProgress.stepDescription || `${taskProgress.currentStep}/${taskProgress.totalSteps}`}
                                </div>
                            </div>
                        )}

                        {task.status === 'completed' && task.response && (
                            <div className="task-response">
                                {task.response.substring(0, 200)}
                                {task.response.length > 200 && '...'}
                            </div>
                        )}

                        {task.status === 'failed' && task.error && (
                            <div className="task-error">
                                {task.error}
                            </div>
                        )}
                    </div>
                );
            })}
        </div>
    );
};
