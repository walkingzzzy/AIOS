/**
 * VoiceInput - 语音输入按钮组件
 * 用于录制语音并转换为文本（使用 Web Speech API）
 */

import React, { useState, useCallback } from 'react';

interface VoiceInputProps {
    onTranscript: (text: string) => void;
    disabled?: boolean;
}

const VoiceInput: React.FC<VoiceInputProps> = ({ onTranscript, disabled = false }) => {
    const [isRecording, setIsRecording] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleVoiceInput = useCallback(async () => {
        setError(null);

        // 检查浏览器支持
        const SpeechRecognition =
            (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

        if (!SpeechRecognition) {
            setError('浏览器不支持语音识别');
            return;
        }

        try {
            const recognition = new SpeechRecognition();
            recognition.lang = 'zh-CN';
            recognition.interimResults = false;
            recognition.maxAlternatives = 1;

            recognition.onstart = () => {
                setIsRecording(true);
            };

            recognition.onend = () => {
                setIsRecording(false);
            };

            recognition.onresult = (event: any) => {
                const transcript = event.results[0][0].transcript;
                onTranscript(transcript);
            };

            recognition.onerror = (event: any) => {
                console.error('[VoiceInput] Recognition error:', event.error);
                setIsRecording(false);
                if (event.error === 'not-allowed') {
                    setError('请允许使用麦克风');
                } else {
                    setError(`识别错误: ${event.error}`);
                }
            };

            recognition.start();
        } catch (err) {
            console.error('[VoiceInput] Failed to start:', err);
            setError('无法启动语音识别');
        }
    }, [onTranscript]);

    return (
        <div className="voice-input-container">
            <button
                className={`voice-btn ${isRecording ? 'recording' : ''}`}
                onClick={handleVoiceInput}
                disabled={disabled || isRecording}
                title={isRecording ? '录音中...' : '语音输入'}
            >
                <span className="voice-icon">🎤</span>
                {isRecording && <span className="recording-indicator"></span>}
            </button>
            {error && <span className="voice-error">{error}</span>}
        </div>
    );
};

export default VoiceInput;
