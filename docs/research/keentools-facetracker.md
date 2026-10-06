# KeenTools FaceTracker vs. FaceForge: o que fazem, onde termina a GPL e o que vale trazer

Pesquisa de 2026-10-05. Fontes: um vídeo promocional vertical de 18 s do FaceTracker (frames extraídos a 2 fps
mais cortes de cena), o código-fonte do add-on KeenTools para Blender versão 2026.3.1 (~51 mil linhas de Python)
e o estado atual do CaptureForge (FaceForge, BodyForge; ScanForge em roadmap). Ninguém rodou o FaceTracker
(ele exige licença paga e um binário fechado); tudo abaixo vem de ler o código e o vídeo.

Resumo em uma linha: o FaceTracker ajusta uma **malha densa de cabeça** (criada antes no FaceBuilder) quadro a
quadro sobre o vídeo, com pins e refinamento manual, e só depois **converte** a animação de vértices em pesos
ARKit; o FaceForge pede ao MediaPipe os **52 pesos ARKit direto** (sem malha intermediária) e os aplica nos shape
keys do personagem. Os dois terminam no mesmo lugar (shape keys ARKit animados num personagem estilizado), por
caminhos opostos.

## 1. O que o vídeo mostra, passo a passo

1. **Abertura (0 a 4 s).** Em cima, uma pessoa filmada de frente, luz difusa de estúdio, fazendo caretas; embaixo,
   uma cabeça de raposa estilizada (não humana) repetindo a expressão. Legenda "Facial mocap & 3D facial
   animation in Blender".
2. **"Track facial performance" (4 a 10 s).** Viewport do Blender com o vídeo como fundo da câmera e, por cima, um
   wireframe denso de cabeça humana (a malha do FaceBuilder, cerca de 10 mil vértices; a tabela de controle do
   código referencia índices até 9861). Regiões coloridas de verde sobre olhos, sobrancelhas, nariz e lábios (o
   esquema de cores do wireframe por partes do rosto). Pontos vermelhos são **pins**: o cabeçalho diz "LEFT CLICK:
   Create Pin | RIGHT CLICK: Delete Pin | TAB: Hide". Painel flutuante "Tracking" com abas **Head | Camera** (o que
   recebe a animação: a geometria ou a câmera), botões **Back to 3D**, **Auto Align**, navegação de keyframes e
   track para frente/trás, **Refine** e **Refine All**. No rodapé, o progresso em vermelho: "Tracking 5.5% (3/55)"
   ... "Tracking 94.5% (52/55)", ou seja, 55 frames rastreados num timer modal com progresso.
3. **Resultado 3D (10 a 12 s).** O mesmo clipe visto fora da câmera: cabeça cinza sem textura deformando quadro a
   quadro (é animação de **vértices**, não shape keys) e a câmera (triângulo laranja) parada; timeline com um
   keyframe por frame rastreado, ação "CameraAction", botões Push Down/Stash (NLA).
4. **"Convert to ARKit blendshapes" (12 a 15 s).** Painel **Export > Facial Animation** com abas **ARKit | Rigify**,
   campo **Target** (seletor de objeto, escolhem a cabeça da raposa), botão **Convert** e, abaixo, **Save as .csv**.
   Depois do Convert, a raposa anima lado a lado com a cabeça cinza.
5. **Fechamento (15 a 18 s).** Pessoa e raposa de novo lado a lado, "Download from keentools.io".

O que o vídeo **não** mostra e o código confirma: a cabeça cinza não é "escaneada" no FaceTracker. Ela vem do
**FaceBuilder** (produto irmão), que ajusta um modelo paramétrico de cabeça a fotos ou a snapshots do próprio vídeo
usando pins ("New - create new FaceBuilder head using snapshots of video frames and image files"). O FaceTracker
só aceita malhas com essa topologia (`poll_is_facebuilder_mesh`). A raposa já precisa ter shape keys com os nomes
ARKit; o Convert escreve uma ação de F-curves em `key_blocks["<nome>"].value`, igual ao que o FaceForge faz com um
CSV.

## 2. Arquitetura do add-on e a fronteira de licença

