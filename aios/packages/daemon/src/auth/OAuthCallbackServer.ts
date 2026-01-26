import { createServer, Server, IncomingMessage, ServerResponse } from 'http';
import { URL } from 'url';

export interface CallbackResult {
    code: string;
    state?: string;
}

export class OAuthCallbackServer {
    private server: Server | null = null;
    private port: number;
    
    constructor(port: number = 3000) {
        this.port = port;
    }
    
    async waitForCallback(timeoutMs: number = 120000, expectedState?: string): Promise<CallbackResult> {
        return new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                this.stop();
                reject(new Error('OAuth callback timeout'));
            }, timeoutMs);
            
            this.server = createServer((req: IncomingMessage, res: ServerResponse) => {
                const url = new URL(req.url || '/', `http://localhost:${this.port}`);
                
                if (url.pathname === '/oauth/callback') {
                    const code = url.searchParams.get('code');
                    const state = url.searchParams.get('state');
                    const error = url.searchParams.get('error');
                    
                    if (error) {
                        res.writeHead(400, { 'Content-Type': 'text/html' });
                        res.end('<html><body><h1>授权失败</h1><p>您可以关闭此窗口</p></body></html>');
                        clearTimeout(timeout);
                        this.stop();
                        reject(new Error(`OAuth error: ${error}`));
                        return;
                    }
                    
                    if (code) {
                        if (expectedState && state !== expectedState) {
                            res.writeHead(400, { 'Content-Type': 'text/html' });
                            res.end('<html><body><h1>State 校验失败</h1><p>请重新授权</p></body></html>');
                            clearTimeout(timeout);
                            this.stop();
                            reject(new Error('OAuth state mismatch'));
                            return;
                        }
                        res.writeHead(200, { 'Content-Type': 'text/html' });
                        res.end('<html><body><h1>授权成功</h1><p>您可以关闭此窗口</p></body></html>');
                        clearTimeout(timeout);
                        this.stop();
                        resolve({ code, state: state || undefined });
                    } else {
                        res.writeHead(400, { 'Content-Type': 'text/html' });
                        res.end('<html><body><h1>缺少授权码</h1></body></html>');
                    }
                } else {
                    res.writeHead(404);
                    res.end('Not Found');
                }
            });
            
            this.server.listen(this.port);
        });
    }
    
    stop(): void {
        if (this.server) {
            this.server.close();
            this.server = null;
        }
    }
    
    getCallbackUrl(): string {
        return `http://localhost:${this.port}/oauth/callback`;
    }
}
