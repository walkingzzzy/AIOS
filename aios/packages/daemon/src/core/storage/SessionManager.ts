/**
 * SessionManager - 会话管理器
 * 提供会话的高级管理功能
 */

import type Database from 'better-sqlite3';
import { SessionRepository, type SessionQueryOptions } from './SessionRepository.js';
import { TaskRepository, type TaskQueryOptions } from './TaskRepository.js';
import { MessageRepository, type MessageQueryOptions } from './MessageRepository.js';
import type {
    SessionRecord,
    TaskRecord,
    MessageRecord,
    MessageRole,
    StoredTaskStatus,
    PaginatedResult,
} from './types.js';

/**
 * 完整会话数据
 */
export interface FullSession extends SessionRecord {
    tasks: TaskRecord[];
    messages: MessageRecord[];
    stats: {
        taskCount: number;
        completedTasks: number;
        messageCount: number;
    };
}

/**
 * 会话管理器配置
 */
export interface SessionManagerConfig {
    /** 默认会话过期时间 (ms) */
    sessionExpiry?: number;
    /** 最大消息数 (用于上下文) */
    maxContextMessages?: number;
}

/**
 * 会话管理器
 */
export class SessionManager {
    private sessionRepo: SessionRepository;
    private taskRepo: TaskRepository;
    private messageRepo: MessageRepository;
    private config: Required<SessionManagerConfig>;
    private currentSessionId: string | null = null;

    constructor(db: Database.Database, config: SessionManagerConfig = {}) {
        this.sessionRepo = new SessionRepository(db);
        this.taskRepo = new TaskRepository(db);
        this.messageRepo = new MessageRepository(db);
        this.config = {
            sessionExpiry: config.sessionExpiry ?? 7 * 24 * 3600 * 1000, // 7 天
            maxContextMessages: config.maxContextMessages ?? 20,
        };
    }

    // ============ 会话管理 ============

    /**
     * 创建新会话
     */
    createSession(title?: string): SessionRecord {
        const session = this.sessionRepo.create(title);
        this.currentSessionId = session.id;
        console.log(`[SessionManager] Created session: ${session.id}`);
        return session;
    }

    /**
     * 获取或创建当前会话
     */
    getOrCreateSession(): SessionRecord {
        if (this.currentSessionId) {
            const session = this.sessionRepo.get(this.currentSessionId);
            if (session && session.status === 'active') {
                return session;
            }
        }

        // 尝试获取最近的活跃会话
        const activeSession = this.sessionRepo.getActive();
        if (activeSession) {
            this.currentSessionId = activeSession.id;
            return activeSession;
        }

        // 创建新会话
        return this.createSession();
    }

    /**
     * 获取会话
     */
    getSession(id: string): SessionRecord | null {
        return this.sessionRepo.get(id);
    }

    /**
     * 获取完整会话数据
     */
    getFullSession(id: string): FullSession | null {
        const session = this.sessionRepo.get(id);
        if (!session) return null;

        const tasks = this.taskRepo.getBySession(id);
        const messages = this.messageRepo.getBySession(id);
        const taskStats = this.taskRepo.getStats(id);

        return {
            ...session,
            tasks,
            messages,
            stats: {
                taskCount: taskStats.total,
                completedTasks: taskStats.completed,
                messageCount: messages.length,
            },
        };
    }

    /**
     * 查询会话列表
     */
    querySessions(options?: SessionQueryOptions): PaginatedResult<SessionRecord> {
        return this.sessionRepo.query(options);
    }

    /**
     * 结束当前会话
     */
    endSession(): boolean {
        if (!this.currentSessionId) return false;

        const result = this.sessionRepo.update(this.currentSessionId, { status: 'completed' });
        if (result) {
            console.log(`[SessionManager] Ended session: ${this.currentSessionId}`);
            this.currentSessionId = null;
        }
        return result;
    }

    /**
     * 删除会话
     */
    deleteSession(id: string): boolean {
        // 先删除关联数据
        this.messageRepo.deleteBySession(id);
        // 任务会通过 CASCADE 自动删除
        return this.sessionRepo.delete(id);
    }

    // ============ 任务管理 ============

    /**
     * 创建任务
     */
    createTask(prompt: string, type: string = 'simple', metadata?: Record<string, unknown>): TaskRecord {
        const session = this.getOrCreateSession();
        const task = this.taskRepo.create(session.id, prompt, type, metadata);

        // 同时创建用户消息
        this.messageRepo.create(session.id, 'user', prompt, task.id);

        // 更新会话时间
        this.sessionRepo.update(session.id, {});

        return task;
    }

    /**
     * 更新任务状态
     */
    updateTaskStatus(
        taskId: string,
        status: StoredTaskStatus,
        result?: { response?: string; tier?: string; model?: string; executionTime?: number; error?: string }
    ): boolean {
        const updated = this.taskRepo.updateStatus(taskId, status, result);

        // 如果任务完成，创建助手消息
        if (updated && result?.response && (status === 'completed' || status === 'failed')) {
            const task = this.taskRepo.get(taskId);
            if (task) {
                this.messageRepo.create(task.sessionId, 'assistant', result.response, taskId);
            }
        }

        return updated;
    }

    /**
     * 获取任务
     */
    getTask(id: string): TaskRecord | null {
        return this.taskRepo.get(id);
    }

    /**
     * 查询任务
     */
    queryTasks(options?: TaskQueryOptions): PaginatedResult<TaskRecord> {
        return this.taskRepo.query(options);
    }

    // ============ 消息管理 ============

    /**
     * 添加消息
     */
    addMessage(role: MessageRole, content: string, taskId?: string): MessageRecord {
        const session = this.getOrCreateSession();
        return this.messageRepo.create(session.id, role, content, taskId);
    }

    /**
     * 获取上下文消息
     */
    getContextMessages(sessionId?: string): MessageRecord[] {
        const id = sessionId ?? this.currentSessionId;
        if (!id) return [];

        return this.messageRepo.getRecentForContext(id, this.config.maxContextMessages);
    }

    /**
     * 查询消息
     */
    queryMessages(options?: MessageQueryOptions): PaginatedResult<MessageRecord> {
        return this.messageRepo.query(options);
    }

    // ============ 维护功能 ============

    /**
     * 清理过期会话
     */
    cleanup(): { expiredSessions: number } {
        const expiredSessions = this.sessionRepo.cleanupExpired(this.config.sessionExpiry);
        if (expiredSessions > 0) {
            console.log(`[SessionManager] Cleaned up ${expiredSessions} expired sessions`);
        }
        return { expiredSessions };
    }

    /**
     * 获取当前会话 ID
     */
    getCurrentSessionId(): string | null {
        return this.currentSessionId;
    }

    /**
     * 设置当前会话 ID
     */
    setCurrentSessionId(id: string | null): void {
        this.currentSessionId = id;
    }

    /**
     * 获取统计信息
     */
    getStats(): {
        activeSessions: number;
        totalSessions: number;
        totalTasks: number;
        completedTasks: number;
    } {
        const sessionStats = this.sessionRepo.query({ status: 'active', pageSize: 1 });
        const allSessions = this.sessionRepo.query({ pageSize: 1 });
        const taskStats = this.taskRepo.getStats();

        return {
            activeSessions: sessionStats.total,
            totalSessions: allSessions.total,
            totalTasks: taskStats.total,
            completedTasks: taskStats.completed,
        };
    }
}
