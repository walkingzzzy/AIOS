/**
 * 存储系统单元测试
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import Database from 'better-sqlite3';
import {
    SessionRepository,
    TaskRepository,
    MessageRepository,
    SessionManager,
} from '../core/storage/index.js';

describe('SessionRepository', () => {
    let db: Database.Database;
    let repo: SessionRepository;

    beforeEach(() => {
        db = new Database(':memory:');
        repo = new SessionRepository(db);
    });

    afterEach(() => {
        db.close();
    });

    it('should create a session', () => {
        const session = repo.create('Test Session');
        expect(session.id).toBeDefined();
        expect(session.title).toBe('Test Session');
        expect(session.status).toBe('active');
    });

    it('should get a session by id', () => {
        const created = repo.create('My Session');
        const found = repo.get(created.id);
        expect(found).not.toBeNull();
        expect(found?.title).toBe('My Session');
    });

    it('should update session status', () => {
        const session = repo.create();
        const updated = repo.update(session.id, { status: 'completed' });
        expect(updated).toBe(true);

        const found = repo.get(session.id);
        expect(found?.status).toBe('completed');
    });

    it('should delete a session', () => {
        const session = repo.create();
        const deleted = repo.delete(session.id);
        expect(deleted).toBe(true);
        expect(repo.get(session.id)).toBeNull();
    });

    it('should query sessions with pagination', () => {
        repo.create('Session 1');
        repo.create('Session 2');
        repo.create('Session 3');

        const result = repo.query({ pageSize: 2 });
        expect(result.data.length).toBe(2);
        expect(result.total).toBe(3);
        expect(result.totalPages).toBe(2);
    });
});

describe('TaskRepository', () => {
    let db: Database.Database;
    let sessionRepo: SessionRepository;
    let taskRepo: TaskRepository;
    let sessionId: string;

    beforeEach(() => {
        db = new Database(':memory:');
        sessionRepo = new SessionRepository(db);
        taskRepo = new TaskRepository(db);
        sessionId = sessionRepo.create().id;
    });

    afterEach(() => {
        db.close();
    });

    it('should create a task', () => {
        const task = taskRepo.create(sessionId, 'Hello world', 'simple');
        expect(task.id).toBeDefined();
        expect(task.prompt).toBe('Hello world');
        expect(task.status).toBe('pending');
    });

    it('should update task status', () => {
        const task = taskRepo.create(sessionId, 'Test');
        taskRepo.updateStatus(task.id, 'completed', {
            response: 'Done',
            tier: 'fast',
            executionTime: 100,
        });

        const found = taskRepo.get(task.id);
        expect(found?.status).toBe('completed');
        expect(found?.response).toBe('Done');
        expect(found?.executionTime).toBe(100);
    });

    it('should get tasks by session', () => {
        taskRepo.create(sessionId, 'Task 1');
        taskRepo.create(sessionId, 'Task 2');

        const tasks = taskRepo.getBySession(sessionId);
        expect(tasks.length).toBe(2);
    });

    it('should get task stats', () => {
        taskRepo.create(sessionId, 'Task 1');
        const task2 = taskRepo.create(sessionId, 'Task 2');
        taskRepo.updateStatus(task2.id, 'completed');

        const stats = taskRepo.getStats(sessionId);
        expect(stats.total).toBe(2);
        expect(stats.completed).toBe(1);
    });
});

describe('MessageRepository', () => {
    let db: Database.Database;
    let sessionRepo: SessionRepository;
    let taskRepo: TaskRepository;
    let messageRepo: MessageRepository;
    let sessionId: string;

    beforeEach(() => {
        db = new Database(':memory:');
        sessionRepo = new SessionRepository(db);
        taskRepo = new TaskRepository(db); // 需要初始化以创建 tasks 表（外键约束）
        messageRepo = new MessageRepository(db);
        sessionId = sessionRepo.create().id;
    });

    afterEach(() => {
        db.close();
    });

    it('should create a message', () => {
        const msg = messageRepo.create(sessionId, 'user', 'Hello');
        expect(msg.id).toBeDefined();
        expect(msg.role).toBe('user');
        expect(msg.content).toBe('Hello');
    });

    it('should get messages by session', () => {
        messageRepo.create(sessionId, 'user', 'Hello');
        messageRepo.create(sessionId, 'assistant', 'Hi there!');

        const messages = messageRepo.getBySession(sessionId);
        expect(messages.length).toBe(2);
        expect(messages[0].role).toBe('user');
        expect(messages[1].role).toBe('assistant');
    });

    it('should get recent context messages', () => {
        for (let i = 0; i < 15; i++) {
            messageRepo.create(sessionId, 'user', `Message ${i}`);
        }

        const recent = messageRepo.getRecentForContext(sessionId, 5);
        expect(recent.length).toBe(5);
        // 验证消息按时间排序（ASC）
        expect(recent[0].createdAt).toBeLessThanOrEqual(recent[4].createdAt);
    });
});

describe('SessionManager', () => {
    let db: Database.Database;
    let manager: SessionManager;

    beforeEach(() => {
        db = new Database(':memory:');
        manager = new SessionManager(db);
    });

    afterEach(() => {
        db.close();
    });

    it('should create and manage sessions', () => {
        const session = manager.createSession('Test');
        expect(session.title).toBe('Test');
        expect(manager.getCurrentSessionId()).toBe(session.id);
    });

    it('should get or create session', () => {
        const session1 = manager.getOrCreateSession();
        const session2 = manager.getOrCreateSession();
        expect(session1.id).toBe(session2.id);
    });

    it('should create tasks with messages', () => {
        const task = manager.createTask('Hello', 'simple');
        expect(task.prompt).toBe('Hello');

        const messages = manager.getContextMessages();
        expect(messages.length).toBe(1);
        expect(messages[0].role).toBe('user');
    });

    it('should update task and add assistant message', () => {
        const task = manager.createTask('Hello');
        manager.updateTaskStatus(task.id, 'completed', {
            response: 'Hi there!',
        });

        const messages = manager.getContextMessages();
        expect(messages.length).toBe(2);
        expect(messages[1].role).toBe('assistant');
    });

    it('should get stats', () => {
        manager.createTask('Task 1');
        const task2 = manager.createTask('Task 2');
        manager.updateTaskStatus(task2.id, 'completed', { response: 'Done' });

        const stats = manager.getStats();
        expect(stats.totalTasks).toBe(2);
        expect(stats.completedTasks).toBe(1);
    });
});
