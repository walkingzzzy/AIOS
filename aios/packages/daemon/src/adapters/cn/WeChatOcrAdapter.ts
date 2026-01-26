/**
 * 微信 OCR 适配器
 * 使用系统截图 + Tesseract OCR
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';
import { getPlatform } from '@aios/shared';
import { execFile } from 'child_process';
import { promisify } from 'util';
import { existsSync, unlinkSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';

const execFileAsync = promisify(execFile);

const DEFAULT_LANG = 'chi_sim';

export class WeChatOcrAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.wechat_ocr';
    readonly name = '微信 OCR';
    readonly description = '微信界面截图并执行 OCR';

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'wechat_capture_ocr',
            name: '截图并识别文字',
            description: '截图并使用 OCR 识别文本',
            permissionLevel: 'medium',
            parameters: [
                { name: 'mode', type: 'string', required: false, description: '截图模式 screen/window/region' },
                { name: 'language', type: 'string', required: false, description: 'OCR 语言' },
                { name: 'save_path', type: 'string', required: false, description: '截图保存路径' },
                { name: 'keep_image', type: 'boolean', required: false, description: '是否保留截图' },
            ],
        },
    ];

    async checkAvailability(): Promise<boolean> {
        const platform = getPlatform();
        if (platform !== 'darwin' && platform !== 'linux') {
            return false;
        }
        try {
            await execFileAsync('which', ['tesseract']);
            return true;
        } catch {
            return false;
        }
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        try {
            switch (capability) {
                case 'wechat_capture_ocr':
                    return this.captureOcr({
                        mode: (args.mode as string | undefined) || 'screen',
                        language: (args.language as string | undefined) || DEFAULT_LANG,
                        savePath: args.save_path as string | undefined,
                        keepImage: args.keep_image as boolean | undefined,
                    });
                default:
                    return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
            }
        } catch (error) {
            return this.failure('OPERATION_FAILED', String(error));
        }
    }

    private async captureOcr(options: {
        mode: string;
        language: string;
        savePath?: string;
        keepImage?: boolean;
    }): Promise<AdapterResult> {
        const platform = getPlatform();
        if (platform !== 'darwin' && platform !== 'linux') {
            return this.failure('UNSUPPORTED_PLATFORM', '当前平台不支持微信 OCR');
        }

        const screenshotPath = options.savePath || this.generateTempPath();
        await this.captureScreen(platform, options.mode, screenshotPath);

        const text = await this.runTesseract(screenshotPath, options.language);

        if (!options.keepImage && existsSync(screenshotPath)) {
            unlinkSync(screenshotPath);
        }

        return this.success({ text, image_path: screenshotPath, mode: options.mode });
    }

    private async captureScreen(platform: string, mode: string, outputPath: string): Promise<void> {
        if (platform === 'darwin') {
            const args = ['-x'];
            if (mode === 'window') {
                args.push('-w');
            } else if (mode === 'region') {
                args.push('-s');
            }
            args.push(outputPath);
            await execFileAsync('screencapture', args);
            return;
        }

        if (platform === 'linux') {
            if (mode === 'window') {
                await execFileAsync('gnome-screenshot', ['-w', '-f', outputPath]);
                return;
            }
            if (mode === 'region') {
                await execFileAsync('gnome-screenshot', ['-a', '-f', outputPath]);
                return;
            }
            await execFileAsync('gnome-screenshot', ['-f', outputPath]);
        }
    }

    private async runTesseract(imagePath: string, language: string): Promise<string> {
        try {
            await execFileAsync('which', ['tesseract']);
        } catch {
            throw new Error('未检测到 tesseract，请先安装');
        }

        const { stdout } = await execFileAsync('tesseract', [imagePath, 'stdout', '-l', language], { encoding: 'utf8' });
        return stdout.trim();
    }

    private generateTempPath(): string {
        const filename = `wechat-ocr-${Date.now()}.png`;
        return join(tmpdir(), filename);
    }
}

export const wechatOcrAdapter = new WeChatOcrAdapter();
