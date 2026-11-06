"""Run in the upstream CosyVoice environment, not the mobile application env."""
import argparse
import io
import os
import sys
import threading
import wave
from pathlib import Path


def create_app(engine, reference_audio, reference_text, token=''):
    from fastapi import FastAPI, Header, HTTPException
    from fastapi.responses import Response
    from pydantic import BaseModel
    import torch
    import secrets

    app = FastAPI(title='TalkApp CosyVoice bridge')
    lock = threading.Lock()

    class SpeechRequest(BaseModel):
        input: str
        model: str = 'cosyvoice'
        voice: str = 'default'
        speed: float = 1.0
        instructions: str = ''
        response_format: str = 'wav'

    @app.get('/health')
    def health():
        return {'ready': True, 'sample_rate': engine.sample_rate}

    @app.post('/v1/audio/speech')
    def speech(request: SpeechRequest, authorization: str = Header(default='')):
        if token and not secrets.compare_digest(authorization, 'Bearer ' + token):
            raise HTTPException(401, 'Invalid token')
        if not 0 < len(request.input.strip()) <= 600 or not .5 <= request.speed <= 2:
            raise HTTPException(400, 'Text or speed outside limits')
        if request.voice != 'default' or request.response_format != 'wav':
            raise HTTPException(400, 'This bridge exposes one reference voice and PCM WAV only')
        with lock:
            if request.instructions and hasattr(engine, 'inference_instruct2'):
                output = engine.inference_instruct2(request.input, request.instructions, reference_audio,
                                                   stream=False, speed=request.speed)
            else:
                output = engine.inference_zero_shot(request.input, reference_text, reference_audio,
                                                    stream=False, speed=request.speed)
            pieces = [item['tts_speech'].detach().cpu() for item in output]
            if not pieces:
                raise HTTPException(502, 'Model returned no audio')
            audio = torch.cat(pieces, dim=-1).squeeze().clamp(-1, 1)
            pcm = (audio.numpy() * 32767).astype('<i2').tobytes()
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(engine.sample_rate)
            wav.writeframes(pcm)
        return Response(buffer.getvalue(), media_type='audio/wav')

    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True, help='Local upstream CosyVoice checkout')
    parser.add_argument('--model-dir', required=True)
    parser.add_argument('--reference-audio', required=True)
    parser.add_argument('--reference-text', required=True)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=50001)
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    sys.path[:0] = [str(repo), str(repo / 'third_party/Matcha-TTS')]
    from cosyvoice.cli.cosyvoice import AutoModel
    import uvicorn
    engine = AutoModel(model_dir=str(Path(args.model_dir).resolve()))
    app = create_app(engine, str(Path(args.reference_audio).resolve()), args.reference_text,
                     os.environ.get('TALKAPP_VOICE_TOKEN', ''))
    uvicorn.run(app, host=args.host, port=args.port)
