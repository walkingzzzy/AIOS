/**
 * 电源管理适配器
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';
import { runPlatformCommand } from '@aios/shared';

// 危险操作的最小延迟（秒）
const MIN_DANGEROUS_DELAY = 30;

export class PowerAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.power';
    readonly name = '电源管理';
    readonly description = '锁屏、休眠、关机等电源控制';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'lock_screen',
            name: '锁屏',
            description: '锁定屏幕',
            permissionLevel: 'low',
        },
        {
            id: 'sleep',
            name: '休眠',
            description: '进入休眠模式',
            permissionLevel: 'medium',
        },
        {
            id: 'shutdown',
            name: '关机',
            description: '关闭计算机（最少延迟30秒）',
            permissionLevel: 'critical',
            parameters: [
                { name: 'delay', type: 'number', required: false, description: '延迟秒数（最少30秒）' },
                { name: 'confirm', type: 'boolean', required: true, description: '确认执行（必须为true）' },
            ],
        },
        {
            id: 'restart',
            name: '重启',
            description: '重新启动计算机（最少延迟30秒）',
            permissionLevel: 'critical',
            parameters: [
                { name: 'delay', type: 'number', required: false, description: '延迟秒数（最少30秒）' },
                { name: 'confirm', type: 'boolean', required: true, description: '确认执行（必须为true）' },
            ],
        },
        {
            id: 'logout',
            name: '注销',
            description: '注销当前用户',
            permissionLevel: 'high',
            parameters: [
                { name: 'confirm', type: 'boolean', required: true, description: '确认执行（必须为true）' },
            ],
        },
        {
            id: 'cancel_shutdown',
            name: '取消关机',
            description: '取消计划中的关机或重启',
            permissionLevel: 'low',
        },
    ];

    async checkAvailability(): Promise<boolean> {
        return true; // 所有平台都支持电源管理
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            switch (capability) {
                case 'lock_screen':
                    return this.lockScreen();
                case 'sleep':
                    return this.doSleep();
                case 'shutdown':
                    return this.doShutdown(args.delay as number | undefined, args.confirm as boolean);
                case 'restart':
                    return this.doRestart(args.delay as number | undefined, args.confirm as boolean);
                case 'logout':
                    return this.doLogout(args.confirm as boolean);
                case 'cancel_shutdown':
                    return this.cancelShutdown();
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private async lockScreen(): Promise<AdapterResult> {
        await runPlatformCommand({
            darwin: 'pmset displaysleepnow',
            win32: 'rundll32.exe user32.dll,LockWorkStation',
            linux: 'loginctl lock-session',
        });
        return this.success({ action: 'lock_screen' });
    }

    private async doSleep(): Promise<AdapterResult> {
        await runPlatformCommand({
            darwin: 'pmset sleepnow',
            win32: 'rundll32.exe powrprof.dll,SetSuspendState 0,1,0',
            linux: 'systemctl suspend',
        });
        return this.success({ action: 'sleep' });
    }

    private async doShutdown(delay?: number, confirm?: boolean): Promise<AdapterResult> {
        // 安全检查：必须确认
        if (confirm !== true) {
            return this.failure('CONFIRMATION_REQUIRED', '关机操作需要确认，请设置 confirm: true');
        }

        // 强制最小延迟
        const delayArg = Math.max(delay || MIN_DANGEROUS_DELAY, MIN_DANGEROUS_DELAY);
        
        await runPlatformCommand({
            darwin: `shutdown -h +${Math.ceil(delayArg / 60)}`,
            win32: `shutdown /s /t ${delayArg}`,
            linux: `shutdown -h +${Math.ceil(delayArg / 60)}`,
        });
        
        return this.success({ 
            action: 'shutdown', 
            delay: delayArg,
            message: `系统将在 ${delayArg} 秒后关机，可使用 cancel_shutdown 取消`
        });
    }

    private async doRestart(delay?: number, confirm?: boolean): Promise<AdapterResult> {
        // 安全检查：必须确认
        if (confirm !== true) {
            return this.failure('CONFIRMATION_REQUIRED', '重启操作需要确认，请设置 confirm: true');
        }

        // 强制最小延迟
        const delayArg = Math.max(delay || MIN_DANGEROUS_DELAY, MIN_DANGEROUS_DELAY);
        
        await runPlatformCommand({
            darwin: `shutdown -r +${Math.ceil(delayArg / 60)}`,
            win32: `shutdown /r /t ${delayArg}`,
            linux: `shutdown -r +${Math.ceil(delayArg / 60)}`,
        });
        
        return this.success({ 
            action: 'restart', 
            delay: delayArg,
            message: `系统将在 ${delayArg} 秒后重启，可使用 cancel_shutdown 取消`
        });
    }

    private async doLogout(confirm?: boolean): Promise<AdapterResult> {
        // 安全检查：必须确认
        if (confirm !== true) {
            return this.failure('CONFIRMATION_REQUIRED', '注销操作需要确认，请设置 confirm: true');
        }

        await runPlatformCommand({
            darwin: 'osascript -e \'tell app "System Events" to log out\'',
            win32: 'shutdown /l',
            linux: 'loginctl terminate-user $USER',
        });
        return this.success({ action: 'logout' });
    }

    private async cancelShutdown(): Promise<AdapterResult> {
        await runPlatformCommand({
            darwin: 'killall shutdown 2>/dev/null || true',
            win32: 'shutdown /a',
            linux: 'shutdown -c',
        });
        return this.success({ action: 'cancel_shutdown', message: '已取消计划中的关机/重启' });
    }
}

export const powerAdapter = new PowerAdapter();
