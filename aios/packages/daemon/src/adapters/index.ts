/**
 * 适配器导出
 */

// Base
export { BaseAdapter } from './BaseAdapter.js';

// System adapters
export { AudioAdapter, audioAdapter } from './system/AudioAdapter.js';
export { DisplayAdapter, displayAdapter } from './system/DisplayAdapter.js';
export { DesktopAdapter, desktopAdapter } from './system/DesktopAdapter.js';
export { PowerAdapter, powerAdapter } from './system/PowerAdapter.js';
export { SystemInfoAdapter, systemInfoAdapter } from './system/SystemInfoAdapter.js';
export { FileAdapter, fileAdapter } from './system/FileAdapter.js';

// Apps adapters
export { AppsAdapter, appsAdapter } from './apps/AppsAdapter.js';
export { WindowAdapter, windowAdapter } from './apps/WindowAdapter.js';

// Browser adapters
export { BrowserAdapter, browserAdapter } from './browser/BrowserAdapter.js';

// Speech adapter
export { SpeechAdapter, speechAdapter } from './speech/SpeechAdapter.js';

// Notification adapter
export { NotificationAdapter, notificationAdapter } from './notification/NotificationAdapter.js';

// Timer adapter
export { TimerAdapter, timerAdapter } from './timer/TimerAdapter.js';

// Calculator adapter
export { CalculatorAdapter, calculatorAdapter } from './calculator/CalculatorAdapter.js';

// Calendar adapter
export { CalendarAdapter, calendarAdapter } from './calendar/CalendarAdapter.js';

// Weather adapter
export { WeatherAdapter, weatherAdapter } from './weather/WeatherAdapter.js';

// Translate adapter
export { TranslateAdapter, translateAdapter } from './translate/TranslateAdapter.js';
