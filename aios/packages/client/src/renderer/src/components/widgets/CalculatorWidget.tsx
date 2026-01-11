/**
 * CalculatorWidget - 计算器小部件
 */

import React, { useState, useCallback } from 'react';
import { api } from '../../utils/api';

const CalculatorWidget: React.FC = () => {
    const [expression, setExpression] = useState('');
    const [result, setResult] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    const handleCalculate = useCallback(async () => {
        if (!expression.trim()) return;

        setError(null);

        try {
            const response = await api.invoke('com.aios.adapter.calculator', 'calculate', {
                expression,
            }) as { success?: boolean; data?: { result: string }; error?: { message: string } };

            if (response?.success && response.data) {
                setResult(response.data.result);
            } else {
                setError(response?.error?.message || '计算失败');
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : '计算错误');
        }
    }, [expression]);

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            handleCalculate();
        }
    };

    return (
        <div className="calculator-widget">
            <div className="widget-header">
                <h4>🔢 计算器</h4>
            </div>
            <div className="widget-body">
                <div className="calc-input-row">
                    <input
                        type="text"
                        value={expression}
                        onChange={(e) => setExpression(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder="输入表达式 (如 2+2*3)"
                    />
                    <button onClick={handleCalculate}>=</button>
                </div>
                {error && <div className="widget-error">{error}</div>}
                {result && (
                    <div className="calc-result">
                        <span className="result-label">结果:</span>
                        <span className="result-value">{result}</span>
                    </div>
                )}
            </div>
        </div>
    );
};

export default CalculatorWidget;
