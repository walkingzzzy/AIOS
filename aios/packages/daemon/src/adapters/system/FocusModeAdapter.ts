/**
 * 专注模式适配器
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';
import { runPlatformCommand } from '@aios/shared';

export class FocusModeAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.focusmode';
    readonly name = '专注模式';
    readonly description = '管理勿扰模式和专注状态';

    private focusTimer: NodeJS.Timeout | null = null;
    private focusEndTime: number | null = null;

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'dnd_status',
            name: '勿扰状态',
            description: '获取勿扰模式状态',
            permissionLevel: 'low',
        },
        {
            id: 'dnd_toggle',
            name: '勿扰开关',
            description: '开启或关闭勿扰模式',
            permissionLevel: 'medium',
            parameters: [
                { name: 'enabled', type: 'boolean', required: true, description: '是否开启' },
            ],
        },
        {
            id: 'focus_start',
            name: '开始专注',
            description: '开始专注模式（开启勿扰+可选时长）',
            permissionLevel: 'medium',
            parameters: [
                { name: 'duration', type: 'number', required: false, description: '专注时长（分钟）' },
            ],
        },
        {
            id: 'focus_stop',
            name: '结束专注',
            description: '结束专注模式',
            permissionLevel: 'medium',
        },
    ];

    async checkAvailability(): Promise<boolean> {
        return this.getPlatform() === 'darwin'; // 目前仅支持 macOS
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            switch (capability) {
                case 'dnd_status':
                    return this.getDndStatus();
                case 'dnd_toggle':
                    return this.toggleDnd(args.enabled as boolean);
                case 'focus_start':
                    return this.startFocus(args.duration as number | undefined);
                case 'focus_stop':
                    return this.stopFocus();
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private async getDndStatus(): Promise<AdapterResult> {
        if (this.getPlatform() !== 'darwin') {
            return this.failure('UNSUPPORTED_PLATFORM', '当前平台不支持勿扰模式查询');
        }

        const { stdout } = await runPlatformCommand({
            darwin: 'defaults -currentHost read com.apple.notificationcenterui doNotDisturb 2>/dev/null || echo "0"',
        });

        const trimmed = stdout.trim().toLowerCase();
        const enabled = trimmed === '1' || trimmed === 'true' || trimmed === 'yes';

        return this.success({
            enabled,
            focusActive: this.focusEndTime !== null,
            focusEndTime: this.focusEndTime,
        });
    }

    private async toggleDnd(enabled: boolean): Promise<AdapterResult> {
        if (this.getPlatform() !== 'darwin') {
            return this.failure('UNSUPPORTED_PLATFORM', '当前平台不支持勿扰模式');
        }

        const command = enabled
            ? 'defaults -currentHost write com.apple.notificationcenterui doNotDisturb -boolean true; ' +
              'defaults -currentHost write com.apple.notificationcenterui doNotDisturbDate -date "$(date -u +%Y-%m-%dT%H:%M:%S.000Z)"; ' +
              'killall NotificationCenter 2>/dev/null || true'
            : 'defaults -currentHost write com.apple.notificationcenterui doNotDisturb -boolean false; ' +
              'killall NotificationCenter 2>/dev/null || true';

        const result = await runPlatformCommand({ darwin: command });
        if (result.exitCode !== 0) {
            return this.failure('DND_TOGGLE_FAILED', result.stderr || 'Failed to toggle DND');
        }

        return this.success({ enabled, action: 'dnd_toggle' });
    }

    private async startFocus(duration?: number): Promise<AdapterResult> {
        // 开启勿扰
        const dndResult = await this.toggleDnd(true);
        if (!dndResult.success) {
            return dndResult;
        }

        // 设置定时器
        if (duration && duration > 0) {
            if (this.focusTimer) {
                clearTimeout(this.focusTimer);
            }
            this.focusEndTime = Date.now() + duration * 60 * 1000;
            this.focusTimer = setTimeout(() => {
                void this.stopFocus().catch((error) => {
                    console.error('[FocusModeAdapter] Failed to stop focus:', error);
                });
            }, duration * 60 * 1000);
        }

        return this.success({
            action: 'focus_start',
            duration,
            endTime: this.focusEndTime,
        });
    }

    private async stopFocus(): Promise<AdapterResult> {
        // 清除定时器
        if (this.focusTimer) {
            clearTimeout(this.focusTimer);
            this.focusTimer = null;
        }
        this.focusEndTime = null;

        // 关闭勿扰
        const dndResult = await this.toggleDnd(false);
        if (!dndResult.success) {
            return dndResult;
        }

        return this.success({ action: 'focus_stop' });
    }

    async shutdown(): Promise<void> {
        if (this.focusTimer) {
            clearTimeout(this.focusTimer);
            this.focusTimer = null;
        }
    }
}

export const focusModeAdapter = new FocusModeAdapter();
