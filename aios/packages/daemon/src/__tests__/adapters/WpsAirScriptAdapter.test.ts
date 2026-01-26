/**
 * WpsAirScriptAdapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { WpsAirScriptAdapter } from '../../adapters/cn/WpsAirScriptAdapter';

describe('WpsAirScriptAdapter', () => {
    let adapter: WpsAirScriptAdapter;

    beforeEach(() => {
        adapter = new WpsAirScriptAdapter();
    });

    afterEach(() => {
        delete process.env.WPS_ACCESS_TOKEN;
        vi.unstubAllGlobals();
    });

    it('缺少 token 时应失败', async () => {
        const result = await adapter.invoke('wps_run_script', {
            file_id: 'file123',
            script: 'Application.Range("A1").Value = "Hi"',
        });
        expect(result.success).toBe(false);
        expect(result.error?.code).toBe('NO_TOKEN');
    });

    it('应提交脚本并返回结果', async () => {
        process.env.WPS_ACCESS_TOKEN = 'token';
        const fetchMock = vi.fn(async () => ({
            ok: true,
            json: async () => ({ code: 0, task_id: 'task123' }),
        }));
        vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);

        const result = await adapter.invoke('wps_run_script', {
            file_id: 'file123',
            script: 'Application.Range("A1").Value = "Hi"',
        });
        expect(result.success).toBe(true);
    });

    it('应查询脚本状态', async () => {
        process.env.WPS_ACCESS_TOKEN = 'token';
        const fetchMock = vi.fn(async () => ({
            ok: true,
            json: async () => ({ code: 0, status: 'done' }),
        }));
        vi.stubGlobal('fetch', fetchMock as unknown as typeof fetch);

        const result = await adapter.invoke('wps_get_script_status', {
            task_id: 'task123',
        });
        expect(result.success).toBe(true);
    });
});
