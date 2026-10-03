# BodyForge — pesquisa (fase 0)

Levantamento público para o próximo módulo da suíte: **mocap de corpo sem marcadores, a partir de vídeo de celular**,
dentro do Blender 5.2, GPL-3.0-or-later. Data da pesquisa: 2026-10-03. **Clean room:** só páginas de produto,
READMEs, licenças, artigos e documentação oficial; nada foi baixado ou instalado, nenhum código foi copiado.
Referências `[Sn]` apontam para a seção 8. O que é inferência minha (sem fonte direta) vem marcado como
**(inferência)**; o que não consegui verificar vem como **(não verificado)**.

Premissas do cliente: UM celular (Iriun só aceita um dispositivo), RTX 3050 laptop (4 a 6 GB), Windows 11, Blender
5.2. Primeiro cliente: jogo Unity com rig humanoide estilo Mixamo, faltam 4 clipes: mãos ao alto (rendição), revista
policial, pilotar moto, uma dança.

## 0. Resumo executivo

- Os modelos de maior qualidade para vídeo mono (GVHMR, WHAM, TRAM, PromptHMR) dependem de **SMPL/SMPL-X**, cuja
  licença proíbe uso comercial [S11][S12]. Alguns têm código MIT [S6][S8] mas pesos e dados herdam a restrição
  **(inferência)**. Para um jogo comercial isso é risco jurídico, não só técnico.
- A única base 100 % permissiva e já instalável por `pip` no Windows é **MediaPipe** (Apache-2.0) [S19], que o
  FaceForge já usa [S85]. Qualidade menor (profundidade ruim [S16]) mas suficiente para gestos de torso e braço se
  houver limpeza boa. É aqui que o BodyForge agrega: **solver + limpeza + preset Mixamo/Unity**, não um modelo novo.
- Caminho SMPL-free promissor para a v2: **SAM 3D Body + MHR** (Meta; MHR Apache-2.0, pesos sob SAM License que
  permite uso comercial com condições) [S32][S33][S34]. É por imagem, não por vídeo, então exige suavização e chão.
- Retarget genérico já existe grátis e em GPL (extensão **Retarget**, 5.2.0, ago/2026) [S54]. Não reinventar:
  fazer retarget direto para um perfil fixo Mixamo/Unity e interoperar com ela.
- Recomendação v1: MediaPipe Pose + Hands em Python externo, solver de rotações próprio no Blender, One Euro +
  Butterworth, foot lock heurístico, export FBX com as configs recomendadas para Unity [S81]. Opcional baixado à parte:
  RTMW (rtmlib) e importador de saída SMPL (licença do próprio usuário).

## 1. Estado da arte, vídeo mono para movimento 3D

Velocidade: **nenhuma fonte publica números em GPU de 4 a 6 GB**; o resto é estimativa minha, medir no hardware real.
O pré-processamento domina o tempo do GVHMR [S4]; numa 3050 espere minutos por clipe curto **(estimativa)**.

