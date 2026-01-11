/**
 * VoicePlayer - 语音播放控制组件
 * 用于播放 AI 回复（通过 SpeechAdapter TTS）
 */

import React, { useState, useCallback } from 'react';
import { api } from '../../utils/api';

interface VoicePlayerProps {
    text: string;
    autoPlay?: boolean;
}

const VoicePlayer: React.FC<VoicePlayerProps> = ({ text, autoPlay = false }) => {
    const [isPlaying, setIsPlaying] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handlePlay = useCallback(async () => {
        if (!text || isPlaying) return;

        setError(null);
        setIsPlaying(true);

        try {
            const result = await api.invoke('com.aios.adapter.speech', 'speak', {
                text,
                speed: 1.0,
            }) as { success?: boolean; error?: { message?: string } } | undefined;

            if (!result?.success) {
                throw new Error(result?.error?.message || '播放失败');
            }
        } catch (err) {
            console.error('[VoicePlayer] Play error:', err);
            setError(err instanceof Error ? err.message : '播放失败');
        } finally {
            setIsPlaying(false);
        }
    }, [text, isPlaying]);

    const handleStop = useCallback(async () => {
        try {
            await api.invoke('com.aios.adapter.speech', 'stop', {});
            setIsPlaying(false);
        } catch (err) {
            console.error('[VoicePlayer] Stop error:', err);
        }
    }, []);

    // 自动播放
    React.useEffect(() => {
        if (autoPlay && text) {
            handlePlay();
        }
    }, [autoPlay, text, handlePlay]);

    if (!text) return null;

    return (
        <div className="voice-player">
            {isPlaying ? (
                <button
                    className="voice-player-btn playing"
                    onClick={handleStop}
                    title="停止播放"
                >
                    <span className="voice-icon">⏹️</span>
                </button>
            ) : (
                <button
                    className="voice-player-btn"
                    onClick={handlePlay}
                    title="朗读"
                >
                    <span className="voice-icon">🔊</span>
                </button>
            )}
            {error && <span className="voice-error">{error}</span>}
        </div>
    );
};

export default VoicePlayer;