### 2.1 Mapa de pastas (tudo Python, cabeçalho GPL em todo arquivo)

| Pasta | Linhas | O que tem | Depende do core fechado? |
|---|---|---|---|
| `facebuilder/` | ~9.7k | criar cabeça de fotos: pin mode, detecção de rosto, câmera por EXIF, textura projetada, shape keys ARKit (FACS), import CSV | sim (modelo, solver, FACS) |
| `facetracker/` | ~6.3k | tracking da cabeça no vídeo: settings, callbacks, pin mode, shaders, operadores, `rig.py` (transfer para Rigify) | sim (tracker) |
| `geotracker/` | ~10.5k | tracking de objeto rígido; `utils/geotracker_acts.py` guarda as ações compartilhadas com o FaceTracker (track, refine, export CSV, unbreak) | sim |
| `tracker/` | ~4k | base comum: loader, settings, `calc_timer.py` (máquina de estados do timer modal com progresso), inputs de câmera | parcial |
| `common/` | ~1.6k | checagem de licença, bake de wireframe, viewport | sim |
| `utils/` | ~9.8k | `fcurve_operations.py`, `blendshapes.py`, `video.py`, `unbreak.py`, `gpu_shaders.py`, `edges.py`, `mesh_builder.py`, imagens, timers | misto |
| `preferences/`, `updater/` | ~3.1k | instalação do core, aceite da EULA, auto-update | sim |
| `blender_independent_packages/` | ~3.7k | `pykeentools_loader` (baixa, descompacta e importa o core) e `exifread` (BSD, terceiro) | é o loader |

### 2.2 O core fechado: `pykeentools`

- Não vem no zip do add-on. Em `Preferences`, o usuário marca "I have read and I agree to KeenTools End-user License
  Agreement" e clica para instalar; `pykeentools_loader/install.py` baixa
  `https://downloads.keentools.io/latest-keentools-core-<os>` e descompacta em
  `blender_independent_packages/pykeentools_loader/pykeentools/pykeentools_installation/pykeentools`.
- `pykeentools_loader.module()` põe essa pasta no `sys.path` e faz `import pykeentools` (no Windows copia antes para
  uma pasta temporária por PID, para poder atualizar com o Blender aberto). Todo o resto do add-on chama
  `pkt_module().<algo>`.
- A licença do core é verificada online (`license_manager`, `LicenseCheckStrategy`, trial, assinatura, floating) e
  qualquer operação relevante lança `UnlicensedException` sem licença. O manifesto declara
  `license = ["GPL-3.0-or-later", "EULA"]` e `permissions = ["files", "network"]`.

Tudo que é inteligência está no core. A lista dos símbolos chamados pelo Python deixa a fronteira nítida:

| No core (fechado, EULA) | Para que serve |
|---|---|
| `FaceBuilder`, `detect_faces`, `detect_face_pose` | detector de rosto e ajuste do modelo paramétrico a uma foto ("Auto Align") |
| `FaceTracker`, `GeoTracker`, `track_async`, `refine_async`, `track_frames`, `applied_args_model_vertices_at(frame)` | o tracker em si; vértices da malha ajustada em cada frame |
| `FacsExecutor` (`facs_names`, `get_facs_blendshape(i)`) | o modelo FACS: gera os 51 shape keys ARKit na topologia deles e converte vértices em pesos |
| `FacsAnimation` (`load_from_csv_file`, `keyframes`, `at_name`) | leitura e escrita do CSV no formato Live Link Face |
| `precalc.*` | arquivo de análise do vídeo (cache de features) |
| `texture_builder.build_texture` | projeção de textura das fotos na cabeça |
| `math.unbreak_rotation`, `math.proj_mat`, `Mask`, `LoadedMask` | utilidades matemáticas e máscaras |

### 2.3 O que é Python puro e GPL (reutilizável com atribuição)

- **UI e operadores**: painéis, strings de ajuda, operadores de botão, preferências.
- **Pin mode**: operadores modais de clique e arrasto, shaders GPU de wireframe, pins e preenchimento de regiões
  (`utils/gpu_shaders.py`, `utils/edges.py`, `facetracker/edges.py`).