| Modelo | Qualidade / chão | Velocidade, 4 a 6 GB, Windows | Licença |
|---|---|---|---|
| MediaPipe Pose Landmarker (BlazePose GHUM) | 33 pontos em imagem + "world" em metros, origem no quadril [S15]; world com assimetria de 10+ cm reportada [S16]; sem translação global nem chão **(inferência: origem fixa no quadril)** | Modo VIDEO usa tracking [S15]; Hand Landmarker 17 ms em CPU de Pixel 6 [S17]; `pip install mediapipe` [S15] | Apache-2.0 [S19] |
| RTMPose / RTMW / RTMW3D (MMPose, rtmlib) | RTMW3D: 133 pontos (corpo, 6 pés, 68 rosto, 42 mãos) [S22][S23]; COCO-WholeBody AP 0.68, H3WB MPJPE ~56 mm [S22]; formato 3D e z não documentados na página **(não verificado)**; sem chão | RTMPose-m: 430+ FPS numa GTX 1660 Ti [S24]; rtmlib só pede numpy, opencv, onnxruntime [S20]; Windows com onnxruntime-gpu [S20] | Código Apache-2.0 [S20][S21]; pesos treinados em mistura de datasets com licenças próprias [S21][S22] |
| MotionBERT (lifting 2D para 3D) | Entra 2D H36M de 17 juntas, até 243 frames, MPJPE 39,2 mm no H36M (laboratório) [S25]; sem chão | Modelo Lite de 61 MB [S25]; leve **(inferência)** | Código Apache-2.0 [S25]; H36M é só acadêmico [S14], conferir dados do treino **(não verificado)** |
| HMR2 / 4DHumans | Malha SMPL por frame; sem mundo/chão por si | Pesado (ViT) **(inferência)** | Código MIT [S10]; saída SMPL [S11] |
| WHAM | Mundo, refinamento por contato de pé, reduz foot skate, câmera móvel [S7]; SLAM pulável [S5] | Sem números de VRAM/Windows no README [S5] | Código MIT [S6]; exige registro SMPL [S5]; tratar pesos como não comerciais **(inferência)** |
| GVHMR | Coordenadas gravidade-visão, prevê estacionariedade de mãos/dedos do pé/calcanhar e corrige com IK CCD [S4]; mãos sem dedos [S83] | Rede: 0,28 s para 1430 frames numa 4090, mas pré-processo 46 s (YOLO, ViTPose, features, VO) [S4]; Windows: issue aberta e forks da comunidade [S83]; `-s` pula odometria visual [S1] | **Acadêmico/sem fins lucrativos** [S2]; precisa SMPL e SMPL-X [S3]; YOLOv8 é AGPL [S39] |
| TRAM | SLAM mascarado + VIMO, escala métrica pelo fundo [S9] | Muitas dependências (DROID-SLAM, Detectron2, SAM, DEVA, ZoeDepth); só Linux/macOS documentado [S8] | Código MIT [S8]; precisa SMPL [S8] |
| PromptHMR (CVPR 2025) | Vídeo multi-pessoa em mundo com SAM2, DROID-SLAM, Metric3D [S28] | Pesado **(inferência)** | **Não comercial** [S29] |
| SMPLer-X | Corpo inteiro com mãos por frame [S26] | 17 a 36 FPS conforme o tamanho, GPU não informada [S26] | **S-Lab, não comercial** [S27] |
| GENMO/GEM (NVIDIA), CoMotion (Apple) | GEM estima e gera movimento (SMPL) [S30]; CoMotion rastreia multi-pessoa, precisa SMPL [S31] | n/d | GEM: NVIDIA Noncommercial [S30]; CoMotion: licença de modelo à parte, não li **(não verificado)** |
| **SAM 3D Body + MHR** (Meta) | Imagem única, corpo + pés + mãos em parâmetros MHR [S32]; 631 M a 840 M de parâmetros [S32]; versão em vídeo exige camadas extras: SAM-Body4D [S37], contato de pé suave e otimização de raiz no mundo [S36] | Porta C++/ONNX gera BVH; no Windows só build headless; CPU 5 a 15 s por frame, CUDA recomendado [S35]; `pip install mhr` experimental, `pymomentum` pode falhar [S34] | MHR Apache-2.0 [S34]; pesos SAM License: uso comercial permitido, repasse da licença, proibições de uso (militar, ITAR) [S33] |
| OpenCap Monocular | Refina WHAM para cinemática [S38] | n/d | PolyForm Noncommercial [S38] |

Leituras importantes:
- Contato de pé aprendido existe em GVHMR e WHAM [S4][S7]; nenhum modelo permissivo entrega isso pronto, então o
  BodyForge precisa de contato heurístico (seção 3.3).
- Hands: HaMeR tem código MIT mas depende de MANO, licença à parte **(não verificado)** [S41]. MediaPipe Hands entrega
  21 pontos por mão com lateralidade [S17] e é permissivo [S19].

## 2. Multi-câmera (depois)

- **FreeMoCap:** AGPL-3.0, com licenciamento alternativo sob consulta [S42]. Câmera única não precisa de calibração; com
  várias, usa placa **ChArUco** [S44]. Sincroniza webcams USB por software (skellycam) [S43]. Gera cena Blender com
  esqueleto ao final [S43]. Python 3.10 a 3.12 [S43].
- **Pose2Sim (BSD-3):** RTMPose via RTMLib, calibração por tabuleiro/ChArUco, **sincronização por correlação cruzada da
  velocidade vertical** de pontos, triangulação ponderada por confiança, filtros Butterworth, Kalman, OneEuro, GCV,
  LOESS, Gaussian, add-on Blender, instalação Windows documentada, converte calibrações de Caliscope, Anipose e
  FreeMocap [S45]. É a melhor referência de pipeline.
