import { defineConfig, externalizeDepsPlugin } from 'electron-vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
    main: {
        plugins: [externalizeDepsPlugin()],
        build: {
            outDir: 'dist/main',
            rollupOptions: {
                input: './src/main/index.ts',
            },
        },
    },
    preload: {
        plugins: [externalizeDepsPlugin()],
        build: {
            outDir: 'dist/preload',
            rollupOptions: {
                input: './src/preload/index.ts',
                output: {
                    format: 'cjs',
                    entryFileNames: '[name].js',
                },
            },
        },
    },
    renderer: {
        plugins: [react()],
        root: './src/renderer',
        build: {
            outDir: 'dist/renderer',
            rollupOptions: {
                input: './src/renderer/index.html',
            },
        },
        define: {
            // 注入 WebSocket token 环境变量（如果设置了的话）
            'import.meta.env.VITE_AIOS_WEBSOCKET_TOKEN': JSON.stringify(process.env.VITE_AIOS_WEBSOCKET_TOKEN || ''),
        },
        server: {
            headers: {
                'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; connect-src 'self' ws://localhost:8765 http://localhost:*; img-src 'self' data:",
            },
        },
    },
});
