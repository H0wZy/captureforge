# FaceForge — pesquisa (fase 1)

Levantamento público de como ferramentas e estúdios geram blendshapes faciais, para desenhar a nossa
própria extensão do Blender 5.2 (ver `DESIGN.md`). **Clean room:** nenhum add-on pago foi baixado,
descompilado ou copiado. Tudo aqui vem de páginas de produto, documentação, repositórios abertos e da
documentação oficial da Apple e do Blender. Links na seção 6.

## 1. O que cada ferramenta faz e como

### FaceFlex (Gonreel, pago)
- Filosofia declarada: "50 % manual, 50 % automático". O argumento de venda é que soluções de um clique
  falham em personagens estilizados ou não humanoides; o artista mantém o controle da forma.
- Fluxo: (1) rigar o rosto temporariamente (posar é mais rápido que esculpir); (2) seguir um PDF de
  referência com as poses padrão; (3) em Pose Mode, uma expressão por frame, keyframes na ordem do
  preset; espelhar poses com Ctrl+C / Ctrl+Shift+V para ganhar tempo nas simétricas; (4) duplicar a malha
  e remover o modificador Armature da cópia (alvo); (5) escolher Source (rigada) e Target (cópia) por
  conta-gotas, escolher o preset e converter: cada frame posado vira uma shape key com nome correto.
- Presets: **ARKit (61)** — 52 shapes da Apple + 9 colunas de rotação de cabeça/olhos do Live Link Face —
  e **Wonder Studio (90)**.
- "Link Animation": lista de malhas-alvo, carrega `.csv` do app Live Link Face, converte FPS
  automaticamente (independe de FPS de gravação e da cena) e aplica nas shape keys. Botões "Animate"
  (testar) e "Reset" (zerar keys). Permite esculpir detalhe por cima do resultado.
- Não publica a lista de nomes nem detalhes de implementação.

### ARKit Blendshape Helper (elijah-atkins, GitHub, código aberto)
- Mesmo padrão: rig temporário (Rigify ou Auto-Rig Pro), pose neutra (Basis) no frame 0, as 52 poses
  ARKit nos frames 1–52, duplicar o personagem, apontar Source/Target no painel, botão único gera as
  shape keys no alvo.
- Confirma que "frame N = shape N" e a dupla Source/Target é o padrão da comunidade. Lista as 52 shapes
  por região (14 olhos, 4 mandíbula, 24 boca, 5 sobrancelhas, 5 bochechas/nariz, 1 língua).

### FaceIt (pago)
- Semi-automático e não destrutivo: o artista posiciona **landmarks** no rosto, o add-on gera um rig
  ajustado à topologia/morfologia e **expressões procedurais** (presets ARKit, Audio2Face, língua,
  fonemas, ou presets próprios); depois faz o bake da deformação (modifier stack + pose + escultura) para
  shape keys finais. Inclui importação de mocap e retarget.
- Insight: a parte mais cara do fluxo "rig temporário" é construir o rig; landmarks + rig gerado é o
  caminho para automatizar isso (nossa fase 3).

### Pose Shape Keys (Blender Studio, Demeter Dzadik, extensão gratuita)
- Ferramenta de correctives: grava a pose do rig e calcula o **delta da shape key relativo à malha já
  deformada** pelos ossos, não à Basis crua. Assim a corretiva não "briga" com a deformação óssea.
  Drivers (com CloudRig) ligam a key à pose.
- Insight direto para nós: o bake deve usar `delta = avaliado(pose) − avaliado(neutro)`, com o depsgraph
  resolvendo armature, outros modificadores de deformação e shape keys já ligadas.

### Bake Shape Keys (extensions.blender.org, gratuito)
- Duplicar, fundir e **dividir** shape keys; bake de actions de shape key com interpolação, step e FPS
  corretos. Mostra que split e bake de animação de keys são operações rotineiras e esperadas.

### Blender LiveLinkFace Add-On (blender-addons.org) e ARKit CSV Animation Importer (gumroad)
- Importam CSV gravado pelo app Live Link Face para qualquer malha com shape keys de mesmo nome; a
  versão paga do primeiro faz streaming ao vivo pela rede e aciona pescoço por `HeadYaw/Pitch/Roll`.
