/**
 * EmailAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { EmailAdapter } from '../../adapters/messaging/EmailAdapter';

const sendMailMock = vi.hoisted(() => vi.fn(async () => ({ messageId: 'msg-1' })));

vi.mock('nodemailer', () => ({
    createTransport: vi.fn(() => ({
        sendMail: sendMailMock,
    })),
}));

describe('EmailAdapter', () => {
    let adapter: EmailAdapter;

    beforeEach(() => {
        adapter = new EmailAdapter();
        adapter.setConfig({
            host: 'smtp.example.com',
            port: 465,
            secure: true,
            user: 'user@example.com',
            pass: 'password',
        });
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('email');
            expect(adapter.name).toBe('Email');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('send_email');
        });
    });

    describe('邮件发送', () => {
        it('应该能发送邮件', async () => {
            const result = await adapter.invoke('send_email', {
                to: 'test@example.com',
                subject: 'Test',
                body: 'Hello',
            });

            expect(result.success).toBe(true);
            expect((result.data as { messageId?: string }).messageId).toBe('msg-1');
        });

        it('未配置 SMTP 时应该失败', async () => {
            const noConfig = new EmailAdapter();
            const result = await noConfig.invoke('send_email', {
                to: 'test@example.com',
                subject: 'Test',
                body: 'Hello',
            });

            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('NO_CONFIG');
        });
    });
});
