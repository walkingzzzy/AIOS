/**
 * 本地 Office UI 自动化适配器
 * 支持 Microsoft Office 与 WPS（桌面版）
 */

import type { AdapterResult, AdapterCapability } from '@aios/shared';
import { BaseAdapter } from '../BaseAdapter.js';
import { spawnBackground } from '@aios/shared';
import { promises as fs } from 'fs';
import { homedir } from 'os';
import { resolve, dirname, join, basename, extname, relative, isAbsolute, sep } from 'path';
import { execFile, spawn } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

const ALLOWED_PATHS = [
    homedir(),
    '/tmp',
    '/var/tmp',
];

const FORBIDDEN_PATTERNS = [
    /^\/etc/,
    /^\/usr/,
    /^\/bin/,
    /^\/sbin/,
    /^\/boot/,
    /^\/root/,
    /^\/sys/,
    /^\/proc/,
    /^\/dev/,
    /\.ssh/,
    /\.gnupg/,
    /\.aws/,
    /\.config\/.*credentials/,
    /password/i,
    /secret/i,
];

const UI_OPEN_DELAY_MS = 1200;
const UI_STEP_DELAY_MS = 350;
const UI_COPY_DELAY_MS = 500;

const WINDOWS_PROG_IDS: Record<'microsoft' | 'wps', Record<'word' | 'excel' | 'ppt', string[]>> = {
    microsoft: {
        word: ['Word.Application'],
        excel: ['Excel.Application'],
        ppt: ['PowerPoint.Application'],
    },
    wps: {
        word: ['KWps.Application', 'Wps.Application'],
        excel: ['KET.Application', 'Et.Application'],
        ppt: ['KWpp.Application', 'Wpp.Application'],
    },
};

const MAC_APP_NAMES: Record<'microsoft' | 'wps', Record<'word' | 'excel' | 'ppt', string>> = {
    microsoft: {
        word: 'Microsoft Word',
        excel: 'Microsoft Excel',
        ppt: 'Microsoft PowerPoint',
    },
    wps: {
        word: 'WPS Office',
        excel: 'WPS Office',
        ppt: 'WPS Office',
    },
};

const LINUX_COMMANDS: Record<'wps', Record<'word' | 'excel' | 'ppt', string>> = {
    wps: {
        word: 'wps',
        excel: 'et',
        ppt: 'wpp',
    },
};

type OfficeSuite = 'microsoft' | 'wps';
type OfficeApp = 'word' | 'excel' | 'ppt';

type UiStep =
    | { type: 'delay'; ms: number }
    | { type: 'keystroke'; key: string; modifiers?: Array<'command' | 'shift' | 'option' | 'control'> }
    | { type: 'text'; text: string }
    | { type: 'keycode'; code: number; modifiers?: Array<'command' | 'shift' | 'option' | 'control'> }
    | { type: 'linux_key'; keys: string };

export class OfficeLocalAdapter extends BaseAdapter {
    readonly id = 'com.aios.adapter.office_local';
    readonly name = '本地 Office';
    readonly description = '本地 Office/WPS UI 自动化控制';

    private operationQueue: Promise<void> = Promise.resolve();