- **Caliscope (BSD-2):** calibra intrínsecos e extrínsecos com ChArUco, aceita sobreposição parcial, exporta TOML
  (compatível Pose2Sim/Anipose), CSV e TRC; exige câmeras sincronizadas [S46]. **Anipose (BSD-2):** ChArUco, RANSAC [S47].
- **Dois celulares:** sincronizar por **palmas + correlação cruzada do áudio** (pico da correlação) [S48]; ou por
  movimento, como o Pose2Sim [S45]. Erro esperado de ±1 frame a 30 fps e risco de FPS variável em celular
  **(inferência)**; gravar a 60 fps e refinar pelo movimento.
- **Plano:** BodyForge v2 *importa* resultados de Pose2Sim/Caliscope (TRC, TOML) em vez de reimplementar. Licenças
  permissivas deixam interoperar, e AGPL (FreeMoCap) só como programa separado [S67].

## 3. Pipeline de rig no Blender

### 3.1 Landmarks para rotações
- Estimadores SMPL já entregam **rotações** das juntas; o projeto mixamo-llm-mocap (MIT) transfere as rotações
  SMPL-X do GVHMR e assim preserva giro do antebraço e curvatura da coluna, em vez de re-derivar de posições [S49].
- MediaPipe/RTMPose entregam só **posições**. Rotação de cada osso vem de: direção do segmento (swing) e de um segundo
  vetor para o twist **(inferência, matemática padrão)**: plano da palma (pulso, indicador, mindinho) para o giro do
  antebraço, calcanhar e ponta do pé para a guinada do pé, linha dos ombros e dos quadris para a torção do tronco.
  MediaPipe já dá calcanhar, ponta do pé e polegar/indicador/mindinho [S15].
- Referência open source do caminho "posições para rotações": BlendArMocap (GPL-3) calcula rotações em tempo de
  execução, mas só transfere para Rigify e está **descontinuado** [S50]. Open Mocap (MIT) só vai até Blender 4.0 [S55].

### 3.2 Retarget, roll e twist nas ferramentas abertas
- Padrão: **alinhar rest poses (T vs A), aplicar a pose como rest, depois Copy Rotation + bake** [S58]. Copy Rotation
  em vez de Copy Transform deixa a hierarquia do rig-alvo mandar nas posições e tolera roll diferente [S58].
- Ferramentas: Auto-Rig Pro Remap (pago) tem "Redefine Rest Pose", copia orientação de ossos e escala a raiz [S57];
  ReNim (GPL-3) tem "Match Pose" e diz tratar orientação e escala sozinho [S56]; KeeMap (GPL-3) mapeia osso a osso com
  offsets de posição/rotação/escala e salva o mapeamento [S52]; BVH-Motion-Retargeter (MIT) usa JSON de mapeamento,
  constraints + bake NLA, limpeza de root motion e presets FBX Mixamo/UE5 [S51]; Mwni (GitHub) corrige mãos e pés e
  cria IK [S53]; **Retarget** (GPL-3, grátis, Blender 5.0+) tem auto-mapeamento com presets Mixamo [S54].
- **Decisão (inferência):** como o alvo é fixo (rig Mixamo-like), BodyForge calcula a rotação local direto, em espaço
  de mundo, convertendo o delta do osso-fonte para o referencial de rest do osso-alvo. Sem constraints, determinístico
  e mais rápido. Ossos de twist e roll do rig do cliente **devem ser conferidos**; Unity exige só 15 ossos em T-pose [S61].

### 3.3 Pé, contato, suavização, root motion, chão
- **Contato:** aprendido (GVHMR, WHAM [S4][S7]) ou heurístico: velocidade vertical do pé abaixo de limiar marca plantio
  [S65]. Solução clássica de skate: impor o plantio exato e ajustar com IK sem artefatos [S64]; mixamo-llm-mocap combina
  detector, proximidade do chão, rastreio visual e física, e trava o pé chapado ou em pivô [S49].
- **Chão:** GVHMR nasce alinhado à gravidade [S4]. Para MediaPipe: **(inferência)** pose neutra nos primeiros 1 a 2 s
  fixa o vetor "para cima" e as medidas dos ossos; altura do chão = mínimo de calcanhar/ponta nos frames de contato.
