# FaceForge

[English](README.md)

FaceForge é uma extensão gratuita do Blender que transforma um rig facial posado em **shape keys ARKit 52**
(ou qualquer lista de nomes sua), prontas para exportar para Unity, Unreal, Godot ou glTF. Também aciona
essas shape keys a partir de um vídeo ou de uma webcam, para testar um rosto sem iPhone.

Licença: GPL-3.0-or-later. Blender 4.4 LTS ou mais novo (desenvolvido no 5.2). Python puro, sem pacotes
extras dentro do Blender.

## Por que isso existe

Estou fazendo meu primeiro jogo com desenvolvimento assistido por IA e modelagem 3D assistida por IA. Em
blendshapes faciais, as ferramentas de que eu precisava eram pagas, só para iPhone, ou os dois. Então fiz
uma, com um parceiro de programação de IA, e estou compartilhando de graça. A criação assistida por IA está
crescendo rápido; quanto mais ferramentas gratuitas se encaixarem nela, melhor para todo mundo que está
aprendendo como eu. Issues, ideias e pull requests são muito bem-vindos.

## Recursos

- **Biblioteca de poses na timeline.** Um marcador por shape (ARKit 52, ARKit simétrico 34, ou seus
  próprios nomes). Posar, `Key pose`, repetir.
- **Bake.** `avaliado(pose) - avaliado(neutro)` por malha (cabeça, olhos, dentes, língua), então shape keys,
  modificadores de deformação e Armature entram exatamente como você vê. Toda malha recebe as mesmas keys.
- **Split Esquerda/Direita** com falloff suave na linha média (sem degrau no nariz, lábios ou queixo).
- **Importação de mocap.** CSV do Live Link Face ou CSV genérico (`time` em segundos mais uma coluna por
  shape).
- **Vídeo para rosto**. Escolha um vídeo, o FaceForge roda o MediaPipe Face Landmarker num Python separado
  e grava o resultado nas suas shape keys. Funciona com qualquer celular (Android incluso), sem iPhone.
- **Webcam ao vivo** *(chega na v1)*. Um processo auxiliar manda os 52 valores por UDP no localhost; o Blender aciona as
  shape keys em tempo real e pode gravar numa action.
- **Inspetor de qualidade.** Relatório por key (keys vazias, delta máximo, erro de simetria esquerda/direita,
  malha dentro de malha, normais invertidas, triângulos esmagados), mapa de calor do delta como atributo de
  cor e relatório em txt/json.
- **Auto rig fit** *(chega na v1)*. Renderiza a cabeça, acha os pontos do rosto com o MediaPipe e posiciona um rig facial
  enxuto (mandíbula, olhos, pálpebras, sobrancelhas, boca, bochechas, língua) com pesos automáticos, ou
  ajusta um metarig facial do Rigify.
- **Review sheet.** Uma grade PNG com o rosto neutro e cada shape, com legenda.
- **Pronto para headless.** Cada recurso é uma função Python que recebe objetos explícitos, então scripts e
  agentes de IA rodam com `blender --background`.

## Instalação

**Por zip**

1. Gere o zip (precisa do Blender; as aspas e o `&` importam no PowerShell):
   ```
   & "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe" --command extension build --source-dir faceforge --output-dir dist
   ```
   Sai `dist/faceforge-<versão>.zip`. Ou pegue o zip na página de releases do GitHub quando houver um.
2. No Blender: `Edit > Preferences > Get Extensions`, menu `v` no canto, `Install from Disk...`, escolha o
   zip.
3. Abra a barra lateral na janela 3D (mouse em cima, tecla `N`), aba `FaceForge`.

**Pelo Get Extensions**: o FaceForge ainda não está em extensions.blender.org. Quando estiver, procure
`FaceForge` em `Edit > Preferences > Get Extensions` e clique em Install.

## Começo rápido

1. **Rig temporário.** Rigue o rosto (Rigify face funciona bem, ou use o auto rig fit). Cabeça, olhos,
   dentes e língua no mesmo rig. A pose de descanso tem de ser um neutro de verdade: olhos abertos, boca
   fechada e relaxada.
2. **Marcadores.** Escolha o preset e clique em `Create markers`: um marcador `neutral` no frame 0 e um por
   shape a partir do frame 1. Isso apaga os marcadores que já existiam na timeline.
3. **Posar.** Pule de marcador em marcador, pose o rig, clique em `Key pose` (armature ativa). Faça o neutro
   primeiro. Cada shape sozinha, a partir do neutro, com amplitude cheia (`eyeBlink` fecha 100 %).
4. **Bake.** Selecione as malhas rigadas, `Make target` (cria uma cópia sem rig `<nome>_FF` e o par
   Source/Target), depois `Bake shape keys`. `Skip empty` descarta keys que não mexem naquela malha.
5. **Split L/R** (preset simétrico): `Split all`. `jawLeft/Right` e `mouthLeft/Right` nunca são divididas.
6. **Teste** com um CSV de mocap (ou um vídeo; a webcam chega na v1; veja abaixo), depois `Render review sheet`
   e o inspetor de qualidade.
7. Exporte o alvo em FBX ou glTF com shape keys (e normais de blendshape se a engine pedir).

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

A importação de CSV e o **Video to face** funcionam hoje; a **Live webcam** *chega na v1*.

O FaceForge lê um CSV genérico: uma coluna `time` em segundos e uma coluna por shape ARKit, com a mesma
grafia das shape keys (`eyeBlinkLeft`, ...). Os nomes casam sem diferenciar maiúsculas e há um mapa de
renomeação `coluna=key`.

