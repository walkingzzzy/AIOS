/**
 * A2AClient 集成测试（可选）
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { A2AServer } from '../../protocol/A2AServer.js';
import { A2AClient } from '../../protocol/A2AClient.js';

const shouldRun = process.env.AIOS_RUN_A2A === '1';
const describeA2A = shouldRun ? describe : describe.skip;
const host = '127.0.0.1';
const port = Number(process.env.AIOS_A2A_TEST_PORT || 41001);

const tokenSecret = 'aios-a2a-test-secret-0000000000000';

function createAgentCard() {
    return {
        id: 'aios-test',
        name: 'AIOS Test',
        description: 'A2A 集成测试',
        capabilities: ['*'],
        endpoint: `http://${host}:${port}/tasks`,
    };
}

describeA2A('A2AClient 集成测试', () => {
    let server: A2AServer;
    let client: A2AClient;

    beforeAll(async () => {
        server = new A2AServer({
            port,
            agentCard: createAgentCard(),
            tokenSecret,
        });
        server.on('task', ({ taskId }) => {
            server.updateTaskStatus(taskId, 'completed', { ok: true });
        });
        await server.start(port, host);
        const token = server.generateToken('client-1', ['*']);
        client = new A2AClient({ baseUrl: `http://${host}:${port}`, token });
    }, 20000);

    afterAll(() => {
        server?.stop();
    });

    it('能够完成 Agent Card 获取与任务提交', async () => {
        const card = await client.getAgentCard();
        expect(card.id).toBe('aios-test');

        const task = await client.submitTask({ prompt: 'ping' });
        expect(task.taskId).toBeDefined();

        const status = await client.getTaskStatus(task.taskId);
        expect(status.status).toBe('completed');
    });
});
