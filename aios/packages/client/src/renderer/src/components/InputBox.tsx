/**
 * InputBox - 输入框组件
 */

import React, { useState, useRef, useCallback } from 'react';

interface InputBoxProps {
    onSend: (message: string) => void;
    disabled?: boolean;
    onVoiceTranscript?: (text: string) => void;
    voiceButton?: React.ReactNode;
}

const InputBox: React.FC<InputBoxProps> = ({ onSend, disabled = false, voiceButton }) => {
    const [value, setValue] = useState('');
    const inputRef = useRef<HTMLInputElement>(null);

    const handleSubmit = useCallback(() => {
        if (value.trim() && !disabled) {
            onSend(value.trim());
            setValue('');
        }
    }, [value, disabled, onSend]);

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
    };

    return (
        <div className="input-container">
            <div className="input-wrapper">
                <input
                    ref={inputRef}
                    type="text"
                    className="input-box"
                    value={value}
                    onChange={(e) => setValue(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="输入消息... (Enter 发送)"
                    disabled={disabled}
                />
                {voiceButton}
                <button
                    className="send-button"
                    onClick={handleSubmit}
                    disabled={disabled || !value.trim()}
                >
                    发送
                </button>
            </div>
        </div>
    );
};

export default InputBox;
