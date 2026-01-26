/**
 * A2AClient 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { A2AClient } from '../../protocol/A2AClient.js';

const jsonResponse = (data: unknown, ok = true, status = 200, statusText = 'OK') => ({
    ok,
    status,
    statusText,
    text: async () => JSON.stringify(data),
});

describe('A2AClient', () => {
    let fetchMock: ReturnType<typeof vi.fn>;

    beforeEach(() => {
        fetchMock = vi.fn(async (url: RequestInfo, init?: RequestInit) => {
            const target = typeof url === 'string' ? url : url.toString();
            if (target.endsWith('/.well-known/agent.json')) {
                return jsonResponse({ id: 'agent-1', name: 'AIOS', description: 'test', capabilities: [], endpoint: 'http://localhost/tasks' });
            }
            if (target.endsWith('/tasks') && init?.method === 'POST') {
                return jsonResponse({ taskId: 'task-1', status: 'pending' });
            }
            if (target.includes('/tasks/bad')) {
                return jsonResponse({ error: 'not_found' }, false, 404, 'NOT_FOUND');
            }
            if (target.includes('/tasks/')) {
                return jsonResponse({ taskId: 'task-1', status: 'completed', result: { ok: true } });
            }
            return jsonResponse({ error: 'unknown' }, false, 500, 'ERR');
        });
        vi.stubGlobal('fetch', fetchMock);
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('应该能获取 Agent Card 并返回数据', async () => {
        const client = new A2AClient({ baseUrl: 'http://localhost:3000' });
        const card = await client.getAgentCard();
        expect(card.id).toBe('agent-1');
    });

    it('应该携带 token 提交任务并返回 taskId', async () => {
        const client = new A2AClient({ baseUrl: 'http://localhost:3000', token: 'token-1' });
        const result = await client.submitTask({ prompt: 'hello' });
        expect(result.taskId).toBe('task-1');
        const call = fetchMock.mock.calls.find((item) => String(item[0]).endsWith('/tasks'));
        const headers = (call?.[1] as RequestInit | undefined)?.headers as Record<string, string> | undefined;
        expect(headers?.Authorization).toBe('Bearer token-1');
    });

    it('应该在接口失败时抛出错误', async () => {
        const client = new A2AClient({ baseUrl: 'http://localhost:3000' });
        await expect(client.getTaskStatus('bad')).rejects.toThrow('A2A 请求失败');
    });
});