- **Gerência de keyframes e timer**: `tracker/calc_timer.py` (timer modal com estados timeline/runner, progresso
  no cabeçalho, cancelamento com Esc), ações de "clear tracking forward/backward/between", prev/next keyframe.
- **F-curves**: `utils/fcurve_operations.py` (inserir pontos em lote, limpar e "snap" de chaves num intervalo,
  zeros nas pontas) e a parte de `utils/blendshapes.py` que cria shape keys, ações e um painel 3D de sliders com
  drivers.
- **Transfer para rig**: `facetracker/rig.py` (delta de vértice de controle vira posição de osso no espaço da
  cabeça, escala pela distância entre cantos dos olhos, constraints desligadas e compensadas por frame).
- **Vídeo**: `utils/video.py` (MovieClip, proxies, split em frames), `utils/unbreak.py` (wrapper de rotação
  contínua), máscaras 2D (MovieClip ou compositing) e 3D (vertex group).
- **Instalador e updater** (não interessa ao CaptureForge).

### 2.4 Veredito de licença

- **Os arquivos `.py` do add-on são GPL-3.0-or-later**, copyright KeenTools. Podem ser estudados e trechos podem
  ser reaproveitados no CaptureForge (também GPL-3.0-or-later), desde que: (a) se mantenha o aviso de copyright da
  KeenTools no arquivo que receber o trecho, (b) se marque que foi modificado e quando (GPL §5a), (c) a origem
  fique registrada em `THIRD_PARTY_NOTICES.md` e no comentário, como manda o princípio I da constituição.
- **`pykeentools` não é GPL**: é um binário sob EULA própria, licenciado por assinatura, baixado só após aceite e
  nunca redistribuível. Nada dele pode entrar no repositório, ser descompilado ou ter sua API imitada a ponto de
  carregar o binário. Qualquer linha que só faz sentido com `pkt_module()` (o modelo FACS, a topologia da cabeça,
  o tracker, o detector) está fora de alcance como código; só a **ideia** pode ser reimplementada do zero.
- Zona cinzenta a evitar: a tabela de `rig.py` (nome do osso Rigify -> índice de vértice) é código GPL, mas os
  índices só valem para a malha do FaceBuilder, que é um ativo do core. Copiar a tabela não serve para nada e dá
  margem a discussão; o padrão (ponto de controle -> osso) é o que vale.
- `exifread` é BSD-3, de terceiros; irrelevante para nós.
- Marca: "KeenTools", "FaceBuilder" e "FaceTracker" são nomes de produto. O CaptureForge não deve usá-los em nome de
  recurso, só em créditos ("padrão inspirado em ...").

## 3. Comparação recurso a recurso

