/**
 * 桌面设置适配器
 * 壁纸设置等桌面控制
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';
import { runPlatformCommand } from '@aios/shared';

// 动态导入 wallpaper (ESM)
let wallpaper: {
    get: () => Promise<string>;
    set: (imagePath: string) => Promise<void>;
};

export class DesktopAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.desktop';
    readonly name = '桌面设置';
    readonly description = '壁纸和外观控制适配器';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'get_wallpaper',
            name: '获取壁纸',
            description: '获取当前壁纸路径',
            permissionLevel: 'public',
        },
        {
            id: 'set_wallpaper',
            name: '设置壁纸',
            description: '设置桌面壁纸',
            permissionLevel: 'low',
            parameters: [
                { name: 'path', type: 'string', required: true, description: '壁纸图片路径' },
            ],
        },
        {
            id: 'get_appearance',
            name: '获取外观模式',
            description: '获取当前外观模式 (dark/light)',
            permissionLevel: 'public',
        },
        {
            id: 'set_appearance',
            name: '设置外观模式',
            description: '设置外观模式',
            permissionLevel: 'low',
            parameters: [
                { name: 'mode', type: 'string', required: true, description: 'dark 或 light' },
            ],
        },
    ];

    async initialize(): Promise<void> {
        const mod = await import('wallpaper');
        wallpaper = mod.default || mod;
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
                case 'get_wallpaper':
                    return this.getWallpaper();
                case 'set_wallpaper':
                    return this.setWallpaper(args.path as string);
                case 'get_appearance':
                    return this.getAppearance();
                case 'set_appearance':
                    return this.setAppearance(args.mode as 'dark' | 'light');
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private async getWallpaper(): Promise<AdapterResult> {
        const path = await wallpaper.get();
        return this.success({ path });
    }

    private async setWallpaper(path: string): Promise<AdapterResult> {
        await wallpaper.set(path);
        return this.success({ path });
    }

    private async getAppearance(): Promise<AdapterResult> {
        const result = await runPlatformCommand({
            darwin: 'defaults read -g AppleInterfaceStyle 2>/dev/null || echo "Light"',
            win32: 'reg query "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" /v AppsUseLightTheme 2>nul | findstr "0x0" && echo Dark || echo Light',
            linux: 'gsettings get org.gnome.desktop.interface color-scheme 2>/dev/null || echo "default"',
        });

        let mode: 'dark' | 'light' = 'light';
        const output = result.stdout.toLowerCase();
        if (output.includes('dark')) {
            mode = 'dark';
        }

        return this.success({ mode });
    }

    private async setAppearance(mode: 'dark' | 'light'): Promise<AdapterResult> {
        await runPlatformCommand({
            darwin: mode === 'dark'
                ? 'osascript -e \'tell app "System Events" to tell appearance preferences to set dark mode to true\''
                : 'osascript -e \'tell app "System Events" to tell appearance preferences to set dark mode to false\'',
            win32: mode === 'dark'
                ? 'reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" /v AppsUseLightTheme /t REG_DWORD /d 0 /f'
                : 'reg add "HKCU\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" /v AppsUseLightTheme /t REG_DWORD /d 1 /f',
            linux: mode === 'dark'
                ? 'gsettings set org.gnome.desktop.interface color-scheme "prefer-dark"'
                : 'gsettings set org.gnome.desktop.interface color-scheme "prefer-light"',
        });

        return this.success({ mode });
    }
}

export const desktopAdapter = new DesktopAdapter();
