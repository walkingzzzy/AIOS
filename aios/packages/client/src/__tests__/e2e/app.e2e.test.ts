/**
 * AIOS 端到端测试
 * 测试完整的用户场景和工作流
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { chromium, Browser, Page } from 'playwright';
import { spawn, ChildProcess } from 'child_process';
import path from 'path';

describe('AIOS 端到端测试', () => {
    let browser: Browser;
    let page: Page;
    let daemonProcess: ChildProcess;

    beforeAll(async () => {
        // 启动 daemon
        daemonProcess = spawn('node', [
            path.join(__dirname, '../../index.js')
        ], {
            env: {
                ...process.env,
                NODE_ENV: 'test',
                AIOS_PORT: '3001'
            }
        });

        // 等待 daemon 启动
        await new Promise(resolve => setTimeout(resolve, 3000));

        // 启动浏览器
        browser = await chromium.launch({
            headless: true
        });

        page = await browser.newPage();
    }, 30000);

    afterAll(async () => {
        await browser?.close();
        daemonProcess?.kill();
    });

    describe('用户界面测试', () => {
        it('应该能加载主界面', async () => {
            await page.goto('http://localhost:3000');
            await page.waitForSelector('.app');

            const title = await page.textContent('h1');
            expect(title).toBe('AIOS');
        });

        it('应该能切换视图', async () => {
            await page.goto('http://localhost:3000');

            // 点击工具视图
            await page.click('button:has-text("工具")');
            await page.waitForSelector('.tools-view');

            // 点击设置视图
            await page.click('button:has-text("设置")');
            await page.waitForSelector('.settings-view');

            // 点击对话视图
            await page.click('button:has-text("对话")');
            await page.waitForSelector('.chat-view');
        });
    });

    describe('聊天功能测试', () => {
        beforeEach(async () => {
            await page.goto('http://localhost:3000');
            await page.click('button:has-text("对话")');
        });

        it('应该能发送消息', async () => {
            const input = await page.locator('input[placeholder*="输入"]');
            await input.fill('你好');
            await input.press('Enter');

            // 等待响应
            await page.waitForSelector('.message.assistant', { timeout: 10000 });

            const messages = await page.locator('.message').count();
            expect(messages).toBeGreaterThan(1);
        });

        it('应该能执行简单命令', async () => {
            const input = await page.locator('input[placeholder*="输入"]');
            await input.fill('获取系统信息');
            await input.press('Enter');

            // 等待响应
            await page.waitForSelector('.message.assistant', { timeout: 10000 });

            const response = await page.locator('.message.assistant').last().textContent();
            expect(response).toBeTruthy();
        });

        it('应该能显示 Artifact', async () => {
            const input = await page.locator('input[placeholder*="输入"]');
            await input.fill('写一个 Hello World 程序');
            await input.press('Enter');

            // 等待 Artifact 渲染
            await page.waitForSelector('.artifact-renderer', { timeout: 15000 });

            const artifact = await page.locator('.artifact-renderer');
            expect(await artifact.isVisible()).toBe(true);
        });
    });

    describe('工具测试功能', () => {
        beforeEach(async () => {
            await page.goto('http://localhost:3000');
            await page.click('button:has-text("工具")');
        });

        it('应该能显示适配器列表', async () => {
            await page.waitForSelector('.adapter-card');

            const adapters = await page.locator('.adapter-card').count();
            expect(adapters).toBeGreaterThan(0);
        });

        it('应该能测试适配器', async () => {
            // 找到系统信息适配器
            const systemInfoCard = await page.locator('.adapter-card:has-text("System Information")');
            await systemInfoCard.click();

            // 点击测试按钮
            await page.click('button:has-text("测试")');

            // 等待测试结果
            await page.waitForSelector('.test-result', { timeout: 10000 });

            const result = await page.locator('.test-result').textContent();
            expect(result).toBeTruthy();
        });
    });

    describe('设置功能测试', () => {
        beforeEach(async () => {
            await page.goto('http://localhost:3000');
            await page.click('button:has-text("设置")');
        });

        it('应该能显示设置页面', async () => {
            await page.waitForSelector('.settings-view');

            const heading = await page.textContent('h2');
            expect(heading).toContain('设置');
        });

        it('应该能配置 AI 模型', async () => {
            // 找到 API Key 输入框
            const apiKeyInput = await page.locator('input[placeholder*="API"]').first();
            await apiKeyInput.fill('test-api-key');

            // 保存设置
            await page.click('button:has-text("保存")');

            // 等待保存成功提示
            await page.waitForSelector('.success-message', { timeout: 5000 });
        });
    });

    describe('任务板功能测试', () => {
        beforeEach(async () => {
            await page.goto('http://localhost:3000');
            await page.click('button:has-text("对话")');
        });

        it('应该能显示任务板', async () => {
            // 发送一个复杂任务
            const input = await page.locator('input[placeholder*="输入"]');
            await input.fill('分析系统性能并生成报告');
            await input.press('Enter');

            // 等待任务板出现
            await page.waitForSelector('.task-board', { timeout: 15000 });

            const taskBoard = await page.locator('.task-board');
            expect(await taskBoard.isVisible()).toBe(true);
        });

        it('应该能显示任务进度', async () => {
            // 发送任务
            const input = await page.locator('input[placeholder*="输入"]');
            await input.fill('执行多步骤任务');
            await input.press('Enter');

            // 等待任务组出现
            await page.waitForSelector('.task-group', { timeout: 15000 });

            // 展开任务组
            await page.click('.group-header');

            // 检查子任务
            await page.waitForSelector('.subtask-item');
            const subtasks = await page.locator('.subtask-item').count();
            expect(subtasks).toBeGreaterThan(0);
        });
    });

    describe('确认对话框测试', () => {
        beforeEach(async () => {
            await page.goto('http://localhost:3000');
            await page.click('button:has-text("对话")');
        });

        it('应该能显示高危操作确认', async () => {
            // 发送高危操作命令
            const input = await page.locator('input[placeholder*="输入"]');
            await input.fill('删除所有文件');
            await input.press('Enter');

            // 等待确认对话框
            await page.waitForSelector('.confirmation-dialog', { timeout: 10000 });

            const dialog = await page.locator('.confirmation-dialog');
            expect(await dialog.isVisible()).toBe(true);
        });

        it('应该能确认操作', async () => {
            // 发送高危操作
            const input = await page.locator('input[placeholder*="输入"]');
            await input.fill('关机');
            await input.press('Enter');

            // 等待确认对话框
            await page.waitForSelector('.confirmation-dialog', { timeout: 10000 });

            // 点击确认
            await page.click('.btn-confirm');

            // 对话框应该消失
            await page.waitForSelector('.confirmation-dialog', { state: 'hidden', timeout: 5000 });
        });

        it('应该能拒绝操作', async () => {
            // 发送高危操作
            const input = await page.locator('input[placeholder*="输入"]');
            await input.fill('重启系统');
            await input.press('Enter');

            // 等待确认对话框
            await page.waitForSelector('.confirmation-dialog', { timeout: 10000 });

            // 点击拒绝
            await page.click('.btn-reject');

            // 对话框应该消失
            await page.waitForSelector('.confirmation-dialog', { state: 'hidden', timeout: 5000 });
        });
    });

    describe('语音输入测试', () => {
        beforeEach(async () => {
            await page.goto('http://localhost:3000');
            await page.click('button:has-text("对话")');
        });

        it('应该能显示语音输入按钮', async () => {
            const voiceBtn = await page.locator('.voice-btn');
            expect(await voiceBtn.isVisible()).toBe(true);
        });

        it('应该能点击语音按钮', async () => {
            // 授予麦克风权限（在测试环境中模拟）
            await page.context().grantPermissions(['microphone']);

            const voiceBtn = await page.locator('.voice-btn');
            await voiceBtn.click();

            // 检查录音状态
            const isRecording = await voiceBtn.evaluate(el =>
                el.classList.contains('recording')
            );
            expect(isRecording).toBe(true);
        });
    });

    describe('性能测试', () => {
        it('应该能快速加载页面', async () => {
            const startTime = Date.now();
            await page.goto('http://localhost:3000');
            await page.waitForSelector('.app');
            const loadTime = Date.now() - startTime;

            expect(loadTime).toBeLessThan(3000); // 3秒内加载
        });

        it('应该能快速响应用户输入', async () => {
            await page.goto('http://localhost:3000');
            await page.click('button:has-text("对话")');

            const input = await page.locator('input[placeholder*="输入"]');

            const startTime = Date.now();
            await input.fill('你好');
            await input.press('Enter');
            await page.waitForSelector('.message.assistant', { timeout: 10000 });
            const responseTime = Date.now() - startTime;

            expect(responseTime).toBeLessThan(5000); // 5秒内响应
        });
    });

    describe('错误处理测试', () => {
        beforeEach(async () => {
            await page.goto('http://localhost:3000');
            await page.click('button:has-text("对话")');
        });

        it('应该能处理网络错误', async () => {
            // 模拟网络断开
            await page.context().setOffline(true);

            const input = await page.locator('input[placeholder*="输入"]');
            await input.fill('测试消息');
            await input.press('Enter');

            // 等待错误消息
            await page.waitForSelector('.message.system', { timeout: 10000 });

            const errorMsg = await page.locator('.message.system').last().textContent();
            expect(errorMsg).toContain('错误');

            // 恢复网络
            await page.context().setOffline(false);
        });

        it('应该能处理无效命令', async () => {
            const input = await page.locator('input[placeholder*="输入"]');
            await input.fill('执行一个不存在的命令xyz123');
            await input.press('Enter');

            // 等待响应
            await page.waitForSelector('.message.assistant', { timeout: 10000 });

            const response = await page.locator('.message.assistant').last().textContent();
            expect(response).toBeTruthy();
        });
    });

    describe('多窗口测试', () => {
        it('应该能在多个窗口中独立工作', async () => {
            // 打开第一个窗口
            const page1 = await browser.newPage();
            await page1.goto('http://localhost:3000');
            await page1.click('button:has-text("对话")');

            // 打开第二个窗口
            const page2 = await browser.newPage();
            await page2.goto('http://localhost:3000');
            await page2.click('button:has-text("对话")');

            // 在两个窗口中发送不同的消息
            const input1 = await page1.locator('input[placeholder*="输入"]');
            await input1.fill('窗口1的消息');
            await input1.press('Enter');

            const input2 = await page2.locator('input[placeholder*="输入"]');
            await input2.fill('窗口2的消息');
            await input2.press('Enter');

            // 等待响应
            await page1.waitForSelector('.message.assistant', { timeout: 10000 });
            await page2.waitForSelector('.message.assistant', { timeout: 10000 });

            // 验证消息独立
            const msg1 = await page1.locator('.message.user').last().textContent();
            const msg2 = await page2.locator('.message.user').last().textContent();

            expect(msg1).toContain('窗口1');
            expect(msg2).toContain('窗口2');

            await page1.close();
            await page2.close();
        });
    });

    describe('可访问性测试', () => {
        it('应该支持键盘导航', async () => {
            await page.goto('http://localhost:3000');

            // 使用 Tab 键导航
            await page.keyboard.press('Tab');
            await page.keyboard.press('Tab');
            await page.keyboard.press('Enter');

            // 验证导航成功
            await page.waitForTimeout(500);
        });

        it('应该有正确的 ARIA 标签', async () => {
            await page.goto('http://localhost:3000');

            const buttons = await page.locator('button[aria-label]').count();
            expect(buttons).toBeGreaterThan(0);
        });
    });
});
