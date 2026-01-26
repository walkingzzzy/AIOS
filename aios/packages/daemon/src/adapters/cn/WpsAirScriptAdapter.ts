/**
 * WPS AirScript 适配器
 * 基于金山文档开放平台执行脚本
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';

const KDOCS_SCRIPT_BASE = 'https://developer.kdocs.cn/api/v1/openapi/personal';

export class WpsAirScriptAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.wps_airscript';
    readonly name = 'WPS AirScript';
    readonly description = '金山文档 AirScript 脚本执行适配器';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'wps_run_script',
            name: '执行脚本',
            description: '提交 AirScript 脚本并返回任务 ID',
            permissionLevel: 'medium',
            parameters: [
                { name: 'file_id', type: 'string', required: true, description: '文件 ID' },
                { name: 'script', type: 'string', required: true, description: 'AirScript 脚本内容' },
                { name: 'access_token', type: 'string', required: false, description: '访问令牌' },
            ],
        },
        {
            id: 'wps_get_script_status',
            name: '查询脚本状态',
            description: '查询脚本执行状态',
            permissionLevel: 'low',
            parameters: [
                { name: 'task_id', type: 'string', required: true, description: '任务 ID' },
                { name: 'access_token', type: 'string', required: false, description: '访问令牌' },
            ],
        },
    ];

    async checkAvailability(): Promise<boolean> {
        return true;
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            switch (capability) {
                case 'wps_run_script':
                    return this.runScript(
                        args.file_id as string,
                        args.script as string,
                        args.access_token as string | undefined
                    );
                case 'wps_get_script_status':
                    return this.getScriptStatus(
                        args.task_id as string,
                        args.access_token as string | undefined
                    );
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private async runScript(fileId: string, script: string, token?: string): Promise<AdapterResult> {
        if (!fileId || !script) {
            return this.failure('INVALID_PARAM', 'file_id 与 script 为必填参数');
        }

        const accessToken = this.resolveAccessToken(token);
        if (!accessToken) {
            return this.failure('NO_TOKEN', '缺少 WPS access_token');
        }

        const url = `${KDOCS_SCRIPT_BASE}/files/${encodeURIComponent(fileId)}/script?access_token=${encodeURIComponent(accessToken)}`;
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ script }),
        });

        const data = await response.json() as Record<string, unknown>;
        if (!response.ok) {
            return this.failure('WPS_SCRIPT_FAILED', `脚本提交失败: ${response.status}`);
        }
        if (typeof data.code === 'number' && data.code !== 0) {
            return this.failure('WPS_SCRIPT_FAILED', String(data.msg || '脚本提交失败'));
        }

        return this.success({ response: data });
    }

    private async getScriptStatus(taskId: string, token?: string): Promise<AdapterResult> {
        if (!taskId) {
            return this.failure('INVALID_PARAM', 'task_id 为必填参数');
        }

        const accessToken = this.resolveAccessToken(token);
        if (!accessToken) {
            return this.failure('NO_TOKEN', '缺少 WPS access_token');
        }

        const url = `${KDOCS_SCRIPT_BASE}/script/status?access_token=${encodeURIComponent(accessToken)}&task_id=${encodeURIComponent(taskId)}`;
        const response = await fetch(url, { method: 'GET' });
        const data = await response.json() as Record<string, unknown>;
        if (!response.ok) {
            return this.failure('WPS_STATUS_FAILED', `状态查询失败: ${response.status}`);
        }
        if (typeof data.code === 'number' && data.code !== 0) {
            return this.failure('WPS_STATUS_FAILED', String(data.msg || '状态查询失败'));
        }

        return this.success({ response: data });
    }

    private resolveAccessToken(token?: string): string | null {
        return token || process.env.WPS_ACCESS_TOKEN || process.env.KDOCS_ACCESS_TOKEN || null;
    }
}

export const wpsAirScriptAdapter = new WpsAirScriptAdapter();
