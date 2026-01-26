/**
 * OfficeLocalAdapter 集成测试（需真实桌面环境）
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { spawn } from 'child_process';
import { access, mkdtemp, rm, writeFile } from 'fs/promises';
import { join, resolve } from 'path';
import { tmpdir } from 'os';

const shouldRun = process.env.AIOS_RUN_OFFICE_UI === '1';
const describeOffice = shouldRun ? describe : describe.skip;
const adapterId = 'com.aios.adapter.office_local';
const timeoutMs = Number(process.env.AIOS_OFFICE_TEST_TIMEOUT || 120000);

const suiteEnv = process.env.AIOS_OFFICE_SUITES;
const platform = process.platform;
const defaultSuites = platform === 'linux' ? ['wps'] : ['microsoft'];
const suites = suiteEnv
    ? suiteEnv.split(',').map((item) => item.trim()).filter(Boolean)
    : defaultSuites;
const enableExtended = process.env.AIOS_OFFICE_EXTENDED === '1';
const enablePdfExport = process.env.AIOS_OFFICE_PDF_EXPORT === '1';
const pptThemePath = process.env.AIOS_OFFICE_PPT_THEME || '';

class JsonRpcClient {
    private daemon: ReturnType<typeof spawn> | null = null;
    private buffer = '';
    private pending = new Map<number, { resolve: (v: any) => void; reject: (e: Error) => void }>();
    private requestId = 0;

    constructor(private entry: string) {}

    async start(): Promise<void> {
        this.daemon = spawn('node', [this.entry], {
            stdio: ['pipe', 'pipe', 'inherit'],
        });

        this.daemon.stdout?.on('data', (data: Buffer) => {
            this.buffer += data.toString();
            this.processBuffer();
        });

        await new Promise((resolve) => setTimeout(resolve, 1000));
    }

    stop(): void {
        this.daemon?.kill();
    }

    private processBuffer(): void {
        const lines = this.buffer.split('\n');
        this.buffer = lines.pop() || '';
        for (const line of lines) {
            if (!line.trim()) continue;
            try {
                const response = JSON.parse(line);
                const pending = this.pending.get(response.id);
                if (pending) {
                    this.pending.delete(response.id);
                    if (response.error) {
                        pending.reject(new Error(response.error.message));
                    } else {
                        pending.resolve(response.result);
                    }
                }
            } catch {
                // 忽略解析失败
            }
        }
    }

    async call(method: string, params?: Record<string, unknown>): Promise<any> {
        const id = ++this.requestId;
        const request = {
            jsonrpc: '2.0',
            id,
            method,
            params,
        };

        return new Promise((resolve, reject) => {
            this.pending.set(id, { resolve, reject });
            this.daemon?.stdin?.write(JSON.stringify(request) + '\n');
            setTimeout(() => {
                if (this.pending.has(id)) {
                    this.pending.delete(id);
                    reject(new Error('请求超时'));
                }
            }, timeoutMs);
        });
    }
}

async function invokeSafe(client: JsonRpcClient, capability: string, args: Record<string, unknown>) {
    try {
        const result = await client.call('invoke', {
            adapterId,
            capability,
            args,
        });
        return { ok: result?.success === true, result, error: result?.error?.message };
    } catch (error) {
        return { ok: false, result: null, error: (error as Error).message };
    }
}

describeOffice('OfficeLocalAdapter 集成测试', () => {
    let client: JsonRpcClient;
    let tempDir = '';
    let wordPath = '';
    let excelPath = '';
    let pptPath = '';
    let imagePath = '';

    beforeAll(async () => {
        const daemonEntry = resolve(process.cwd(), 'dist/index.js');
        await access(daemonEntry);

        client = new JsonRpcClient(daemonEntry);
        await client.start();

        const status = await client.call('getAdapterStatus', { adapterId });
        expect(status.available).toBe(true);

        tempDir = await mkdtemp(join(tmpdir(), 'aios-office-it-'));
        imagePath = join(tempDir, 'aios-slide.png');
    }, timeoutMs);

    afterAll(async () => {
        if (tempDir) {
            await rm(tempDir, { recursive: true, force: true });
        }
        client?.stop();
    }, timeoutMs);

    it('完整 smoke 流程', async () => {
        const suite = suites[0];
        wordPath = join(tempDir, `aios-it-${suite}.docx`);
        excelPath = join(tempDir, `aios-it-${suite}.xlsx`);
        pptPath = join(tempDir, `aios-it-${suite}.pptx`);

        const wordCreate = await invokeSafe(client, 'word_create', { path: wordPath, suite });
        expect(wordCreate.ok).toBe(true);

        const wordWrite = await invokeSafe(client, 'word_set_content', {
            path: wordPath,
            suite,
            content: 'AIOS Office 自动化',
        });
        expect(wordWrite.ok).toBe(true);

        const wordReplace = await invokeSafe(client, 'word_replace_text', {
            path: wordPath,
            suite,
            search: '自动化',
            replace: '能力',
        });
        expect(wordReplace.ok).toBe(true);

        const wordRead = await invokeSafe(client, 'word_get_content', { path: wordPath, suite });
        expect(wordRead.ok).toBe(true);

        if (enableExtended) {
            const wordAppend = await invokeSafe(client, 'word_append_text', {
                path: wordPath,
                suite,
                text: '扩展能力验证',
            });
            expect(wordAppend.ok).toBe(true);

            const wordList = await invokeSafe(client, 'word_insert_list', {
                path: wordPath,
                suite,
                items: ['一', '二', '三'],
                ordered: true,
            });
            expect(wordList.ok).toBe(true);

            const wordTable = await invokeSafe(client, 'word_insert_table', {
                path: wordPath,
                suite,
                rows: 2,
                cols: 2,
                values: [
                    ['项目', '数量'],
                    ['任务', '3'],
                ],
            });
            expect(wordTable.ok).toBe(true);

            const wordHeading = await invokeSafe(client, 'word_apply_heading', {
                path: wordPath,
                suite,
                level: 1,
            });
            expect(wordHeading.ok).toBe(true);

            const wordComment = await invokeSafe(client, 'word_add_comment', {
                path: wordPath,
                suite,
                comment: '扩展批注',
                search: 'AIOS Office',
            });
            expect(wordComment.ok).toBe(true);

            const wordTrack = await invokeSafe(client, 'word_toggle_track_changes', {
                path: wordPath,
                suite,
                enabled: true,
            });
            expect(wordTrack.ok).toBe(true);

            if (enablePdfExport) {
                const pdfPath = wordPath.replace(/\.docx$/i, '.pdf');
                const wordPdf = await invokeSafe(client, 'word_export_pdf', {
                    path: wordPath,
                    suite,
                    outputPath: pdfPath,
                });
                expect(wordPdf.ok).toBe(true);
            }
        }

        const excelCreate = await invokeSafe(client, 'excel_create', { path: excelPath, suite });
        expect(excelCreate.ok).toBe(true);

        const excelWrite = await invokeSafe(client, 'excel_write_range', {
            path: excelPath,
            suite,
            range: 'A1:B4',
            values: [
                ['名称', '价格'],
                ['茶杯', '10'],
                ['鼠标', '20'],
                ['键盘', '30'],
            ],
        });
        expect(excelWrite.ok).toBe(true);

        const excelRead = await invokeSafe(client, 'excel_read_range', {
            path: excelPath,
            suite,
            range: 'A1:B4',
        });
        expect(excelRead.ok).toBe(true);

        const addSheet = await invokeSafe(client, 'excel_add_worksheet', {
            path: excelPath,
            suite,
            name: `AIOS_${suite}`,
        });
        expect(addSheet.ok).toBe(true);

        if (enableExtended) {
            const setFormula = await invokeSafe(client, 'excel_set_formula', {
                path: excelPath,
                suite,
                range: 'C2',
                formula: '=B2*2',
            });
            expect(setFormula.ok).toBe(true);

            const sortRange = await invokeSafe(client, 'excel_sort_range', {
                path: excelPath,
                suite,
                range: 'A1:B4',
                key: 'B',
                order: 'desc',
                hasHeader: true,
            });
            expect(sortRange.ok).toBe(true);

            const filterRange = await invokeSafe(client, 'excel_filter_range', {
                path: excelPath,
                suite,
                range: 'A1:B4',
                column: 1,
                criteria: '茶杯',
            });
            expect(filterRange.ok).toBe(true);

            const createTable = await invokeSafe(client, 'excel_create_table', {
                path: excelPath,
                suite,
                range: 'A1:B4',
                name: 'AIOS_Table',
                hasHeader: true,
            });
            expect(createTable.ok).toBe(true);

            const addNamedRange = await invokeSafe(client, 'excel_add_named_range', {
                path: excelPath,
                suite,
                range: 'A2:B2',
                name: 'ItemRow',
            });
            expect(addNamedRange.ok).toBe(true);

            const setValidation = await invokeSafe(client, 'excel_set_data_validation', {
                path: excelPath,
                suite,
                range: 'C2',
                validationType: 'list',
                criteria: 'A,B',
                allowBlank: true,
            });
            expect(setValidation.ok).toBe(true);

            const applyFormatting = await invokeSafe(client, 'excel_apply_conditional_formatting', {
                path: excelPath,
                suite,
                range: 'B2:B4',
                ruleType: 'greater_than',
                value1: '15',
            });
            expect(applyFormatting.ok).toBe(true);

            const createChart = await invokeSafe(client, 'excel_create_chart', {
                path: excelPath,
                suite,
                range: 'A1:B4',
                chartType: 'column',
                title: '价格',
            });
            expect(createChart.ok).toBe(true);
        }

        const pptCreate = await invokeSafe(client, 'ppt_create', { path: pptPath, suite });
        expect(pptCreate.ok).toBe(true);

        const pptSlides = await invokeSafe(client, 'ppt_get_slides', { path: pptPath, suite });
        expect(pptSlides.ok).toBe(true);

        if (enableExtended) {
            await writeFile(imagePath, Buffer.from(
                'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=',
                'base64'
            ));

            const addSlide = await invokeSafe(client, 'ppt_add_slide', {
                path: pptPath,
                suite,
                layout: 'title',
            });
            expect(addSlide.ok).toBe(true);

            const duplicateSlide = await invokeSafe(client, 'ppt_duplicate_slide', {
                path: pptPath,
                suite,
                index: 1,
            });
            expect(duplicateSlide.ok).toBe(true);

            const insertText = await invokeSafe(client, 'ppt_insert_text', {
                path: pptPath,
                suite,
                index: 1,
                text: 'AIOS 演示',
            });
            expect(insertText.ok).toBe(true);

            const insertImage = await invokeSafe(client, 'ppt_insert_image', {
                path: pptPath,
                suite,
                index: 1,
                imagePath,
            });
            expect(insertImage.ok).toBe(true);

            const setLayout = await invokeSafe(client, 'ppt_set_layout', {
                path: pptPath,
                suite,
                index: 1,
                layout: 'title',
            });
            expect(setLayout.ok).toBe(true);

            if (pptThemePath) {
                const setTheme = await invokeSafe(client, 'ppt_set_theme', {
                    path: pptPath,
                    suite,
                    theme: pptThemePath,
                });
                expect(setTheme.ok).toBe(true);
            }

            const setNotes = await invokeSafe(client, 'ppt_set_notes', {
                path: pptPath,
                suite,
                index: 1,
                notes: '备注信息',
            });
            expect(setNotes.ok).toBe(true);

            const setTransition = await invokeSafe(client, 'ppt_set_transition', {
                path: pptPath,
                suite,
                index: 1,
                transition: 'fade',
            });
            expect(setTransition.ok).toBe(true);

            const setAnimation = await invokeSafe(client, 'ppt_set_animation', {
                path: pptPath,
                suite,
                index: 1,
                animation: 'appear',
            });
            expect(setAnimation.ok).toBe(true);

            const deleteSlide = await invokeSafe(client, 'ppt_delete_slide', {
                path: pptPath,
                suite,
                index: 2,
            });
            expect(deleteSlide.ok).toBe(true);
        }

        const listFiles = await invokeSafe(client, 'list_files', { folder: tempDir });
        expect(listFiles.ok).toBe(true);
    }, timeoutMs);

    it('权限缺失场景（需手动关闭权限后执行）', async () => {
        if (process.env.AIOS_EXPECT_PERMISSION_DENIED !== '1') return;

        const suite = suites[0];
        const result = await invokeSafe(client, 'word_create', { path: wordPath, suite });
        expect(result.ok).toBe(false);
        expect(result.error || '').toContain('Permission denied');
    }, timeoutMs);

    it('应用未安装场景（需确保指定套件未安装）', async () => {
        if (process.env.AIOS_EXPECT_APP_MISSING !== '1') return;

        const suite = process.env.AIOS_EXPECT_MISSING_SUITE || suites[0];
        const result = await invokeSafe(client, 'word_create', {
            path: join(tempDir, `aios-missing-${suite}.docx`),
            suite,
        });
        expect(result.ok).toBe(false);
    }, timeoutMs);

    it('前台焦点场景（执行中请切走焦点）', async () => {
        if (process.env.AIOS_EXPECT_FOCUS_FAIL !== '1') return;

        const suite = suites[0];
        const result = await invokeSafe(client, 'word_get_content', { path: wordPath, suite });
        expect(result.ok).toBe(false);
    }, timeoutMs);
});