- Insight: casar colunas por nome (case-insensitive) é suficiente; alertar que o FPS da cena importa.

### Rigify face (embutido no Blender, `rigs/face/skin_jaw.py`, `skin_eye.py`, `basic_tongue.py`)
- Rig facial por "skin chains": `jaw_master`, controles de boca, pálpebras, sobrancelhas, olhos e
  língua, com widgets. Convenção `.L` em +X com personagem olhando para −Y.
- É o rig temporário recomendado: gratuito, embutido, e a convenção de lado bate com o `Left` do ARKit.

### NVIDIA Audio2Face
- Gera animação nas 52 shapes ARKit a partir de áudio (A2F-3D, microserviço e samples abertos no
  GitHub). O "blendshape transfer" projeta as shapes de uma cabeça-modelo numa malha custom usando
  pontos de correspondência ajustáveis.
- Insight: ARKit 52 é a lingua franca (MetaHuman, Unity, A2F). Transferência por correspondência é um
  caminho alternativo ao rig para gerar shapes (fase 3, "reference-driven").

## 2. O que faz uma expressão estilizada ficar boa

- **Híbrido osso + shape key.** Osso para o grosso e o que gira (mandíbula, olhos, pescoço); shape key
  para o que osso não faz bem (bochecha, lábio enrolando, nariz franzindo, pálpebra deslizando sobre o
  olho). O ARKit espera 52 shapes; para Unity é mais simples entregar tudo como shape key e deixar o
  osso do maxilar só no rig de corpo.
- **Correctives / combinações.** `jawOpen + mouthSmileLeft` costuma rasgar o canto da boca;
  `mouthFunnel + mouthPucker` se sobrepõem. Solução clássica: shape corretiva disparada pelo produto dos
  pesos (`a*b`), baked como `pose_combinada − (neutro + Σ shapes isoladas)`.
- **Split L/R.** Posar simétrico e dividir pela linha média é ~2× mais rápido e garante lados iguais. O
  falloff precisa ser **suave** (smoothstep em alguns centímetros ao redor de X=0) para não criar degrau
  no nariz, lábios e queixo. Shapes que são *direção* e não *lado* (`jawLeft/Right`, `mouthLeft/Right`)
  não se dividem.
- **Neutro de verdade.** Olhos abertos, boca fechada e relaxada, sobrancelha natural. Qualquer desvio
  vira offset em todas as 52.
- **Amplitude exagerada no estilizado.** O rastreamento do iPhone raramente passa de 0,7 na maioria das
  shapes; shape tímida vira rosto morto no jogo. Nos olhos, `eyeBlink` tem de fechar 100 % na pose.
- **Isolamento.** Cada shape posada sozinha a partir do neutro (o Live Link Face soma pesos
  independentes). `mouthClose` é "lábios fechados com mandíbula aberta": posar com `jawOpen` ativo e
  depois subtrair, ou documentar que ela é relativa ao `jawOpen` (como a Apple descreve).
- **Olhos e dentes separados.** Globo ocular, dentes e língua são malhas próprias no mesmo rig; o bake
  precisa gerar as keys em cada malha com os mesmos nomes (eyeLook* nos olhos, tongueOut na língua).
- **Normais.** Shape keys em malha low-poly estilizada mudam a sombra; Unity importa normais de
  blendshape do FBX (opção "Normals" no export de shape keys do Blender) — checar no export.

## 3. Lista ARKit (52) com definições

Fonte: Apple, `ARFaceAnchor.BlendShapeLocation` (valores 0–1). Lado = lado do próprio personagem.

