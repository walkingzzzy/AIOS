export interface NormalizedBase64Image {
    mimeType: string;
    data: string;
}

export function normalizeBase64Image(
    input: string,
    defaultMimeType: string = 'image/png'
): NormalizedBase64Image {
    const trimmed = input.trim();
    if (trimmed.startsWith('data:')) {
        const match = trimmed.match(/^data:([^;]+);base64,(.*)$/);
        if (match) {
            return { mimeType: match[1], data: match[2].trim() };
        }
    }

    return { mimeType: defaultMimeType, data: trimmed };
}

export function toDataUrl(image: NormalizedBase64Image): string {
    return `data:${image.mimeType};base64,${image.data}`;
}

