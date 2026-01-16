/**
 * 截图适配器
 * 跨平台截图功能
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { runPlatformCommand, getPlatform } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';
import { exec } from 'child_process';
import { promisify } from 'util';
import { existsSync, mkdirSync, readFileSync, unlinkSync } from 'fs';
import { join } from 'path';
import { tmpdir, homedir } from 'os';

const execAsync = promisify(exec);

export class ScreenshotAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.screenshot';
    readonly name = '截图';
    readonly description = '跨平台截图功能';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'capture_screen',
            name: '截取全屏',
            description: '截取整个屏幕',
            permissionLevel: 'low',
            parameters: [
                { name: 'save_path', type: 'string', required: false, description: '保存路径（可选）' },
            ],
        },
        {
            id: 'capture_window',
            name: '截取窗口',
            description: '截取当前活动窗口',
            permissionLevel: 'low',
            parameters: [
                { name: 'save_path', type: 'string', required: false, description: '保存路径（可选）' },
            ],
        },
        {
            id: 'capture_region',
            name: '截取区域',
            description: '截取指定区域（交互式选择）',
            permissionLevel: 'low',
            parameters: [
                { name: 'save_path', type: 'string', required: false, description: '保存路径（可选）' },
            ],
        },
        {
            id: 'get_screenshot_dir',
            name: '获取截图目录',
            description: '获取默认截图保存目录',
            permissionLevel: 'public',
        },
    ];

    private screenshotDir: string;

    constructor() {
        super();
        // 默认截图目录
        this.screenshotDir = join(homedir(), 'Pictures', 'AIOS Screenshots');
    }

    async initialize(): Promise<void> {
        // 确保截图目录存在
        if (!existsSync(this.screenshotDir)) {
            mkdirSync(this.screenshotDir, { recursive: true });
        }
    }

    async checkAvailability(): Promise<boolean> {
        const platform = getPlatform();
        try {
            if (platform === 'darwin') {
                // macOS 使用 screencapture
                await execAsync('which screencapture');
                return true;
            } else if (platform === 'win32') {
                // Windows 使用 PowerShell
                return true;
            } else {
                // Linux 检查 gnome-screenshot 或 scrot
                try {
                    await execAsync('which gnome-screenshot');
                    return true;
                } catch {
                    await execAsync('which scrot');
                    return true;
                }
            }
        } catch {
            return false;
        }
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            switch (capability) {
                case 'capture_screen':
                    return this.captureScreen(args.save_path as string | undefined);
                case 'capture_window':
                    return this.captureWindow(args.save_path as string | undefined);
                case 'capture_region':
                    return this.captureRegion(args.save_path as string | undefined);
                case 'get_screenshot_dir':
                    return this.getScreenshotDir();
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private generateFilename(): string {
        const now = new Date();
        const timestamp = now.toISOString().replace(/[:.]/g, '-').slice(0, 19);
        return `screenshot-${timestamp}.png`;
    }

    private async captureScreen(savePath?: string): Promise<AdapterResult> {
        const filename = this.generateFilename();
        const outputPath = savePath || join(this.screenshotDir, filename);
        const platform = getPlatform();

        // 确保目录存在
        const dir = join(outputPath, '..');
        if (!existsSync(dir)) {
            mkdirSync(dir, { recursive: true });
        }

        if (platform === 'darwin') {
            await execAsync(`screencapture -x "${outputPath}"`);
        } else if (platform === 'win32') {
            // Windows PowerShell 截图
            const psScript = `
                Add-Type -AssemblyName System.Windows.Forms
                $screen = [System.Windows.Forms.Screen]::PrimaryScreen
                $bitmap = New-Object System.Drawing.Bitmap($screen.Bounds.Width, $screen.Bounds.Height)
                $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
                $graphics.CopyFromScreen($screen.Bounds.Location, [System.Drawing.Point]::Empty, $screen.Bounds.Size)
                $bitmap.Save("${outputPath.replace(/\\/g, '\\\\')}")
                $graphics.Dispose()
                $bitmap.Dispose()
            `;
            await execAsync(`powershell -Command "${psScript.replace(/"/g, '\\"').replace(/\n/g, ' ')}"`);
        } else {
            // Linux
            try {
                await execAsync(`gnome-screenshot -f "${outputPath}"`);
            } catch {
                await execAsync(`scrot "${outputPath}"`);
            }
        }

        return this.success({
            path: outputPath,
            filename,
            type: 'fullscreen',
        });
    }

    private async captureWindow(savePath?: string): Promise<AdapterResult> {
        const filename = this.generateFilename();
        const outputPath = savePath || join(this.screenshotDir, filename);
        const platform = getPlatform();

        // 确保目录存在
        const dir = join(outputPath, '..');
        if (!existsSync(dir)) {
            mkdirSync(dir, { recursive: true });
        }

        if (platform === 'darwin') {
            // -l 参数需要窗口 ID，使用 -w 交互式选择
            await execAsync(`screencapture -x -w "${outputPath}"`);
        } else if (platform === 'win32') {
            // Windows 截取活动窗口
            const psScript = `
                Add-Type -AssemblyName System.Windows.Forms
                Add-Type @"
                    using System;
                    using System.Runtime.InteropServices;
                    public class Win32 {
                        [DllImport("user32.dll")]
                        public static extern IntPtr GetForegroundWindow();
                        [DllImport("user32.dll")]
                        public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
                    }
                    public struct RECT {
                        public int Left, Top, Right, Bottom;
                    }
"@
                $hwnd = [Win32]::GetForegroundWindow()
                $rect = New-Object RECT
                [Win32]::GetWindowRect($hwnd, [ref]$rect)
                $width = $rect.Right - $rect.Left
                $height = $rect.Bottom - $rect.Top
                $bitmap = New-Object System.Drawing.Bitmap($width, $height)
                $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
                $graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, [System.Drawing.Size]::new($width, $height))
                $bitmap.Save("${outputPath.replace(/\\/g, '\\\\')}")
                $graphics.Dispose()
                $bitmap.Dispose()
            `;
            await execAsync(`powershell -Command "${psScript.replace(/"/g, '\\"').replace(/\n/g, ' ')}"`);
        } else {
            // Linux
            try {
                await execAsync(`gnome-screenshot -w -f "${outputPath}"`);
            } catch {
                await execAsync(`scrot -u "${outputPath}"`);
            }
        }

        return this.success({
            path: outputPath,
            filename,
            type: 'window',
        });
    }

    private async captureRegion(savePath?: string): Promise<AdapterResult> {
        const filename = this.generateFilename();
        const outputPath = savePath || join(this.screenshotDir, filename);
        const platform = getPlatform();

        // 确保目录存在
        const dir = join(outputPath, '..');
        if (!existsSync(dir)) {
            mkdirSync(dir, { recursive: true });
        }

        if (platform === 'darwin') {
            // -s 交互式选择区域
            await execAsync(`screencapture -x -s "${outputPath}"`);
        } else if (platform === 'win32') {
            // Windows 使用 Snipping Tool 或提示用户
            // 简化实现：使用全屏截图
            return this.failure('NOT_SUPPORTED', 'Windows 区域截图请使用 Win+Shift+S');
        } else {
            // Linux
            try {
                await execAsync(`gnome-screenshot -a -f "${outputPath}"`);
            } catch {
                await execAsync(`scrot -s "${outputPath}"`);
            }
        }

        // 检查文件是否创建（用户可能取消）
        if (!existsSync(outputPath)) {
            return this.failure('CANCELLED', '截图已取消');
        }

        return this.success({
            path: outputPath,
            filename,
            type: 'region',
        });
    }

    private getScreenshotDir(): AdapterResult {
        return this.success({
            directory: this.screenshotDir,
        });
    }
}

export const screenshotAdapter = new ScreenshotAdapter();
