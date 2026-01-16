/**
 * 剪贴板适配器
 * 跨平台剪贴板操作
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { getPlatform } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

export class ClipboardAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.clipboard';
    readonly name = '剪贴板';
    readonly description = '跨平台剪贴板操作';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'read_text',
            name: '读取文本',
            description: '读取剪贴板中的文本内容',
            permissionLevel: 'low',
        },
        {
            id: 'write_text',
            name: '写入文本',
            description: '将文本写入剪贴板',
            permissionLevel: 'low',
            parameters: [
                { name: 'text', type: 'string', required: true, description: '要写入的文本' },
            ],
        },
        {
            id: 'clear',
            name: '清空剪贴板',
            description: '清空剪贴板内容',
            permissionLevel: 'low',
        },
        {
            id: 'has_text',
            name: '检查文本',
            description: '检查剪贴板是否包含文本',
            permissionLevel: 'public',
        },
    ];

    async checkAvailability(): Promise<boolean> {
        const platform = getPlatform();
        try {
            if (platform === 'darwin') {
                await execAsync('which pbcopy');
                return true;
            } else if (platform === 'win32') {
                return true; // Windows 总是有 clip 和 PowerShell
            } else {
                // Linux 检查 xclip 或 xsel
                try {
                    await execAsync('which xclip');
                    return true;
                } catch {
                    await execAsync('which xsel');
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
                case 'read_text':
                    return this.readText();
                case 'write_text':
                    return this.writeText(args.text as string);
                case 'clear':
                    return this.clear();
                case 'has_text':
                    return this.hasText();
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private async readText(): Promise<AdapterResult> {
        const platform = getPlatform();
        let text = '';

        if (platform === 'darwin') {
            const { stdout } = await execAsync('pbpaste');
            text = stdout;
        } else if (platform === 'win32') {
            const { stdout } = await execAsync('powershell -Command "Get-Clipboard"');
            text = stdout.trim();
        } else {
            // Linux
            try {
                const { stdout } = await execAsync('xclip -selection clipboard -o');
                text = stdout;
            } catch {
                const { stdout } = await execAsync('xsel --clipboard --output');
                text = stdout;
            }
        }

        return this.success({ text });
    }

    private async writeText(text: string): Promise<AdapterResult> {
        if (!text) {
            return this.failure('INVALID_PARAM', '文本不能为空');
        }

        const platform = getPlatform();
        // 转义特殊字符
        const escapedText = text.replace(/'/g, "'\\''");

        if (platform === 'darwin') {
            await execAsync(`echo '${escapedText}' | pbcopy`);
        } else if (platform === 'win32') {
            // Windows PowerShell
            const psText = text.replace(/'/g, "''");
            await execAsync(`powershell -Command "Set-Clipboard -Value '${psText}'"`);
        } else {
            // Linux
            try {
                await execAsync(`echo '${escapedText}' | xclip -selection clipboard`);
            } catch {
                await execAsync(`echo '${escapedText}' | xsel --clipboard --input`);
            }
        }

        return this.success({ written: true, length: text.length });
    }

    private async clear(): Promise<AdapterResult> {
        const platform = getPlatform();

        if (platform === 'darwin') {
            await execAsync('pbcopy < /dev/null');
        } else if (platform === 'win32') {
            await execAsync('powershell -Command "Set-Clipboard -Value $null"');
        } else {
            // Linux
            try {
                await execAsync('xclip -selection clipboard < /dev/null');
            } catch {
                await execAsync('xsel --clipboard --clear');
            }
        }

        return this.success({ cleared: true });
    }

    private async hasText(): Promise<AdapterResult> {
        try {
            const result = await this.readText();
            const text = result.data?.text as string || '';
            return this.success({
                hasText: text.length > 0,
                length: text.length,
            });
        } catch {
            return this.success({ hasText: false, length: 0 });
        }
    }
}

export const clipboardAdapter = new ClipboardAdapter();
