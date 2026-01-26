#!/usr/bin/env node
import { spawn } from 'child_process';
import { access } from 'fs/promises';
import { join, resolve } from 'path';
const cwd = process.cwd();
const daemonEntry = resolve(process.env.AIOS_DAEMON_ENTRY || join(cwd, 'packages/daemon/dist/index.js'));
const timeoutMs = Number(process.env.AIOS_SAAS_TIMEOUT_MS || 20000);
const flags = {
    spotify: process.env.AIOS_E2E_SPOTIFY === '1',
    slack: process.env.AIOS_E2E_SLACK === '1',
    gmail: process.env.AIOS_E2E_GMAIL === '1',
    notion: process.env.AIOS_E2E_NOTION === '1',
    feishu: process.env.AIOS_E2E_FEISHU === '1',
    wps: process.env.AIOS_E2E_WPS === '1',
};
const mockMode = process.env.AIOS_E2E_MOCK === '1';
const hasEnabledFlags = Object.values(flags).some(Boolean);
const effectiveFlags = mockMode && !hasEnabledFlags
    ? {
        spotify: true,
        slack: true,
        gmail: true,
        notion: true,
        feishu: true,
        wps: true,
    }
    : flags;

const results = [];
const record = (name, ok, message) => {
    results.push({ name, ok, message });
    const suffix = message ? ` - ${message}` : '';
    console[ok ? 'log' : 'error'](`[${ok ? 'OK' : 'FAIL'}] ${name}${suffix}`);
};