| Nome | Definição |
|---|---|
| eyeBlinkLeft / eyeBlinkRight | fechamento da pálpebra do olho esquerdo / direito |
| eyeLookDownLeft / Right | olhar para baixo |
| eyeLookInLeft / Right | olhar para dentro (em direção ao nariz) |
| eyeLookOutLeft / Right | olhar para fora (em direção à orelha) |
| eyeLookUpLeft / Right | olhar para cima |
| eyeSquintLeft / Right | pálpebras apertando (contração ao redor do olho) |
| eyeWideLeft / Right | pálpebras arregaladas |
| jawForward | mandíbula para a frente |
| jawLeft / jawRight | mandíbula deslocada para a esquerda / direita |
| jawOpen | mandíbula aberta (boca abre) |
| mouthClose | lábios fechados independentemente da mandíbula (relativa ao jawOpen) |
| mouthFunnel | lábios em funil, boca em "O" aberto |
| mouthPucker | lábios franzidos/bico (beijo) |
| mouthLeft / mouthRight | boca inteira deslocada para a esquerda / direita |
| mouthSmileLeft / Right | canto da boca sobe (sorriso) |
| mouthFrownLeft / Right | canto da boca desce |
| mouthDimpleLeft / Right | canto da boca puxado para trás (covinha) |
| mouthStretchLeft / Right | canto da boca esticado para fora |
| mouthRollLower | lábio inferior enrola para dentro |
| mouthRollUpper | lábio superior enrola para dentro |
| mouthShrugLower | lábio inferior empurrado para cima/fora ("beicinho") |
| mouthShrugUpper | lábio superior empurrado para cima |
| mouthPressLeft / Right | lábios pressionados um contra o outro, por lado |
| mouthLowerDownLeft / Right | lábio inferior desce (mostra dentes de baixo) |
| mouthUpperUpLeft / Right | lábio superior sobe (mostra dentes de cima) |
| browDownLeft / Right | sobrancelha desce (externa) |
| browInnerUp | parte interna das sobrancelhas sobe (as duas juntas) |
| browOuterUpLeft / Right | parte externa da sobrancelha sobe |
| cheekPuff | bochechas infladas |
| cheekSquintLeft / Right | bochecha sobe apertando o olho |
| noseSneerLeft / Right | asa do nariz sobe (desdém) |
| tongueOut | língua para fora |

Ordem oficial da Apple (e das colunas do CSV): olho esquerdo (7), olho direito (7), mandíbula e boca
(27), sobrancelhas/bochechas/nariz (10), língua (1).

Pares espelhados (18): eyeBlink, eyeLookDown, eyeLookIn, eyeLookOut, eyeLookUp, eyeSquint, eyeWide,
browDown, browOuterUp, cheekSquint, noseSneer, mouthSmile, mouthFrown, mouthDimple, mouthStretch,
mouthPress, mouthLowerDown, mouthUpperUp (= 36 shapes). Sem par (16): jawForward, jawLeft, jawRight,
jawOpen, mouthClose, mouthFunnel, mouthPucker, mouthLeft, mouthRight, mouthRollLower, mouthRollUpper,
mouthShrugLower, mouthShrugUpper, browInnerUp, cheekPuff, tongueOut. Modo simétrico = 34 poses.

## 4. Formato do CSV do Live Link Face

Observado em importadores abertos e na documentação do app (Epic):

```
Timecode,BlendShapeCount,EyeBlinkLeft,EyeLookDownLeft,...,TongueOut,HeadYaw,HeadPitch,HeadRoll,LeftEyeYaw,LeftEyePitch,LeftEyeRoll,RightEyeYaw,RightEyePitch,RightEyeRoll
14:03:52:28.207,61,0.0123,0.0,...
```

- Nomes em **PascalCase** (`EyeBlinkLeft`), enquanto o ARKit usa camelCase (`eyeBlinkLeft`): casar sem
  diferenciar maiúsculas.
- `BlendShapeCount` = 61 = 52 shapes + 9 rotações (cabeça e olhos, em graus/radianos conforme a
  versão; tratar como opcionais).
- `Timecode` = `HH:MM:SS:FF.sub`, com `FF` contado no FPS do app (60 por padrão, 30 configurável);
  o sub-frame após o ponto é fração. Conversão: `t = h*3600 + m*60 + s + FF.sub / fps_app`, relativa à
  primeira linha. Fallback seguro: `índice_da_linha / fps_app`.
- Reamostrar para o FPS da cena (frame mais próximo; última linha vence em empate). O streaming UDP do
  app (porta 11111) usa o mesmo pacote de 61 floats (fora do MVP).

