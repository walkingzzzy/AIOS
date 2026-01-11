/**
 * WeatherWidget - 天气小部件
 */

import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../../utils/api';

interface WeatherData {
    temp: number;
    feels_like: number;
    description: string;
    humidity: number;
    wind_speed: number;
    city: string;
}

const WeatherWidget: React.FC = () => {
    const [weather, setWeather] = useState<WeatherData | null>(null);
    const [city, setCity] = useState('Beijing');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const fetchWeather = useCallback(async () => {
        setLoading(true);
        setError(null);

        try {
            const result = await api.invoke('com.aios.adapter.weather', 'get_current_weather', {
                city,
            }) as { success?: boolean; data?: { weather: WeatherData }; error?: { message: string } };

            if (result?.success && result.data?.weather) {
                setWeather(result.data.weather);
            } else {
                setError(result?.error?.message || '获取天气失败');
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : '网络错误');
        } finally {
            setLoading(false);
        }
    }, [city]);

    useEffect(() => {
        fetchWeather();
    }, []);

    return (
        <div className="weather-widget">
            <div className="widget-header">
                <h4>🌤️ 天气</h4>
                <button onClick={fetchWeather} disabled={loading} className="refresh-btn">
                    🔄
                </button>
            </div>
            <div className="widget-body">
                <div className="city-input">
                    <input
                        type="text"
                        value={city}
                        onChange={(e) => setCity(e.target.value)}
                        placeholder="城市名称"
                        onKeyDown={(e) => e.key === 'Enter' && fetchWeather()}
                    />
                </div>
                {loading && <div className="widget-loading">加载中...</div>}
                {error && <div className="widget-error">{error}</div>}
                {weather && !loading && (
                    <div className="weather-info">
                        <div className="weather-temp">{weather.temp}°C</div>
                        <div className="weather-desc">{weather.description}</div>
                        <div className="weather-details">
                            <span>体感 {weather.feels_like}°C</span>
                            <span>湿度 {weather.humidity}%</span>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default WeatherWidget;