- **Suavização:** One Euro (`fcmin` e `beta`; ajustar `fcmin` perto de 1 Hz com `beta` 0, depois subir `beta` para
  tirar lag) [S59]; Butterworth de 4ª ordem, fase zero, ~3 Hz na translação da raiz e ~6 Hz em rotação/pose é prática
  de pré-processo mocap [S66]; Pose2Sim oferece ambos e mais [S45]; Blender 5.1 tem modificador Gaussian Smooth no
  Graph Editor, não destrutivo [S60]. Filtrar **quaternions** (SLERP-EMA), não Euler [S35].
  Plano: One Euro (causal) na prévia, Butterworth zero-phase (offline) no resultado final.
- **Root motion:** o Unity deriva a Root Transform da projeção em Y do Body Transform (centro de massa) [S62]; no clipe
  há Bake Into Pose para rotação, Y e XZ, e "Based Upon" [S63]. Os 4 clipes do cliente são quase todos *in place*
  (rendição, revista, moto parada, dança): exportar com Hips sem deriva e deixar XZ baked no import.

### 3.4 Ambiguidade de profundidade e jitter
- MediaPipe: profundidade com erro grande, mais ruidosa que o 2D [S16]. Mitigações (todas **inferência**): comprimentos
  de osso fixos medidos na pose neutra; limites de junta (cotovelo/joelho não dobram ao contrário); peso por
  `visibility`; câmera em 3/4 (45°) para a profundidade virar deslocamento visível; continuidade temporal para evitar o
  "flip" frente/trás do braço; levantar 2D mais preciso (RTMPose) e elevar com janela temporal (MotionBERT) [S25].

### 3.5 Export FBX para Unity Humanoid
- Humanoid pede >= 15 ossos, pose T, Avatar automap e Avatar reutilizável entre arquivos [S61]. Clipes podem usar o
  Avatar do FBX do personagem **(inferência a partir de [S61])**.
- Configuração de FBX do Blender recomendada para Unity: Apply Transform ligado, Add Leaf Bones desligado, Forward -Z,
  Up Y, eixos de osso primário Y e secundário X, opcional Only Deform Bones [S81]. Virar preset e validar com clipe de teste.

## 4. GPL: o que embutir e o que baixar à parte

Regra da plataforma: add-on em extensions.blender.org deve ser **GPL-3.0-or-later** [S68]; wheels vão em `wheels = [...]`
no manifesto, por plataforma [S69]. Apache-2.0, MIT e BSD são compatíveis com GPLv3; Apache não com GPLv2 [S67].
AGPL e GPL só combinam como módulos separados [S67].

| Pode embutir (código) | Só download opcional / processo externo |
|---|---|
| MediaPipe (Apache-2.0) [S19], rtmlib (Apache-2.0) [S20], Pose2Sim/Caliscope/Anipose (BSD) [S45][S46][S47], One Euro (BSD/MIT) [S59], Retarget/KeeMap/ReNim (GPL-3) [S54][S52][S56] | SMPL, SMPL-X, AMASS [S11][S12][S13]; GVHMR [S2]; PromptHMR [S29]; SMPLer-X [S27]; GEM [S30]; OpenCap Monocular [S38]; 3DGS e 2DGS [S76][S77]; VGGT original [S79]; Ultralytics AGPL [S39]; FreeMoCap AGPL [S42]; SAM License [S33] |

Notas:
- **Pesos de modelo são dados com licença própria**, separados do código. Conferir o model card de cada `.task`/`.onnx`
  antes de empacotar **(não verificado para MediaPipe)**. Pesos grandes não entram no zip, baixar sob demanda.
- SAM License tem restrições de uso (militar, ITAR) [S33]; isso conflita com o "sem restrições adicionais" da GPL
  **(inferência, validar)**, então fica como download externo mesmo sendo comercial.
- "Código MIT + dados NC" (WHAM, TRAM, HMR2 [S6][S8][S10]) é armadilha: SMPL e AMASS proíbem inclusive treinar modelos
  para uso comercial [S11][S13]. Se o usuário quiser, o BodyForge só **importa** o arquivo de saída, com aviso.
- O SMPL tem licenciamento comercial pela Meshcapade [S11]. Fora disso, não sabemos se clipes *gerados* com SMPL e
  usados num jogo à venda ficam cobertos **(não verificado, perguntar a eles)**.

