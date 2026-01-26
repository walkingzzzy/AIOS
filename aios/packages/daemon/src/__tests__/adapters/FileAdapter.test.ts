/**
 * FileAdapter 单元测试
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { FileAdapter } from '../../adapters/system/FileAdapter';
import { promises as fs } from 'fs';
import { join } from 'path';

const tmpBase = '/tmp/aios-file-test';

describe('FileAdapter', () => {
    let adapter: FileAdapter;
    let tempDir: string;

    beforeEach(async () => {
        adapter = new FileAdapter();
        tempDir = await fs.mkdtemp(`${tmpBase}-`);
    });

    afterEach(async () => {
        await fs.rm(tempDir, { recursive: true, force: true });
    });

    describe('基本功能', () => {
        it('应该正确初始化', () => {
            expect(adapter.id).toBe('com.aios.adapter.file');
            expect(adapter.name).toBe('文件管理');
            expect(adapter.capabilities.length).toBeGreaterThan(0);
        });

        it('应该返回正确的能力列表', () => {
            const capabilityIds = adapter.capabilities.map((cap) => cap.id);
            expect(capabilityIds).toContain('read_file');
            expect(capabilityIds).toContain('write_file');
            expect(capabilityIds).toContain('list_dir');
            expect(capabilityIds).toContain('create_dir');
        });
    });

    describe('文件操作', () => {
        it('应该能写入并读取文件', async () => {
            const filePath = join(tempDir, 'test.txt');
            const writeResult = await adapter.invoke('write_file', {
                path: filePath,
                content: 'hello',
            });

            expect(writeResult.success).toBe(true);

            const readResult = await adapter.invoke('read_file', { path: filePath });
            expect(readResult.success).toBe(true);
            expect((readResult.data as { content?: string }).content).toBe('hello');
        });

        it('应该能列出目录', async () => {
            const filePath = join(tempDir, 'file.txt');
            await fs.writeFile(filePath, 'data');

            const result = await adapter.invoke('list_dir', { path: tempDir });
            expect(result.success).toBe(true);
            const items = (result.data as { items?: unknown[] }).items;
            expect(Array.isArray(items)).toBe(true);
        });

        it('应该能创建并删除目录', async () => {
            const dirPath = join(tempDir, 'nested');
            const createResult = await adapter.invoke('create_dir', { path: dirPath });
            expect(createResult.success).toBe(true);

            const deleteResult = await adapter.invoke('delete_file', { path: dirPath });
            expect(deleteResult.success).toBe(true);
        });

        it('应该拒绝访问受限路径', async () => {
            if (process.platform === 'win32') {
                return;
            }
            const result = await adapter.invoke('read_file', { path: '/etc/passwd' });
            expect(result.success).toBe(false);
            expect(result.error?.code).toBe('SECURITY_DENIED');
        });
    });
});
