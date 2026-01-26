#!/usr/bin/env node
/**
 * Office 本地 UI 自动化 smoke 测试脚本
 */

import { spawn } from 'child_process';
import { access, mkdtemp, rm, writeFile } from 'fs/promises';
import { join, resolve } from 'path';
import { tmpdir } from 'os';

const adapterId = 'com.aios.adapter.office_local';
const requestTimeoutMs = Number(process.env.AIOS_OFFICE_TIMEOUT_MS || 60000);
const keepFiles = process.env.AIOS_OFFICE_KEEP_FILES === '1';
const allowUnsupported = process.env.AIOS_OFFICE_ALLOW_UNSUPPORTED === '1';
const enableExtended = process.env.AIOS_OFFICE_EXTENDED === '1';
const enablePdfExport = process.env.AIOS_OFFICE_PDF_EXPORT === '1';
const pptThemePath = process.env.AIOS_OFFICE_PPT_THEME || '';

const cwd = process.cwd();
const daemonEntry = resolve(
    process.env.AIOS_DAEMON_ENTRY || join(cwd, 'packages/daemon/dist/index.js')
);

const suiteEnv = process.env.AIOS_OFFICE_SUITES;
const platform = process.platform;
const defaultSuites = platform === 'linux' ? ['wps'] : ['microsoft'];
const suites = suiteEnv
    ? suiteEnv.split(',').map((item) => item.trim()).filter(Boolean)
    : defaultSuites;

const results = [];

function logInfo(message) {
    console.log(`[INFO] ${message}`);
}

function logWarn(message) {
    console.warn(`[WARN] ${message}`);
}

function logError(message) {
    console.error(`[ERROR] ${message}`);
}

async function ensureDaemonEntry() {
    try {
        await access(daemonEntry);
    } catch {
        throw new Error(`未找到 daemon 入口文件：${daemonEntry}，请先执行 pnpm --filter @aios/daemon build`);
    }
}

class JsonRpcClient {
    constructor(entry) {
        this.entry = entry;
        this.daemon = null;
        this.buffer = '';
        this.pending = new Map();
        this.requestId = 0;
    }

    async start() {
        this.daemon = spawn('node', [this.entry], {
            stdio: ['pipe', 'pipe', 'inherit'],
        });

        this.daemon.stdout?.on('data', (data) => {
            this.buffer += data.toString();
            this.processBuffer();
        });

        this.daemon.on('error', (error) => {
            logError(`daemon 启动失败: ${error.message}`);
        });

        this.daemon.on('exit', (code) => {
            logWarn(`daemon 退出，code=${code ?? 'unknown'}`);
        });

        await new Promise((resolve) => setTimeout(resolve, 1000));
    }

    stop() {
        this.daemon?.kill();
    }

    processBuffer() {
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

    async call(method, params) {
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
            }, requestTimeoutMs);
        });
    }
}

function recordResult(name, success, message) {
    results.push({ name, success, message });
    if (success) {
        logInfo(`${name} 成功`);
    } else {
        logError(`${name} 失败：${message}`);
    }
}

function normalizeTable(value) {
    if (!Array.isArray(value)) return [];
    return value.map((row) =>
        Array.isArray(row) ? row.map((cell) => (cell === null || cell === undefined ? '' : String(cell))) : []
    );
}