**Stack v1 comercialmente segura (sem SMPL):** MediaPipe Pose + Hand Landmarker (opcional Holistic [S18]) em Python
externo (mesmo padrão do `requirements-mocap.txt` do FaceForge [S85]); resolução de rotações, filtros, contato e
export em Python puro + numpy dentro do Blender; saída FBX. Opcionais: RTMW via rtmlib; importador de saída SMPL.

## 5. Lacunas que o BodyForge pode preencher

- **Concorrência paga/limitada:** Rokoko Vision grátis só 30 s/mês de processamento [S70]; DeepMotion grátis 60
  créditos/mês, 20 s por clipe e uso pessoal não comercial [S71]. Ambos são nuvem.
- **Ferramentas livres** estão quebradas ou descontinuadas: BlendArMocap [S50], Open Mocap até Blender 4.0 [S55];
  mixamo-llm-mocap exige ~8 GB de VRAM, Blender 5.1+, só câmera fixa e Blender MCP [S49].
- Oportunidades:
  1. **Um clique dentro do Blender** (vídeo para clipe), sem terminal, com instalador do Python auxiliar.
  2. **Android-friendly:** qualquer arquivo de vídeo de qualquer celular, sem LiDAR nem iPhone (alinhado ao README do
     FaceForge).
  3. **Painel de limpeza** voltado a gesto de jogo: foot lock, loop closer (cruzar o fim com o início), in place,
     espelhar, aparar, métricas de skate/jitter, filmstrip de revisão.
  4. **Preset Mixamo/Unity** pronto, com export FBX validado em um projeto Unity de teste.
  5. **Mãos e dedos** por MediaPipe Hands [S17]: curl por dedo; GVHMR não tem dedos [S83].
  6. **Corpo + rosto do mesmo vídeo:** Holistic dá pose, mãos e rosto numa passada [S18]. Em enquadramento de corpo
     inteiro o rosto é pequeno **(inferência)**; solução: recortar a cabeça pelos pontos do corpo e rodar o Face
     Landmarker do FaceForge no recorte, com a mesma linha de tempo.

## 6. Escopo proposto

Clipes do cliente e dificuldade (**inferência**): *mãos ao alto*, fácil (pose quase estática, câmera de frente em 3/4);
*revista*, média (braços cruzando o tronco, oclusão; mãos importam); *moto*, difícil (pernas ocultas pela moto/cadeira,
gravar com a pessoa sentada e a perna visível, ajustar pés na mão); *dança*, a mais difícil (movimento rápido, borrão;
gravar 60 fps, luz forte, tentar quality pack).

**v1 (MVP):**
1. Botão "Vídeo para corpo": Python externo grava `landmarks.npz` (pose + mãos, confiança, FPS real do arquivo).
2. Pose neutra nos primeiros frames: mede ossos, vetor "para cima" e chão.
3. Solver para **perfil Mixamo/Unity Humanoid** (mapa fixo de ossos), rotações locais + Hips; dedos opcionais.
4. Limpeza: One Euro e Butterworth, foot lock heurístico, in place, loop closer, trim, mirror.
5. Inspetor (skate em cm/s, deriva de osso, violações de junta, jitter) + filmstrip PNG de revisão.
6. Export FBX com preset Unity; funções puras para uso headless/agentes (como no FaceForge).
7. Mesma linha de tempo do FaceForge: rodar rosto no mesmo vídeo e keyar na mesma action.

**v2:** RTMW como quality pack; importador GVHMR/WHAM (aviso de licença); SAM 3D Body + MHR (SMPL-free, com contato
e suavização temporal); duas câmeras via Pose2Sim/Caliscope e sync por palma; recorte de cabeça para o rosto; live
(webcam/Iriun); retarget para outros perfis (Rigify, UE5) usando a extensão Retarget [S54].

**Riscos:**
- Qualidade de profundidade do MediaPipe pode não bastar para revista e dança [S16] (mitigar com 3/4, 60 fps, RTMW).
- Chão/contato heurístico falha em saltos, agachamentos e moto sentada.
- Dependências nativas no Windows (pymomentum [S34], DPVO/SLAM [S3]); manter Python auxiliar separado do Python do
  Blender (que mudou para 3.13 no 5.1 [S60b]) evita quebrar com cada versão.
- Licença de pesos pode mudar entre versões do HF; fixar hash e registrar licença no repositório.
- Escopo: competir com GVHMR em qualidade é perder; competir em **fluxo + limpeza + preset**. Privacidade: vídeo de
  pessoas, reaproveitar a política de uso responsável do FaceForge.

