/**
 * 通知适配器
 * 跨平台桌面通知
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';

// 动态导入 node-notifier
let notifier: {
    notify: (
        options: {
            title: string;
            message: string;
            icon?: string;
            sound?: boolean;
            wait?: boolean;
        },
        callback?: (err: Error | null, response: unknown) => void
    ) => void;
};

export class NotificationAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.notification';
    readonly name = '桌面通知';
    readonly description = '跨平台桌面通知适配器';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'notify',
            name: '发送通知',
            description: '发送桌面通知',
            permissionLevel: 'low',
            parameters: [
                { name: 'title', type: 'string', required: true, description: '通知标题' },
                { name: 'message', type: 'string', required: true, description: '通知内容' },
                { name: 'icon', type: 'string', required: false, description: '图标路径' },
                { name: 'sound', type: 'boolean', required: false, description: '是否播放声音' },
            ],
        },
    ];

    async initialize(): Promise<void> {
        const mod = await import('node-notifier');
        notifier = mod.default || mod;
    }

    async checkAvailability(): Promise<boolean> {
        try {
            await this.initialize();
            return true;
        } catch {
            return false;
        }
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            switch (capability) {
                case 'notify':
                    return this.notify(
                        args.title as string,
                        args.message as string,
                        args.icon as string | undefined,
                        args.sound as boolean | undefined
                    );
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private notify(
        title: string,
        message: string,
        icon?: string,
        sound?: boolean
    ): Promise<AdapterResult> {
        return new Promise((resolve) => {
            if (!title || !message) {
                resolve(this.failure('INVALID_ARGS', '标题和内容不能为空'));
                return;
            }

            notifier.notify(
                {
                    title,
                    message,
                    icon,
                    sound: sound ?? true,
                    wait: false,
                },
                (err) => {
                    if (err) {
                        console.error('[NotificationAdapter] notify failed:', err);
                        resolve(this.failure('NOTIFY_FAILED', err.message));
                    } else {
                        resolve(this.success({ title, message, sent: true }));
                    }
                }
            );
        });
    }
}

export const notificationAdapter = new NotificationAdapter();
