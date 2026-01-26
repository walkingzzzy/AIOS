/**
 * CapCutDraftAdapter 单元测试
 */

import { describe, it, expect } from 'vitest';
import { CapCutDraftAdapter } from '../../adapters/cn/CapCutDraftAdapter';
import { promises as fs } from 'fs';
import { join } from 'path';

async function createTempProject() {
    const root = await fs.mkdtemp(join('/tmp', 'capcut-'));
    const projectDir = join(root, 'project1');
    await fs.mkdir(projectDir);
    await fs.writeFile(join(projectDir, 'draft_content.json'), JSON.stringify({ hello: 'world' }));
    await fs.writeFile(join(projectDir, 'draft_meta_info.json'), JSON.stringify({ meta: true }));
    return { root, projectDir };
}

describe('CapCutDraftAdapter', () => {
    it('应列出草稿项目', async () => {
        const adapter = new CapCutDraftAdapter();
        const { root } = await createTempProject();
        const result = await adapter.invoke('capcut_list_projects', { base_path: root });
        expect(result.success).toBe(true);
        const projects = (result.data as { projects?: unknown[] }).projects;
        expect(Array.isArray(projects)).toBe(true);
    });

    it('应读取草稿', async () => {
        const adapter = new CapCutDraftAdapter();
        const { projectDir } = await createTempProject();
        const result = await adapter.invoke('capcut_read_draft', { project_path: projectDir });
        expect(result.success).toBe(true);
        const data = result.data as { content?: Record<string, unknown> };
        expect(data.content?.hello).toBe('world');
    });

    it('应写入草稿', async () => {
        const adapter = new CapCutDraftAdapter();
        const { projectDir } = await createTempProject();
        const result = await adapter.invoke('capcut_write_draft', {
            project_path: projectDir,
            draft_content: { title: 'demo' },
            draft_meta: { updated: true },
        });
        expect(result.success).toBe(true);
        const content = JSON.parse(await fs.readFile(join(projectDir, 'draft_content.json'), 'utf8'));
        expect(content.title).toBe('demo');
    });
});
