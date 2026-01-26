/**
 * OfficeLocalAdapter 单元测试
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { mkdtemp, writeFile, rm } from 'fs/promises';
import { join } from 'path';

const platformMock = vi.hoisted(() => ({ value: 'win32' as 'win32' | 'darwin' | 'linux' }));
const spawnBackgroundMock = vi.hoisted(() => vi.fn());

vi.mock('@aios/shared', async () => {
    const actual = await vi.importActual<typeof import('@aios/shared')>('@aios/shared');
    return {
        ...actual,
        getPlatform: () => platformMock.value,
        spawnBackground: spawnBackgroundMock,
    };
});

const execFileMock = vi.hoisted(() => {
    const promisifySymbol = Symbol.for('nodejs.util.promisify.custom');
    const baseImpl = (cmd: string, args: string[], options?: any, cb?: (err: Error | null, stdout?: string, stderr?: string) => void) => {
        const callback = typeof options === 'function'
            ? options
            : typeof cb === 'function'
                ? cb
                : undefined;
        const normalized = cmd.toLowerCase();
        const stdout = normalized.includes('powershell') || normalized.includes('pwsh') ? 'Hello' : '';
        callback?.(null, stdout, '');
    };
    const mock = vi.fn(baseImpl);
    (mock as any)[promisifySymbol] = (cmd: string, args: string[], options?: any) => new Promise((resolve, reject) => {
        mock(cmd, args, options, (err: Error | null, stdout?: string, stderr?: string) => {
            if (err) {
                reject(err);
                return;
            }
            resolve({ stdout: stdout ?? '', stderr: stderr ?? '' });
        });
    });
    return mock;
});

vi.mock('child_process', async (importOriginal) => {
    const actual = await importOriginal<typeof import('child_process')>();
    return {
        ...actual,
        execFile: execFileMock,
    };
});

import { OfficeLocalAdapter } from '../../adapters/office/OfficeLocalAdapter';

describe('OfficeLocalAdapter', () => {
    let adapter: OfficeLocalAdapter;

    beforeEach(() => {
        adapter = new OfficeLocalAdapter();
        vi.spyOn(adapter as any, 'getPlatform').mockImplementation(() => platformMock.value);
        spawnBackgroundMock.mockClear();
        execFileMock.mockClear();
    });

    it('应该包含完整能力列表', () => {
        const capabilityIds = adapter.capabilities.map((cap) => cap.id);
        expect(capabilityIds).toContain('word_create');
        expect(capabilityIds).toContain('word_get_content');
        expect(capabilityIds).toContain('word_set_content');
        expect(capabilityIds).toContain('word_replace_text');
        expect(capabilityIds).toContain('word_append_text');
        expect(capabilityIds).toContain('word_insert_list');
        expect(capabilityIds).toContain('word_insert_table');
        expect(capabilityIds).toContain('word_apply_heading');
        expect(capabilityIds).toContain('word_export_pdf');
        expect(capabilityIds).toContain('word_add_comment');
        expect(capabilityIds).toContain('word_toggle_track_changes');
        expect(capabilityIds).toContain('excel_read_range');
        expect(capabilityIds).toContain('excel_write_range');
        expect(capabilityIds).toContain('excel_add_worksheet');
        expect(capabilityIds).toContain('excel_set_formula');
        expect(capabilityIds).toContain('excel_sort_range');
        expect(capabilityIds).toContain('excel_filter_range');
        expect(capabilityIds).toContain('excel_create_table');
        expect(capabilityIds).toContain('excel_add_named_range');
        expect(capabilityIds).toContain('excel_set_data_validation');
        expect(capabilityIds).toContain('excel_apply_conditional_formatting');
        expect(capabilityIds).toContain('excel_create_chart');
        expect(capabilityIds).toContain('ppt_get_slides');
        expect(capabilityIds).toContain('ppt_add_slide');
        expect(capabilityIds).toContain('ppt_delete_slide');
        expect(capabilityIds).toContain('ppt_duplicate_slide');
        expect(capabilityIds).toContain('ppt_insert_text');
        expect(capabilityIds).toContain('ppt_insert_image');
        expect(capabilityIds).toContain('ppt_set_layout');
        expect(capabilityIds).toContain('ppt_set_theme');
        expect(capabilityIds).toContain('ppt_set_notes');
        expect(capabilityIds).toContain('ppt_set_transition');
        expect(capabilityIds).toContain('ppt_set_animation');
    });

    it('Windows 下应该通过 PowerShell 执行 Word 创建', async () => {
        platformMock.value = 'win32';
        const tempDir = await mkdtemp('/tmp/aios-office-');
        const path = join(tempDir, 'demo.docx');

        const result = await adapter.invoke('word_create', { path, suite: 'microsoft' });

        expect(result.success).toBe(true);
        expect(execFileMock).toHaveBeenCalled();
        await rm(tempDir, { recursive: true, force: true });
    });

    it('Windows 下应该读取 Word 内容', async () => {
        platformMock.value = 'win32';
        const tempDir = await mkdtemp('/tmp/aios-office-');
        const path = join(tempDir, 'demo.docx');
        await writeFile(path, '');

        const result = await adapter.invoke('word_get_content', { path, suite: 'microsoft' });

        expect(result.success).toBe(true);
        expect((result.data as { content?: string }).content).toBe('Hello');
        await rm(tempDir, { recursive: true, force: true });
    });

    it('Windows 下应该写入 Word 内容', async () => {
        platformMock.value = 'win32';
        const tempDir = await mkdtemp('/tmp/aios-office-');
        const path = join(tempDir, 'demo.docx');
        await writeFile(path, '');

        const result = await adapter.invoke('word_set_content', { path, suite: 'microsoft', content: 'AIOS' });

        expect(result.success).toBe(true);
        expect(execFileMock).toHaveBeenCalled();
        await rm(tempDir, { recursive: true, force: true });
    });

    it('Windows 下应该替换 Word 内容', async () => {
        platformMock.value = 'win32';
        const tempDir = await mkdtemp('/tmp/aios-office-');
        const path = join(tempDir, 'demo.docx');
        await writeFile(path, '');

        const result = await adapter.invoke('word_replace_text', {
            path,
            suite: 'microsoft',
            search: 'hello',
            replace: 'hi',
        });

        expect(result.success).toBe(true);
        expect(execFileMock).toHaveBeenCalled();
        await rm(tempDir, { recursive: true, force: true });
    });

    it('Windows 下应该追加 Word 文本', async () => {
        platformMock.value = 'win32';
        const tempDir = await mkdtemp('/tmp/aios-office-');
        const path = join(tempDir, 'append.docx');
        await writeFile(path, '');

        const result = await adapter.invoke('word_append_text', {
            path,
            suite: 'microsoft',
            text: '追加内容',
        });

        expect(result.success).toBe(true);
        expect(execFileMock).toHaveBeenCalled();
        await rm(tempDir, { recursive: true, force: true });
    });

    it('macOS 下应该走 UI 自动化流程', async () => {
        platformMock.value = 'darwin';
        const tempDir = await mkdtemp('/tmp/aios-office-');
        const path = join(tempDir, 'demo.docx');

        const result = await adapter.invoke('word_create', { path, suite: 'wps' });

        expect(result.success).toBe(true);
        expect(execFileMock).toHaveBeenCalled();
        await rm(tempDir, { recursive: true, force: true });
    });

    it('Windows 下应该写入 Excel 公式', async () => {
        platformMock.value = 'win32';
        const tempDir = await mkdtemp('/tmp/aios-office-');
        const path = join(tempDir, 'formula.xlsx');
        await writeFile(path, '');

        const result = await adapter.invoke('excel_set_formula', {
            path,
            suite: 'microsoft',
            range: 'A1',
            formula: '=SUM(1,2)',
        });

        expect(result.success).toBe(true);
        expect(execFileMock).toHaveBeenCalled();
        await rm(tempDir, { recursive: true, force: true });
    });

    it('Windows 下应该新增 PPT 幻灯片', async () => {
        platformMock.value = 'win32';
        const tempDir = await mkdtemp('/tmp/aios-office-');
        const path = join(tempDir, 'deck.pptx');
        await writeFile(path, '');

        const result = await adapter.invoke('ppt_add_slide', {
            path,
            suite: 'microsoft',
            layout: 'title',
        });

        expect(result.success).toBe(true);
        expect(execFileMock).toHaveBeenCalled();
        await rm(tempDir, { recursive: true, force: true });
    });

    it('应该能列出并筛选文件', async () => {
        platformMock.value = 'win32';
        const tempDir = await mkdtemp('/tmp/aios-office-');
        await writeFile(join(tempDir, 'a.docx'), '');
        await writeFile(join(tempDir, 'b.xlsx'), '');

        const result = await adapter.invoke('list_files', { folder: tempDir, type: 'word' });

        expect(result.success).toBe(true);
        expect((result.data as { count?: number }).count).toBe(1);
        await rm(tempDir, { recursive: true, force: true });
    });

    it('应该拒绝敏感路径删除', async () => {
        platformMock.value = 'win32';
        const result = await adapter.invoke('delete_file', { path: '/etc/passwd' });

        expect(result.success).toBe(false);
        expect(result.error?.code).toBe('SECURITY_DENIED');
    });
});