| Recurso | KeenTools FaceTracker (+ FaceBuilder) | CaptureForge FaceForge (hoje) |
|---|---|---|
| Cabeça do ator | FaceBuilder: modelo paramétrico ajustado a fotos ou a snapshots do vídeo, com pins; textura projetada | Não gera cabeça. Usa a malha que o usuário já tem (ScanForge, em roadmap, fará o scan por fotogrametria) |
| Entrada | MovieClip no Blender (vídeo ou sequência de frames), câmera do Blender; análise prévia (`.precalc`) | Vídeo de qualquer celular ou webcam, processado num Python externo; webcam ao vivo por UDP |
| Densidade de landmarks | Malha densa (~10k vértices) ajustada ao vídeo; detector de rosto próprio para o Auto Align | 478 pontos do MediaPipe Face Landmarker (468 + 10 de íris) e 52 pesos de blendshape do modelo Blendshape V2 |
| Resultado por frame | Vértices da malha (animação de vértices) + pose da cabeça ou da câmera (com distância focal estimada ou rastreada) | 52 pesos ARKit por frame (51 na prática: `tongueOut` não existe no MediaPipe); pose da cabeça ignorada |
| Conversão para blendshapes | Depois: `FacsExecutor` projeta os vértices no modelo FACS e devolve pesos ARKit (`Convert` ou CSV) | Direta: o peso já vem do modelo; sem ajuste à geometria do personagem |
| Correção manual | Pins, keyframes como âncoras, `Refine` entre keyframes e `Refine All`, limpar tracking em intervalos | Nenhuma por frame; só calibração do neutro, `gain`, `smooth` e remapeamento de colunas |
| Estabilização | Painel de suavização (0..1 por parâmetro, aplicado no track/refine), rigidez geral, de piscada e de pescoço, travas de piscada e pescoço, `spring pins back`, `unbreak rotation` | Média móvel exponencial (`smooth`), hold de frames sem rosto, neutro pela média dos 2 s iniciais; BodyForge já tem filtro biquad zero-phase e one-euro |
| Máscaras | 2D (MovieClip ou compositing) e 3D (vertex group) para excluir regiões do tracking | Recorte pela caixa da cabeça do BodyForge (`--crop`) |
| Retarget para personagem estilizado | Por nome de shape key no `Target` (ARKit) ou por ossos Rigify (`rig.py`) | Por nome de shape key em qualquer alvo (preset ARKit 52 / simétrico 34 / lista própria); fit de rig FaceForge ou metarig Rigify a partir dos landmarks |
| Saídas | Ação em shape keys, CSV Live Link Face, ação em ossos Rigify, keyframes de forma por frame, FBX via Blender | CSV genérico (`time` + colunas), F-curves em shape keys, ação ao vivo, FBX/glTF via Blender; relatório de qualidade |
| Preview | Wireframe e pins no viewport, progresso no cabeçalho | Vídeo de preview com landmarks e top 5 shapes; folha de revisão PNG |
| Custo e licença | Pago por produto (assinatura, floating, trial), core fechado com checagem online; add-on Python GPL | Gratuito, GPL-3.0-or-later, 100 % offline, modelos Apache-2.0 baixados pelo usuário |
| Blender | 2.80+ | 4.4 LTS+ |
| Hardware | CPU, offline, tracking demorado com cache | CPU em tempo real (MediaPipe) |

## 4. Ideias que valem trazer (ordem valor/esforço)

Cada uma implementada do nosso jeito, sobre os 478 pontos e os pesos do MediaPipe, ou copiando um padrão GPL do
Python da KeenTools com crédito. Esforço: P (um dia), M (uma semana), G (uma spec inteira).

