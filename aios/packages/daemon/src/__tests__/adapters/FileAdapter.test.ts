/**
 * FileAdapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { FileAdapter } from '../../adapters/system/FileAdapter';
import * as fs from 'fs/promises';
import * as path from 'path';
import * as os from 'os';

describe('FileAdapter', () => {
    let adapter: FileAdapter;
    let testDir: string;

    beforeEach(async () => {
        adapter = new FileAdapter();
        testDir = path.join(os.tmpdir(), `aios-test-${Date.now()}`);
        await fs.mkdir(testDir, { recursive: true });
    });

    afterEach(async () => {
        try {
            await fs.rm(testDir, { recursive: true, force: true });
        } catch (error) {
            // Ignore cleanup errors
        }
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('file');
            expect(adapter.name).toBe('File System');
            expect(adapter.permissionLevel).toBe('high');
        });

        it('应该返回正确的工具列表', () => {
            const tools = adapter.getTools();
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map(t => t.name);
            expect(toolNames).toContain('file_read');
            expect(toolNames).toContain('file_write');
            expect(toolNames).toContain('file_delete');
            expect(toolNames).toContain('file_list');
        });
    });

    describe('文件操作', () => {
        it('应该能写入文件', async () => {
            const filePath = path.join(testDir, 'test.txt');
            const result = await adapter.execute('file_write', {
                path: filePath,
                content: 'Hello World'
            });

            expect(result.success).toBe(true);
            const content = await fs.readFile(filePath, 'utf-8');
            expect(content).toBe('Hello World');
        });

        it('应该能读取文件', async () => {
            const filePath = path.join(testDir, 'test.txt');
            await fs.writeFile(filePath, 'Test Content');

            const result = await adapter.execute('file_read', {
                path: filePath
            });

            expect(result.content).toBe('Test Content');
        });

        it('应该能删除文件', async () => {
            const filePath = path.join(testDir, 'test.txt');
            await fs.writeFile(filePath, 'Test');

            const result = await adapter.execute('file_delete', {
                path: filePath
            });

            expect(result.success).toBe(true);
            await expect(fs.access(filePath)).rejects.toThrow();
        });

        it('应该能列出目录内容', async () => {
            await fs.writeFile(path.join(testDir, 'file1.txt'), 'Test');
            await fs.writeFile(path.join(testDir, 'file2.txt'), 'Test');

            const result = await adapter.execute('file_list', {
                path: testDir
            });

            expect(Array.isArray(result.files)).toBe(true);
            expect(result.files.length).toBeGreaterThanOrEqual(2);
        });

        it('应该能创建目录', async () => {
            const dirPath = path.join(testDir, 'subdir');
            const result = await adapter.execute('file_create_directory', {
                path: dirPath
            });

            expect(result.success).toBe(true);
            const stats = await fs.stat(dirPath);
            expect(stats.isDirectory()).toBe(true);
        });

        it('应该拒绝访问敏感路径', async () => {
            await expect(
                adapter.execute('file_read', { path: '/etc/passwd' })
            ).rejects.toThrow();
        });

        it('应该拒绝路径遍历攻击', async () => {
            await expect(
                adapter.execute('file_read', { path: '../../../etc/passwd' })
            ).rejects.toThrow();
        });
    });
});