**A partir de um vídeo** (gravação de celular, gravação do Iriun Webcam, qualquer coisa que o OpenCV abra):

1. Crie um ambiente Python com MediaPipe e OpenCV (qualquer versão de Python que o MediaPipe suporte):
   ```
   python -m venv .venv
   .venv/Scripts/python -m pip install -r requirements-mocap.txt      # Linux/macOS: .venv/bin/python
   ```
2. Baixe o modelo MediaPipe Face Landmarker (uns 3,6 MB) do armazenamento de modelos do Google:
   `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task`
3. Em `Edit > Preferences > Add-ons > FaceForge`, defina o **Python** (o python do venv) e o **arquivo do
   modelo**. A seção `Video to face` do painel tem um botão `Setup instructions` que repete esses passos.
4. Escolha o vídeo no painel e clique em `Video to face`.

Dicas de gravação: luz frontal e difusa; rosto ocupando uns 50 % do quadro; sem óculos; comece com 2 s de
rosto neutro parado (vira o zero de cada canal), depois segure cada expressão por 2 s. O Iriun Webcam
transforma um Android (ou iPhone) em webcam, o que também serve para o modo ao vivo.

O MediaPipe não produz `tongueOut`, então 51 das 52 shapes são acionadas.

**Webcam ao vivo** *(chega na v1)*: defina o mesmo Python e modelo nas preferências, clique em `Start` e as shape keys
seguem o seu rosto. `Record` grava o que chega numa action. `Stop` encerra o auxiliar.

Também dá para rodar o script auxiliar na mão:
`python faceforge/helpers/video_to_csv.py video.mp4 -o out.csv --model face_landmarker.task`.

## Headless, linha de comando e agentes de IA

Os módulos de núcleo (`bake`, `markers`, `split`, `mocap`, `sheet`, `video`, `quality`; `autofit` e `live` chegam na v1)
recebem objetos explícitos e não dependem do contexto da interface, então rodam no Blender em segundo plano:

```python
# blender --background rig.blend --python bake_it.py
import sys
sys.path.insert(0, "/caminho/para/faceforge")     # a raiz do repositório
from faceforge import bake, markers, split, presets
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
```

O primeiro monta uma cabeça procedural (esfera, armature, olhos, dentes) e imprime
`FaceForge tests: N passed, M failed`, saindo com código diferente de 0 em falha. O GitHub Actions roda o
mesmo a cada push. Defina `FACEFORGE_PYTHON` (um python com mediapipe e opencv) e `FACEFORGE_MODEL` (o arquivo
`.task`) para rodar também o teste do auxiliar MediaPipe de verdade; também valem para o `Video to face` quando
as preferências do add-on estão vazias. Valide o manifesto com `blender --command extension validate faceforge`.

## Limites conhecidos

- Source e Target precisam da mesma contagem e ordem de vértices (Target é duplicata da malha base).
  Modificadores que mudam topologia (Subsurf, Mirror, Solidify, Geometry Nodes, ...) são desligados durante
  o bake e religados no fim.
- O split assume a linha média em X = 0 do objeto.
- Rotações de cabeça e olhos do Live Link Face são ignoradas por enquanto.
- O review sheet é um render Workbench: serve para conferir forma, não para apresentação.

## Roadmap

- Presets de pose inicial para o rig gerado (ex.: `jawOpen` = rotação da mandíbula), para você só ajustar o
  estilo.
- Shapes corretivas para combinações (`jawOpen + mouthSmile`), baked a partir da pose combinada.
- Checker de export: os 52 nomes exatos em toda malha, ordem, normais de blendshape, keys não zeradas.
- Rotação de cabeça e olhos do mocap para ossos; streaming UDP do Live Link Face.
- Listas de nomes carregáveis (Audio2Face e outras).
- Publicação em extensions.blender.org.

Ideias da v1.1:

- Pose a partir de imagem de referência: resolver o rig para o MediaPipe enxergar a mesma expressão de uma
  foto ou de uma imagem de IA.
- Mapas automáticos de rugas e tensão por shape.
- Transferência de expressões entre personagens.

### A família Forge

Dois projetos irmãos futuros, no mesmo espírito (gratuitos, Blender, amigáveis a IA):

- **BodyForge**: mocap corporal sem marcadores a partir de 1 a 3 vídeos de celular (MediaPipe Pose,
  triangulação de várias câmeras, trava de pés, retarget para um humanoide).
- **ScanForge**: scan de rosto e corpo a partir de um vídeo 360 graus (escolha de quadros nítidos, COLMAP ou
  Meshroom como ferramentas externas, wrap numa topologia limpa e animável, depois FaceForge).

## Uso responsável

Não escaneie, recrie nem anime uma pessoa real, incluindo celebridades, sem o consentimento explícito dela, e
siga as leis locais de imagem e privacidade. O mantenedor não se responsabiliza por mau uso. É uma forte
recomendação e um aviso, não um termo de licença. Leia o [POLICY.md](POLICY.md) (em inglês).

## Créditos e clean room

O FaceForge foi escrito do zero a partir de documentação pública e da API do Blender: a lista de blendshapes
ARKit da Apple, o MediaPipe Face Landmarker do Google, o formato de CSV do Live Link Face como visto em
importadores abertos e o manual do Blender. Nenhum add-on pago foi baixado, descompilado ou copiado. As
notas de pesquisa (em português) estão em [`docs/pt-BR`](docs/pt-BR/RESEARCH.md); o design está em
[`docs/pt-BR/DESIGN.md`](docs/pt-BR/DESIGN.md).

Mantenedor: H0wZy. Veja [CONTRIBUTING.md](CONTRIBUTING.md).
