# Contrato do tracker (resumo em pt-BR)

O texto de referência é o inglês: [`docs/TRACKER-CONTRACT.md`](../TRACKER-CONTRACT.md).

O FaceForge fala com o rastreador de rosto por um único arquivo, `captureforge/face/helpers/tracker.py`. É o único
módulo que importa o MediaPipe (um teste, `tests/test_capture_contract.py`, confere). Todos os helpers que rastreiam
rosto passam por ele: vídeo (`video_to_csv.py`), render do auto rig (`face_landmarks.py`), webcam UDP
(`webcam_stream.py`) e o helper de captura ao vivo. Se o MediaPipe for arquivado ou mudar de API, outro backend
substitui só esse arquivo. Não há registro de plugins.

O tracker roda no Python do helper (um venv), nunca dentro do Blender.

## Interface

```python
from tracker import Tracker, TrackerError

with Tracker.video(caminho_do_modelo) as t:   # ou Tracker.image(...), Tracker.live(...)
    resultado = t.process(frame_rgb, timestamp_ms)
```

- Entrada: `frame_rgb` é um array `uint8` altura x largura x 3 em **RGB** (o OpenCV lê BGR: converta antes) e
  `timestamp_ms` em milissegundos, estritamente crescente nos modos `video` e `live`.
- Saída (`Result`): `timestamp_ms`; `scores` (nome ARKit para 0..1, ou `None` sem rosto); `landmarks` (478 x 3
  `float32` normalizados, ou `None`); `matrix` (4 x 4 `float32`, a pose da cabeça, ou `None`).
- No modo `live` o resultado é assíncrono: `process` devolve o resultado mais novo já pronto (pode ser de um quadro
  anterior, veja `timestamp_ms`) ou `None` antes do primeiro.
- Erros: `TrackerError` com o código `helper_missing` (pacote não instalado), `model_missing` (arquivo do modelo não
  existe) ou `model_corrupt` (o arquivo não carrega).