## 7. Prévia do ScanForge (fotogrametria e Gaussian splatting)

Entrada: um vídeo orbitando o objeto/pessoa, ou 360° (equiretangular). Para 360°, cortar em vistas em perspectiva/cubo
com o filtro `v360` do FFmpeg [S80] e montar rig no COLMAP [S80]; para celular comum, extrair frames nítidos.

| Peça | Licença | Notas |
|---|---|---|
| COLMAP (SfM + MVS) | BSD [S72] | Binários Windows, `pycolmap`, `pycolmap-cuda12` com GPU [S72]; dá poses para tudo abaixo |
| Meshroom / AliceVision | MPL-2.0 [S73] | Binários Windows [S73]; CUDA e VRAM mínimos **(não verificado)** |
| OpenMVS (densa, malha, textura) | **AGPL-3.0** [S74] | Só como processo externo [S67] |
| gsplat (3DGS, 2DGS, MCMC, compressão) | Apache-2.0 [S75] | ~4x menos memória que a implementação oficial; Windows com instalação dedicada [S75] |
| 3DGS oficial (Inria) | **Pesquisa/avaliação apenas** [S76] | 24 GB de VRAM para qualidade do artigo; precisa MSVC e CUDA 11.x [S76] |
| 2DGS (superfície, malha por TSDF) | **Não comercial** (Inria/MPII) [S77] | gsplat reimplementa 2DGS com Apache [S75]; malha via TSDF [S77] |
| VGGT (poses por feed-forward, export COLMAP) | Checkpoint original NC; versão comercial sob formulário [S79] | Alternativa rápida ao SfM |

- VRAM em 4 a 6 GB: 3DGS oficial é inviável [S76]; gsplat com ~4x menos memória [S75] e menos imagens/resolução
  pode caber **(estimativa, medir)**.
- **Malha limpa:** splat vira nuvem/superfície (TSDF, OpenMVS), depois **retopologia**: Instant Meshes (BSD-3) faz quad
  alinhado ao campo [S78]; para personagem, melhor *embrulhar* a malha-base do personagem no scan: alinhamento rígido, depois
  Shrinkwrap do Blender por superfície mais relaxamento, preservando UV e skin weights **(inferência)**. É a ponte
  natural com o BodyForge (mesmo rig) e com o FaceForge (cabeça).

## 8. Fontes