    readonly capabilities: AdapterCapability[] = [
        {
            id: 'word_create',
            name: 'word_create',
            description: '创建本地 Word 文档',
            permissionLevel: 'medium',
            parameters: [
                { name: 'name', type: 'string', required: false, description: '文档名称' },
                { name: 'folder', type: 'string', required: false, description: '文件夹路径' },
                { name: 'path', type: 'string', required: false, description: '文档完整路径' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'word_get_content',
            name: 'word_get_content',
            description: '读取本地 Word 文档内容',
            permissionLevel: 'low',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '文档路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '文档路径' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'word_set_content',
            name: 'word_set_content',
            description: '写入本地 Word 文档内容（覆盖）',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '文档路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '文档路径' },
                { name: 'content', type: 'string', required: true, description: '写入内容（纯文本）' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'word_replace_text',
            name: 'word_replace_text',
            description: '替换本地 Word 文档内容（纯文本）',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '文档路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '文档路径' },
                { name: 'search', type: 'string', required: true, description: '查找文本' },
                { name: 'replace', type: 'string', required: false, description: '替换文本（默认空）' },
                { name: 'matchCase', type: 'boolean', required: false, description: '是否区分大小写' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'word_append_text',
            name: 'word_append_text',
            description: '在本地 Word 文档末尾追加文本',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '文档路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '文档路径' },
                { name: 'text', type: 'string', required: true, description: '追加文本' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'word_insert_list',
            name: 'word_insert_list',
            description: '插入本地 Word 列表',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '文档路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '文档路径' },
                { name: 'items', type: 'array', required: true, description: '列表项数组' },
                { name: 'ordered', type: 'boolean', required: false, description: '是否有序列表' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'word_insert_table',
            name: 'word_insert_table',
            description: '插入本地 Word 表格',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '文档路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '文档路径' },
                { name: 'rows', type: 'number', required: true, description: '行数' },
                { name: 'cols', type: 'number', required: true, description: '列数' },
                { name: 'values', type: 'array', required: false, description: '表格内容（二维数组）' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'word_apply_heading',
            name: 'word_apply_heading',
            description: '应用本地 Word 标题样式',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '文档路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '文档路径' },
                { name: 'level', type: 'number', required: true, description: '标题级别（1-3）' },
                { name: 'search', type: 'string', required: false, description: '查找文本（为空则作用于首段）' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'word_export_pdf',
            name: 'word_export_pdf',
            description: '导出本地 Word 为 PDF',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '文档路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '文档路径' },
                { name: 'outputPath', type: 'string', required: false, description: '导出 PDF 路径' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'word_add_comment',
            name: 'word_add_comment',
            description: '在本地 Word 中添加批注',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '文档路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '文档路径' },
                { name: 'comment', type: 'string', required: true, description: '批注内容' },
                { name: 'search', type: 'string', required: false, description: '查找文本（为空则批注首段）' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'word_toggle_track_changes',
            name: 'word_toggle_track_changes',
            description: '切换本地 Word 修订模式',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '文档路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '文档路径' },
                { name: 'enabled', type: 'boolean', required: true, description: '是否启用修订' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'excel_create',
            name: 'excel_create',
            description: '创建本地 Excel 工作簿',
            permissionLevel: 'medium',
            parameters: [
                { name: 'name', type: 'string', required: false, description: '工作簿名称' },
                { name: 'folder', type: 'string', required: false, description: '文件夹路径' },
                { name: 'path', type: 'string', required: false, description: '工作簿完整路径' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'excel_read_range',
            name: 'excel_read_range',
            description: '读取本地 Excel 单元格范围',
            permissionLevel: 'low',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '工作簿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '工作簿路径' },
                { name: 'worksheet', type: 'string', required: false, description: '工作表名称' },
                { name: 'range', type: 'string', required: true, description: '范围（如 A1:C10）' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'excel_write_range',
            name: 'excel_write_range',
            description: '写入本地 Excel 单元格范围',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '工作簿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '工作簿路径' },
                { name: 'worksheet', type: 'string', required: false, description: '工作表名称' },
                { name: 'range', type: 'string', required: true, description: '范围' },
                { name: 'values', type: 'array', required: true, description: '数据（二维数组）' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'excel_add_worksheet',
            name: 'excel_add_worksheet',
            description: '添加本地 Excel 工作表',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '工作簿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '工作簿路径' },
                { name: 'name', type: 'string', required: true, description: '工作表名称' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'excel_set_formula',
            name: 'excel_set_formula',
            description: '写入本地 Excel 公式',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '工作簿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '工作簿路径' },
                { name: 'worksheet', type: 'string', required: false, description: '工作表名称' },
                { name: 'range', type: 'string', required: true, description: '范围' },
                { name: 'formula', type: 'string', required: true, description: '公式字符串（以 = 开头）' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'excel_sort_range',
            name: 'excel_sort_range',
            description: '排序本地 Excel 范围',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '工作簿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '工作簿路径' },
                { name: 'worksheet', type: 'string', required: false, description: '工作表名称' },
                { name: 'range', type: 'string', required: true, description: '范围' },
                { name: 'key', type: 'string', required: true, description: '排序键（列，如 A）' },
                { name: 'order', type: 'string', required: false, description: '排序方向 asc/desc' },
                { name: 'hasHeader', type: 'boolean', required: false, description: '是否包含表头' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'excel_filter_range',
            name: 'excel_filter_range',
            description: '筛选本地 Excel 范围',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '工作簿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '工作簿路径' },
                { name: 'worksheet', type: 'string', required: false, description: '工作表名称' },
                { name: 'range', type: 'string', required: true, description: '范围' },
                { name: 'column', type: 'number', required: true, description: '列索引（从1开始）' },
                { name: 'criteria', type: 'string', required: true, description: '筛选条件' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'excel_create_table',
            name: 'excel_create_table',
            description: '创建本地 Excel 表格',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '工作簿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '工作簿路径' },
                { name: 'worksheet', type: 'string', required: false, description: '工作表名称' },
                { name: 'range', type: 'string', required: true, description: '范围' },
                { name: 'name', type: 'string', required: false, description: '表格名称' },
                { name: 'hasHeader', type: 'boolean', required: false, description: '是否包含表头' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'excel_add_named_range',
            name: 'excel_add_named_range',
            description: '创建本地 Excel 命名区域',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '工作簿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '工作簿路径' },
                { name: 'worksheet', type: 'string', required: false, description: '工作表名称' },
                { name: 'range', type: 'string', required: true, description: '范围' },
                { name: 'name', type: 'string', required: true, description: '命名区域名称' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'excel_set_data_validation',
            name: 'excel_set_data_validation',
            description: '设置本地 Excel 数据验证',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '工作簿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '工作簿路径' },
                { name: 'worksheet', type: 'string', required: false, description: '工作表名称' },
                { name: 'range', type: 'string', required: true, description: '范围' },
                { name: 'validationType', type: 'string', required: true, description: '验证类型 list/whole/decimal' },
                { name: 'criteria', type: 'string', required: true, description: '验证条件/列表值' },
                { name: 'allowBlank', type: 'boolean', required: false, description: '是否允许空值' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'excel_apply_conditional_formatting',
            name: 'excel_apply_conditional_formatting',
            description: '设置本地 Excel 条件格式',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '工作簿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '工作簿路径' },
                { name: 'worksheet', type: 'string', required: false, description: '工作表名称' },
                { name: 'range', type: 'string', required: true, description: '范围' },
                { name: 'ruleType', type: 'string', required: true, description: '规则类型 greater_than/less_than/between' },
                { name: 'value1', type: 'string', required: true, description: '条件值1' },
                { name: 'value2', type: 'string', required: false, description: '条件值2' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'excel_create_chart',
            name: 'excel_create_chart',
            description: '创建本地 Excel 图表',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '工作簿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '工作簿路径' },
                { name: 'worksheet', type: 'string', required: false, description: '工作表名称' },
                { name: 'range', type: 'string', required: true, description: '数据范围' },
                { name: 'chartType', type: 'string', required: false, description: '图表类型 column/line/pie' },
                { name: 'title', type: 'string', required: false, description: '图表标题' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'ppt_create',
            name: 'ppt_create',
            description: '创建本地 PowerPoint 演示文稿',
            permissionLevel: 'medium',
            parameters: [
                { name: 'name', type: 'string', required: false, description: '演示文稿名称' },
                { name: 'folder', type: 'string', required: false, description: '文件夹路径' },
                { name: 'path', type: 'string', required: false, description: '演示文稿完整路径' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'ppt_get_slides',
            name: 'ppt_get_slides',
            description: '获取本地 PowerPoint 幻灯片信息',
            permissionLevel: 'low',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '演示文稿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '演示文稿路径' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'ppt_add_slide',
            name: 'ppt_add_slide',
            description: '新增本地 PowerPoint 幻灯片',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '演示文稿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '演示文稿路径' },
                { name: 'layout', type: 'string', required: false, description: '布局名称' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'ppt_delete_slide',
            name: 'ppt_delete_slide',
            description: '删除本地 PowerPoint 幻灯片',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '演示文稿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '演示文稿路径' },
                { name: 'index', type: 'number', required: true, description: '幻灯片序号（从1开始）' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'ppt_duplicate_slide',
            name: 'ppt_duplicate_slide',
            description: '复制本地 PowerPoint 幻灯片',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '演示文稿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '演示文稿路径' },
                { name: 'index', type: 'number', required: true, description: '幻灯片序号（从1开始）' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'ppt_insert_text',
            name: 'ppt_insert_text',
            description: '插入本地 PowerPoint 文本框',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '演示文稿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '演示文稿路径' },
                { name: 'index', type: 'number', required: true, description: '幻灯片序号（从1开始）' },
                { name: 'text', type: 'string', required: true, description: '文本内容' },
                { name: 'left', type: 'number', required: false, description: '左边距（磅）' },
                { name: 'top', type: 'number', required: false, description: '上边距（磅）' },
                { name: 'width', type: 'number', required: false, description: '宽度（磅）' },
                { name: 'height', type: 'number', required: false, description: '高度（磅）' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'ppt_insert_image',
            name: 'ppt_insert_image',
            description: '插入本地 PowerPoint 图片',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '演示文稿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '演示文稿路径' },
                { name: 'index', type: 'number', required: true, description: '幻灯片序号（从1开始）' },
                { name: 'imagePath', type: 'string', required: true, description: '图片路径' },
                { name: 'left', type: 'number', required: false, description: '左边距（磅）' },
                { name: 'top', type: 'number', required: false, description: '上边距（磅）' },
                { name: 'width', type: 'number', required: false, description: '宽度（磅）' },
                { name: 'height', type: 'number', required: false, description: '高度（磅）' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'ppt_set_layout',
            name: 'ppt_set_layout',
            description: '设置本地 PowerPoint 幻灯片布局',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '演示文稿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '演示文稿路径' },
                { name: 'index', type: 'number', required: true, description: '幻灯片序号（从1开始）' },
                { name: 'layout', type: 'string', required: true, description: '布局名称' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'ppt_set_theme',
            name: 'ppt_set_theme',
            description: '设置本地 PowerPoint 主题',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '演示文稿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '演示文稿路径' },
                { name: 'theme', type: 'string', required: true, description: '主题名称' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'ppt_set_notes',
            name: 'ppt_set_notes',
            description: '设置本地 PowerPoint 备注',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '演示文稿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '演示文稿路径' },
                { name: 'index', type: 'number', required: true, description: '幻灯片序号（从1开始）' },
                { name: 'notes', type: 'string', required: true, description: '备注内容' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'ppt_set_transition',
            name: 'ppt_set_transition',
            description: '设置本地 PowerPoint 过渡效果',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '演示文稿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '演示文稿路径' },
                { name: 'index', type: 'number', required: true, description: '幻灯片序号（从1开始）' },
                { name: 'transition', type: 'string', required: true, description: '过渡类型 fade/wipe' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'ppt_set_animation',
            name: 'ppt_set_animation',
            description: '设置本地 PowerPoint 动画效果',
            permissionLevel: 'medium',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '演示文稿路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '演示文稿路径' },
                { name: 'index', type: 'number', required: true, description: '幻灯片序号（从1开始）' },
                { name: 'animation', type: 'string', required: true, description: '动画类型 appear/fade' },
                { name: 'suite', type: 'string', required: false, description: '套件类型 microsoft/wps' },
            ],
        },
        {
            id: 'list_files',
            name: 'list_files',
            description: '列出本地 Office 文件',
            permissionLevel: 'low',
            parameters: [
                { name: 'folder', type: 'string', required: false, description: '文件夹路径' },
                { name: 'type', type: 'string', required: false, description: '文件类型过滤（word/excel/ppt）' },
            ],
        },
        {
            id: 'delete_file',
            name: 'delete_file',
            description: '删除本地 Office 文件',
            permissionLevel: 'high',
            parameters: [
                { name: 'itemId', type: 'string', required: false, description: '文件路径（兼容字段）' },
                { name: 'path', type: 'string', required: false, description: '文件路径' },
            ],
        },
    ];

    async checkAvailability(): Promise<boolean> {
        const platform = this.getPlatform();
        try {
            if (platform === 'darwin') {
                await execFileAsync('which', ['osascript']);
                return true;
            }
            if (platform === 'linux') {
                await execFileAsync('which', ['xdotool']);
                try {
                    await execFileAsync('which', ['xclip']);
                    return true;
                } catch {
                    await execFileAsync('which', ['xsel']);
                    return true;
                }
            }
            return platform === 'win32';
        } catch {
            return false;
        }
    }

    async invoke(capability: string, args: Record<string, unknown>): Promise<AdapterResult> {
        return this.runExclusive(async () => {
            try {
                switch (capability) {
                    case 'word_create':
                        return this.wordCreate(args);
                    case 'word_get_content':
                        return this.wordGetContent(args);
                    case 'word_set_content':
                        return this.wordSetContent(args);
                    case 'word_replace_text':
                        return this.wordReplaceText(args);
                    case 'word_append_text':
                        return this.wordAppendText(args);
                    case 'word_insert_list':
                        return this.wordInsertList(args);
                    case 'word_insert_table':
                        return this.wordInsertTable(args);
                    case 'word_apply_heading':
                        return this.wordApplyHeading(args);
                    case 'word_export_pdf':
                        return this.wordExportPdf(args);
                    case 'word_add_comment':
                        return this.wordAddComment(args);
                    case 'word_toggle_track_changes':
                        return this.wordToggleTrackChanges(args);
                    case 'excel_create':
                        return this.excelCreate(args);
                    case 'excel_read_range':
                        return this.excelReadRange(args);
                    case 'excel_write_range':
                        return this.excelWriteRange(args);
                    case 'excel_add_worksheet':
                        return this.excelAddWorksheet(args);
                    case 'excel_set_formula':
                        return this.excelSetFormula(args);
                    case 'excel_sort_range':
                        return this.excelSortRange(args);
                    case 'excel_filter_range':
                        return this.excelFilterRange(args);
                    case 'excel_create_table':
                        return this.excelCreateTable(args);
                    case 'excel_add_named_range':
                        return this.excelAddNamedRange(args);
                    case 'excel_set_data_validation':
                        return this.excelSetDataValidation(args);
                    case 'excel_apply_conditional_formatting':
                        return this.excelApplyConditionalFormatting(args);
                    case 'excel_create_chart':
                        return this.excelCreateChart(args);
                    case 'ppt_create':
                        return this.pptCreate(args);
                    case 'ppt_get_slides':
                        return this.pptGetSlides(args);
                    case 'ppt_add_slide':
                        return this.pptAddSlide(args);
                    case 'ppt_delete_slide':
                        return this.pptDeleteSlide(args);
                    case 'ppt_duplicate_slide':
                        return this.pptDuplicateSlide(args);
                    case 'ppt_insert_text':
                        return this.pptInsertText(args);
                    case 'ppt_insert_image':
                        return this.pptInsertImage(args);
                    case 'ppt_set_layout':
                        return this.pptSetLayout(args);
                    case 'ppt_set_theme':
                        return this.pptSetTheme(args);
                    case 'ppt_set_notes':
                        return this.pptSetNotes(args);
                    case 'ppt_set_transition':
                        return this.pptSetTransition(args);
                    case 'ppt_set_animation':
                        return this.pptSetAnimation(args);
                    case 'list_files':
                        return this.listFiles(args);
                    case 'delete_file':
                        return this.deleteFile(args);
                    default:
                        return this.failure('CAPABILITY_NOT_FOUND', `未知能力: ${capability}`);
                }
            } catch (error) {
                return this.failure('OPERATION_FAILED', String(error));
            }
        });
    }

    private runExclusive<T>(operation: () => Promise<T>): Promise<T> {
        const current = this.operationQueue.then(operation, operation);
        this.operationQueue = current.then(() => undefined, () => undefined);
        return current;
    }

    private parseSuite(input: unknown): OfficeSuite {
        if (input === undefined || input === null) {
            return 'microsoft';
        }
        if (typeof input !== 'string') {
            throw new Error('suite 必须是字符串');
        }
        const normalized = input.toLowerCase();
        if (normalized === 'microsoft' || normalized === 'wps') {
            return normalized as OfficeSuite;
        }
        throw new Error('suite 必须是 microsoft 或 wps');
    }

    private resolvePathInput(input: string): string {
        if (input.startsWith('~')) {
            return resolve(join(homedir(), input.slice(1)));
        }
        return resolve(input);
    }

    private checkPathSecurity(path: string): { allowed: boolean; reason?: string } {
        const normalizedPath = resolve(path);
        for (const pattern of FORBIDDEN_PATTERNS) {
            if (pattern.test(normalizedPath)) {
                return { allowed: false, reason: `路径包含敏感内容: ${normalizedPath}` };
            }
        }

        const isAllowed = ALLOWED_PATHS.some(allowedPath => {
            const rel = relative(allowedPath, normalizedPath);
            if (rel === '') return true;
            if (rel === '..' || rel.startsWith(`..${sep}`)) return false;
            return !isAbsolute(rel);
        });

        if (!isAllowed) {
            return { allowed: false, reason: `路径不在允许范围内: ${normalizedPath}` };
        }

        return { allowed: true };
    }

    private normalizeFilePath(params: Record<string, unknown>, extension: string, requireExisting: boolean): { ok: true; path: string } | { ok: false; result: AdapterResult } {
        const pathInput = typeof params.path === 'string' && params.path.trim()
            ? params.path
            : typeof params.itemId === 'string' && params.itemId.trim()
                ? params.itemId
                : '';
        const nameInput = typeof params.name === 'string' && params.name.trim() ? params.name : '';
        const folderInput = typeof params.folder === 'string' && params.folder.trim() ? params.folder : '';

        let filePath = '';
        if (pathInput) {
            filePath = this.resolvePathInput(pathInput);
        } else if (nameInput) {
            const fileName = nameInput.endsWith(`.${extension}`) ? nameInput : `${nameInput}.${extension}`;
            const folderPath = folderInput ? this.resolvePathInput(folderInput) : homedir();
            filePath = resolve(join(folderPath, fileName));
        } else {
            return { ok: false, result: this.failure('INVALID_PARAM', '必须提供 path/itemId 或 name') };
        }

        if (!extname(filePath)) {
            filePath = `${filePath}.${extension}`;
        }

        const security = this.checkPathSecurity(filePath);
        if (!security.allowed) {
            return { ok: false, result: this.failure('SECURITY_DENIED', security.reason || '路径访问被拒绝') };
        }

        if (requireExisting) {
            return { ok: true, path: filePath };
        }

        const folder = dirname(filePath);
        if (!this.checkPathSecurity(folder).allowed) {
            return { ok: false, result: this.failure('SECURITY_DENIED', '保存目录不在允许范围内') };
        }

        return { ok: true, path: filePath };
    }

    private async ensureFileExists(path: string): Promise<AdapterResult | null> {
        try {
            await fs.access(path);
            return null;
        } catch {
            return this.failure('NOT_FOUND', `文件不存在: ${path}`);
        }
    }

    private validateRange(range: unknown): string | null {
        if (typeof range !== 'string' || !range.trim()) {
            return null;
        }
        return range.trim();
    }

    private validateValues(values: unknown): unknown[][] | null {
        if (!Array.isArray(values)) return null;
        const rows = values as unknown[];
        if (!rows.every((row) => Array.isArray(row))) {
            return null;
        }
        return rows as unknown[][];
    }

    private normalizeStringArray(values: unknown): string[] | null {
        if (!Array.isArray(values)) return null;
        const items = values
            .map((item) => (typeof item === 'string' ? item.trim() : ''))
            .filter((item) => item.length > 0);
        if (items.length === 0) return null;
        return items;
    }

    private ensurePositiveInt(value: unknown, name: string): number | null {
        const num = Number(value);
        if (!Number.isInteger(num) || num <= 0) {
            return null;
        }
        return num;
    }

    private columnLettersToIndex(letters: string): number | null {
        if (!/^[A-Za-z]+$/.test(letters)) return null;
        const normalized = letters.toUpperCase();
        let result = 0;
        for (const char of normalized) {
            result = result * 26 + (char.charCodeAt(0) - 64);
        }
        return result;
    }

    private parseRange(range: string): { startCol: number; startRow: number; endCol: number; endRow: number } | null {
        const trimmed = range.trim();
        const singleMatch = /^([A-Za-z]+)(\d+)$/.exec(trimmed);
        if (singleMatch) {
            const col = this.columnLettersToIndex(singleMatch[1]);
            const row = Number(singleMatch[2]);
            if (!col || !Number.isInteger(row) || row <= 0) return null;
            return { startCol: col, startRow: row, endCol: col, endRow: row };
        }
        const match = /^([A-Za-z]+)(\d+):([A-Za-z]+)(\d+)$/.exec(trimmed);
        if (!match) return null;
        const startCol = this.columnLettersToIndex(match[1]);
        const startRow = Number(match[2]);
        const endCol = this.columnLettersToIndex(match[3]);
        const endRow = Number(match[4]);
        if (!startCol || !endCol || !Number.isInteger(startRow) || !Number.isInteger(endRow)) return null;
        if (startRow <= 0 || endRow <= 0) return null;
        return {
            startCol: Math.min(startCol, endCol),
            startRow: Math.min(startRow, endRow),
            endCol: Math.max(startCol, endCol),
            endRow: Math.max(startRow, endRow),
        };
    }

    private resolvePptLayout(layout?: string): number {
        const key = (layout || '').trim().toLowerCase();
        const mapping: Record<string, number> = {
            title: 1,
            text: 2,
            title_and_content: 2,
            two_column_text: 3,
            table: 4,
            chart: 8,
            title_only: 11,
            blank: 12,
            section_header: 33,
            comparison: 34,
            content_with_caption: 35,
            picture_with_caption: 36,
            two_objects: 29,
        };
        return mapping[key] ?? 2;
    }

    private resolvePptEntryEffect(effect: string): number {
        const key = effect.trim().toLowerCase();
        const mapping: Record<string, number> = {
            fade: 1793,
            appear: 3844,
            wipe: 1283,
        };
        return mapping[key] ?? 1793;
    }

    private async delay(ms: number): Promise<void> {
        await new Promise(resolve => setTimeout(resolve, ms));
    }

    private escapeAppleScriptString(text: string): string {
        return text.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    }

    private async runAppleScript(lines: string[]): Promise<string> {
        const args = lines.flatMap(line => ['-e', line]);
        const { stdout = '' } = await execFileAsync('osascript', args, { encoding: 'utf8' });
        return stdout.trimEnd();
    }

    private escapePowerShellString(text: string): string {
        return text.replace(/'/g, "''");
    }

    private async runPowerShell(script: string): Promise<string> {
        const { stdout = '' } = await execFileAsync('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', script], { encoding: 'utf8' });
        return stdout.trimEnd();
    }

    private async readClipboardText(): Promise<string> {
        const platform = this.getPlatform();
        if (platform === 'darwin') {
            const { stdout } = await execFileAsync('pbpaste', [], { encoding: 'utf8' });
            return stdout;
        }
        if (platform === 'win32') {
            const { stdout } = await execFileAsync('powershell', ['-NoProfile', '-Command', 'Get-Clipboard'], { encoding: 'utf8' });
            return stdout.trimEnd();
        }
        try {
            const { stdout } = await execFileAsync('xclip', ['-selection', 'clipboard', '-o'], { encoding: 'utf8' });
            return stdout;
        } catch {
            const { stdout } = await execFileAsync('xsel', ['--clipboard', '--output'], { encoding: 'utf8' });
            return stdout;
        }
    }

    private async writeClipboardText(text: string): Promise<void> {
        const platform = this.getPlatform();
        if (platform === 'darwin') {
            await this.runWithInput('pbcopy', [], text);
            return;
        }
        if (platform === 'win32') {
            await this.runWithInput('powershell', ['-NoProfile', '-Command', 'Set-Clipboard -Value ([Console]::In.ReadToEnd())'], text);
            return;
        }
        try {
            await this.runWithInput('xclip', ['-selection', 'clipboard'], text);
        } catch {
            await this.runWithInput('xsel', ['--clipboard', '--input'], text);
        }
    }

    private async writeClipboardImage(imagePath: string): Promise<void> {
        const platform = this.getPlatform();
        const extension = extname(imagePath).toLowerCase();
        if (platform === 'darwin') {
            const type = extension === '.png' ? 'PNG' : 'JPEG';
            const script = [
                `set theFile to POSIX file "${this.escapeAppleScriptString(imagePath)}"`,
                `set the clipboard to (read theFile as ${type} picture)`,
            ];
            await this.runAppleScript(script);
            return;
        }
        if (platform === 'linux') {
            const mime = extension === '.png' ? 'image/png' : 'image/jpeg';
            await execFileAsync('xclip', ['-selection', 'clipboard', '-t', mime, '-i', imagePath]);
            return;
        }
        throw new Error('当前平台不支持剪贴板图片');
    }

    private runWithInput(command: string, args: string[], input: string): Promise<void> {
        return new Promise((resolve, reject) => {
            const child = spawn(command, args, { stdio: ['pipe', 'ignore', 'pipe'] });
            let stderr = '';
            if (child.stderr) {
                child.stderr.on('data', (chunk) => {
                    stderr += chunk.toString();
                });
            }
            child.on('error', reject);
            child.on('close', (code) => {
                if (code === 0) {
                    resolve();
                    return;
                }
                const message = stderr.trim() || `${command} exited with code ${code ?? 'unknown'}`;
                reject(new Error(message));
            });
            if (child.stdin) {
                child.stdin.end(input);
            }
        });
    }

    private serializeTable(values: unknown[][]): string {
        return values.map((row) => row.map((cell) => {
            if (cell === null || cell === undefined) return '';
            if (typeof cell === 'string') return cell;
            if (typeof cell === 'number' || typeof cell === 'boolean') return String(cell);
            return JSON.stringify(cell);
        }).join('\t')).join('\n');
    }

    private parseTable(text: string): string[][] {
        const rows = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
        return rows.filter(row => row.length > 0).map(row => row.split('\t'));
    }

    private async openAppForUi(suite: OfficeSuite, app: OfficeApp, filePath?: string): Promise<void> {
        const platform = this.getPlatform();
        if (platform === 'darwin') {
            const appName = MAC_APP_NAMES[suite][app];
            const args = filePath ? ['-a', appName, filePath] : ['-a', appName];
            await execFileAsync('open', args);
            return;
        }
        if (platform === 'linux') {
            if (suite !== 'wps') {
                throw new Error('Linux 仅支持 WPS UI 自动化');
            }
            const command = LINUX_COMMANDS.wps[app];
            const args = filePath ? [filePath] : [];
            spawnBackground(command, args);
            return;
        }
        throw new Error('当前平台不支持 UI 启动');
    }

    private async runMacUiSteps(appName: string, steps: UiStep[]): Promise<void> {
        const lines: string[] = [];
        lines.push(`tell application "${this.escapeAppleScriptString(appName)}" to activate`);
        lines.push('tell application "System Events"');
        for (const step of steps) {
            if (step.type === 'delay') {
                lines.push(`delay ${Math.max(step.ms, 0) / 1000}`);
            } else if (step.type === 'keystroke') {
                const key = this.escapeAppleScriptString(step.key);
                if (step.modifiers && step.modifiers.length > 0) {
                    const mods = step.modifiers.map(mod => `${mod} down`).join(', ');
                    lines.push(`keystroke "${key}" using {${mods}}`);
                } else {
                    lines.push(`keystroke "${key}"`);
                }
            } else if (step.type === 'text') {
                const text = this.escapeAppleScriptString(step.text);
                lines.push(`keystroke "${text}"`);
            } else if (step.type === 'keycode') {
                if (step.modifiers && step.modifiers.length > 0) {
                    const mods = step.modifiers.map(mod => `${mod} down`).join(', ');
                    lines.push(`key code ${step.code} using {${mods}}`);
                } else {
                    lines.push(`key code ${step.code}`);
                }
            }
        }
        lines.push('end tell');
        await this.runAppleScript(lines);
    }

    private async runLinuxUiSteps(appName: string, steps: UiStep[]): Promise<void> {
        await execFileAsync('xdotool', ['search', '--name', appName, 'windowactivate', '--sync']).catch(() => undefined);
        for (const step of steps) {
            if (step.type === 'delay') {
                await this.delay(step.ms);
            } else if (step.type === 'linux_key') {
                await execFileAsync('xdotool', ['key', '--clearmodifiers', step.keys]);
            } else if (step.type === 'text') {
                await execFileAsync('xdotool', ['type', '--delay', '20', step.text]);
            }
        }
    }

    private async runUiSequence(suite: OfficeSuite, app: OfficeApp, steps: UiStep[]): Promise<void> {
        const platform = this.getPlatform();
        if (platform === 'darwin') {
            const appName = MAC_APP_NAMES[suite][app];
            await this.runMacUiSteps(appName, steps);
            return;
        }
        if (platform === 'linux') {
            if (suite !== 'wps') {
                throw new Error('Linux 仅支持 WPS UI 自动化');
            }
            const appName = LINUX_COMMANDS.wps[app];
            await this.runLinuxUiSteps(appName, steps);
            return;
        }
        throw new Error('当前平台不支持 UI 自动化步骤');
    }

    private async wordCreate(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const normalized = this.normalizeFilePath(params, 'docx', false);
        if (!normalized.ok) return normalized.result;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.wordCreateWindows(suite, normalized.path);
            return this.success({ path: normalized.path });
        }

        await fs.mkdir(dirname(normalized.path), { recursive: true });
        await this.openAppForUi(suite, 'word');
        await this.delay(UI_OPEN_DELAY_MS);
        await this.runUiSequence(suite, 'word', [
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'n', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+n' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
        ]);
        await this.saveAsUi(suite, 'word', normalized.path);
        return this.success({ path: normalized.path });
    }

    private async wordGetContent(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const normalized = this.normalizeFilePath(params, 'docx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            const text = await this.wordGetContentWindows(suite, normalized.path);
            return this.success({ path: normalized.path, content: text });
        }

        const previousClipboard = await this.safeReadClipboard();
        await this.openAppForUi(suite, 'word', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.runUiSequence(suite, 'word', [
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'a', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+a' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'c', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+c' },
            { type: 'delay', ms: UI_COPY_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        const content = await this.safeReadClipboard();
        await this.restoreClipboard(previousClipboard);
        return this.success({ path: normalized.path, content });
    }

    private async wordSetContent(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        if (typeof params.content !== 'string') {
            return this.failure('INVALID_PARAM', 'content 必须是字符串');
        }
        const normalized = this.normalizeFilePath(params, 'docx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();
        const content = params.content as string;

        if (platform === 'win32') {
            await this.wordSetContentWindows(suite, normalized.path, content);
            return this.success({ path: normalized.path, length: content.length });
        }

        const previousClipboard = await this.safeReadClipboard();
        await this.writeClipboardText(content);
        await this.openAppForUi(suite, 'word', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.runUiSequence(suite, 'word', [
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'a', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+a' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'v', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+v' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        await this.restoreClipboard(previousClipboard);
        return this.success({ path: normalized.path, length: content.length });
    }

    private async wordReplaceText(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const search = typeof params.search === 'string' ? params.search : '';
        if (!search.trim()) {
            return this.failure('INVALID_PARAM', 'search 必须是非空字符串');
        }
        const replace = typeof params.replace === 'string' ? params.replace : '';
        const matchCase = params.matchCase === true;
        const normalized = this.normalizeFilePath(params, 'docx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.wordReplaceTextWindows(suite, normalized.path, search, replace, matchCase);
            return this.success({ path: normalized.path, replaced: true });
        }

        const current = await this.wordGetContent({ path: normalized.path, suite });
        if (!current.success) return current;
        const content = (current.data?.content as string) ?? '';
        const updated = this.replacePlainText(content, search, replace, matchCase);
        await this.wordSetContent({ path: normalized.path, suite, content: updated });
        return this.success({ path: normalized.path, replaced: true });
    }

    private async wordAppendText(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        if (typeof params.text !== 'string') {
            return this.failure('INVALID_PARAM', 'text 必须是字符串');
        }
        const normalized = this.normalizeFilePath(params, 'docx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();
        const text = params.text as string;

        if (platform === 'win32') {
            await this.wordAppendTextWindows(suite, normalized.path, text);
            return this.success({ path: normalized.path, appended: true });
        }

        const previousClipboard = await this.safeReadClipboard();
        await this.writeClipboardText(text);
        await this.openAppForUi(suite, 'word', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.runUiSequence(suite, 'word', [
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'a', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+a' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keycode', code: 124 }
                : { type: 'linux_key', keys: 'End' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'v', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+v' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        await this.restoreClipboard(previousClipboard);
        return this.success({ path: normalized.path, appended: true });
    }

    private async wordInsertList(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const items = this.normalizeStringArray(params.items);
        if (!items) {
            return this.failure('INVALID_PARAM', 'items 必须是非空字符串数组');
        }
        const ordered = params.ordered === true;
        const normalized = this.normalizeFilePath(params, 'docx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.wordInsertListWindows(suite, normalized.path, items, ordered);
            return this.success({ path: normalized.path, inserted: items.length });
        }

        const previousClipboard = await this.safeReadClipboard();
        const listText = items.join('\n');
        await this.writeClipboardText(listText);
        await this.openAppForUi(suite, 'word', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        const listShortcut = ordered
            ? (platform === 'darwin'
                ? { type: 'keystroke', key: '7', modifiers: ['command', 'shift'] }
                : { type: 'linux_key', keys: 'ctrl+shift+7' })
            : (platform === 'darwin'
                ? { type: 'keystroke', key: 'l', modifiers: ['command', 'shift'] }
                : { type: 'linux_key', keys: 'ctrl+shift+l' });
        await this.runUiSequence(suite, 'word', [
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'a', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+a' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keycode', code: 124 }
                : { type: 'linux_key', keys: 'End' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            listShortcut,
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'v', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+v' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keycode', code: 36 }
                : { type: 'linux_key', keys: 'Return' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            listShortcut,
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        await this.restoreClipboard(previousClipboard);
        return this.success({ path: normalized.path, inserted: items.length });
    }

    private async wordInsertTable(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const rows = this.ensurePositiveInt(params.rows, 'rows');
        const cols = this.ensurePositiveInt(params.cols, 'cols');
        if (!rows || !cols) {
            return this.failure('INVALID_PARAM', 'rows/cols 必须是正整数');
        }
        const values = params.values ? this.validateValues(params.values) : null;
        if (params.values !== undefined && !values) {
            return this.failure('INVALID_PARAM', 'values 必须是二维数组');
        }
        const normalized = this.normalizeFilePath(params, 'docx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.wordInsertTableWindows(suite, normalized.path, rows, cols, values ?? []);
            return this.success({ path: normalized.path, rows, cols });
        }

        const previousClipboard = await this.safeReadClipboard();
        if (values) {
            await this.writeClipboardText(this.serializeTable(values));
        }
        await this.openAppForUi(suite, 'word', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        const tableShortcut = platform === 'darwin'
            ? { type: 'keystroke', key: 't', modifiers: ['command', 'option', 'shift'] }
            : { type: 'linux_key', keys: 'ctrl+alt+shift+t' };
        await this.runUiSequence(suite, 'word', [
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'a', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+a' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keycode', code: 124 }
                : { type: 'linux_key', keys: 'End' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            tableShortcut,
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            { type: 'text', text: `${rows}` },
            platform === 'darwin'
                ? { type: 'keycode', code: 48 }
                : { type: 'linux_key', keys: 'Tab' },
            { type: 'text', text: `${cols}` },
            platform === 'darwin'
                ? { type: 'keycode', code: 36 }
                : { type: 'linux_key', keys: 'Return' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            ...(values ? [
                platform === 'darwin'
                    ? { type: 'keystroke', key: 'v', modifiers: ['command'] }
                    : { type: 'linux_key', keys: 'ctrl+v' },
                { type: 'delay', ms: UI_STEP_DELAY_MS },
            ] : []),
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        await this.restoreClipboard(previousClipboard);
        return this.success({ path: normalized.path, rows, cols });
    }

    private async wordApplyHeading(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const level = this.ensurePositiveInt(params.level, 'level');
        if (!level || level > 3) {
            return this.failure('INVALID_PARAM', 'level 必须是 1-3');
        }
        const search = typeof params.search === 'string' ? params.search.trim() : '';
        const normalized = this.normalizeFilePath(params, 'docx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.wordApplyHeadingWindows(suite, normalized.path, level, search);
            return this.success({ path: normalized.path, level });
        }

        await this.openAppForUi(suite, 'word', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        if (search) {
            const previousClipboard = await this.safeReadClipboard();
            await this.writeClipboardText(search);
            await this.runUiSequence(suite, 'word', [
                platform === 'darwin'
                    ? { type: 'keystroke', key: 'f', modifiers: ['command'] }
                    : { type: 'linux_key', keys: 'ctrl+f' },
                { type: 'delay', ms: UI_STEP_DELAY_MS },
                platform === 'darwin'
                    ? { type: 'keystroke', key: 'v', modifiers: ['command'] }
                    : { type: 'linux_key', keys: 'ctrl+v' },
                { type: 'delay', ms: UI_STEP_DELAY_MS },
                platform === 'darwin'
                    ? { type: 'keycode', code: 36 }
                    : { type: 'linux_key', keys: 'Return' },
                { type: 'delay', ms: UI_STEP_DELAY_MS },
            ]);
            await this.restoreClipboard(previousClipboard);
        }
        const headingShortcut = platform === 'darwin'
            ? { type: 'keystroke', key: String(level), modifiers: ['command', 'option'] }
            : { type: 'linux_key', keys: `ctrl+alt+${level}` };
        await this.runUiSequence(suite, 'word', [
            headingShortcut,
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        return this.success({ path: normalized.path, level });
    }

    private async wordExportPdf(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const normalized = this.normalizeFilePath(params, 'docx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const outputInput = typeof params.outputPath === 'string' && params.outputPath.trim()
            ? params.outputPath.trim()
            : normalized.path.replace(/\.docx$/i, '.pdf');
        const outputPath = this.resolvePathInput(outputInput);
        const security = this.checkPathSecurity(outputPath);
        if (!security.allowed) {
            return this.failure('SECURITY_DENIED', security.reason || '导出路径不在允许范围内');
        }
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.wordExportPdfWindows(suite, normalized.path, outputPath);
            return this.success({ path: normalized.path, outputPath });
        }

        try {
            await execFileAsync('soffice', ['--headless', '--convert-to', 'pdf', '--outdir', dirname(outputPath), normalized.path]);
            return this.success({ path: normalized.path, outputPath });
        } catch {
            return this.failure('EXPORT_FAILED', '未能导出 PDF，请确保安装 soffice');
        }
    }

    private async wordAddComment(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const comment = typeof params.comment === 'string' ? params.comment.trim() : '';
        if (!comment) {
            return this.failure('INVALID_PARAM', 'comment 必须是非空字符串');
        }
        const search = typeof params.search === 'string' ? params.search.trim() : '';
        const normalized = this.normalizeFilePath(params, 'docx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.wordAddCommentWindows(suite, normalized.path, comment, search);
            return this.success({ path: normalized.path, commented: true });
        }

        await this.openAppForUi(suite, 'word', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        if (search) {
            const previousClipboard = await this.safeReadClipboard();
            await this.writeClipboardText(search);
            await this.runUiSequence(suite, 'word', [
                platform === 'darwin'
                    ? { type: 'keystroke', key: 'f', modifiers: ['command'] }
                    : { type: 'linux_key', keys: 'ctrl+f' },
                { type: 'delay', ms: UI_STEP_DELAY_MS },
                platform === 'darwin'
                    ? { type: 'keystroke', key: 'v', modifiers: ['command'] }
                    : { type: 'linux_key', keys: 'ctrl+v' },
                { type: 'delay', ms: UI_STEP_DELAY_MS },
                platform === 'darwin'
                    ? { type: 'keycode', code: 36 }
                    : { type: 'linux_key', keys: 'Return' },
                { type: 'delay', ms: UI_STEP_DELAY_MS },
            ]);
            await this.restoreClipboard(previousClipboard);
        }
        const previousClipboard = await this.safeReadClipboard();
        await this.writeClipboardText(comment);
        await this.runUiSequence(suite, 'word', [
            platform === 'darwin'
                ? { type: 'keystroke', key: 'm', modifiers: ['command', 'option'] }
                : { type: 'linux_key', keys: 'ctrl+alt+m' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'v', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+v' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keycode', code: 53 }
                : { type: 'linux_key', keys: 'Escape' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        await this.restoreClipboard(previousClipboard);
        return this.success({ path: normalized.path, commented: true });
    }

    private async wordToggleTrackChanges(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const enabled = params.enabled === true;
        const normalized = this.normalizeFilePath(params, 'docx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.wordToggleTrackChangesWindows(suite, normalized.path, enabled);
            return this.success({ path: normalized.path, enabled });
        }

        await this.openAppForUi(suite, 'word', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.runUiSequence(suite, 'word', [
            platform === 'darwin'
                ? { type: 'keystroke', key: 'e', modifiers: ['command', 'shift'] }
                : { type: 'linux_key', keys: 'ctrl+shift+e' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        return this.success({ path: normalized.path, enabled });
    }

    private async excelCreate(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const normalized = this.normalizeFilePath(params, 'xlsx', false);
        if (!normalized.ok) return normalized.result;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.excelCreateWindows(suite, normalized.path);
            return this.success({ path: normalized.path });
        }

        await fs.mkdir(dirname(normalized.path), { recursive: true });
        await this.openAppForUi(suite, 'excel');
        await this.delay(UI_OPEN_DELAY_MS);
        await this.runUiSequence(suite, 'excel', [
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'n', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+n' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
        ]);
        await this.saveAsUi(suite, 'excel', normalized.path);
        return this.success({ path: normalized.path });
    }

    private async excelReadRange(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const range = this.validateRange(params.range);
        if (!range) {
            return this.failure('INVALID_PARAM', 'range 必须是非空字符串');
        }
        const normalized = this.normalizeFilePath(params, 'xlsx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            const values = await this.excelReadRangeWindows(suite, normalized.path, params.worksheet as string, range);
            return this.success({ path: normalized.path, range, values });
        }

        const previousClipboard = await this.safeReadClipboard();
        await this.openAppForUi(suite, 'excel', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.goToRangeUi(suite, 'excel', range);
        await this.runUiSequence(suite, 'excel', [
            platform === 'darwin'
                ? { type: 'keystroke', key: 'c', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+c' },
            { type: 'delay', ms: UI_COPY_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        const text = await this.safeReadClipboard();
        await this.restoreClipboard(previousClipboard);
        const values = this.parseTable(text);
        return this.success({ path: normalized.path, range, values });
    }

    private async excelWriteRange(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const range = this.validateRange(params.range);
        if (!range) {
            return this.failure('INVALID_PARAM', 'range 必须是非空字符串');
        }
        const values = this.validateValues(params.values);
        if (!values) {
            return this.failure('INVALID_PARAM', 'values 必须是二维数组');
        }
        const normalized = this.normalizeFilePath(params, 'xlsx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.excelWriteRangeWindows(suite, normalized.path, params.worksheet as string, range, values);
            return this.success({ path: normalized.path, range, written: true });
        }

        const previousClipboard = await this.safeReadClipboard();
        await this.writeClipboardText(this.serializeTable(values));
        await this.openAppForUi(suite, 'excel', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.goToRangeUi(suite, 'excel', range);
        await this.runUiSequence(suite, 'excel', [
            platform === 'darwin'
                ? { type: 'keystroke', key: 'v', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+v' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        await this.restoreClipboard(previousClipboard);
        return this.success({ path: normalized.path, range, written: true });
    }

    private async excelAddWorksheet(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const name = typeof params.name === 'string' ? params.name.trim() : '';
        if (!name) {
            return this.failure('INVALID_PARAM', 'name 必须是非空字符串');
        }
        const normalized = this.normalizeFilePath(params, 'xlsx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.excelAddWorksheetWindows(suite, normalized.path, name);
            return this.success({ path: normalized.path, name });
        }

        await this.openAppForUi(suite, 'excel', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.runUiSequence(suite, 'excel', [
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keycode', code: 103, modifiers: ['shift'] }
                : { type: 'linux_key', keys: 'shift+F11' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keycode', code: 120 }
                : { type: 'linux_key', keys: 'F2' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            { type: 'text', text: name },
            platform === 'darwin'
                ? { type: 'keycode', code: 36 }
                : { type: 'linux_key', keys: 'Return' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);

        return this.success({ path: normalized.path, name });
    }

    private async excelSetFormula(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const range = this.validateRange(params.range);
        if (!range) {
            return this.failure('INVALID_PARAM', 'range 必须是非空字符串');
        }
        const formula = typeof params.formula === 'string' ? params.formula.trim() : '';
        if (!formula) {
            return this.failure('INVALID_PARAM', 'formula 必须是非空字符串');
        }
        const normalized = this.normalizeFilePath(params, 'xlsx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.excelSetFormulaWindows(suite, normalized.path, params.worksheet as string, range, formula);
            return this.success({ path: normalized.path, range, formula });
        }

        const parsed = this.parseRange(range);
        if (!parsed) {
            return this.failure('INVALID_PARAM', 'range 格式无效');
        }
        const rows = parsed.endRow - parsed.startRow + 1;
        const cols = parsed.endCol - parsed.startCol + 1;
        const values = Array.from({ length: rows }, () => Array.from({ length: cols }, () => formula));
        const result = await this.excelWriteRange({
            path: normalized.path,
            suite,
            worksheet: params.worksheet,
            range,
            values,
        });
        if (!result.success) return result;
        return this.success({ path: normalized.path, range, formula });
    }

    private async excelSortRange(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const range = this.validateRange(params.range);
        if (!range) {
            return this.failure('INVALID_PARAM', 'range 必须是非空字符串');
        }
        const keyInput = params.key;
        const order = typeof params.order === 'string' && params.order.toLowerCase() === 'desc' ? 'desc' : 'asc';
        const hasHeader = params.hasHeader === true;
        const normalized = this.normalizeFilePath(params, 'xlsx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();
        const parsed = this.parseRange(range);
        if (!parsed) {
            return this.failure('INVALID_PARAM', 'range 格式无效');
        }

        let keyColIndex: number | null = null;
        if (typeof keyInput === 'string' && keyInput.trim()) {
            const colIndex = this.columnLettersToIndex(keyInput.trim());
            if (colIndex) {
                keyColIndex = colIndex - parsed.startCol;
            }
        } else if (typeof keyInput === 'number' && Number.isFinite(keyInput)) {
            keyColIndex = Math.floor(keyInput) - 1;
        }
        if (keyColIndex === null || keyColIndex < 0 || keyColIndex > (parsed.endCol - parsed.startCol)) {
            return this.failure('INVALID_PARAM', 'key 必须是有效列');
        }

        if (platform === 'win32') {
            await this.excelSortRangeWindows(suite, normalized.path, params.worksheet as string, range, keyColIndex + 1, order, hasHeader);
            return this.success({ path: normalized.path, range, key: keyInput, order });
        }

        const read = await this.excelReadRange({
            path: normalized.path,
            suite,
            worksheet: params.worksheet,
            range,
        });
        if (!read.success) return read;
        const values = (read.data?.values as string[][]) ?? [];
        const header = hasHeader ? values.slice(0, 1) : [];
        const body = hasHeader ? values.slice(1) : values.slice(0);
        const sorted = [...body].sort((a, b) => {
            const left = a[keyColIndex] ?? '';
            const right = b[keyColIndex] ?? '';
            const leftNum = Number(left);
            const rightNum = Number(right);
            let result = 0;
            if (Number.isFinite(leftNum) && Number.isFinite(rightNum)) {
                result = leftNum - rightNum;
            } else {
                result = String(left).localeCompare(String(right), 'zh');
            }
            return order === 'desc' ? -result : result;
        });
        const next = [...header, ...sorted];
        const result = await this.excelWriteRange({
            path: normalized.path,
            suite,
            worksheet: params.worksheet,
            range,
            values: next,
        });
        if (!result.success) return result;
        return this.success({ path: normalized.path, range, key: keyInput, order });
    }

    private async excelFilterRange(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const range = this.validateRange(params.range);
        if (!range) {
            return this.failure('INVALID_PARAM', 'range 必须是非空字符串');
        }
        const column = this.ensurePositiveInt(params.column, 'column');
        if (!column) {
            return this.failure('INVALID_PARAM', 'column 必须是正整数');
        }
        const criteria = typeof params.criteria === 'string' ? params.criteria.trim() : '';
        if (!criteria) {
            return this.failure('INVALID_PARAM', 'criteria 必须是非空字符串');
        }
        const normalized = this.normalizeFilePath(params, 'xlsx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.excelFilterRangeWindows(suite, normalized.path, params.worksheet as string, range, column, criteria);
            return this.success({ path: normalized.path, range, column, criteria });
        }

        const read = await this.excelReadRange({
            path: normalized.path,
            suite,
            worksheet: params.worksheet,
            range,
        });
        if (!read.success) return read;
        const values = (read.data?.values as string[][]) ?? [];
        const header = values.slice(0, 1);
        const body = values.slice(1);
        const index = column - 1;
        const filtered = body.filter((row) => String(row[index] ?? '').includes(criteria));
        const parsed = this.parseRange(range);
        if (!parsed) {
            return this.failure('INVALID_PARAM', 'range 格式无效');
        }
        const totalRows = parsed.endRow - parsed.startRow + 1;
        const colCount = parsed.endCol - parsed.startCol + 1;
        const padded = [...header, ...filtered];
        while (padded.length < totalRows) {
            padded.push(Array.from({ length: colCount }, () => ''));
        }
        const result = await this.excelWriteRange({
            path: normalized.path,
            suite,
            worksheet: params.worksheet,
            range,
            values: padded,
        });
        if (!result.success) return result;
        return this.success({ path: normalized.path, range, column, criteria, matched: filtered.length });
    }

    private async excelCreateTable(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const range = this.validateRange(params.range);
        if (!range) {
            return this.failure('INVALID_PARAM', 'range 必须是非空字符串');
        }
        const name = typeof params.name === 'string' ? params.name.trim() : '';
        const hasHeader = params.hasHeader !== false;
        const normalized = this.normalizeFilePath(params, 'xlsx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.excelCreateTableWindows(suite, normalized.path, params.worksheet as string, range, name, hasHeader);
            return this.success({ path: normalized.path, range, name: name || undefined });
        }

        await this.openAppForUi(suite, 'excel', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.goToRangeUi(suite, 'excel', range);
        await this.runUiSequence(suite, 'excel', [
            platform === 'darwin'
                ? { type: 'keystroke', key: 't', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+t' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keycode', code: 36 }
                : { type: 'linux_key', keys: 'Return' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        return this.success({ path: normalized.path, range, name: name || undefined });
    }

    private async excelAddNamedRange(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const range = this.validateRange(params.range);
        if (!range) {
            return this.failure('INVALID_PARAM', 'range 必须是非空字符串');
        }
        const name = typeof params.name === 'string' ? params.name.trim() : '';
        if (!name) {
            return this.failure('INVALID_PARAM', 'name 必须是非空字符串');
        }
        const normalized = this.normalizeFilePath(params, 'xlsx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.excelAddNamedRangeWindows(suite, normalized.path, params.worksheet as string, range, name);
            return this.success({ path: normalized.path, range, name });
        }

        const previousClipboard = await this.safeReadClipboard();
        await this.writeClipboardText(name);
        await this.openAppForUi(suite, 'excel', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.goToRangeUi(suite, 'excel', range);
        await this.runUiSequence(suite, 'excel', [
            platform === 'darwin'
                ? { type: 'keycode', code: 99 }
                : { type: 'linux_key', keys: 'ctrl+f3' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'v', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+v' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keycode', code: 36 }
                : { type: 'linux_key', keys: 'Return' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        await this.restoreClipboard(previousClipboard);
        return this.success({ path: normalized.path, range, name });
    }

    private async excelSetDataValidation(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const range = this.validateRange(params.range);
        if (!range) {
            return this.failure('INVALID_PARAM', 'range 必须是非空字符串');
        }
        const validationType = typeof params.validationType === 'string' ? params.validationType.trim() : '';
        const criteria = typeof params.criteria === 'string' ? params.criteria.trim() : '';
        if (!validationType || !criteria) {
            return this.failure('INVALID_PARAM', 'validationType/criteria 必须是非空字符串');
        }
        const allowBlank = params.allowBlank !== false;
        const normalized = this.normalizeFilePath(params, 'xlsx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.excelSetDataValidationWindows(suite, normalized.path, params.worksheet as string, range, validationType, criteria, allowBlank);
            return this.success({ path: normalized.path, range, validationType });
        }

        const previousClipboard = await this.safeReadClipboard();
        await this.writeClipboardText(criteria);
        await this.openAppForUi(suite, 'excel', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.goToRangeUi(suite, 'excel', range);
        await this.runUiSequence(suite, 'excel', [
            platform === 'darwin'
                ? { type: 'keystroke', key: 'd', modifiers: ['command', 'shift'] }
                : { type: 'linux_key', keys: 'alt+d' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'v', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+v' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keycode', code: 36 }
                : { type: 'linux_key', keys: 'Return' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        await this.restoreClipboard(previousClipboard);
        return this.success({ path: normalized.path, range, validationType });
    }

    private async excelApplyConditionalFormatting(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const range = this.validateRange(params.range);
        if (!range) {
            return this.failure('INVALID_PARAM', 'range 必须是非空字符串');
        }
        const ruleType = typeof params.ruleType === 'string' ? params.ruleType.trim() : '';
        const value1 = typeof params.value1 === 'string' ? params.value1.trim() : '';
        const value2 = typeof params.value2 === 'string' ? params.value2.trim() : '';
        if (!ruleType || !value1) {
            return this.failure('INVALID_PARAM', 'ruleType/value1 必须是非空字符串');
        }
        const normalized = this.normalizeFilePath(params, 'xlsx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.excelApplyConditionalFormattingWindows(suite, normalized.path, params.worksheet as string, range, ruleType, value1, value2);
            return this.success({ path: normalized.path, range, ruleType });
        }

        const previousClipboard = await this.safeReadClipboard();
        await this.writeClipboardText(value1);
        await this.openAppForUi(suite, 'excel', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.goToRangeUi(suite, 'excel', range);
        await this.runUiSequence(suite, 'excel', [
            platform === 'darwin'
                ? { type: 'keystroke', key: 'l', modifiers: ['command', 'shift'] }
                : { type: 'linux_key', keys: 'alt+h' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'v', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+v' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keycode', code: 36 }
                : { type: 'linux_key', keys: 'Return' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        await this.restoreClipboard(previousClipboard);
        return this.success({ path: normalized.path, range, ruleType });
    }

    private async excelCreateChart(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const range = this.validateRange(params.range);
        if (!range) {
            return this.failure('INVALID_PARAM', 'range 必须是非空字符串');
        }
        const chartType = typeof params.chartType === 'string' ? params.chartType.trim().toLowerCase() : 'column';
        const title = typeof params.title === 'string' ? params.title.trim() : '';
        const normalized = this.normalizeFilePath(params, 'xlsx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.excelCreateChartWindows(suite, normalized.path, params.worksheet as string, range, chartType, title);
            return this.success({ path: normalized.path, range, chartType });
        }

        await this.openAppForUi(suite, 'excel', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.goToRangeUi(suite, 'excel', range);
        await this.runUiSequence(suite, 'excel', [
            platform === 'darwin'
                ? { type: 'keycode', code: 103 }
                : { type: 'linux_key', keys: 'F11' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        return this.success({ path: normalized.path, range, chartType });
    }

    private async pptCreate(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const normalized = this.normalizeFilePath(params, 'pptx', false);
        if (!normalized.ok) return normalized.result;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.pptCreateWindows(suite, normalized.path);
            return this.success({ path: normalized.path });
        }

        await fs.mkdir(dirname(normalized.path), { recursive: true });
        await this.openAppForUi(suite, 'ppt');
        await this.delay(UI_OPEN_DELAY_MS);
        await this.runUiSequence(suite, 'ppt', [
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'n', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+n' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
        ]);
        await this.saveAsUi(suite, 'ppt', normalized.path);
        return this.success({ path: normalized.path });
    }

    private async pptGetSlides(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const normalized = this.normalizeFilePath(params, 'pptx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            const slides = await this.pptGetSlidesWindows(suite, normalized.path);
            return this.success({ path: normalized.path, slides });
        }

        const slides = await this.extractSlidesFromZip(normalized.path);
        return this.success({ path: normalized.path, slides });
    }

    private async pptAddSlide(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const normalized = this.normalizeFilePath(params, 'pptx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();
        const layoutValue = this.resolvePptLayout(params.layout as string | undefined);

        if (platform === 'win32') {
            await this.pptAddSlideWindows(suite, normalized.path, layoutValue);
            return this.success({ path: normalized.path, layout: layoutValue });
        }

        await this.openAppForUi(suite, 'ppt', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.runUiSequence(suite, 'ppt', [
            platform === 'darwin'
                ? { type: 'keystroke', key: 'n', modifiers: ['command', 'shift'] }
                : { type: 'linux_key', keys: 'ctrl+m' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        return this.success({ path: normalized.path, layout: layoutValue });
    }

    private async pptDeleteSlide(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const index = this.ensurePositiveInt(params.index, 'index');
        if (!index) {
            return this.failure('INVALID_PARAM', 'index 必须是正整数');
        }
        const normalized = this.normalizeFilePath(params, 'pptx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.pptDeleteSlideWindows(suite, normalized.path, index);
            return this.success({ path: normalized.path, index });
        }

        await this.openAppForUi(suite, 'ppt', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.goToSlideUi(suite, index);
        await this.runUiSequence(suite, 'ppt', [
            platform === 'darwin'
                ? { type: 'keycode', code: 51 }
                : { type: 'linux_key', keys: 'Delete' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        return this.success({ path: normalized.path, index });
    }

    private async pptDuplicateSlide(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const index = this.ensurePositiveInt(params.index, 'index');
        if (!index) {
            return this.failure('INVALID_PARAM', 'index 必须是正整数');
        }
        const normalized = this.normalizeFilePath(params, 'pptx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.pptDuplicateSlideWindows(suite, normalized.path, index);
            return this.success({ path: normalized.path, index });
        }

        await this.openAppForUi(suite, 'ppt', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.goToSlideUi(suite, index);
        await this.runUiSequence(suite, 'ppt', [
            platform === 'darwin'
                ? { type: 'keystroke', key: 'd', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+d' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        return this.success({ path: normalized.path, index });
    }

    private async pptInsertText(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const index = this.ensurePositiveInt(params.index, 'index');
        if (!index) {
            return this.failure('INVALID_PARAM', 'index 必须是正整数');
        }
        const text = typeof params.text === 'string' ? params.text : '';
        if (!text) {
            return this.failure('INVALID_PARAM', 'text 必须是非空字符串');
        }
        const normalized = this.normalizeFilePath(params, 'pptx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.pptInsertTextWindows(
                suite,
                normalized.path,
                index,
                text,
                params.left as number,
                params.top as number,
                params.width as number,
                params.height as number
            );
            return this.success({ path: normalized.path, index });
        }

        const previousClipboard = await this.safeReadClipboard();
        await this.writeClipboardText(text);
        await this.openAppForUi(suite, 'ppt', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.goToSlideUi(suite, index);
        await this.runUiSequence(suite, 'ppt', [
            platform === 'darwin'
                ? { type: 'keystroke', key: 't', modifiers: ['command', 'option', 'shift'] }
                : { type: 'linux_key', keys: 'ctrl+alt+shift+t' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'v', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+v' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        await this.restoreClipboard(previousClipboard);
        return this.success({ path: normalized.path, index });
    }

    private async pptInsertImage(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const index = this.ensurePositiveInt(params.index, 'index');
        if (!index) {
            return this.failure('INVALID_PARAM', 'index 必须是正整数');
        }
        const imageInput = typeof params.imagePath === 'string' ? params.imagePath.trim() : '';
        if (!imageInput) {
            return this.failure('INVALID_PARAM', 'imagePath 必须是非空字符串');
        }
        const imagePath = this.resolvePathInput(imageInput);
        const security = this.checkPathSecurity(imagePath);
        if (!security.allowed) {
            return this.failure('SECURITY_DENIED', security.reason || '图片路径不在允许范围内');
        }
        const imageMissing = await this.ensureFileExists(imagePath);
        if (imageMissing) return imageMissing;
        const normalized = this.normalizeFilePath(params, 'pptx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.pptInsertImageWindows(
                suite,
                normalized.path,
                index,
                imagePath,
                params.left as number,
                params.top as number,
                params.width as number,
                params.height as number
            );
            return this.success({ path: normalized.path, index });
        }

        const previousClipboard = await this.safeReadClipboard();
        await this.writeClipboardImage(imagePath);
        await this.openAppForUi(suite, 'ppt', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.goToSlideUi(suite, index);
        await this.runUiSequence(suite, 'ppt', [
            platform === 'darwin'
                ? { type: 'keystroke', key: 'v', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+v' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        await this.restoreClipboard(previousClipboard);
        return this.success({ path: normalized.path, index });
    }

    private async pptSetLayout(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const index = this.ensurePositiveInt(params.index, 'index');
        if (!index) {
            return this.failure('INVALID_PARAM', 'index 必须是正整数');
        }
        const layoutName = typeof params.layout === 'string' ? params.layout.trim() : '';
        if (!layoutName) {
            return this.failure('INVALID_PARAM', 'layout 必须是非空字符串');
        }
        const normalized = this.normalizeFilePath(params, 'pptx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();
        const layoutValue = this.resolvePptLayout(layoutName);

        if (platform === 'win32') {
            await this.pptSetLayoutWindows(suite, normalized.path, index, layoutValue);
            return this.success({ path: normalized.path, index, layout: layoutValue });
        }

        const previousClipboard = await this.safeReadClipboard();
        await this.writeClipboardText(layoutName);
        await this.openAppForUi(suite, 'ppt', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.goToSlideUi(suite, index);
        await this.runUiSequence(suite, 'ppt', [
            platform === 'darwin'
                ? { type: 'keystroke', key: 'l', modifiers: ['command', 'shift'] }
                : { type: 'linux_key', keys: 'ctrl+shift+l' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'v', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+v' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keycode', code: 36 }
                : { type: 'linux_key', keys: 'Return' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        await this.restoreClipboard(previousClipboard);
        return this.success({ path: normalized.path, index, layout: layoutValue });
    }

    private async pptSetTheme(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const theme = typeof params.theme === 'string' ? params.theme.trim() : '';
        if (!theme) {
            return this.failure('INVALID_PARAM', 'theme 必须是非空字符串');
        }
        const normalized = this.normalizeFilePath(params, 'pptx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.pptSetThemeWindows(suite, normalized.path, theme);
            return this.success({ path: normalized.path, theme });
        }

        const previousClipboard = await this.safeReadClipboard();
        await this.writeClipboardText(theme);
        await this.openAppForUi(suite, 'ppt', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.runUiSequence(suite, 'ppt', [
            platform === 'darwin'
                ? { type: 'keystroke', key: 't', modifiers: ['command', 'shift'] }
                : { type: 'linux_key', keys: 'ctrl+shift+t' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'v', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+v' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keycode', code: 36 }
                : { type: 'linux_key', keys: 'Return' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        await this.restoreClipboard(previousClipboard);
        return this.success({ path: normalized.path, theme });
    }

    private async pptSetNotes(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const index = this.ensurePositiveInt(params.index, 'index');
        if (!index) {
            return this.failure('INVALID_PARAM', 'index 必须是正整数');
        }
        const notes = typeof params.notes === 'string' ? params.notes : '';
        if (!notes) {
            return this.failure('INVALID_PARAM', 'notes 必须是非空字符串');
        }
        const normalized = this.normalizeFilePath(params, 'pptx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();

        if (platform === 'win32') {
            await this.pptSetNotesWindows(suite, normalized.path, index, notes);
            return this.success({ path: normalized.path, index });
        }

        const previousClipboard = await this.safeReadClipboard();
        await this.writeClipboardText(notes);
        await this.openAppForUi(suite, 'ppt', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.goToSlideUi(suite, index);
        await this.runUiSequence(suite, 'ppt', [
            platform === 'darwin'
                ? { type: 'keystroke', key: 'n', modifiers: ['command', 'option'] }
                : { type: 'linux_key', keys: 'ctrl+alt+n' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'v', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+v' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        await this.restoreClipboard(previousClipboard);
        return this.success({ path: normalized.path, index });
    }

    private async pptSetTransition(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const index = this.ensurePositiveInt(params.index, 'index');
        if (!index) {
            return this.failure('INVALID_PARAM', 'index 必须是正整数');
        }
        const transition = typeof params.transition === 'string' ? params.transition.trim() : '';
        if (!transition) {
            return this.failure('INVALID_PARAM', 'transition 必须是非空字符串');
        }
        const normalized = this.normalizeFilePath(params, 'pptx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();
        const effectValue = this.resolvePptEntryEffect(transition);

        if (platform === 'win32') {
            await this.pptSetTransitionWindows(suite, normalized.path, index, effectValue);
            return this.success({ path: normalized.path, index, transition: effectValue });
        }

        const previousClipboard = await this.safeReadClipboard();
        await this.writeClipboardText(transition);
        await this.openAppForUi(suite, 'ppt', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.goToSlideUi(suite, index);
        await this.runUiSequence(suite, 'ppt', [
            platform === 'darwin'
                ? { type: 'keystroke', key: 'r', modifiers: ['command', 'shift'] }
                : { type: 'linux_key', keys: 'ctrl+shift+r' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'v', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+v' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keycode', code: 36 }
                : { type: 'linux_key', keys: 'Return' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        await this.restoreClipboard(previousClipboard);
        return this.success({ path: normalized.path, index, transition: effectValue });
    }

    private async pptSetAnimation(params: Record<string, unknown>): Promise<AdapterResult> {
        const suite = this.parseSuite(params.suite);
        const index = this.ensurePositiveInt(params.index, 'index');
        if (!index) {
            return this.failure('INVALID_PARAM', 'index 必须是正整数');
        }
        const animation = typeof params.animation === 'string' ? params.animation.trim() : '';
        if (!animation) {
            return this.failure('INVALID_PARAM', 'animation 必须是非空字符串');
        }
        const normalized = this.normalizeFilePath(params, 'pptx', true);
        if (!normalized.ok) return normalized.result;
        const missing = await this.ensureFileExists(normalized.path);
        if (missing) return missing;
        const platform = this.getPlatform();
        const effectValue = this.resolvePptEntryEffect(animation);

        if (platform === 'win32') {
            await this.pptSetAnimationWindows(suite, normalized.path, index, effectValue);
            return this.success({ path: normalized.path, index, animation: effectValue });
        }

        await this.openAppForUi(suite, 'ppt', normalized.path);
        await this.delay(UI_OPEN_DELAY_MS);
        await this.goToSlideUi(suite, index);
        await this.runUiSequence(suite, 'ppt', [
            platform === 'darwin'
                ? { type: 'keystroke', key: 'a', modifiers: ['command', 'shift'] }
                : { type: 'linux_key', keys: 'ctrl+shift+a' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 's', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'w', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+w' },
        ]);
        return this.success({ path: normalized.path, index, animation: effectValue });
    }

    private async listFiles(params: Record<string, unknown>): Promise<AdapterResult> {
        const folderInput = typeof params.folder === 'string' && params.folder.trim() ? params.folder : homedir();
        const folder = this.resolvePathInput(folderInput);
        const security = this.checkPathSecurity(folder);
        if (!security.allowed) {
            return this.failure('SECURITY_DENIED', security.reason || '路径访问被拒绝');
        }
        const type = typeof params.type === 'string' ? params.type.toLowerCase() : '';
        const extensions: Record<string, string[]> = {
            word: ['.doc', '.docx'],
            excel: ['.xls', '.xlsx'],
            ppt: ['.ppt', '.pptx'],
        };
        const allowed = extensions[type] ?? null;

        const entries = await fs.readdir(folder, { withFileTypes: true });
        const files = entries
            .filter(entry => entry.isFile())
            .map(entry => entry.name)
            .filter(name => {
                if (!allowed) return true;
                return allowed.includes(extname(name).toLowerCase());
            })
            .map(name => ({
                name,
                path: resolve(join(folder, name)),
            }));

        return this.success({ folder, count: files.length, files });
    }

    private async deleteFile(params: Record<string, unknown>): Promise<AdapterResult> {
        const pathInput = typeof params.path === 'string' && params.path.trim()
            ? params.path
            : typeof params.itemId === 'string' && params.itemId.trim()
                ? params.itemId
                : '';
        if (!pathInput) {
            return this.failure('INVALID_PARAM', '必须提供 path/itemId');
        }
        const filePath = this.resolvePathInput(pathInput);
        const security = this.checkPathSecurity(filePath);
        if (!security.allowed) {
            return this.failure('SECURITY_DENIED', security.reason || '路径访问被拒绝');
        }
        await fs.rm(filePath);
        return this.success({ path: filePath, deleted: true });
    }

    private async saveAsUi(suite: OfficeSuite, app: OfficeApp, filePath: string): Promise<void> {
        const platform = this.getPlatform();
        const folder = dirname(filePath);
        const fileName = basename(filePath);
        const fullPath = filePath;

        if (platform === 'darwin') {
            await this.runUiSequence(suite, app, [
                { type: 'keystroke', key: 's', modifiers: ['command', 'shift'] },
                { type: 'delay', ms: UI_STEP_DELAY_MS },
                { type: 'keystroke', key: 'g', modifiers: ['command', 'shift'] },
                { type: 'delay', ms: UI_STEP_DELAY_MS },
                { type: 'text', text: folder },
                { type: 'keycode', code: 36 },
                { type: 'delay', ms: UI_STEP_DELAY_MS },
                { type: 'text', text: fileName },
                { type: 'keycode', code: 36 },
                { type: 'delay', ms: UI_STEP_DELAY_MS },
                { type: 'keystroke', key: 'w', modifiers: ['command'] },
            ]);
            return;
        }

        await this.runUiSequence(suite, app, [
            { type: 'linux_key', keys: 'ctrl+shift+s' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            { type: 'linux_key', keys: 'ctrl+l' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            { type: 'text', text: fullPath },
            { type: 'linux_key', keys: 'Return' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            { type: 'linux_key', keys: 'ctrl+w' },
        ]);
    }

    private async goToRangeUi(suite: OfficeSuite, app: OfficeApp, range: string): Promise<void> {
        const platform = this.getPlatform();
        await this.runUiSequence(suite, app, [
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'g', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+g' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            { type: 'text', text: range },
            platform === 'darwin'
                ? { type: 'keycode', code: 36 }
                : { type: 'linux_key', keys: 'Return' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
        ]);
    }

    private async goToSlideUi(suite: OfficeSuite, index: number): Promise<void> {
        const platform = this.getPlatform();
        await this.runUiSequence(suite, 'ppt', [
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            platform === 'darwin'
                ? { type: 'keystroke', key: 'g', modifiers: ['command'] }
                : { type: 'linux_key', keys: 'ctrl+g' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
            { type: 'text', text: String(index) },
            platform === 'darwin'
                ? { type: 'keycode', code: 36 }
                : { type: 'linux_key', keys: 'Return' },
            { type: 'delay', ms: UI_STEP_DELAY_MS },
        ]);
    }

    private async safeReadClipboard(): Promise<string> {
        try {
            return await this.readClipboardText();
        } catch {
            return '';
        }
    }

    private async restoreClipboard(previous: string): Promise<void> {
        if (!previous) return;
        try {
            await this.writeClipboardText(previous);
        } catch {
            // ignore
        }
    }

    private async wordCreateWindows(suite: OfficeSuite, filePath: string): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].word.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Word COM 对象' }
$doc = $null
try {
  $app.Visible = $false
  $doc = $app.Documents.Add()
  $doc.SaveAs([ref]'${escapedPath}')
} finally {
  if ($doc) { $doc.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async wordGetContentWindows(suite: OfficeSuite, filePath: string): Promise<string> {
        const progIds = WINDOWS_PROG_IDS[suite].word.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Word COM 对象' }
$doc = $null
try {
  $app.Visible = $false
  $doc = $app.Documents.Open('${escapedPath}', $false, $true)
  $text = $doc.Content.Text
  $text
} finally {
  if ($doc) { $doc.Close($false) }
  $app.Quit()
}
`;
        return await this.runPowerShell(script);
    }

    private async wordSetContentWindows(suite: OfficeSuite, filePath: string, content: string): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].word.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedContent = this.escapePowerShellString(JSON.stringify(content));
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Word COM 对象' }
$doc = $null
try {
  $app.Visible = $false
  $doc = $app.Documents.Open('${escapedPath}', $false, $false)
  $content = ConvertFrom-Json '${escapedContent}'
  $doc.Content.Text = $content
  $doc.Save()
} finally {
  if ($doc) { $doc.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async wordReplaceTextWindows(suite: OfficeSuite, filePath: string, search: string, replace: string, matchCase: boolean): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].word.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedSearch = this.escapePowerShellString(JSON.stringify(search));
        const escapedReplace = this.escapePowerShellString(JSON.stringify(replace));
        const caseFlag = matchCase ? '$true' : '$false';
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Word COM 对象' }
$doc = $null
try {
  $app.Visible = $false
  $doc = $app.Documents.Open('${escapedPath}', $false, $false)
  $findText = ConvertFrom-Json '${escapedSearch}'
  $replaceText = ConvertFrom-Json '${escapedReplace}'
  $find = $doc.Content.Find
  $find.ClearFormatting()
  $find.Replacement.ClearFormatting()
  $null = $find.Execute($findText, ${caseFlag}, $false, $false, $false, $false, $true, 1, $false, $replaceText, 2)
  $doc.Save()
} finally {
  if ($doc) { $doc.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async wordAppendTextWindows(suite: OfficeSuite, filePath: string, text: string): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].word.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedText = this.escapePowerShellString(JSON.stringify(text));
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Word COM 对象' }
$doc = $null
try {
  $app.Visible = $false
  $doc = $app.Documents.Open('${escapedPath}', $false, $false)
  $content = ConvertFrom-Json '${escapedText}'
  $range = $doc.Content
  $range.InsertAfter($content)
  $doc.Save()
} finally {
  if ($doc) { $doc.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async wordInsertListWindows(suite: OfficeSuite, filePath: string, items: string[], ordered: boolean): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].word.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedItems = this.escapePowerShellString(JSON.stringify(items));
        const listFlag = ordered ? '$true' : '$false';
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Word COM 对象' }
$doc = $null
try {
  $app.Visible = $false
  $doc = $app.Documents.Open('${escapedPath}', $false, $false)
  $items = ConvertFrom-Json '${escapedItems}'
  $range = $doc.Content
  foreach ($item in $items) {
    $range.InsertAfter($item)
    $range.InsertParagraphAfter()
  }
  if (${listFlag}) {
    $range.ListFormat.ApplyNumberDefault()
  } else {
    $range.ListFormat.ApplyBulletDefault()
  }
  $doc.Save()
} finally {
  if ($doc) { $doc.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async wordInsertTableWindows(suite: OfficeSuite, filePath: string, rows: number, cols: number, values: unknown[][]): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].word.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const valuesJson = this.escapePowerShellString(JSON.stringify(values));
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Word COM 对象' }
$doc = $null
try {
  $app.Visible = $false
  $doc = $app.Documents.Open('${escapedPath}', $false, $false)
  $range = $doc.Content
  $table = $doc.Tables.Add($range, ${rows}, ${cols})
  $values = ConvertFrom-Json '${valuesJson}'
  if ($values) {
    for ($r = 1; $r -le ${rows}; $r++) {
      for ($c = 1; $c -le ${cols}; $c++) {
        $rowIndex = $r - 1
        $colIndex = $c - 1
        if ($values.Count -gt $rowIndex -and $values[$rowIndex].Count -gt $colIndex) {
          $table.Cell($r, $c).Range.Text = $values[$rowIndex][$colIndex]
        }
      }
    }
  }
  $doc.Save()
} finally {
  if ($doc) { $doc.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async wordApplyHeadingWindows(suite: OfficeSuite, filePath: string, level: number, search: string): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].word.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedSearch = this.escapePowerShellString(JSON.stringify(search));
        const headingName = `Heading ${level}`;
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Word COM 对象' }
$doc = $null
try {
  $app.Visible = $false
  $doc = $app.Documents.Open('${escapedPath}', $false, $false)
  if ('${escapedSearch}' -ne '""') {
    $searchText = ConvertFrom-Json '${escapedSearch}'
    $range = $doc.Content
    $find = $range.Find
    $find.ClearFormatting()
    $find.Replacement.ClearFormatting()
    $found = $find.Execute($searchText)
    if ($found) {
      $range.Style = '${headingName}'
    }
  } else {
    $para = $doc.Paragraphs.Item(1).Range
    $para.Style = '${headingName}'
  }
  $doc.Save()
} finally {
  if ($doc) { $doc.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async wordExportPdfWindows(suite: OfficeSuite, filePath: string, outputPath: string): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].word.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedOut = this.escapePowerShellString(outputPath);
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Word COM 对象' }
$doc = $null
try {
  $app.Visible = $false
  $doc = $app.Documents.Open('${escapedPath}', $false, $true)
  $doc.SaveAs([ref]'${escapedOut}', 17)
} finally {
  if ($doc) { $doc.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async wordAddCommentWindows(suite: OfficeSuite, filePath: string, comment: string, search: string): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].word.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedComment = this.escapePowerShellString(JSON.stringify(comment));
        const escapedSearch = this.escapePowerShellString(JSON.stringify(search));
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Word COM 对象' }
$doc = $null
try {
  $app.Visible = $false
  $doc = $app.Documents.Open('${escapedPath}', $false, $false)
  $commentText = ConvertFrom-Json '${escapedComment}'
  if ('${escapedSearch}' -ne '""') {
    $searchText = ConvertFrom-Json '${escapedSearch}'
    $range = $doc.Content
    $find = $range.Find
    $find.ClearFormatting()
    $find.Replacement.ClearFormatting()
    $found = $find.Execute($searchText)
    if ($found) {
      $doc.Comments.Add($range, $commentText)
    }
  } else {
    $range = $doc.Paragraphs.Item(1).Range
    $doc.Comments.Add($range, $commentText)
  }
  $doc.Save()
} finally {
  if ($doc) { $doc.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async wordToggleTrackChangesWindows(suite: OfficeSuite, filePath: string, enabled: boolean): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].word.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const flag = enabled ? '$true' : '$false';
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Word COM 对象' }
$doc = $null
try {
  $app.Visible = $false
  $doc = $app.Documents.Open('${escapedPath}', $false, $false)
  $doc.TrackRevisions = ${flag}
  $doc.Save()
} finally {
  if ($doc) { $doc.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private replacePlainText(source: string, search: string, replace: string, matchCase: boolean): string {
        if (!search) return source;
        if (matchCase) {
            return source.split(search).join(replace);
        }
        const escaped = search.replace(/[.*+?^${}()|[\]\\]/g, '\\\\$&');
        const regex = new RegExp(escaped, 'gi');
        return source.replace(regex, replace);
    }

    private async excelCreateWindows(suite: OfficeSuite, filePath: string): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].excel.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Excel COM 对象' }
$book = $null
try {
  $app.Visible = $false
  $book = $app.Workbooks.Add()
  $book.SaveAs('${escapedPath}')
} finally {
  if ($book) { $book.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async excelReadRangeWindows(suite: OfficeSuite, filePath: string, worksheet: string | undefined, range: string): Promise<unknown[][]> {
        const progIds = WINDOWS_PROG_IDS[suite].excel.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedSheet = worksheet ? this.escapePowerShellString(worksheet) : '';
        const escapedRange = this.escapePowerShellString(range);
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Excel COM 对象' }
$book = $null
try {
  $app.Visible = $false
  $book = $app.Workbooks.Open('${escapedPath}')
  if ('${escapedSheet}') {
    $sheet = $book.Worksheets.Item('${escapedSheet}')
  } else {
    $sheet = $book.ActiveSheet
  }
  $values = $sheet.Range('${escapedRange}').Value2
  $values | ConvertTo-Json -Depth 10 -Compress
} finally {
  if ($book) { $book.Close($false) }
  $app.Quit()
}
`;
        const output = await this.runPowerShell(script);
        if (!output) return [];
        const parsed = JSON.parse(output) as unknown;
        if (!Array.isArray(parsed)) {
            return [[parsed]];
        }
        return parsed as unknown[][];
    }

    private async excelWriteRangeWindows(suite: OfficeSuite, filePath: string, worksheet: string | undefined, range: string, values: unknown[][]): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].excel.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedSheet = worksheet ? this.escapePowerShellString(worksheet) : '';
        const escapedRange = this.escapePowerShellString(range);
        const valuesJson = this.escapePowerShellString(JSON.stringify(values));
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Excel COM 对象' }
$book = $null
try {
  $app.Visible = $false
  $book = $app.Workbooks.Open('${escapedPath}')
  if ('${escapedSheet}') {
    $sheet = $book.Worksheets.Item('${escapedSheet}')
  } else {
    $sheet = $book.ActiveSheet
  }
  $values = '${valuesJson}' | ConvertFrom-Json
  $sheet.Range('${escapedRange}').Value2 = $values
  $book.Save()
} finally {
  if ($book) { $book.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async excelAddWorksheetWindows(suite: OfficeSuite, filePath: string, name: string): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].excel.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedName = this.escapePowerShellString(name);
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Excel COM 对象' }
$book = $null
try {
  $app.Visible = $false
  $book = $app.Workbooks.Open('${escapedPath}')
  $sheet = $book.Worksheets.Add()
  $sheet.Name = '${escapedName}'
  $book.Save()
} finally {
  if ($book) { $book.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async excelSetFormulaWindows(suite: OfficeSuite, filePath: string, worksheet: string | undefined, range: string, formula: string): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].excel.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedSheet = worksheet ? this.escapePowerShellString(worksheet) : '';
        const escapedRange = this.escapePowerShellString(range);
        const formulaJson = this.escapePowerShellString(JSON.stringify(formula));
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Excel COM 对象' }
$book = $null
try {
  $app.Visible = $false
  $book = $app.Workbooks.Open('${escapedPath}')
  if ('${escapedSheet}') {
    $sheet = $book.Worksheets.Item('${escapedSheet}')
  } else {
    $sheet = $book.ActiveSheet
  }
  $formula = ConvertFrom-Json '${formulaJson}'
  $sheet.Range('${escapedRange}').Formula = $formula
  $book.Save()
} finally {
  if ($book) { $book.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async excelSortRangeWindows(
        suite: OfficeSuite,
        filePath: string,
        worksheet: string | undefined,
        range: string,
        keyIndex: number,
        order: 'asc' | 'desc',
        hasHeader: boolean
    ): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].excel.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedSheet = worksheet ? this.escapePowerShellString(worksheet) : '';
        const escapedRange = this.escapePowerShellString(range);
        const orderValue = order === 'desc' ? 2 : 1;
        const headerValue = hasHeader ? 1 : 2;
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Excel COM 对象' }
$book = $null
try {
  $app.Visible = $false
  $book = $app.Workbooks.Open('${escapedPath}')
  if ('${escapedSheet}') {
    $sheet = $book.Worksheets.Item('${escapedSheet}')
  } else {
    $sheet = $book.ActiveSheet
  }
  $range = $sheet.Range('${escapedRange}')
  $key = $range.Columns.Item(${keyIndex})
  $range.Sort($key, ${orderValue}, $null, $null, $null, $null, $null, ${headerValue})
  $book.Save()
} finally {
  if ($book) { $book.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async excelFilterRangeWindows(
        suite: OfficeSuite,
        filePath: string,
        worksheet: string | undefined,
        range: string,
        columnIndex: number,
        criteria: string
    ): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].excel.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedSheet = worksheet ? this.escapePowerShellString(worksheet) : '';
        const escapedRange = this.escapePowerShellString(range);
        const escapedCriteria = this.escapePowerShellString(JSON.stringify(criteria));
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Excel COM 对象' }
$book = $null
try {
  $app.Visible = $false
  $book = $app.Workbooks.Open('${escapedPath}')
  if ('${escapedSheet}') {
    $sheet = $book.Worksheets.Item('${escapedSheet}')
  } else {
    $sheet = $book.ActiveSheet
  }
  $criteria = ConvertFrom-Json '${escapedCriteria}'
  $range = $sheet.Range('${escapedRange}')
  $range.AutoFilter(${columnIndex}, $criteria)
  $book.Save()
} finally {
  if ($book) { $book.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async excelCreateTableWindows(
        suite: OfficeSuite,
        filePath: string,
        worksheet: string | undefined,
        range: string,
        name: string,
        hasHeader: boolean
    ): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].excel.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedSheet = worksheet ? this.escapePowerShellString(worksheet) : '';
        const escapedRange = this.escapePowerShellString(range);
        const escapedName = this.escapePowerShellString(name);
        const headerValue = hasHeader ? 1 : 2;
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Excel COM 对象' }
$book = $null
try {
  $app.Visible = $false
  $book = $app.Workbooks.Open('${escapedPath}')
  if ('${escapedSheet}') {
    $sheet = $book.Worksheets.Item('${escapedSheet}')
  } else {
    $sheet = $book.ActiveSheet
  }
  $range = $sheet.Range('${escapedRange}')
  $table = $sheet.ListObjects.Add(1, $range, $null, ${headerValue})
  if ('${escapedName}') {
    $table.Name = '${escapedName}'
  }
  $book.Save()
} finally {
  if ($book) { $book.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async excelAddNamedRangeWindows(
        suite: OfficeSuite,
        filePath: string,
        worksheet: string | undefined,
        range: string,
        name: string
    ): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].excel.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedSheet = worksheet ? this.escapePowerShellString(worksheet) : '';
        const escapedRange = this.escapePowerShellString(range);
        const escapedName = this.escapePowerShellString(name);
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Excel COM 对象' }
$book = $null
try {
  $app.Visible = $false
  $book = $app.Workbooks.Open('${escapedPath}')
  if ('${escapedSheet}') {
    $sheet = $book.Worksheets.Item('${escapedSheet}')
    $sheetName = '${escapedSheet}'
  } else {
    $sheet = $book.ActiveSheet
    $sheetName = $sheet.Name
  }
  $book.Names.Add('${escapedName}', "=" + $sheetName + "!${escapedRange}")
  $book.Save()
} finally {
  if ($book) { $book.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async excelSetDataValidationWindows(
        suite: OfficeSuite,
        filePath: string,
        worksheet: string | undefined,
        range: string,
        validationType: string,
        criteria: string,
        allowBlank: boolean
    ): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].excel.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedSheet = worksheet ? this.escapePowerShellString(worksheet) : '';
        const escapedRange = this.escapePowerShellString(range);
        const criteriaJson = this.escapePowerShellString(JSON.stringify(criteria));
        const typeValue = validationType === 'list' ? 3 : validationType === 'decimal' ? 2 : 1;
        const allowBlankFlag = allowBlank ? '$true' : '$false';
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Excel COM 对象' }
$book = $null
try {
  $app.Visible = $false
  $book = $app.Workbooks.Open('${escapedPath}')
  if ('${escapedSheet}') {
    $sheet = $book.Worksheets.Item('${escapedSheet}')
  } else {
    $sheet = $book.ActiveSheet
  }
  $criteria = ConvertFrom-Json '${criteriaJson}'
  $range = $sheet.Range('${escapedRange}')
  $range.Validation.Delete()
  $formula1 = $criteria
  if (${typeValue} -eq 3 -and $criteria -notmatch '^=') {
    $formula1 = '"' + $criteria + '"'
  }
  $range.Validation.Add(${typeValue}, 1, 1, $formula1)
  $range.Validation.IgnoreBlank = ${allowBlankFlag}
  $book.Save()
} finally {
  if ($book) { $book.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async excelApplyConditionalFormattingWindows(
        suite: OfficeSuite,
        filePath: string,
        worksheet: string | undefined,
        range: string,
        ruleType: string,
        value1: string,
        value2: string
    ): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].excel.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedSheet = worksheet ? this.escapePowerShellString(worksheet) : '';
        const escapedRange = this.escapePowerShellString(range);
        const value1Json = this.escapePowerShellString(JSON.stringify(value1));
        const value2Json = this.escapePowerShellString(JSON.stringify(value2));
        const operatorValue = ruleType === 'between' ? 1 : ruleType === 'less_than' ? 6 : 5;
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Excel COM 对象' }
$book = $null
try {
  $app.Visible = $false
  $book = $app.Workbooks.Open('${escapedPath}')
  if ('${escapedSheet}') {
    $sheet = $book.Worksheets.Item('${escapedSheet}')
  } else {
    $sheet = $book.ActiveSheet
  }
  $range = $sheet.Range('${escapedRange}')
  $val1 = ConvertFrom-Json '${value1Json}'
  $val2 = ConvertFrom-Json '${value2Json}'
  $format = $range.FormatConditions.Add(1, ${operatorValue}, $val1, $val2)
  $format.Interior.Color = 65535
  $book.Save()
} finally {
  if ($book) { $book.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async excelCreateChartWindows(
        suite: OfficeSuite,
        filePath: string,
        worksheet: string | undefined,
        range: string,
        chartType: string,
        title: string
    ): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].excel.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedSheet = worksheet ? this.escapePowerShellString(worksheet) : '';
        const escapedRange = this.escapePowerShellString(range);
        const escapedTitle = this.escapePowerShellString(JSON.stringify(title));
        const chartTypeValue = chartType === 'line' ? 4 : chartType === 'pie' ? 5 : 51;
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 Excel COM 对象' }
$book = $null
try {
  $app.Visible = $false
  $book = $app.Workbooks.Open('${escapedPath}')
  if ('${escapedSheet}') {
    $sheet = $book.Worksheets.Item('${escapedSheet}')
  } else {
    $sheet = $book.ActiveSheet
  }
  $range = $sheet.Range('${escapedRange}')
  $chartObject = $sheet.ChartObjects().Add(100, 50, 400, 300)
  $chart = $chartObject.Chart
  $chart.ChartType = ${chartTypeValue}
  $chart.SetSourceData($range)
  $title = ConvertFrom-Json '${escapedTitle}'
  if ($title) {
    $chart.HasTitle = $true
    $chart.ChartTitle.Text = $title
  }
  $book.Save()
} finally {
  if ($book) { $book.Close($false) }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async pptCreateWindows(suite: OfficeSuite, filePath: string): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].ppt.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 PowerPoint COM 对象' }
$presentation = $null
try {
  $app.Visible = $false
  $presentation = $app.Presentations.Add()
  $presentation.SaveAs('${escapedPath}')
} finally {
  if ($presentation) { $presentation.Close() }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async pptGetSlidesWindows(suite: OfficeSuite, filePath: string): Promise<Array<{ index: number; title: string }>> {
        const progIds = WINDOWS_PROG_IDS[suite].ppt.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 PowerPoint COM 对象' }
$presentation = $null
try {
  $app.Visible = $false
  $presentation = $app.Presentations.Open('${escapedPath}', $true, $false, $false)
  $slides = @()
  foreach ($slide in $presentation.Slides) {
    $title = ''
    try { $title = $slide.Shapes.Title.TextFrame.TextRange.Text } catch {}
    $slides += @{ index = $slide.SlideIndex; title = $title }
  }
  $slides | ConvertTo-Json -Depth 5 -Compress
} finally {
  if ($presentation) { $presentation.Close() }
  $app.Quit()
}
`;
        const output = await this.runPowerShell(script);
        if (!output) {
            return [];
        }
        const parsed = JSON.parse(output) as Array<{ index: number; title: string }>;
        return Array.isArray(parsed) ? parsed : [];
    }

    private async pptAddSlideWindows(suite: OfficeSuite, filePath: string, layoutValue: number): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].ppt.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 PowerPoint COM 对象' }
$presentation = $null
try {
  $app.Visible = $false
  $presentation = $app.Presentations.Open('${escapedPath}', $true, $false, $false)
  $presentation.Slides.Add($presentation.Slides.Count + 1, ${layoutValue}) | Out-Null
  $presentation.Save()
} finally {
  if ($presentation) { $presentation.Close() }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async pptDeleteSlideWindows(suite: OfficeSuite, filePath: string, index: number): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].ppt.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 PowerPoint COM 对象' }
$presentation = $null
try {
  $app.Visible = $false
  $presentation = $app.Presentations.Open('${escapedPath}', $true, $false, $false)
  $presentation.Slides.Item(${index}).Delete()
  $presentation.Save()
} finally {
  if ($presentation) { $presentation.Close() }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async pptDuplicateSlideWindows(suite: OfficeSuite, filePath: string, index: number): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].ppt.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 PowerPoint COM 对象' }
$presentation = $null
try {
  $app.Visible = $false
  $presentation = $app.Presentations.Open('${escapedPath}', $true, $false, $false)
  $presentation.Slides.Item(${index}).Duplicate() | Out-Null
  $presentation.Save()
} finally {
  if ($presentation) { $presentation.Close() }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async pptInsertTextWindows(
        suite: OfficeSuite,
        filePath: string,
        index: number,
        text: string,
        left?: number,
        top?: number,
        width?: number,
        height?: number
    ): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].ppt.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedText = this.escapePowerShellString(JSON.stringify(text));
        const leftValue = Number.isFinite(left) ? left : 100;
        const topValue = Number.isFinite(top) ? top : 100;
        const widthValue = Number.isFinite(width) ? width : 500;
        const heightValue = Number.isFinite(height) ? height : 200;
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 PowerPoint COM 对象' }
$presentation = $null
try {
  $app.Visible = $false
  $presentation = $app.Presentations.Open('${escapedPath}', $true, $false, $false)
  $slide = $presentation.Slides.Item(${index})
  $shape = $slide.Shapes.AddTextbox(1, ${leftValue}, ${topValue}, ${widthValue}, ${heightValue})
  $shape.TextFrame.TextRange.Text = (ConvertFrom-Json '${escapedText}')
  $presentation.Save()
} finally {
  if ($presentation) { $presentation.Close() }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async pptInsertImageWindows(
        suite: OfficeSuite,
        filePath: string,
        index: number,
        imagePath: string,
        left?: number,
        top?: number,
        width?: number,
        height?: number
    ): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].ppt.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedImage = this.escapePowerShellString(imagePath);
        const leftValue = Number.isFinite(left) ? left : 100;
        const topValue = Number.isFinite(top) ? top : 100;
        const widthValue = Number.isFinite(width) ? width : 400;
        const heightValue = Number.isFinite(height) ? height : 300;
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 PowerPoint COM 对象' }
$presentation = $null
try {
  $app.Visible = $false
  $presentation = $app.Presentations.Open('${escapedPath}', $true, $false, $false)
  $slide = $presentation.Slides.Item(${index})
  $slide.Shapes.AddPicture('${escapedImage}', $false, $true, ${leftValue}, ${topValue}, ${widthValue}, ${heightValue}) | Out-Null
  $presentation.Save()
} finally {
  if ($presentation) { $presentation.Close() }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async pptSetLayoutWindows(suite: OfficeSuite, filePath: string, index: number, layoutValue: number): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].ppt.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 PowerPoint COM 对象' }
$presentation = $null
try {
  $app.Visible = $false
  $presentation = $app.Presentations.Open('${escapedPath}', $true, $false, $false)
  $presentation.Slides.Item(${index}).Layout = ${layoutValue}
  $presentation.Save()
} finally {
  if ($presentation) { $presentation.Close() }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async pptSetThemeWindows(suite: OfficeSuite, filePath: string, theme: string): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].ppt.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const escapedTheme = this.escapePowerShellString(theme);
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 PowerPoint COM 对象' }
$presentation = $null
try {
  $app.Visible = $false
  $presentation = $app.Presentations.Open('${escapedPath}', $true, $false, $false)
  $themePath = '${escapedTheme}'
  try {
    if (Test-Path $themePath) {
      $presentation.ApplyTemplate($themePath)
    } else {
      $presentation.ApplyTemplate($themePath)
    }
  } catch {
    throw '应用主题失败'
  }
  $presentation.Save()
} finally {
  if ($presentation) { $presentation.Close() }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async pptSetNotesWindows(suite: OfficeSuite, filePath: string, index: number, notes: string): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].ppt.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const notesJson = this.escapePowerShellString(JSON.stringify(notes));
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 PowerPoint COM 对象' }
$presentation = $null
try {
  $app.Visible = $false
  $presentation = $app.Presentations.Open('${escapedPath}', $true, $false, $false)
  $slide = $presentation.Slides.Item(${index})
  $notes = ConvertFrom-Json '${notesJson}'
  $slide.NotesPage.Shapes.Placeholders.Item(2).TextFrame.TextRange.Text = $notes
  $presentation.Save()
} finally {
  if ($presentation) { $presentation.Close() }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async pptSetTransitionWindows(suite: OfficeSuite, filePath: string, index: number, effectValue: number): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].ppt.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 PowerPoint COM 对象' }
$presentation = $null
try {
  $app.Visible = $false
  $presentation = $app.Presentations.Open('${escapedPath}', $true, $false, $false)
  $slide = $presentation.Slides.Item(${index})
  $slide.SlideShowTransition.EntryEffect = ${effectValue}
  $presentation.Save()
} finally {
  if ($presentation) { $presentation.Close() }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async pptSetAnimationWindows(suite: OfficeSuite, filePath: string, index: number, effectValue: number): Promise<void> {
        const progIds = WINDOWS_PROG_IDS[suite].ppt.map(id => `'${this.escapePowerShellString(id)}'`).join(',');
        const escapedPath = this.escapePowerShellString(filePath);
        const script = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$progIds = @(${progIds})
$app = $null
foreach ($pid in $progIds) {
  try { $app = New-Object -ComObject $pid; break } catch {}
}
if (-not $app) { throw '无法创建 PowerPoint COM 对象' }
$presentation = $null
try {
  $app.Visible = $false
  $presentation = $app.Presentations.Open('${escapedPath}', $true, $false, $false)
  $slide = $presentation.Slides.Item(${index})
  if ($slide.Shapes.Count -gt 0) {
    $shape = $slide.Shapes.Item(1)
    $slide.TimeLine.MainSequence.AddEffect($shape, ${effectValue}, 1, 1) | Out-Null
  }
  $presentation.Save()
} finally {
  if ($presentation) { $presentation.Close() }
  $app.Quit()
}
`;
        await this.runPowerShell(script);
    }

    private async extractSlidesFromZip(filePath: string): Promise<Array<{ index: number; title: string }>> {
        const platform = this.getPlatform();
        if (platform === 'linux' || platform === 'darwin') {
            await execFileAsync('which', ['unzip']);
            const { stdout } = await execFileAsync('unzip', ['-l', filePath], { encoding: 'utf8' });
            const lines = stdout.split('\n');
            const slides = lines
                .map(line => line.trim().split(/\s+/).pop() || '')
                .filter(name => /^ppt\/slides\/slide\d+\.xml$/.test(name))
                .sort();
            return slides.map((name, idx) => ({ index: idx + 1, title: name }));
        }

        const escapedPath = this.escapePowerShellString(filePath);
        const script = `
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [System.IO.Compression.ZipFile]::OpenRead('${escapedPath}')
$entries = $archive.Entries | Where-Object { $_.FullName -match '^ppt/slides/slide\d+\.xml$' } | Sort-Object FullName
$slides = @()
$index = 1
foreach ($entry in $entries) {
  $slides += @{ index = $index; title = $entry.FullName }
  $index += 1
}
$archive.Dispose()
$slides | ConvertTo-Json -Depth 3 -Compress
`;
        const output = await this.runPowerShell(script);
        if (!output) return [];
        const parsed = JSON.parse(output) as Array<{ index: number; title: string }>;
        return Array.isArray(parsed) ? parsed : [];
    }
}

export const officeLocalAdapter = new OfficeLocalAdapter();
