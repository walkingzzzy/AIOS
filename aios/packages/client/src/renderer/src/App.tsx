/**
 * AIOS Client - 主应用组件
 */

import React, { useState, useEffect } from 'react';
import ChatView from './views/ChatView';
import SettingsView from './views/SettingsView';
import ToolsView from './views/ToolsView';
import WidgetsView from './views/WidgetsView';
import './App.css';

type ViewType = 'chat' | 'tools' | 'widgets' | 'settings';

const App: React.FC = () => {
    const [currentView, setCurrentView] = useState<ViewType>('tools');
    const [showQuickLauncher, setShowQuickLauncher] = useState(false);

    useEffect(() => {
        // 监听导航事件
        window.aios?.onNavigate((path) => {
            if (path === '/settings') {
                setCurrentView('settings');
            } else if (path === '/tools') {
                setCurrentView('tools');
            } else if (path === '/widgets') {
                setCurrentView('widgets');
            } else {
                setCurrentView('chat');
            }
        });

        // 监听快速启动器事件
        window.aios?.onShowQuickLauncher(() => {
            setShowQuickLauncher(true);
        });
    }, []);

    return (
        <div className="app">
            <nav className="sidebar">
                <div className="sidebar-header">
                    <h1>AIOS</h1>
                </div>
                <div className="sidebar-nav">
                    <button
                        className={`nav-item ${currentView === 'chat' ? 'active' : ''}`}
                        onClick={() => setCurrentView('chat')}
                    >
                        <span className="icon">💬</span>
                        <span>对话</span>
                    </button>
                    <button
                        className={`nav-item ${currentView === 'tools' ? 'active' : ''}`}
                        onClick={() => setCurrentView('tools')}
                    >
                        <span className="icon">🛠️</span>
                        <span>工具</span>
                    </button>
                    <button
                        className={`nav-item ${currentView === 'widgets' ? 'active' : ''}`}
                        onClick={() => setCurrentView('widgets')}
                    >
                        <span className="icon">📦</span>
                        <span>小部件</span>
                    </button>
                    <button
                        className={`nav-item ${currentView === 'settings' ? 'active' : ''}`}
                        onClick={() => setCurrentView('settings')}
                    >
                        <span className="icon">⚙️</span>
                        <span>设置</span>
                    </button>
                </div>
            </nav>
            <main className="main-content">
                {currentView === 'chat' && (
                    <ChatView
                        quickLauncherOpen={showQuickLauncher}
                        onQuickLauncherClose={() => setShowQuickLauncher(false)}
                    />
                )}
                {currentView === 'tools' && <ToolsView />}
                {currentView === 'widgets' && <WidgetsView />}
                {currentView === 'settings' && <SettingsView />}
            </main>
        </div>
    );
};

export default App;