- [S1] https://github.com/zju3dv/GVHMR | [S2] https://raw.githubusercontent.com/zju3dv/GVHMR/main/LICENSE
- [S3] https://github.com/zju3dv/GVHMR/blob/main/docs/INSTALL.md | [S4] https://arxiv.org/html/2409.06662
- [S5] https://github.com/yohanshin/WHAM | [S6] https://raw.githubusercontent.com/yohanshin/WHAM/main/LICENSE
- [S7] https://arxiv.org/abs/2312.07531 | [S8] https://github.com/yufu-wang/tram | [S9] https://arxiv.org/abs/2403.17346
- [S10] https://raw.githubusercontent.com/shubham-goel/4D-Humans/master/LICENSE.md
- [S11] https://smpl.is.tue.mpg.de/modellicense.html | [S12] https://smpl-x.is.tue.mpg.de/modellicense.html
- [S13] https://amass.is.tue.mpg.de/license.html | [S14] http://vision.imar.ro/human3.6m/eula.php
- [S15] https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python
- [S16] https://github.com/google-ai-edge/mediapipe/issues/4917
- [S17] https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker
- [S18] https://developers.google.com/edge/mediapipe/solutions/vision/holistic_landmarker
- [S19] https://github.com/google-ai-edge/mediapipe | [S20] https://github.com/Tau-J/rtmlib
- [S21] https://github.com/open-mmlab/mmpose | [S22] https://github.com/open-mmlab/mmpose/tree/main/projects/rtmpose3d
- [S23] https://huggingface.co/Soykaf/RTMW3D-x | [S24] https://arxiv.org/abs/2303.07399
- [S25] https://github.com/Walter0807/MotionBERT | [S26] https://github.com/caizhongang/SMPLer-X
- [S27] https://raw.githubusercontent.com/caizhongang/SMPLer-X/main/LICENSE | [S28] https://github.com/yufu-wang/PromptHMR
- [S29] https://raw.githubusercontent.com/yufu-wang/PromptHMR/main/LICENSE | [S30] https://github.com/NVlabs/GENMO
- [S31] https://github.com/apple/ml-comotion | [S32] https://github.com/facebookresearch/sam-3d-body
- [S33] https://github.com/facebookresearch/sam-3d-body/blob/main/LICENSE | [S34] https://github.com/facebookresearch/MHR
- [S35] https://github.com/AmmarkoV/SAM3DBody-cpp | [S36] https://arxiv.org/abs/2512.21573
- [S37] https://github.com/gaomingqi/sam-body4d | [S38] https://github.com/vxbrandon/opencap-monocular
- [S39] https://github.com/ultralytics/ultralytics
- [S41] https://github.com/geopavlakos/hamer | [S42] https://github.com/freemocap/freemocap | [S43] https://docs.freemocap.org/
- [S44] https://docs.freemocap.org/documentation/single-camera-recording.html | [S45] https://github.com/perfanalytics/pose2sim
- [S46] https://github.com/mprib/caliscope | [S47] https://github.com/lambdaloop/anipose
- [S48] https://github.com/allisonllx/multi-stereo-robotics | [S49] https://github.com/squall01337/mixamo-llm-mocap
- [S50] https://github.com/cgtinker/BlendArMocap | [S51] https://github.com/BacteriaJun/BVH-Motion-Retargeter/
- [S52] https://github.com/nkeeline/Keemap-Blender-Rig-ReTargeting-Addon | [S53] https://github.com/Mwni/blender-animation-retargeting
- [S54] https://extensions.blender.org/add-ons/retarget/ | [S55] https://github.com/Larenju-Rai/open-mocap-blender
- [S56] https://github.com/anasrar/ReNim | [S57] https://www.lucky3d.fr/auto-rig-pro/doc/remap_doc.html
- [S58] https://blenderartists.org/t/retargeting-armatures-with-different-bone-orientation/1406823
- [S59] https://gery.casiez.net/1euro/ | [S60] https://www.cgchannel.com/2026/03/discover-5-key-features-in-blender-5-1/
- [S60b] https://www.blender.org/download/releases/5-1/ (Python 3.13) | [S63] https://docs.unity3d.com/Manual/class-AnimationClip.html
- [S61] https://docs.unity3d.com/Manual/ConfiguringtheAvatar.html | [S62] https://docs.unity3d.com/Manual/RootMotion.html
- [S64] https://research.cs.wisc.edu/graphics/Gallery/kovar.vol/Cleanup/cleanup.pdf | [S67] https://www.gnu.org/licenses/license-list.html
- [S65] https://mocaponline.com/blogs/mocap-news/mocap-data-cleanup-workflow | [S66] https://arxiv.org/pdf/2510.26236
- [S68] https://docs.blender.org/manual/en/latest/advanced/extensions/licenses.html
- [S69] https://docs.blender.org/manual/en/latest/advanced/extensions/python_wheels.html | [S70] https://www.rokoko.com/products/vision
- [S71] https://www.deepmotion.com/release-updates | [S72] https://github.com/colmap/colmap
- [S73] https://github.com/alicevision/Meshroom | [S74] https://github.com/cdcseacave/openMVS
- [S75] https://github.com/nerfstudio-project/gsplat | [S76] https://github.com/graphdeco-inria/gaussian-splatting
  (licença: https://raw.githubusercontent.com/graphdeco-inria/gaussian-splatting/main/LICENSE.md)
- [S77] https://github.com/hbb1/2d-gaussian-splatting (licença: raw.githubusercontent.com/hbb1/2d-gaussian-splatting/main/LICENSE.md)
- [S78] https://raw.githubusercontent.com/wjakob/instant-meshes/master/LICENSE.txt | [S79] https://github.com/facebookresearch/vggt
- [S80] https://github.com/colmap/colmap/issues/3221 ; https://ayosec.github.io/ffmpeg-filters-docs/5.1/Filters/Video/v360.html
- [S81] https://bitsoulhosting.com/marketplace/blog/blender-to-unity-skinned-mesh-armature-animation-export
- [S83] https://github.com/zju3dv/GVHMR/issues (#23, #77, #85, #90) | [S85] Experiência própria: `faceforge/requirements-mocap.txt` e `docs/pt-BR/RESEARCH.md` §5 (numpy embutido no Blender)
