/**
 * 意图分类器
 * 基于规则的本地意图分类，用于三层路由决策
 */

/** 意图类型 */
export type IntentType = 'simple' | 'visual' | 'complex';

/** 意图分类结果 */
export interface IntentClassification {
    type: IntentType;
    confidence: number;
    keywords: string[];
}

/** 关键词模式 */
interface KeywordPattern {
    patterns: RegExp[];
    type: IntentType;
}

export class IntentClassifier {
    private patterns: KeywordPattern[] = [
        // 视觉相关意图
        {
            type: 'visual',
            patterns: [
                /屏幕|截图|看看|显示了什么|界面|窗口.*内容|画面/,
                /screenshot|screen|display|what.*see|visual/i,
            ],
        },
        // 简单指令意图
        {
            type: 'simple',
            patterns: [
                /音量|亮度|静音|壁纸|锁屏|关机|重启|休眠/,
                /打开|关闭|启动|退出|切换/,
                /设置.*到|调.*到|改成/,
                /当前.*是多少|查看.*状态/,
                /volume|brightness|mute|wallpaper|lock|shutdown|restart|sleep/i,
                /open|close|launch|quit|switch/i,
                /set.*to|change.*to/i,
            ],
        },
        // 复杂推理意图 (默认)
        {
            type: 'complex',
            patterns: [
                /分析|总结|比较|解释|为什么|如何|帮我想/,
                /写一个|创建.*代码|生成.*文件/,
                /多步|然后|接着|之后/,
                /analyze|summarize|compare|explain|why|how|help.*think/i,
                /write.*code|create.*file|generate/i,
                /multi.*step|then|after.*that/i,
            ],
        },
    ];

    /** 分类意图 */
    classify(input: string): IntentClassification {
        const normalizedInput = input.toLowerCase().trim();
        const matchedKeywords: string[] = [];

        // 先检查视觉意图 (优先级最高)
        for (const pattern of this.patterns[0].patterns) {
            const match = normalizedInput.match(pattern);
            if (match) {
                matchedKeywords.push(match[0]);
            }
        }
        if (matchedKeywords.length > 0) {
            return {
                type: 'visual',
                confidence: Math.min(0.9, 0.6 + matchedKeywords.length * 0.1),
                keywords: matchedKeywords,
            };
        }

        // 检查简单指令意图
        for (const pattern of this.patterns[1].patterns) {
            const match = normalizedInput.match(pattern);
            if (match) {
                matchedKeywords.push(match[0]);
            }
        }
        if (matchedKeywords.length > 0) {
            return {
                type: 'simple',
                confidence: Math.min(0.95, 0.7 + matchedKeywords.length * 0.1),
                keywords: matchedKeywords,
            };
        }

        // 检查复杂意图
        for (const pattern of this.patterns[2].patterns) {
            const match = normalizedInput.match(pattern);
            if (match) {
                matchedKeywords.push(match[0]);
            }
        }
        if (matchedKeywords.length > 0) {
            return {
                type: 'complex',
                confidence: Math.min(0.85, 0.5 + matchedKeywords.length * 0.15),
                keywords: matchedKeywords,
            };
        }

        // 默认为简单意图 (短输入) 或复杂意图 (长输入)
        const wordCount = normalizedInput.split(/\s+/).length;
        if (wordCount <= 10) {
            return {
                type: 'simple',
                confidence: 0.5,
                keywords: [],
            };
        }

        return {
            type: 'complex',
            confidence: 0.4,
            keywords: [],
        };
    }
}

/** 全局意图分类器实例 */
export const intentClassifier = new IntentClassifier();
