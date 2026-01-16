// 第三方库类型声明

declare module 'brightness' {
    export function get(): Promise<number>;
    export function set(value: number): Promise<void>;
}

declare module 'nodemailer' {
    export interface Transporter {
        sendMail(options: MailOptions): Promise<unknown>;
    }

    export interface MailOptions {
        from: string;
        to: string;
        subject: string;
        text?: string;
        html?: string;
    }

    export interface TransportOptions {
        host: string;
        port: number;
        secure?: boolean;
        auth: {
            user: string;
            pass: string;
        };
    }

    export function createTransport(options: TransportOptions): Transporter;
}