1. **Pose da cabeça (rotação e translação) junto com os pesos.** Esforço P, valor alto. O Face Landmarker já
   devolve `facial_transformation_matrixes` quando se pede `output_facial_transformation_matrixes=True`; basta
   gravar no CSV (ou no `.npz`) e aplicar num osso `head` ou num Empty. Fecha o limite documentado ("Head and eye
   rotations ... are ignored") e é o que faz a cabeça cinza do vídeo parecer viva. Usar o padrão de `unbreak
   rotation` (Euler contínuo entre frames) do `utils/unbreak.py`, reescrito em numpy.
2. **Frames-âncora com refine entre eles.** Esforço M, valor alto. O que diferencia o FaceTracker na prática é
   poder parar num frame ruim, corrigir e mandar refinar. Nossa versão: o usuário marca um frame, ajusta os
   valores dos shape keys (ou o rig) ali, e o FaceForge interpola a **correção** (delta entre o valor corrigido e
   o rastreado) até os âncoras vizinhos, como o `Refine` entre keyframes. Mais "limpar entre âncoras / para
   frente / para trás", direto das ações GPL do `geotracker_acts.py`. Tudo em F-curves, testável headless.
3. **Suavização por grupo e travas.** Esforço P, valor médio-alto. Trocar a EMA única por filtro zero-phase
   (já existe em `captureforge/body/filters.py`) com corte diferente por grupo: piscada (rápida, quase sem
   filtro), boca, sobrancelhas, cabeça; mais "lock blinking" (zera `eyeBlink*` ou mantém simétrico) e "lock
   neck" (zera a pose da cabeça). É o painel Smoothing e as rigidezes do FaceTracker, sem o solver.
4. **Cache de landmarks por vídeo.** Esforço P, valor médio. Equivalente ao `.precalc`: salvar os 478 pontos, os
   52 pesos e a matriz por frame num `.npz` ao lado do vídeo (o BodyForge já faz isso com `landmarks.npz`), e
   reaplicar `smooth`, `gain` e neutro sem rodar o MediaPipe de novo. Em vídeos longos é a diferença entre
   segundos e minutos por tentativa.
5. **Pesos ajustados à geometria do personagem.** Esforço G, valor alto (é o "Convert" deles, na nossa base). Em vez
   de usar os pesos genéricos do MediaPipe, resolver por mínimos quadrados os pesos dos shape keys ARKit **do
   próprio personagem** que melhor reproduzem os 478 pontos do frame (shape keys projetados na mesma câmera
   frontal do `autofit`, pontos rastreados pelo `map_landmarks` já existente). Com regularização (pesos entre 0 e
   1, penalidade L1) e `tongueOut` excluído. Entrega o que o FaceTracker vende: a expressão "cola" no personagem
   estilizado, não na média humana do modelo. Pré-requisito: shape keys já baked e bons (o inspetor de qualidade
   ajuda).
6. **Progresso e cancelamento no viewport.** Esforço P, valor médio. O `calc_timer.py` é um bom molde GPL de
   timer modal com estados, texto de progresso no cabeçalho ("Tracking 52/55") e Esc para cancelar; o `Video to
   face` hoje roda o subprocesso e espera. Reescrever o padrão (não copiar: ele carrega dependências do core).
7. **Retarget de animação para ossos Rigify.** Esforço M, valor médio. O FaceForge já posiciona o metarig; falta
   animar os ossos a partir dos landmarks. O padrão de `rig.py` (delta do ponto de controle no espaço do osso
   `head`, escala pela distância entre cantos dos olhos, constraints desligadas e compensadas) vale copiar com
   crédito, trocando a tabela de índices da malha deles por índices dos 478 pontos do MediaPipe.
8. **Overlay do resultado sobre o vídeo.** Esforço P, valor baixo-médio. O preview atual desenha só os pontos;
   desenhar também o wireframe do personagem renderizado com os pesos daquele frame (Workbench, mesma câmera do
   `autofit`) dá o "scan dentro do Blender" que impressiona no vídeo, sem nenhum tracking novo.

Fora da lista, de propósito: cabeça por modelo paramétrico com pins (é o FaceBuilder inteiro; o ScanForge vai por
fotogrametria e wrap), máscaras 2D e 3D (pouco ganho com MediaPipe, que já ignora fundo) e painel de sliders 3D
com drivers (Blender já tem o painel de shape keys).

## 5. Riscos

- **Contaminação de licença.** Os arquivos GPL da KeenTools misturam, no mesmo módulo, código puro e chamadas ao
  core. Reaproveitar por padrão (reescrever) é mais seguro que colar trechos; se colar, só de funções sem
  `pkt_module()` e com o cabeçalho de copyright da KeenTools preservado. Nunca abrir o binário `pykeentools`.
- **Dever de atribuição.** GPL §5 exige aviso de modificação e data. Registrar em `THIRD_PARTY_NOTICES.md` e no
  comentário de cada trecho ("padrão de ... KeenTools add-on, GPL-3.0-or-later, adaptado em 2026-..").
- **Marca.** Não nomear recurso com "FaceTracker", "FaceBuilder" ou "KeenTools".
- **Base de comparação fraca.** Um vídeo de 18 s em condições ideais (frontal, luz de estúdio, sem óculos) e
  leitura de código, sem rodar o produto. A qualidade real do tracking deles e os tempos não foram medidos.
- **Limite do MediaPipe.** Os pesos do Blendshape V2 são treinados em rostos humanos e expressões moderadas; em
  caretas fortes ou rostos atípicos eles saturam. A ideia 5 mitiga, mas depende de shape keys bons no alvo
  (ovo e galinha: o personagem precisa estar pronto antes).
- **Escopo.** As ideias 2 e 5 são specs inteiras. Pelo fluxo do projeto, cada uma vira um `[spec]` no Backlog;
  1, 3 e 4 cabem numa spec só de "qualidade do mocap facial". Não abrir todas de uma vez.
- **Privacidade.** Cache de landmarks (ideia 4) guarda dados de um rosto real ao lado do vídeo; documentar que
  é dado pessoal e dar botão de apagar, como já se faz com o `landmarks.npz` do BodyForge.
