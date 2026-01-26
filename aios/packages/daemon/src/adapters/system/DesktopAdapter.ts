/**
 * 桌面设置适配器
 * 壁纸设置等桌面控制
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';
import { runPlatformCommand } from '@aios/shared';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

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
        {
            id: 'click',
            name: '点击',
            description: '在指定坐标点击',
            permissionLevel: 'medium',
            parameters: [
                { name: 'x', type: 'number', required: true, description: 'X坐标' },
                { name: 'y', type: 'number', required: true, description: 'Y坐标' },
            ],
        },
        {
            id: 'type_text',
            name: '输入文字',
            description: '输入文字',
            permissionLevel: 'medium',
            parameters: [
                { name: 'text', type: 'string', required: true, description: '要输入的文字' },
            ],
        },
        {
            id: 'scroll',
            name: '滚动',
            description: '滚动页面',
            permissionLevel: 'low',
            parameters: [
                { name: 'direction', type: 'string', required: true, description: 'up/down' },
                { name: 'amount', type: 'number', required: false, description: '滚动量' },
            ],
        },
    ];

    private ensureNumber(value: unknown, name: string): number | null {
        const num = Number(value);
        if (!Number.isFinite(num)) {
            return null;
        }
        return num;
    }

    async initialize(): Promise<void> {
        const mod = await import('wallpaper') as unknown as {
            default?: typeof wallpaper;
            get?: () => Promise<string>;
            set?: (imagePath: string) => Promise<void>;
        };
        wallpaper = mod.default ?? mod as typeof wallpaper;
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
                case 'click':
                    {
                        const x = this.ensureNumber(args.x, 'x');
                        const y = this.ensureNumber(args.y, 'y');
                        if (x === null || y === null) {
                            return this.failure('INVALID_PARAM', '参数 x/y 必须是有效数字');
                        }
                        return this.click(x, y);
                    }
                case 'type_text':
                    if (typeof args.text !== 'string' || !args.text) {
                        return this.failure('INVALID_PARAM', '参数 text 必须是非空字符串');
                    }
                    return this.typeText(args.text as string);
                case 'scroll':
                    {
                        const direction = args.direction as string;
                        if (direction !== 'up' && direction !== 'down') {
                            return this.failure('INVALID_PARAM', '参数 direction 必须是 up 或 down');
                        }
                        const amount = args.amount === undefined ? undefined : this.ensureNumber(args.amount, 'amount');
                        if (amount === null) {
                            return this.failure('INVALID_PARAM', '参数 amount 必须是有效数字');
                        }
                        return this.scroll(direction, amount);
                    }
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

    private async click(x: number, y: number): Promise<AdapterResult> {
        if (process.platform === 'win32') {
            const psScript = `
                Add-Type @"
                    using System;
                    using System.Runtime.InteropServices;
                    public class User32 {
                        [DllImport("user32.dll")]
                        public static extern bool SetCursorPos(int X, int Y);
                        [DllImport("user32.dll")]
                        public static extern void mouse_event(int dwFlags, int dx, int dy, int cButtons, int dwExtraInfo);
                    }
"@
                [User32]::SetCursorPos(${x}, ${y}) | Out-Null
                $MOUSEEVENTF_LEFTDOWN = 0x02
                $MOUSEEVENTF_LEFTUP = 0x04
                [User32]::mouse_event($MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                [User32]::mouse_event($MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            `.replace(/\n/g, ' ');
            await execFileAsync('powershell', ['-NoProfile', '-Command', psScript]);
        } else {
            await runPlatformCommand({
                darwin: `osascript -e 'tell application "System Events" to click at {${x}, ${y}}'`,
                linux: `xdotool mousemove ${x} ${y} click 1`,
                win32: '',
            });
        }
        return this.success({ clicked: true, x, y });
    }

    private async typeText(text: string): Promise<AdapterResult> {
        if (process.platform === 'darwin') {
            await execFileAsync('osascript', [
                '-e',
                'on run argv\n' +
                'tell application "System Events" to keystroke (item 1 of argv)\n' +
                'end run',
                '--',
                text,
            ]);
        } else if (process.platform === 'win32') {
            const encoded = Buffer.from(text, 'utf8').toString('base64');
            const psScript = `$bytes=[System.Convert]::FromBase64String("${encoded}");` +
                '$text=[System.Text.Encoding]::UTF8.GetString($bytes);' +
                'Add-Type -AssemblyName System.Windows.Forms;' +
                '[System.Windows.Forms.SendKeys]::SendWait($text)';
            await execFileAsync('powershell', ['-NoProfile', '-Command', psScript]);
        } else {
            await execFileAsync('xdotool', ['type', '--', text]);
        }
        return this.success({ typed: true, text });
    }

    private async scroll(direction: string, amount: number = 3): Promise<AdapterResult> {
        const scrollAmount = direction === 'up' ? amount : -amount;
        await runPlatformCommand({
            darwin: `osascript -e 'tell application "System Events" to scroll ${scrollAmount}'`,
            win32: `powershell -c "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('{${direction === 'up' ? 'PGUP' : 'PGDN'}}')"`,
            linux: `xdotool click --repeat ${amount} ${direction === 'up' ? 4 : 5}`,
        });
        return this.success({ scrolled: true, direction, amount });
    }
}

export const desktopAdapter = new DesktopAdapter();
