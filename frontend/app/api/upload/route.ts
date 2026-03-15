import { NextResponse } from 'next/server';
import fs from 'fs/promises';
import path from 'path';

const MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024; // 25 MB

function sanitizeFilename(name: string) {
  return path.basename(name).replace(/[<>:"/\\|?*\x00-\x1F]/g, '_');
}

export async function POST(req: Request) {
  try {
    const formData = await req.formData();
    const uploadedFile = formData.get('file');

    if (!uploadedFile || typeof uploadedFile === 'string') {
      return NextResponse.json({ error: 'No file provided.' }, { status: 400 });
    }

    if (typeof uploadedFile.arrayBuffer !== 'function') {
      return NextResponse.json({ error: 'Invalid file payload.' }, { status: 400 });
    }

    const file = uploadedFile as Blob & { name?: string; size?: number };
    const fileSize = Number(file.size || 0);

    if (fileSize <= 0) {
      return NextResponse.json({ error: 'Empty file.' }, { status: 400 });
    }

    if (fileSize > MAX_FILE_SIZE_BYTES) {
      return NextResponse.json(
        { error: 'File too large. Max size is 25 MB.' },
        { status: 413 }
      );
    }

    const safeName = sanitizeFilename(file.name || 'uploaded_file');
    const dataDir = path.join(process.cwd(), '..', 'data');
    await fs.mkdir(dataDir, { recursive: true });

    const destination = path.join(dataDir, safeName);
    const bytes = Buffer.from(await file.arrayBuffer());
    await fs.writeFile(destination, bytes);

    return NextResponse.json({
      success: true,
      filename: safeName,
      size: fileSize,
      savedTo: destination,
    });
  } catch (error) {
    console.error('Upload API Error:', error);
    return NextResponse.json({ error: 'Failed to upload file.' }, { status: 500 });
  }
}
