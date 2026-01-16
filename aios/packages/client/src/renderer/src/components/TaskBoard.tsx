/**
 * TaskBoard - 任务板组件
 * 显示并行子任务执行状态和进度
 */

import React, { useState, useEffect } from 'react';
import './TaskBoard.css';

export interface SubTask {
    id: string;
    description: string;
    status: 'pending' | 'running' | 'completed' | 'failed';
    progress?: number;
    result?: string;
    error?: string;
    startTime?: number;
    endTime?: number;
}

export interface TaskGroup {
    id: string;
    title: string;
    status: 'pending' | 'running' | 'completed' | 'failed';
    subTasks: SubTask[];
    createdAt: number;
}

interface TaskBoardProps {
    tasks: TaskGroup[];
    onCancel?: (taskId: string) => void;
    onRetry?: (taskId: string) => void;
    className?: string;
}

const TaskBoard: React.FC<TaskBoardProps> = ({
    tasks,
    onCancel,
    onRetry,
    className = '',
}) => {
    const [expandedTasks, setExpandedTasks] = useState<Set<string>>(new Set());

    const toggleExpand = (taskId: string) => {
        setExpandedTasks((prev) => {
            const next = new Set(prev);
            if (next.has(taskId)) {
                next.delete(taskId);
            } else {
                next.add(taskId);
            }
            return next;
        });
    };

    const getStatusIcon = (status: SubTask['status']) => {
        switch (status) {
            case 'pending':
                return '⏳';
            case 'running':
                return '🔄';
            case 'completed':
                return '✅';
            case 'failed':
                return '❌';
            default:
                return '⚪';
        }
    };

    const getStatusColor = (status: SubTask['status']) => {
        switch (status) {
            case 'pending':
                return '#888';
            case 'running':
                return '#4fc3f7';
            case 'completed':
                return '#66bb6a';
            case 'failed':
                return '#ef5350';
            default:
                return '#888';
        }
    };

    const calculateGroupProgress = (group: TaskGroup): number => {
        if (group.subTasks.length === 0) return 0;
        const completed = group.subTasks.filter(
            (t) => t.status === 'completed' || t.status === 'failed'
        ).length;
        return Math.round((completed / group.subTasks.length) * 100);
    };

    const formatDuration = (start?: number, end?: number): string => {
        if (!start) return '-';
        const endTime = end || Date.now();
        const duration = endTime - start;
        if (duration < 1000) return `${duration}ms`;
        if (duration < 60000) return `${(duration / 1000).toFixed(1)}s`;
        return `${Math.floor(duration / 60000)}m ${Math.floor((duration % 60000) / 1000)}s`;
    };

    if (tasks.length === 0) {
        return (
            <div className={`task-board empty ${className}`}>
                <div className="empty-state">
                    <span className="empty-icon">📋</span>
                    <p>暂无并行任务</p>
                </div>
            </div>
        );
    }

    return (
        <div className={`task-board ${className}`}>
            <div className="task-board-header">
                <h3>任务执行板</h3>
                <span className="task-count">{tasks.length} 个任务组</span>
            </div>
            <div className="task-groups">
                {tasks.map((group) => (
                    <div
                        key={group.id}
                        className={`task-group ${group.status}`}
                    >
                        <div
                            className="group-header"
                            onClick={() => toggleExpand(group.id)}
                        >
                            <div className="group-info">
                                <span className="group-status-icon">
                                    {getStatusIcon(group.status as SubTask['status'])}
                                </span>
                                <span className="group-title">{group.title}</span>
                            </div>
                            <div className="group-meta">
                                <span className="progress-text">
                                    {calculateGroupProgress(group)}%
                                </span>
                                <span className="subtask-count">
                                    {group.subTasks.filter((t) => t.status === 'completed').length}/
                                    {group.subTasks.length}
                                </span>
                                <button className="expand-btn">
                                    {expandedTasks.has(group.id) ? '▲' : '▼'}
                                </button>
                            </div>
                        </div>
                        <div className="group-progress-bar">
                            <div
                                className="progress-fill"
                                style={{
                                    width: `${calculateGroupProgress(group)}%`,
                                    backgroundColor: getStatusColor(group.status as SubTask['status']),
                                }}
                            />
                        </div>
                        {expandedTasks.has(group.id) && (
                            <div className="subtasks-list">
                                {group.subTasks.map((subTask) => (
                                    <div
                                        key={subTask.id}
                                        className={`subtask-item ${subTask.status}`}
                                    >
                                        <div className="subtask-header">
                                            <span className="subtask-status">
                                                {getStatusIcon(subTask.status)}
                                            </span>
                                            <span className="subtask-desc">
                                                {subTask.description}
                                            </span>
                                            <span className="subtask-duration">
                                                {formatDuration(subTask.startTime, subTask.endTime)}
                                            </span>
                                        </div>
                                        {subTask.progress !== undefined && subTask.status === 'running' && (
                                            <div className="subtask-progress">
                                                <div
                                                    className="progress-fill"
                                                    style={{ width: `${subTask.progress}%` }}
                                                />
                                            </div>
                                        )}
                                        {subTask.result && (
                                            <div className="subtask-result">
                                                <pre>{subTask.result}</pre>
                                            </div>
                                        )}
                                        {subTask.error && (
                                            <div className="subtask-error">
                                                <span className="error-icon">⚠️</span>
                                                {subTask.error}
                                            </div>
                                        )}
                                    </div>
                                ))}
                            </div>
                        )}
                        {group.status === 'running' && onCancel && (
                            <div className="group-actions">
                                <button
                                    className="cancel-btn"
                                    onClick={() => onCancel(group.id)}
                                >
                                    取消任务
                                </button>
                            </div>
                        )}
                        {group.status === 'failed' && onRetry && (
                            <div className="group-actions">
                                <button
                                    className="retry-btn"
                                    onClick={() => onRetry(group.id)}
                                >
                                    重试
                                </button>
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
};

export default TaskBoard;
