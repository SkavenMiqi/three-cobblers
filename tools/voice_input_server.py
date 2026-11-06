"""Computer-assisted offline ASR service. All model/cache paths are explicit."""
import argparse
import os
import tempfile
from pathlib import Path


def create_app(model):
    from fastapi import FastAPI, UploadFile, HTTPException
    import threading
    app = FastAPI(title='TalkApp voice input')
    lock = threading.Lock()

    @app.get('/health')
    def health():
        return {'ready': True}

    @app.post('/v1/audio/transcriptions')
    def transcriptions(file: UploadFile):
        data = file.file.read(10 * 1024 * 1024 + 1)
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(413, 'Audio too large')
        suffix = '.m4a' if (file.filename or '').endswith('.m4a') else '.wav'
        with tempfile.TemporaryDirectory(dir=os.environ.get('TALKAPP_VOICE_TMP')) as folder:
            path = Path(folder) / ('input' + suffix)
            path.write_bytes(data)
            with lock:
                # Client already segments speech using silence detection. Avoid an
                # additional ONNX runtime requirement on Windows.
                segments, _ = model.transcribe(str(path), language='zh', beam_size=3, vad_filter=False)
                text = ''.join(segment.text for segment in segments).strip()
        return {'text': text}
    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='small')
    parser.add_argument('--cache', default='F:/TalkAppEnvs/voice-models')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=50002)
    args = parser.parse_args()
    from faster_whisper import WhisperModel
    import uvicorn
    model = WhisperModel(args.model, device='cpu', compute_type='int8', download_root=args.cache,
                         local_files_only=os.environ.get('HF_HUB_OFFLINE') == '1')
    uvicorn.run(create_app(model), host=args.host, port=args.port)
