/**
 * 飞书适配器
 * 基于官方 Node SDK 的消息与文档能力
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';
import * as lark from '@larksuiteoapi/node-sdk';

type LarkClient = InstanceType<typeof lark.Client>;

type LarkRequestResult = {
    code?: number;
    msg?: string;
    data?: Record<string, unknown>;
};

export class FeishuAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.feishu';
    readonly name = '飞书';
    readonly description = '飞书开放平台适配器';

    private client: LarkClient | null = null;
    private appId = '';
    private appSecret = '';
    private tenantAccessToken: string | null = null;

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'feishu_send_card',
            name: '发送卡片消息',
            description: '发送交互式卡片消息',
            permissionLevel: 'medium',
            parameters: [
                { name: 'receive_id', type: 'string', required: true, description: '接收 ID' },
                { name: 'receive_id_type', type: 'string', required: false, description: '接收 ID 类型' },
                { name: 'card', type: 'object', required: true, description: '卡片 JSON' },
                { name: 'tenant_access_token', type: 'string', required: false, description: '租户访问令牌' },
            ],
        },
        {
            id: 'feishu_send_text',
            name: '发送文本消息',
            description: '发送文本消息',
            permissionLevel: 'medium',
            parameters: [
                { name: 'receive_id', type: 'string', required: true, description: '接收 ID' },
                { name: 'receive_id_type', type: 'string', required: false, description: '接收 ID 类型' },
                { name: 'text', type: 'string', required: true, description: '文本内容' },
                { name: 'tenant_access_token', type: 'string', required: false, description: '租户访问令牌' },
            ],
        },
        {
            id: 'feishu_create_doc',
            name: '创建文档',
            description: '创建飞书文档',
            permissionLevel: 'medium',
            parameters: [
                { name: 'title', type: 'string', required: true, description: '文档标题' },
                { name: 'folder_token', type: 'string', required: false, description: '父文件夹 token' },
                { name: 'tenant_access_token', type: 'string', required: false, description: '租户访问令牌' },
            ],
        },
    ];

    setCredentials(appId: string, appSecret: string, tenantAccessToken?: string): void {
        this.appId = appId;
        this.appSecret = appSecret;
        this.tenantAccessToken = tenantAccessToken || null;
        this.client = null;
    }

    setTenantAccessToken(token: string): void {
        this.tenantAccessToken = token;
    }

    async initialize(): Promise<void> {
        if (this.client) {
            return;
        }

        if (!this.appId) {
            this.appId = process.env.FEISHU_APP_ID || process.env.LARK_APP_ID || '';
        }
        if (!this.appSecret) {
            this.appSecret = process.env.FEISHU_APP_SECRET || process.env.LARK_APP_SECRET || '';
        }
        if (!this.tenantAccessToken) {
            this.tenantAccessToken = process.env.FEISHU_TENANT_ACCESS_TOKEN || process.env.LARK_TENANT_ACCESS_TOKEN || null;
        }

        if (!this.appId || !this.appSecret) {
            return;
        }

        this.client = new lark.Client({
            appId: this.appId,
            appSecret: this.appSecret,
            domain: 'https://open.feishu.cn',
        });
    }

    async checkAvailability(): Promise<boolean> {
        try {
            await this.initialize();
            return Boolean(this.client);
        } catch {
            return false;
        }
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            await this.initialize();
            if (!this.client) {
                return this.failure('NO_CREDENTIALS', '缺少飞书应用凭证');
            }

            switch (capability) {
                case 'feishu_send_card':
                    return this.sendCard({
                        receiveId: args.receive_id as string,
                        receiveIdType: (args.receive_id_type as string | undefined) || 'chat_id',
                        card: args.card as Record<string, unknown>,
                        tenantAccessToken: args.tenant_access_token as string | undefined,
                    });
                case 'feishu_send_text':
                    return this.sendText({
                        receiveId: args.receive_id as string,
                        receiveIdType: (args.receive_id_type as string | undefined) || 'chat_id',
                        text: args.text as string,
                        tenantAccessToken: args.tenant_access_token as string | undefined,
                    });
                case 'feishu_create_doc':
                    return this.createDoc({
                        title: args.title as string,
                        folderToken: args.folder_token as string | undefined,
                        tenantAccessToken: args.tenant_access_token as string | undefined,
                    });
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private async sendCard(options: {
        receiveId: string;
        receiveIdType: string;
        card: Record<string, unknown>;
        tenantAccessToken?: string;
    }): Promise<AdapterResult> {
        if (!options.receiveId || !options.card) {
            return this.failure('INVALID_PARAM', 'receive_id 与 card 为必填参数');
        }

        const request = this.client!.im.message.create({
            params: { receive_id_type: options.receiveIdType },
            data: {
                receive_id: options.receiveId,
                msg_type: 'interactive',
                content: JSON.stringify(options.card),
            },
        }) as unknown as { withTenantToken?: (token: string) => Promise<LarkRequestResult> };

        const response = await this.withTenantToken(request, options.tenantAccessToken);
        return this.normalizeResponse(response, '发送卡片失败');
    }

    private async sendText(options: {
        receiveId: string;
        receiveIdType: string;
        text: string;
        tenantAccessToken?: string;
    }): Promise<AdapterResult> {
        if (!options.receiveId || !options.text) {
            return this.failure('INVALID_PARAM', 'receive_id 与 text 为必填参数');
        }

        const request = this.client!.im.message.create({
            params: { receive_id_type: options.receiveIdType },
            data: {
                receive_id: options.receiveId,
                msg_type: 'text',
                content: JSON.stringify({ text: options.text }),
            },
        }) as unknown as { withTenantToken?: (token: string) => Promise<LarkRequestResult> };

        const response = await this.withTenantToken(request, options.tenantAccessToken);
        return this.normalizeResponse(response, '发送文本失败');
    }

    private async createDoc(options: {
        title: string;
        folderToken?: string;
        tenantAccessToken?: string;
    }): Promise<AdapterResult> {
        if (!options.title) {
            return this.failure('INVALID_PARAM', 'title 为必填参数');
        }

        const request = this.client!.docx.document.create({
            data: {
                title: options.title,
                folder_token: options.folderToken,
            },
        }) as unknown as { withTenantToken?: (token: string) => Promise<LarkRequestResult> };

        const response = await this.withTenantToken(request, options.tenantAccessToken);
        return this.normalizeResponse(response, '创建文档失败');
    }

    private async withTenantToken(
        request: { withTenantToken?: (token: string) => Promise<LarkRequestResult> },
        token?: string
    ): Promise<LarkRequestResult> {
        const tenantToken = token || this.tenantAccessToken;
        if (!request.withTenantToken) {
            return request as unknown as LarkRequestResult;
        }
        if (!tenantToken) {
            return { code: 1, msg: '缺少 tenant_access_token' };
        }
        return request.withTenantToken(tenantToken);
    }

    private normalizeResponse(response: LarkRequestResult, fallbackMessage: string): AdapterResult {
        const code = response.code ?? 0;
        if (code !== 0) {
            return this.failure('FEISHU_ERROR', response.msg || fallbackMessage);
        }
        return this.success({ data: response.data ?? response });
    }
}

export const feishuAdapter = new FeishuAdapter();
