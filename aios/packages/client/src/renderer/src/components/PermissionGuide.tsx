/**
 * PermissionGuide - 权限引导组件
 */
import React from 'react';

interface PermissionGuideProps {
    adapterId: string;
    adapterName: string;
    available: boolean;
}

const PermissionGuide: React.FC<PermissionGuideProps> = ({ adapterId, adapterName, available }) => {
    if (available) return null;

    const getGuidance = () => {
        if (adapterId === 'com.aios.adapter.window') {
            return {
                title: '需要辅助功能权限',
                steps: [
                    '打开"系统偏好设置" → "安全性与隐私"',
                    '点击"隐私"选项卡',
                    '选择"辅助功能"',
                    '点击🔒图标并输入密码',
                    '勾选 AIOS 应用',
                ],
            };
        }
        if (adapterId === 'com.aios.adapter.desktop') {
            return {
                title: '需要屏幕录制权限',
                steps: [
                    '打开"系统偏好设置" → "安全性与隐私"',
                    '点击"隐私"选项卡',
                    '选择"屏幕录制"',
                    '勾选 AIOS 应用',
                ],
            };
        }
        return null;
    };

    const guidance = getGuidance();
    if (!guidance) return null;

    return (
        <div className="permission-guide" style={{
            backgroundColor: '#fff7ed',
            border: '1px solid #fdba74',
            borderRadius: 8,
            padding: '12px 16px',
            marginTop: 12,
        }}>
            <h4 style={{ margin: '0 0 8px 0', color: '#c2410c' }}>⚠️ {guidance.title}</h4>
            <p style={{ margin: '0 0 8px 0', fontSize: 14, color: '#7c2d12' }}>
                {adapterName} 需要额外权限才能正常工作:
            </p>
            <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13, color: '#7c2d12' }}>
                {guidance.steps.map((step, i) => (
                    <li key={i} style={{ marginBottom: 4 }}>{step}</li>
                ))}
            </ol>
        </div>
    );
};

export default PermissionGuide;
