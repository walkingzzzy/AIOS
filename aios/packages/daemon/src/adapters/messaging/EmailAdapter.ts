import { BaseAdapter } from '../BaseAdapter.js';
import type { AdapterCapability, AdapterResult } from '@aios/shared';

export interface SMTPConfig {
    host: string;
    port: number;
    secure: boolean;
    user: string;
    pass: string;
}

// Nodemailer 响应类型
interface SendMailResult {
    messageId?: string;
}

export class EmailAdapter extends BaseAdapter {
    readonly id = 'email';
    readonly name = 'Email';
    readonly description = '通用邮件适配器，支持通过 SMTP 发送邮件';
    readonly capabilities: AdapterCapability[] = [
        {
            id: 'send_email',
            name: 'send_email',
            description: '发送电子邮件',
            permissionLevel: 'medium',
            parameters: [
                { name: 'to', type: 'string', required: true, description: '收件人邮箱' },
                { name: 'subject', type: 'string', required: true, description: '邮件主题' },
                { name: 'body', type: 'string', required: true, description: '邮件正文' },
                { name: 'html', type: 'boolean', required: false, description: '是否为 HTML 格式' },
            ],
        },
    ];

    private config: SMTPConfig | null = null;

    setConfig(config: SMTPConfig): void {
        this.config = config;
    }

    async checkAvailability(): Promise<boolean> {
        return this.config !== null;
    }

    async invoke(capability: string, params: Record<string, unknown>): Promise<AdapterResult> {
        if (!this.config) {
            return this.failure('NO_CONFIG', 'SMTP config not configured');
        }

        switch (capability) {
            case 'send_email':
                return this.sendEmail(
                    params.to as string,
                    params.subject as string,
                    params.body as string,
                    params.html as boolean
                );
            default:
                return this.failure('UNKNOWN_CAPABILITY', `Unknown capability: ${capability}`);
        }
    }

    private async sendEmail(to: string, subject: string, body: string, html?: boolean): Promise<AdapterResult> {
        try {
            // 动态导入 nodemailer
            const nodemailer = await import('nodemailer') as {
                createTransport: (options: {
                    host: string;
                    port: number;
                    secure: boolean;
                    auth: { user: string; pass: string };
                }) => {
                    sendMail: (options: {
                        from: string;
                        to: string;
                        subject: string;
                        text?: string;
                        html?: string;
                    }) => Promise<SendMailResult>;
                };
            };

            const transporter = nodemailer.createTransport({
                host: this.config!.host,
                port: this.config!.port,
                secure: this.config!.secure,
                auth: { user: this.config!.user, pass: this.config!.pass },
            });

            const info = await transporter.sendMail({
                from: this.config!.user,
                to,
                subject,
                [html ? 'html' : 'text']: body,
            });

            return this.success({ messageId: info.messageId });
        } catch (error) {
            return this.failure('SEND_FAILED', `Failed to send email: ${(error as Error).message}`);
        }
    }
}