async function runSuite(client, suite, tempDir, imagePath) {
    if (platform === 'linux' && suite === 'microsoft' && !allowUnsupported) {
        logWarn('Linux 默认仅支持 WPS，已跳过 microsoft（如需强制执行请设置 AIOS_OFFICE_ALLOW_UNSUPPORTED=1）');
        return;
    }

    const wordPath = join(tempDir, `aios-${suite}-word.docx`);
    const excelPath = join(tempDir, `aios-${suite}-excel.xlsx`);
    const pptPath = join(tempDir, `aios-${suite}-ppt.pptx`);

    logInfo(`开始执行 suite=${suite} smoke 测试`);

    await client.call('invoke', {
        adapterId,
        capability: 'word_create',
        args: { path: wordPath, suite },
    }).then(
        (result) => recordResult(`${suite}:word_create`, result?.success === true, result?.error?.message || '未知错误'),
        (error) => recordResult(`${suite}:word_create`, false, error.message)
    );

    await client.call('invoke', {
        adapterId,
        capability: 'word_get_content',
        args: { path: wordPath, suite },
    }).then(
        (result) => {
            const ok = result?.success === true && typeof result?.data?.content === 'string';
            recordResult(`${suite}:word_get_content`, ok, result?.error?.message || '未返回文本内容');
        },
        (error) => recordResult(`${suite}:word_get_content`, false, error.message)
    );

    if (enableExtended) {
        await client.call('invoke', {
            adapterId,
            capability: 'word_append_text',
            args: { path: wordPath, suite, text: '扩展能力验证' },
        }).then(
            (result) => recordResult(`${suite}:word_append_text`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:word_append_text`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'word_insert_list',
            args: { path: wordPath, suite, items: ['一', '二', '三'], ordered: true },
        }).then(
            (result) => recordResult(`${suite}:word_insert_list`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:word_insert_list`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'word_insert_table',
            args: {
                path: wordPath,
                suite,
                rows: 2,
                cols: 2,
                values: [
                    ['项目', '数量'],
                    ['任务', '3'],
                ],
            },
        }).then(
            (result) => recordResult(`${suite}:word_insert_table`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:word_insert_table`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'word_apply_heading',
            args: { path: wordPath, suite, level: 1 },
        }).then(
            (result) => recordResult(`${suite}:word_apply_heading`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:word_apply_heading`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'word_add_comment',
            args: { path: wordPath, suite, comment: '扩展批注', search: 'AIOS Office' },
        }).then(
            (result) => recordResult(`${suite}:word_add_comment`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:word_add_comment`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'word_toggle_track_changes',
            args: { path: wordPath, suite, enabled: true },
        }).then(
            (result) => recordResult(`${suite}:word_toggle_track_changes`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:word_toggle_track_changes`, false, error.message)
        );

        if (enablePdfExport) {
            const pdfPath = wordPath.replace(/\\.docx$/i, '.pdf');
            await client.call('invoke', {
                adapterId,
                capability: 'word_export_pdf',
                args: { path: wordPath, suite, outputPath: pdfPath },
            }).then(
                (result) => recordResult(`${suite}:word_export_pdf`, result?.success === true, result?.error?.message || '未知错误'),
                (error) => recordResult(`${suite}:word_export_pdf`, false, error.message)
            );
        }
    }

    await client.call('invoke', {
        adapterId,
        capability: 'excel_create',
        args: { path: excelPath, suite },
    }).then(
        (result) => recordResult(`${suite}:excel_create`, result?.success === true, result?.error?.message || '未知错误'),
        (error) => recordResult(`${suite}:excel_create`, false, error.message)
    );

    const values = [
        ['名称', '价格'],
        ['茶杯', '10'],
        ['鼠标', '20'],
        ['键盘', '30'],
    ];

    await client.call('invoke', {
        adapterId,
        capability: 'excel_write_range',
        args: { path: excelPath, range: 'A1:B4', values, suite },
    }).then(
        (result) => recordResult(`${suite}:excel_write_range`, result?.success === true, result?.error?.message || '未知错误'),
        (error) => recordResult(`${suite}:excel_write_range`, false, error.message)
    );

    await client.call('invoke', {
        adapterId,
        capability: 'excel_read_range',
        args: { path: excelPath, range: 'A1:B4', suite },
    }).then(
        (result) => {
            const readValues = normalizeTable(result?.data?.values || result?.data?.rows || result?.data?.data);
            const ok = result?.success === true && readValues.length > 0;
            recordResult(`${suite}:excel_read_range`, ok, result?.error?.message || '读取数据为空');
        },
        (error) => recordResult(`${suite}:excel_read_range`, false, error.message)
    );

    await client.call('invoke', {
        adapterId,
        capability: 'excel_add_worksheet',
        args: { path: excelPath, name: `AIOS_${suite}`, suite },
    }).then(
        (result) => recordResult(`${suite}:excel_add_worksheet`, result?.success === true, result?.error?.message || '未知错误'),
        (error) => recordResult(`${suite}:excel_add_worksheet`, false, error.message)
    );

    if (enableExtended) {
        await client.call('invoke', {
            adapterId,
            capability: 'excel_set_formula',
            args: { path: excelPath, range: 'C2', formula: '=B2*2', suite },
        }).then(
            (result) => recordResult(`${suite}:excel_set_formula`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:excel_set_formula`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'excel_sort_range',
            args: { path: excelPath, range: 'A1:B4', key: 'B', order: 'desc', hasHeader: true, suite },
        }).then(
            (result) => recordResult(`${suite}:excel_sort_range`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:excel_sort_range`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'excel_filter_range',
            args: { path: excelPath, range: 'A1:B4', column: 1, criteria: '茶杯', suite },
        }).then(
            (result) => recordResult(`${suite}:excel_filter_range`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:excel_filter_range`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'excel_create_table',
            args: { path: excelPath, range: 'A1:B4', name: 'AIOS_Table', hasHeader: true, suite },
        }).then(
            (result) => recordResult(`${suite}:excel_create_table`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:excel_create_table`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'excel_add_named_range',
            args: { path: excelPath, range: 'A2:B2', name: 'ItemRow', suite },
        }).then(
            (result) => recordResult(`${suite}:excel_add_named_range`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:excel_add_named_range`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'excel_set_data_validation',
            args: { path: excelPath, range: 'C2', validationType: 'list', criteria: 'A,B', allowBlank: true, suite },
        }).then(
            (result) => recordResult(`${suite}:excel_set_data_validation`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:excel_set_data_validation`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'excel_apply_conditional_formatting',
            args: { path: excelPath, range: 'B2:B4', ruleType: 'greater_than', value1: '15', suite },
        }).then(
            (result) => recordResult(`${suite}:excel_apply_conditional_formatting`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:excel_apply_conditional_formatting`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'excel_create_chart',
            args: { path: excelPath, range: 'A1:B4', chartType: 'column', title: '价格', suite },
        }).then(
            (result) => recordResult(`${suite}:excel_create_chart`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:excel_create_chart`, false, error.message)
        );
    }

    await client.call('invoke', {
        adapterId,
        capability: 'ppt_create',
        args: { path: pptPath, suite },
    }).then(
        (result) => recordResult(`${suite}:ppt_create`, result?.success === true, result?.error?.message || '未知错误'),
        (error) => recordResult(`${suite}:ppt_create`, false, error.message)
    );

    await client.call('invoke', {
        adapterId,
        capability: 'ppt_get_slides',
        args: { path: pptPath, suite },
    }).then(
        (result) => {
            const slides = result?.data?.slides;
            const ok = result?.success === true && Array.isArray(slides);
            recordResult(`${suite}:ppt_get_slides`, ok, result?.error?.message || '未返回幻灯片列表');
        },
        (error) => recordResult(`${suite}:ppt_get_slides`, false, error.message)
    );

    if (enableExtended) {
        await client.call('invoke', {
            adapterId,
            capability: 'ppt_add_slide',
            args: { path: pptPath, suite, layout: 'title' },
        }).then(
            (result) => recordResult(`${suite}:ppt_add_slide`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:ppt_add_slide`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'ppt_duplicate_slide',
            args: { path: pptPath, suite, index: 1 },
        }).then(
            (result) => recordResult(`${suite}:ppt_duplicate_slide`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:ppt_duplicate_slide`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'ppt_insert_text',
            args: { path: pptPath, suite, index: 1, text: 'AIOS 演示' },
        }).then(
            (result) => recordResult(`${suite}:ppt_insert_text`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:ppt_insert_text`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'ppt_insert_image',
            args: { path: pptPath, suite, index: 1, imagePath },
        }).then(
            (result) => recordResult(`${suite}:ppt_insert_image`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:ppt_insert_image`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'ppt_set_layout',
            args: { path: pptPath, suite, index: 1, layout: 'title' },
        }).then(
            (result) => recordResult(`${suite}:ppt_set_layout`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:ppt_set_layout`, false, error.message)
        );

        if (pptThemePath) {
            await client.call('invoke', {
                adapterId,
                capability: 'ppt_set_theme',
                args: { path: pptPath, suite, theme: pptThemePath },
            }).then(
                (result) => recordResult(`${suite}:ppt_set_theme`, result?.success === true, result?.error?.message || '未知错误'),
                (error) => recordResult(`${suite}:ppt_set_theme`, false, error.message)
            );
        }

        await client.call('invoke', {
            adapterId,
            capability: 'ppt_set_notes',
            args: { path: pptPath, suite, index: 1, notes: '备注信息' },
        }).then(
            (result) => recordResult(`${suite}:ppt_set_notes`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:ppt_set_notes`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'ppt_set_transition',
            args: { path: pptPath, suite, index: 1, transition: 'fade' },
        }).then(
            (result) => recordResult(`${suite}:ppt_set_transition`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:ppt_set_transition`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'ppt_set_animation',
            args: { path: pptPath, suite, index: 1, animation: 'appear' },
        }).then(
            (result) => recordResult(`${suite}:ppt_set_animation`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:ppt_set_animation`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'ppt_delete_slide',
            args: { path: pptPath, suite, index: 2 },
        }).then(
            (result) => recordResult(`${suite}:ppt_delete_slide`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:ppt_delete_slide`, false, error.message)
        );
    }

    await client.call('invoke', {
        adapterId,
        capability: 'list_files',
        args: { folder: tempDir },
    }).then(
        (result) => recordResult(`${suite}:list_files`, result?.success === true, result?.error?.message || '未知错误'),
        (error) => recordResult(`${suite}:list_files`, false, error.message)
    );

    if (!keepFiles) {
        await client.call('invoke', {
            adapterId,
            capability: 'delete_file',
            args: { path: wordPath },
        }).then(
            (result) => recordResult(`${suite}:delete_word`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:delete_word`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'delete_file',
            args: { path: excelPath },
        }).then(
            (result) => recordResult(`${suite}:delete_excel`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:delete_excel`, false, error.message)
        );

        await client.call('invoke', {
            adapterId,
            capability: 'delete_file',
            args: { path: pptPath },
        }).then(
            (result) => recordResult(`${suite}:delete_ppt`, result?.success === true, result?.error?.message || '未知错误'),
            (error) => recordResult(`${suite}:delete_ppt`, false, error.message)
        );
    } else {
        logWarn(`已保留测试文件目录：${tempDir}`);
    }
}

async function main() {
    await ensureDaemonEntry();

    const client = new JsonRpcClient(daemonEntry);
    await client.start();

    const status = await client.call('getAdapterStatus', { adapterId });
    if (!status?.available) {
        client.stop();
        throw new Error('Office 本地适配器不可用，请检查依赖与权限。');
    }

    const tempDir = await mkdtemp(join(tmpdir(), 'aios-office-smoke-'));
    const imagePath = join(tempDir, 'aios-slide.png');

    try {
        if (enableExtended) {
            await writeFile(
                imagePath,
                Buffer.from(
                    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=',
                    'base64'
                )
            );
        }

        for (const suite of suites) {
            await runSuite(client, suite, tempDir, imagePath);
        }
    } finally {
        if (!keepFiles) {
            await rm(tempDir, { recursive: true, force: true });
        }
        client.stop();
    }

    const failures = results.filter((item) => !item.success);
    console.log('');
    console.log('==== Smoke 测试汇总 ====');
    results.forEach((item) => {
        console.log(`${item.success ? '✅' : '❌'} ${item.name}${item.success ? '' : ` - ${item.message}`}`);
    });

    if (failures.length > 0) {
        process.exitCode = 1;
    }
}

main().catch((error) => {
    logError(error.message || String(error));
    process.exit(1);
});
