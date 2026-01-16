/**
 * 容错重试模块单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import Database from 'better-sqlite3';
import {
    RetryPolicy,
    RETRY_POLICIES,
    CheckpointManager,
} from '../core/resilience/index.js';

describe('RetryPolicy', () => {
    describe('execute', () => {
        it('should succeed on first attempt', async () => {
            const policy = new RetryPolicy({ maxRetries: 3 });
            const operation = vi.fn().mockResolvedValue('success');

            const result = await policy.execute(operation);

            expect(result.success).toBe(true);
            expect(result.data).toBe('success');
            expect(result.attempts).toBe(1);
            expect(operation).toHaveBeenCalledTimes(1);
        });

        it('should retry on failure and succeed', async () => {
            const policy = new RetryPolicy({
                maxRetries: 3,
                initialDelay: 10,
            });
            const operation = vi.fn()
                .mockRejectedValueOnce(new Error('network error'))
                .mockRejectedValueOnce(new Error('timeout'))
                .mockResolvedValue('success');

            const result = await policy.execute(operation);

            expect(result.success).toBe(true);
            expect(result.data).toBe('success');
            expect(result.attempts).toBe(3);
            expect(operation).toHaveBeenCalledTimes(3);
        });

        it('should fail after max retries', async () => {
            const policy = new RetryPolicy({
                maxRetries: 2,
                initialDelay: 10,
            });
            const operation = vi.fn().mockRejectedValue(new Error('network error'));

            const result = await policy.execute(operation);

            expect(result.success).toBe(false);
            expect(result.error?.message).toBe('network error');
            expect(result.attempts).toBe(3); // 1 initial + 2 retries
        });

        it('should not retry non-retryable errors', async () => {
            const policy = new RetryPolicy({ maxRetries: 3 });
            const operation = vi.fn().mockRejectedValue(new Error('unauthorized 401'));

            const result = await policy.execute(operation);

            expect(result.success).toBe(false);
            expect(result.attempts).toBe(1);
            expect(operation).toHaveBeenCalledTimes(1);
        });

        it('should call onRetry callback', async () => {
            const policy = new RetryPolicy({
                maxRetries: 2,
                initialDelay: 10,
            });
            const operation = vi.fn()
                .mockRejectedValueOnce(new Error('timeout'))
                .mockResolvedValue('success');
            const onRetry = vi.fn();

            await policy.execute(operation, onRetry);

            expect(onRetry).toHaveBeenCalledTimes(1);
            expect(onRetry).toHaveBeenCalledWith(expect.objectContaining({
                attempt: 1,
                maxRetries: 2,
            }));
        });
    });

    describe('calculateDelay', () => {
        it('should calculate exponential delay', () => {
            const policy = new RetryPolicy({
                initialDelay: 1000,
                backoffMultiplier: 2,
                maxDelay: 60000,
                jitter: 0,
            });

            expect(policy.calculateDelay(0)).toBe(1000);
            expect(policy.calculateDelay(1)).toBe(2000);
            expect(policy.calculateDelay(2)).toBe(4000);
        });

        it('should respect maxDelay', () => {
            const policy = new RetryPolicy({
                initialDelay: 1000,
                backoffMultiplier: 2,
                maxDelay: 3000,
                jitter: 0,
            });

            expect(policy.calculateDelay(10)).toBe(3000);
        });
    });

    describe('classifyError', () => {
        it('should classify network errors', () => {
            const policy = new RetryPolicy();
            expect(policy.classifyError(new Error('network error'))).toBe('network');
            expect(policy.classifyError(new Error('ECONNREFUSED'))).toBe('network');
        });

        it('should classify timeout errors', () => {
            const policy = new RetryPolicy();
            expect(policy.classifyError(new Error('timeout'))).toBe('timeout');
            expect(policy.classifyError(new Error('request timed out'))).toBe('timeout');
        });

        it('should classify rate limit errors', () => {
            const policy = new RetryPolicy();
            expect(policy.classifyError(new Error('429 too many requests'))).toBe('rate_limit');
        });

        it('should classify auth errors', () => {
            const policy = new RetryPolicy();
            expect(policy.classifyError(new Error('401 unauthorized'))).toBe('auth_error');
            expect(policy.classifyError(new Error('403 forbidden'))).toBe('auth_error');
        });
    });

    describe('RETRY_POLICIES', () => {
        it('should have predefined policies', () => {
            expect(RETRY_POLICIES.fast).toBeInstanceOf(RetryPolicy);
            expect(RETRY_POLICIES.standard).toBeInstanceOf(RetryPolicy);
            expect(RETRY_POLICIES.persistent).toBeInstanceOf(RetryPolicy);
            expect(RETRY_POLICIES.ai).toBeInstanceOf(RetryPolicy);
        });
    });
});

describe('CheckpointManager', () => {
    let db: Database.Database;
    let manager: CheckpointManager;

    beforeEach(() => {
        db = new Database(':memory:');
        manager = new CheckpointManager(db);
    });

    afterEach(() => {
        db.close();
    });

    describe('create', () => {
        it('should create a checkpoint', () => {
            const checkpoint = manager.create('task1', 5, { key: 'value' });

            expect(checkpoint.taskId).toBe('task1');
            expect(checkpoint.stepIndex).toBe(0);
            expect(checkpoint.totalSteps).toBe(5);
            expect(checkpoint.context.key).toBe('value');
        });
    });

    describe('load', () => {
        it('should load a checkpoint', () => {
            manager.create('task1', 5);
            const checkpoint = manager.load('task1');

            expect(checkpoint).not.toBeNull();
            expect(checkpoint?.taskId).toBe('task1');
        });

        it('should return null for non-existent task', () => {
            const checkpoint = manager.load('unknown');
            expect(checkpoint).toBeNull();
        });
    });

    describe('updateProgress', () => {
        it('should update step index', () => {
            manager.create('task1', 5);
            manager.updateProgress('task1', 2, { result: 'step2' });

            const checkpoint = manager.load('task1');
            expect(checkpoint?.stepIndex).toBe(2);
            expect(checkpoint?.completedResults.length).toBe(1);
        });
    });

    describe('delete', () => {
        it('should delete a checkpoint', () => {
            manager.create('task1', 5);
            const deleted = manager.delete('task1');

            expect(deleted).toBe(true);
            expect(manager.load('task1')).toBeNull();
        });
    });

    describe('getIncomplete', () => {
        it('should return incomplete checkpoints', () => {
            manager.create('task1', 5);
            manager.create('task2', 3);
            manager.updateProgress('task2', 3); // complete

            const incomplete = manager.getIncomplete();
            expect(incomplete.length).toBe(1);
            expect(incomplete[0].taskId).toBe('task1');
        });
    });
});