class JsonRpcClient {
    constructor(entry) { this.entry = entry; this.proc = null; this.buffer = ''; this.pending = new Map(); this.id = 0; }
    async start() {
        this.proc = spawn('node', [this.entry], { stdio: ['pipe', 'pipe', 'inherit'] });
        this.proc.stdout?.on('data', (data) => {
            this.buffer += data.toString();
            const lines = this.buffer.split('\n');
            this.buffer = lines.pop() || '';
            for (const line of lines) {
                if (!line.trim()) continue;
                try {
                    const res = JSON.parse(line);
                    const pending = this.pending.get(res.id);
                    if (pending) {
                        this.pending.delete(res.id);
                        res.error ? pending.reject(new Error(res.error.message)) : pending.resolve(res.result);
                    }
                } catch {
                    // 忽略解析失败
                }
            }
        });
        await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    stop() { this.proc?.kill(); }
    async call(method, params) {
        const id = ++this.id;
        const req = { jsonrpc: '2.0', id, method, params };
        return new Promise((resolve, reject) => {
            this.pending.set(id, { resolve, reject });
            this.proc?.stdin?.write(JSON.stringify(req) + '\n');
            setTimeout(() => {
                if (this.pending.has(id)) { this.pending.delete(id); reject(new Error('请求超时')); }
            }, timeoutMs);
        });
    }
}

const missingEnv = (names) => names.filter((name) => !process.env[name]);

async function runScenario(client, item, options = {}) {
    if (!item.enabled) return;
    if (options.mock) {
        return record(item.name, true, 'mock 模式已跳过真实调用');
    }
    const missing = item.checkEnv ? item.checkEnv() : missingEnv(item.requiredEnv || []);
    if (missing.length) return record(item.name, false, `缺少环境变量: ${missing.join(', ')}`);
    const status = await client.call('getAdapterStatus', { adapterId: item.adapterId }).catch((error) => ({ error }));
    if (status?.error || status?.available === false) return record(item.name, false, status?.error?.message || '适配器不可用');
    const result = await client.call('invoke', { adapterId: item.adapterId, capability: item.capability, args: item.args }).catch((error) => ({ error }));
    if (result?.error) return record(item.name, false, result.error.message);
    const ok = result?.success === true;
    return record(item.name, ok, ok ? undefined : result?.error?.message || '未知错误');
}

async function main() {
    if (mockMode && !hasEnabledFlags) {
        console.warn('[WARN] 已启用 mock 模式且未设置 AIOS_E2E_*，默认执行全部场景');
    }
    if (!mockMode) {
        await access(daemonEntry);
    }
    const client = mockMode ? null : new JsonRpcClient(daemonEntry);
    if (!mockMode) {
        await client.start();
    } else {
        console.warn('[WARN] 已启用 mock 模式，将跳过真实 API 调用');
    }

    const slackSend = process.env.AIOS_SLACK_SEND === '1';
    const gmailSend = process.env.AIOS_GMAIL_SEND === '1';
    const feishuTitle = process.env.AIOS_FEISHU_TITLE || 'AIOS E2E 文档';
    const wpsToken = process.env.WPS_ACCESS_TOKEN || process.env.KDOCS_ACCESS_TOKEN || '';
    const wpsFileId = process.env.AIOS_WPS_FILE_ID || '';
    const scenarios = [
        {
            name: 'Spotify 搜索',
            enabled: effectiveFlags.spotify,
            adapterId: 'com.aios.adapter.spotify',
            capability: 'search',
            args: { query: process.env.AIOS_SPOTIFY_QUERY || 'AIOS', type: 'track' },
            requiredEnv: ['SPOTIFY_CLIENT_ID', 'SPOTIFY_CLIENT_SECRET'],
        },
        {
            name: slackSend ? 'Slack 发送消息' : 'Slack 列出频道',
            enabled: effectiveFlags.slack,
            adapterId: 'com.aios.adapter.slack',
            capability: slackSend ? 'send_message' : 'list_channels',
            args: slackSend ? { channel: process.env.AIOS_SLACK_CHANNEL, text: process.env.AIOS_SLACK_TEXT || 'AIOS E2E Smoke' } : {},
            requiredEnv: slackSend ? ['SLACK_BOT_TOKEN', 'AIOS_SLACK_CHANNEL'] : ['SLACK_BOT_TOKEN'],
        },
        {
            name: gmailSend ? 'Gmail 发送邮件' : 'Gmail 列出邮件',
            enabled: effectiveFlags.gmail,
            adapterId: 'com.aios.adapter.gmail',
            capability: gmailSend ? 'send_email' : 'list_messages',
            args: gmailSend
                ? { to: process.env.AIOS_GMAIL_TO, subject: process.env.AIOS_GMAIL_SUBJECT || 'AIOS E2E', body: process.env.AIOS_GMAIL_BODY || 'AIOS Gmail E2E Smoke' }
                : { maxResults: Number(process.env.AIOS_GMAIL_MAX || 5) },
            requiredEnv: gmailSend ? ['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET', 'AIOS_GMAIL_TO'] : ['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET'],
        },
        {
            name: 'Notion 搜索',
            enabled: effectiveFlags.notion,
            adapterId: 'com.aios.adapter.notion',
            capability: 'search',
            args: { query: process.env.AIOS_NOTION_QUERY || 'AIOS' },
            requiredEnv: ['NOTION_TOKEN'],
        },
        {
            name: '飞书创建文档',
            enabled: effectiveFlags.feishu,
            adapterId: 'com.aios.adapter.feishu',
            capability: 'feishu_create_doc',
            args: {
                title: feishuTitle,
                folder_token: process.env.AIOS_FEISHU_FOLDER_TOKEN,
                tenant_access_token: process.env.FEISHU_TENANT_ACCESS_TOKEN || process.env.LARK_TENANT_ACCESS_TOKEN,
            },
            checkEnv: () => {
                const missing = [];
                if (!process.env.FEISHU_APP_ID) missing.push('FEISHU_APP_ID');
                if (!process.env.FEISHU_APP_SECRET) missing.push('FEISHU_APP_SECRET');
                if (!process.env.FEISHU_TENANT_ACCESS_TOKEN && !process.env.LARK_TENANT_ACCESS_TOKEN) {
                    missing.push('FEISHU_TENANT_ACCESS_TOKEN 或 LARK_TENANT_ACCESS_TOKEN');
                }
                return missing;
            },
        },
        {
            name: 'WPS 执行脚本',
            enabled: effectiveFlags.wps,
            adapterId: 'com.aios.adapter.wps_airscript',
            capability: 'wps_run_script',
            args: {
                file_id: wpsFileId,
                script: 'Application.Range(\"A1\").Value = \"AIOS\"',
                access_token: wpsToken,
            },
            checkEnv: () => {
                const missing = [];
                if (!wpsFileId) missing.push('AIOS_WPS_FILE_ID');
                if (!wpsToken) missing.push('WPS_ACCESS_TOKEN 或 KDOCS_ACCESS_TOKEN');
                return missing;
            },
        },
    ];

    if (!scenarios.some((item) => item.enabled)) {
        console.warn('[WARN] 未启用任何 SaaS E2E 测试，请设置 AIOS_E2E_* 环境变量');
        client?.stop();
        return;
    }

    for (const item of scenarios) await runScenario(client, item, { mock: mockMode });
    client?.stop();
    if (results.some((item) => !item.ok)) process.exitCode = 1;
}

main().catch((error) => {
    console.error(`[ERROR] 执行失败: ${error.message}`);
    process.exit(1);
});
