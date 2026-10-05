# CaptureForge

[English](README.md) | [howzysolutions.com](https://howzysolutions.com)

CaptureForge é uma extensão gratuita do Blender para animação guiada por captura, feita como uma suíte de
módulos que compartilham uma aba na barra lateral (`CaptureForge`):

| Módulo | O que faz | Situação |
|---|---|---|
| **FaceForge** | Transforma um rig facial posado em **shape keys ARKit 52** (ou sua lista) e aciona essas keys a partir de um vídeo ou webcam, sem iPhone. | disponível |
| **BodyForge** | **Mocap corporal sem marcadores a partir de um vídeo de celular**: limpeza, trava de pés, relatório e exportação de FBX Humanoid para o Unity. | disponível (0.2) |
| **ScanForge** | Scan de rosto e corpo a partir de um vídeo 360 graus. | roadmap |

Licença: GPL-3.0-or-later. Blender 4.4 LTS ou mais novo (desenvolvido no 5.2). Python puro, sem pacotes
extras dentro do Blender. As seções do FaceForge vêm primeiro; o
[BodyForge](#bodyforge-mocap-corporal-a-partir-de-um-vídeo-de-celular) tem a sua própria seção.

## Por que isso existe

Estou fazendo meu primeiro jogo com desenvolvimento assistido por IA e modelagem 3D assistida por IA. Em
blendshapes faciais, as ferramentas de que eu precisava eram pagas, só para iPhone, ou os dois. Então fiz
uma, com um parceiro de programação de IA, e estou compartilhando de graça. A criação assistida por IA está
crescendo rápido; quanto mais ferramentas gratuitas se encaixarem nela, melhor para todo mundo que está
aprendendo como eu. Issues, ideias e pull requests são muito bem-vindos.

## Recursos do FaceForge

- **Biblioteca de poses na timeline.** Um marcador por shape (ARKit 52, ARKit simétrico 34, ou seus
  próprios nomes). Posar, `Key pose`, repetir.
- **Bake.** `avaliado(pose) - avaliado(neutro)` por malha (cabeça, olhos, dentes, língua), então shape keys,
  modificadores de deformação e Armature entram exatamente como você vê. Toda malha recebe as mesmas keys.
- **Split Esquerda/Direita** com falloff suave na linha média (sem degrau no nariz, lábios ou queixo).
- **Importação de mocap.** CSV do Live Link Face ou CSV genérico (`time` em segundos mais uma coluna por
  shape).
- **Pose da cabeça.** O `Video to face` também grava a rotação da cabeça, e a importação aplica no seu osso de
  cabeça (padrão `Head`, com parte opcional para o pescoço, ganho e liga/desliga).
- **Vídeo para rosto**. Escolha um vídeo, o FaceForge roda o MediaPipe Face Landmarker num Python separado
  e grava o resultado nas suas shape keys. Funciona com qualquer celular (Android incluso), sem iPhone.
- **Webcam ao vivo.** Um processo auxiliar manda os 52 valores por UDP no localhost; o Blender aciona as
  shape keys em tempo real e pode gravar numa action.
- **Inspetor de qualidade.** Relatório por key (keys vazias, delta máximo, erro de simetria esquerda/direita,
  malha dentro de malha, normais invertidas, triângulos esmagados), mapa de calor do delta como atributo de
  cor e relatório em txt/json.
- **Auto rig fit.** Renderiza a cabeça, acha os pontos do rosto com o MediaPipe e posiciona um rig facial
  enxuto (mandíbula, olhos, pálpebras, sobrancelhas, boca, bochechas, língua) com pesos automáticos, ou
  ajusta um metarig facial do Rigify.
- **Review sheet.** Uma grade PNG com o rosto neutro e cada shape, com legenda.
- **Pronto para headless.** Cada recurso é uma função Python que recebe objetos explícitos, então scripts e
  agentes de IA rodam com `blender --background`.

## Instalação

**Por zip**

1. Gere o zip (precisa do Blender; as aspas e o `&` importam no PowerShell):
   ```
   & "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --command extension build --source-dir captureforge --output-dir dist
   ```
   Sai `dist/captureforge-<versão>.zip`. Ou pegue o zip na página de releases do GitHub quando houver um.
2. No Blender: `Edit > Preferences > Get Extensions`, menu `v` no canto, `Install from Disk...`, escolha o
   zip.
3. Abra a barra lateral na janela 3D (mouse em cima, tecla `N`), aba `CaptureForge`, painel `FaceForge`.

**Pelo Get Extensions**: o CaptureForge ainda não está em extensions.blender.org. Quando estiver, procure
`CaptureForge` em `Edit > Preferences > Get Extensions` e clique em Install.

## Começo rápido

1. **Rig temporário.** Rigue o rosto (Rigify face funciona bem, ou deixe o `Auto rig from face` montar um, veja abaixo). Cabeça, olhos,
   dentes e língua no mesmo rig. A pose de descanso tem de ser um neutro de verdade: olhos abertos, boca
   fechada e relaxada.
2. **Marcadores.** Escolha o preset e clique em `Create markers`: um marcador `neutral` no frame 0 e um por
   shape a partir do frame 1. Isso apaga os marcadores que já existiam na timeline.
3. **Posar.** Pule de marcador em marcador, pose o rig, clique em `Key pose` (armature ativa). Faça o neutro
   primeiro. Cada shape sozinha, a partir do neutro, com amplitude cheia (`eyeBlink` fecha 100 %).
4. **Bake.** Selecione as malhas rigadas, `Make target` (cria uma cópia sem rig `<nome>_FF` e o par
   Source/Target), depois `Bake shape keys`. `Skip empty` descarta keys que não mexem naquela malha.
5. **Split L/R** (preset simétrico): `Split all`. `jawLeft/Right` e `mouthLeft/Right` nunca são divididas.
6. **Teste** com um CSV de mocap (ou um vídeo, ou a webcam ao vivo; veja abaixo), depois `Render review sheet`
   e o inspetor de qualidade.
7. Exporte o alvo em FBX ou glTF com shape keys (e normais de blendshape se a engine pedir).

## Auto rig fit

Rigar o rosto é a etapa mais lenta, então o FaceForge pode fazer uma primeira passada (seção 0 do painel).

1. Deixe a **cabeça** como malha ativa e selecione também as outras malhas do rosto (globos oculares, dentes,
   língua e peças de nariz ou sobrancelha que sejam objetos separados).
2. Defina o **Python** e o **Model** nas preferências do add-on (os mesmos do `Video to face`).
3. Escolha o rig e clique em `Auto rig from face`. O FaceForge renderiza as malhas selecionadas de frente
   (ortográfica, Workbench), pede ao MediaPipe Face Landmarker os 478 pontos do rosto, projeta os pontos na
   malha com um raio ao longo de +Y e monta o rig a partir deles.

**Rig FaceForge** (26 ossos): `head`, `jaw`, e por lado `eye`, `lid` superior e inferior, três `brow`,
`mouth.corner`, `cheek` e três ossos de lábio (`lip.T`/`lip.B` mais `.L`/`.R`), os centrais `lip.T`/`lip.B`, e
`tongue` com `tongue.tip`. Os nomes seguem o Rigify (`.L` é a esquerda do personagem, +X). A malha da cabeça
recebe pesos automáticos calculados por distância: queda ao redor da âncora de cada osso (pálpebras,
sobrancelhas, lábios, cantos, bochechas), a mandíbula pega tudo abaixo da linha dos lábios e à frente da
articulação, e `head` fica com o resto, então cada vértice soma 1. Os pesos por bone heat do Blender não são
usados: falham em pálpebras e lábios e precisam de contexto de interface. Malhas extras são presas de forma
rígida: globos oculares ao osso do olho mais próximo, uma malha chamada `tongue` ao osso `tongue`, o que estiver
abaixo da linha dos lábios ao `jaw`, o resto ao `head`. Os ossos dos olhos ficam nos globos quando eles existem.

**Metarig do Rigify**: escolha `Rigify metarig` (precisa do add-on Rigify ligado) e o FaceForge adiciona o
metarig facial de exemplo do Rigify escalado e posicionado nos olhos e no queixo. Ajuste e gere com o Rigify
como de costume.

Limites: o personagem precisa olhar para -Y com a esquerda em +X, vista frontal clara com olhos e boca
visíveis e proporções parecidas com humanas. Se o MediaPipe não achar rosto, vem um erro claro; cabeças
estilizadas às vezes precisam de olhos e lábios modelados para serem reconhecidas. O resultado é um ponto de
partida: confira os ossos e depois pose cada shape.

## Inspetor de qualidade

Selecione os alvos e clique em `Inspect keys` (seção 5 do painel). Para cada shape key ele informa:

- **keys vazias** e o **delta máximo** (maior deslocamento de vértice, em unidades do objeto);
- **erro de simetria esquerda/direita**: cada key `...Left` espelhada contra a sua par `...Right` (e `.L`/`.R`);
- **malha dentro de malha**: escolha uma malha **Collider** fechada (globo ocular, dentes) e, se quiser, um
  **Group** de vértices da malha inspecionada (pálpebras, lábios); vértices que a key empurra para dentro do
  collider são contados, com o mais fundo;
- **normais invertidas** e **triângulos esmagados** (área abaixo de 10 % da neutra).

Os problemas aparecem no painel e vão para o **Report file** (`.txt` ou `.json`). `Delta heatmap` pinta o delta
da shape key ativa num atributo de cor (azul = parado, vermelho = mais movido; Solid, Color: Attribute).

## Mocap facial sem iPhone

A importação de CSV, o **Video to face** e a **Live webcam** funcionam hoje.

O FaceForge lê um CSV genérico: uma coluna `time` em segundos e uma coluna por shape ARKit, com a mesma
grafia das shape keys (`eyeBlinkLeft`, ...). Os nomes casam sem diferenciar maiúsculas e há um mapa de
renomeação `coluna=key`.

**Pose da cabeça.** O helper de vídeo também grava seis colunas opcionais depois dos shapes (`--no-head-pose` tira):

| Coluna | Unidade | Significado |
|---|---|---|
| `headRotX`, `headRotY`, `headRotZ` | radianos | pitch, yaw, roll da cabeça em relação à pose neutra (zero = a cabeça dos segundos neutros) |
| `headPosX`, `headPosY`, `headPosZ` | centímetros | posição da cabeça em relação à neutra (escala do MediaPipe: aproximada) |

O referencial da cabeça é X = esquerda da pessoa, Y para cima, Z para fora do rosto, e os ângulos seguem a ordem
`Ry * Rx * Rz` (yaw, depois pitch, depois roll; Euler `ZXY` do Blender). Yaw positivo vira para a esquerda da
pessoa, pitch positivo olha para baixo, roll positivo leva o lado esquerdo para cima. Os ângulos vêm da matriz de
transformação facial do MediaPipe, ficam contínuos entre os quadros (sem saltos de 360 graus) e recebem o mesmo
`Smooth` e a mesma calibração do neutro dos shapes; quadros sem rosto repetem a última pose. O `Gain` não escala
esses ângulos: use o `Head gain` na importação.

Na importação (`4. Mocap CSV`), `Head pose` aplica a rotação no osso `Head` (qualquer caixa) do rig escolhido em
`Rig`; vazio, usa a armature dos alvos, senão a única armature da cena que tem o osso. `Neck share` (0,3 = 30 %)
dá essa parte da rotação ao osso `Neck` e o osso da cabeça fica com o resto, então as duas somam. `Head gain`
multiplica os ângulos (0,5 para um personagem sutil). `Translation` também move o osso da cabeça, com `Scale`
unidades de cena por centímetro (0,01 = metros); precisa de um osso de cabeça sem Connected, e o movimento é o do
rosto, não o do pescoço. As keys seguem o modo de rotação do osso (Quaternion ou Euler) e vão para a action atual do
rig (uma `<rig>_headmocap` nova se ele não tiver nenhuma); os outros canais da action ficam intactos. Supõe-se o rig
na orientação padrão do Blender (o personagem olha para -Y, +Z para cima); o roll dos ossos não importa. Um CSV sem
essas colunas (arquivos antigos, Live Link Face) importa como antes. Desmarcar `Head pose` pula tudo isso.

**A partir de um vídeo** (gravação de celular, gravação do Iriun Webcam, qualquer coisa que o OpenCV abra):

1. Crie um ambiente Python com MediaPipe e OpenCV (qualquer versão de Python que o MediaPipe suporte):
   ```
   python -m venv .venv
   .venv/Scripts/python -m pip install -r requirements-mocap.txt      # Linux/macOS: .venv/bin/python
   ```
2. Baixe o modelo MediaPipe Face Landmarker (uns 3,6 MB) do armazenamento de modelos do Google:
   `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task`
3. Em `Edit > Preferences > Add-ons > CaptureForge`, defina o **Python** (o python do venv) e o **arquivo do
   modelo**. A seção `Video to face` do painel tem um botão `Setup instructions` que repete esses passos.
4. Escolha o vídeo no painel e clique em `Video to face`.

Dicas de gravação: luz frontal e difusa; rosto ocupando uns 50 % do quadro; sem óculos; comece com 2 s de
rosto neutro parado (vira o zero de cada canal), depois segure cada expressão por 2 s. O Iriun Webcam
transforma um Android (ou iPhone) em webcam, o que também serve para o modo ao vivo.

O MediaPipe não produz `tongueOut`, então 51 das 52 shapes são acionadas.

**Webcam ao vivo** (seção 4c do painel): defina o mesmo Python e modelo nas preferências, clique em `Start`, fique
com o rosto neutro e parado por 2 segundos (calibra) e as shape keys dos alvos seguem o seu rosto. `Record` grava o
que chega numa action `<objeto>_livemocap` (pode ligar no meio da captura e começa no frame atual). `Stop` encerra o
auxiliar. `Camera` é o índice da webcam (o Iriun aparece como uma); `Smooth`, `Neutral s` e `Gain` são os mesmos do
`Video to face`. Com `Start helper` desligado, só escuta: qualquer coisa que mande o pacote abaixo para
`127.0.0.1:<porta>` aciona o rig.

O pacote é um datagrama UDP de JSON, uns 30 por segundo: `{"t": segundos, "state": "calibrating" | "live" |
"noface", "v": [52 floats na ordem ARKit]}`, ou `"s": {"jawOpen": 0.3, ...}` no lugar de `"v"` para nomear só
algumas shapes. Datagramas inválidos são ignorados; com `noface` a última pose é mantida. Rode o emissor na mão com
`python captureforge/face/helpers/webcam_stream.py --model face_landmarker.task --source 0 --port 9876`
(`--source` também aceita um arquivo de vídeo, com `--loop`).

Também dá para rodar o script auxiliar na mão:
`python captureforge/face/helpers/video_to_csv.py video.mp4 -o out.csv --model face_landmarker.task`.

## BodyForge: mocap corporal a partir de um vídeo de celular

O BodyForge transforma um vídeo comum de celular (qualquer Android ou webcam, sem iPhone, sensor de profundidade ou
LiDAR) numa animação em um armature **Humanoid Mixamo/Unity**, limpa o resultado e exporta um FBX que o Unity lê como
clipe Humanoid. Ele adiciona um painel `BodyForge` na mesma aba `CaptureForge`.

1. **Helper (uma vez).** Preferências > Add-ons > CaptureForge > **Install helper**. Ele mostra o que vai fazer (um
   ambiente Python com `mediapipe` e `opencv-python`, e o modelo de pose do MediaPipe, uns 31 MB, Apache-2.0, do
   armazenamento do Google) e pergunta antes de baixar qualquer coisa. O mesmo ambiente serve ao FaceForge. Sem o helper
   o add-on continua funcionando e mostra os passos de instalação.
2. **Rig.** Escolha seu armature estilo Mixamo (nomes com ou sem `mixamorig:`), ou **Create reference armature**.
3. **Filme.** Siga o [guia de gravação](docs/pt-BR/BODYFORGE-RECORDING.md) (celular fixo, 30 fps ou mais, da cabeça aos
   pés no quadro, 1,5 a 2 s parado no começo). O BodyForge avisa de taxa de quadros baixa, corpo fora do quadro, pouca
   confiança e várias pessoas.
4. **Video to body.** Esc cancela durante o rastreio. **Hands and fingers** (precisa do modelo de mãos) adiciona a curva
   dos dedos e o giro do antebraço guiado pela palma; **Video to body and face** também anima o rosto do mesmo vídeo com
   o FaceForge.
5. **Clean up.** Suavização de fase zero (ou um filtro causal de prévia), detecção de contato e **trava de pés**, depois
   **In place**, **Trim**, **Close loop**, **Mirror**. Tudo recomeça do clipe bruto guardado na action.
6. **Report.** Deslize do pé (cm/s), deriva do comprimento dos ossos, violações de limite das juntas, tremor e trechos
   fracos, em texto, `report.json` e um `filmstrip.png` para revisão, gravados ao lado do vídeo.
7. **Export for Unity.** Um FBX com o preset documentado (repouso em T-pose, sem leaf bones, Y para cima, baked, só ossos
   de deformação); ele recusa, listando os ossos que faltam ou sobram, quando o armature não bate. No Unity: Animation
   Type Humanoid, Avatar = o avatar do personagem.

Os passos puros (leitor de pontos, solver, filtros, trava de pés, relatório) são funções numpy que recebem dados
explícitos, então scripts e agentes chamam sem o Blender. Limites: uma pessoa, uma câmera fixa, quase tudo no lugar;
profundidade é o ponto fraco de uma câmera só; a trava de pés é uma heurística que precisa ficar desligada em pulos e
poses sentadas; dedos são só curvatura e giro. Licenças e checksums dos modelos estão em
[`docs/BODYFORGE-MODELS.md`](docs/BODYFORGE-MODELS.md). Os modelos MediaPipe são Apache-2.0, só são baixados depois da sua
confirmação e nunca vão empacotados no CaptureForge; o resultado (pontos, animação em shape keys e ossos) é seu. Não filme nem anime uma pessoa real sem o consentimento dela
([POLICY.md](POLICY.md)).

## Headless, linha de comando e agentes de IA

Os módulos de núcleo (`bake`, `markers`, `split`, `mocap`, `sheet`, `video`, `quality`, `autofit`, `live`)
recebem objetos explícitos e não dependem do contexto da interface, então rodam no Blender em segundo plano:

```python
# blender --background rig.blend --python bake_it.py
import sys
sys.path.insert(0, "/caminho/para/repo-captureforge")  # a raiz do repositório
from captureforge.face import bake, markers, split, presets
import bpy

scene = bpy.context.scene
markers.create_markers(scene, presets.ARKIT_SYMMETRIC)
# ... keyar as poses (markers.key_pose(armature, frame) para cada marcador) ...
head = bpy.data.objects["Head"]
head_target = bake.make_target(head)
bake.bake_shapes(scene, [(head, head_target)], markers.frames_from_markers(scene), neutral_frame=0)
split.split_all(head_target)
```

`video.run(python, model, caminho_do_video, csv_saida)` roda o MediaPipe e grava o CSV; `mocap.import_csv(scene, targets, caminho_csv)` aplica nas keys.

`quality.inspect(alvo, depsgraph, collider=globo_ocular)` devolve o relatório por key como dict, `quality.write_report(relatorio, "report.json")` salva.

A suíte de testes é o melhor conjunto de exemplos: `tests/run_tests.py`.

## Testes

Headless, um processo do Blender:

```
timeout 300 "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --background --factory-startup --python tests/run_tests.py
python tests/test_video_to_csv.py
python tests/test_webcam_stream.py
# BodyForge: testes numpy puros, depois o lado Blender
for t in landmarks quat solve helper cleanup; do python tests/test_body_$t.py; done
timeout 600 "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --background --factory-startup --python tests/run_body_tests.py
```

O teste com MediaPipe de verdade do BodyForge renderiza um vídeo sintético de manequim e roda tudo de ponta a ponta;
ele é pulado a menos que `BODYFORGE_PYTHON` (o python do venv do helper) e `BODYFORGE_POSE_MODEL` (um arquivo `.task` de
pose) estejam definidos.

O primeiro monta uma cabeça procedural (esfera, armature, olhos, dentes) e imprime
`FaceForge tests: N passed, M failed`, saindo com código diferente de 0 em falha. O GitHub Actions roda o
mesmo a cada push. Defina `FACEFORGE_PYTHON` (um python com mediapipe e opencv) e `FACEFORGE_MODEL` (o arquivo
`.task`) para rodar também os testes dos auxiliares MediaPipe de verdade (vídeo, auto rig num rosto de teste, stream ao vivo); sem eles esses testes imprimem `skipped` e passam; também valem para o `Video to face` quando
as preferências do add-on estão vazias. Valide o manifesto com `blender --command extension validate captureforge`.

## Limites conhecidos

- Source e Target precisam da mesma contagem e ordem de vértices (Target é duplicata da malha base).
  Modificadores que mudam topologia (Subsurf, Mirror, Solidify, Geometry Nodes, ...) são desligados durante
  o bake e religados no fim.
- O split assume a linha média em X = 0 do objeto.
- Rotações de cabeça e olhos do Live Link Face são ignoradas por enquanto; a rotação da cabeça vem só do `Video to face`.
- O timer da captura ao vivo (o botão `Start`) é um operador modal e é testado na mão; o caminho de
  recepção, a leitura dos pacotes, a gravação e o tratamento do auxiliar são cobertos pelos testes headless.
- O review sheet é um render Workbench: serve para conferir forma, não para apresentação.

## Roadmap

- Presets de pose inicial para o rig gerado (ex.: `jawOpen` = rotação da mandíbula), para você só ajustar o
  estilo.
- Shapes corretivas para combinações (`jawOpen + mouthSmile`), baked a partir da pose combinada.
- Checker de export: os 52 nomes exatos em toda malha, ordem, normais de blendshape, keys não zeradas.
- Rotação dos olhos do mocap para ossos; streaming UDP do Live Link Face.
- Listas de nomes carregáveis (Audio2Face e outras).
- Publicação em extensions.blender.org.

Ideias da v1.1:

- Pose a partir de imagem de referência: resolver o rig para o MediaPipe enxergar a mesma expressão de uma
  foto ou de uma imagem de IA.
- Mapas automáticos de rugas e tensão por shape.
- Transferência de expressões entre personagens.

### A família Forge

Módulos irmãos do CaptureForge, no mesmo espírito (gratuitos, Blender, amigáveis a IA):

- **BodyForge** (disponível, veja acima). Próximas ideias: mais estimadores (RTMW), outros rigs e retarget, 1 a 3 câmeras.
- **ScanForge**: scan de rosto e corpo a partir de um vídeo 360 graus (escolha de quadros nítidos, COLMAP ou
  Meshroom como ferramentas externas, wrap numa topologia limpa e animável, depois FaceForge).

## Uso responsável

Não escaneie, recrie nem anime uma pessoa real, incluindo celebridades, sem o consentimento explícito dela, e
siga as leis locais de imagem e privacidade. O mantenedor não se responsabiliza por mau uso. É uma forte
recomendação e um aviso, não um termo de licença. Leia o [POLICY.md](POLICY.md) (em inglês).

## Créditos e clean room

O CaptureForge foi escrito do zero a partir de documentação pública e da API do Blender: a lista de blendshapes
ARKit da Apple, o MediaPipe Face Landmarker do Google, o formato de CSV do Live Link Face como visto em
importadores abertos e o manual do Blender. Nenhum add-on pago foi baixado, descompilado ou copiado. As
notas de pesquisa (em português) estão em [`docs/pt-BR`](docs/pt-BR/RESEARCH.md); o design está em
[`docs/pt-BR/DESIGN.md`](docs/pt-BR/DESIGN.md).

Mantenedor: H0wZy. Veja [CONTRIBUTING.md](CONTRIBUTING.md).
