/**
 * WidgetsView - 小部件视图
 */

import React from 'react';
import { WeatherWidget, TranslateWidget, CalculatorWidget } from '../components/widgets';

const WidgetsView: React.FC = () => {
    return (
        <div className="widgets-view">
            <header className="widgets-header">
                <h2>小部件</h2>
                <p>常用工具和信息服务</p>
            </header>
            <div className="widgets-grid">
                <WeatherWidget />
                <TranslateWidget />
                <CalculatorWidget />
            </div>
        </div>
    );
};

export default WidgetsView;
