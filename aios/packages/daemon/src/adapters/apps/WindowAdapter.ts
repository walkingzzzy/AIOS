/**
 * 窗口管理适配器
 * 使用键盘快捷键模拟实现窗口控制
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';
import { runPlatformCommand } from '@aios/shared';

export class WindowAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.window';
    readonly name = '窗口管理';
    readonly description = '窗口移动、调整、平铺等控制';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'maximize',
            name: '最大化',
            description: '最大化当前窗口',
            permissionLevel: 'low',
        },
        {
            id: 'minimize',
            name: '最小化',
            description: '最小化当前窗口',
            permissionLevel: 'low',
        },
        {
            id: 'tile_left',
            name: '左半屏',
            description: '将窗口平铺到左半屏',
            permissionLevel: 'low',
        },
        {
            id: 'tile_right',
            name: '右半屏',
            description: '将窗口平铺到右半屏',
            permissionLevel: 'low',
        },
        {
            id: 'close_window',
            name: '关闭窗口',
            description: '关闭当前窗口',
            permissionLevel: 'low',
        },
        {
            id: 'switch_app',
            name: '切换应用',
            description: '切换到下一个应用',
            permissionLevel: 'low',
        },
        {
            id: 'fullscreen',
            name: '全屏',
            description: '切换全屏模式',
            permissionLevel: 'low',
        },
    ];

    async checkAvailability(): Promise<boolean> {
        const platform = this.getPlatform();

        if (platform === 'darwin') {
            // macOS: Check if accessibility permissions are granted
            try {
                const { execSync } = await import('child_process');
                // This AppleScript checks if System Events can be accessed
                execSync('osascript -e \'tell application "System Events" to return name of first process\'', {
                    timeout: 2000,
                    stdio: 'pipe'
                });
                return true;
            } catch {
                return false;
            }
        }

        if (platform === 'linux') {
            // Linux: Check if xdotool is available
            try {
                const { execSync } = await import('child_process');
                execSync('which xdotool', { stdio: 'pipe' });
                return true;
            } catch {
                return false;
            }
        }

        // Windows: Assume available
        return true;
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            switch (capability) {
                case 'maximize':
                    return this.maximize();
                case 'minimize':
                    return this.minimize();
                case 'tile_left':
                    return this.tileLeft();
                case 'tile_right':
                    return this.tileRight();
                case 'close_window':
                    return this.closeWindow();
                case 'switch_app':
                    return this.switchApp();
                case 'fullscreen':
                    return this.fullscreen();
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private async maximize(): Promise<AdapterResult> {
        await runPlatformCommand({
            darwin: 'osascript -e \'tell application "System Events" to keystroke "f" using {control down, command down}\'',
            win32: 'powershell -Command "(New-Object -ComObject WScript.Shell).SendKeys(\'^{UP}\')"',
            linux: 'xdotool key super+Up',
        });
        return this.success({ action: 'maximize' });
    }

    private async minimize(): Promise<AdapterResult> {
        await runPlatformCommand({
            darwin: 'osascript -e \'tell application "System Events" to keystroke "m" using command down\'',
            win32: 'powershell -Command "(New-Object -ComObject WScript.Shell).SendKeys(\'^{DOWN}\')"',
            linux: 'xdotool key super+h',
        });
        return this.success({ action: 'minimize' });
    }

    private async tileLeft(): Promise<AdapterResult> {
        await runPlatformCommand({
            darwin: 'osascript -e \'tell application "System Events" to keystroke "Left" using {control down, option down}\'',
            win32: 'powershell -Command "(New-Object -ComObject WScript.Shell).SendKeys(\'#{LEFT}\')"',
            linux: 'xdotool key super+Left',
        });
        return this.success({ action: 'tile_left' });
    }

    private async tileRight(): Promise<AdapterResult> {
        await runPlatformCommand({
            darwin: 'osascript -e \'tell application "System Events" to keystroke "Right" using {control down, option down}\'',
            win32: 'powershell -Command "(New-Object -ComObject WScript.Shell).SendKeys(\'#{RIGHT}\')"',
            linux: 'xdotool key super+Right',
        });
        return this.success({ action: 'tile_right' });
    }

    private async closeWindow(): Promise<AdapterResult> {
        await runPlatformCommand({
            darwin: 'osascript -e \'tell application "System Events" to keystroke "w" using command down\'',
            win32: 'powershell -Command "(New-Object -ComObject WScript.Shell).SendKeys(\'^w\')"',
            linux: 'xdotool key alt+F4',
        });
        return this.success({ action: 'close_window' });
    }

    private async switchApp(): Promise<AdapterResult> {
        await runPlatformCommand({
            darwin: 'osascript -e \'tell application "System Events" to keystroke tab using command down\'',
            win32: 'powershell -Command "(New-Object -ComObject WScript.Shell).SendKeys(\'%{TAB}\')"',
            linux: 'xdotool key alt+Tab',
        });
        return this.success({ action: 'switch_app' });
    }

    private async fullscreen(): Promise<AdapterResult> {
        await runPlatformCommand({
            darwin: 'osascript -e \'tell application "System Events" to keystroke "f" using {control down, command down}\'',
            win32: 'powershell -Command "(New-Object -ComObject WScript.Shell).SendKeys(\'{F11}\')"',
            linux: 'xdotool key F11',
        });
        return this.success({ action: 'fullscreen' });
    }
}

export const windowAdapter = new WindowAdapter();