## 5. Descobertas da API do Blender 5.2.1 (sondagem headless feita nesta fase)

- `bpy.app.version_string == "5.2.1 LTS"`; numpy 2.3 vem embutido (sem dependência externa).
- **Actions com slots:** `Action.fcurves` (API legada) **não existe mais**; usar
  `action.fcurve_ensure_for_datablock(shape_keys_datablock, 'key_blocks["nome"].value')`, que cria o
  slot e o atribui ao `animation_data`. `keyframe_points.add(n)` + `foreach_set("co", ...)` para escrever
  rápido.
- `scene.timeline_markers.new(nome, frame=...)` disponível; marcadores servem de biblioteca de poses.
- Avaliação: `obj.evaluated_get(depsgraph).data` após `scene.frame_set(f)` e
  `bpy.context.evaluated_depsgraph_get()`; `vertices.foreach_get("co", buf)` para numpy.
- Modificadores que **preservam contagem/ordem de vértices** (podem ficar ligados no bake): ARMATURE,
  CAST, CURVE, DISPLACE, HOOK, LAPLACIANDEFORM, LATTICE, MESH_DEFORM, SHRINKWRAP, SIMPLE_DEFORM, SMOOTH,
  CORRECTIVE_SMOOTH, LAPLACIANSMOOTH, SURFACE_DEFORM, WARP, WAVE, VOLUME_DISPLACE. Os demais (SUBSURF,
  MIRROR, SOLIDIFY, NODES, BEVEL, ARRAY, DECIMATE…) devem ser desligados durante o bake.
- Workbench renderiza em `--background`; `bpy.data.fonts` vem vazio no factory-startup, mas um objeto
  FONT novo usa a fonte embutida.
- Extensão: `blender_manifest.toml` com `schema_version`, `id`, `version`, `name`, `tagline`,
  `maintainer`, `type = "add-on"`, `license = ["SPDX:GPL-3.0-or-later"]`, `blender_version_min`.
  Build/validação: `blender --command extension build|validate <pasta>`; instalação por
  `Edit > Preferences > Get Extensions > Install from Disk` ou `blender --command extension install`.

## 6. Fontes

- FaceFlex — https://www.gonreel.com/p/faceflex-blender-add-on-arkit.html
- ARKit Blendshape Helper — https://github.com/elijah-atkins/ARKitBlendshapeHelper
- FaceIt docs — https://faceit-doc.readthedocs.io/ ; página do produto — https://superhivemarket.com/products/faceit
- Pose Shape Keys — https://studio.blender.org/training/blender-studio-rigging-tools/pose-shape-keys/ ;
  https://extensions.blender.org/add-ons/pose-shape-keys/
- Bake Shape Keys — https://extensions.blender.org/add-ons/bake-shape-keys/
- Blender LiveLinkFace Add-On — https://blender-addons.org/blender-livelinkface-add-on/
- ARKit CSV Animation Importer — https://seanowenblue.gumroad.com/l/arkitcsvanimationimporter
- Live Link Face → MetaHuman retarget (formato do CSV) — https://dev.to/alexdjulin/live-link-face-to-unreal-metahuman-retarget-5f9b
- Face_Landmark_Link (gera CSV compatível) — https://github.com/Qaanaaq/Face_Landmark_Link
- llv (pacote UDP de 61 floats do Live Link Face) — https://github.com/lucasjinreal/llv
- Audio2Face-3D samples — https://github.com/NVIDIA/Audio2Face-3D-Samples ;
  blendshape transfer — https://www.cgchannel.com/2022/01/omniverse-audio2face-now-generates-facial-blendshapes/
- Apple ARFaceAnchor.BlendShapeLocation — https://developer.apple.com/documentation/arkit/arfaceanchor/blendshapelocation
- Blender: criar extensões — https://docs.blender.org/manual/en/latest/advanced/extensions/getting_started.html
- Blender: baking de poses em shape keys (fórum) — https://blenderartists.org/t/is-it-possible-to-bake-armature-poses-into-shape-keys-morph-targets/580965
- Rigify face — código embutido em `<Blender 5.2>/scripts/addons_core/rigify/rigs/face/`
