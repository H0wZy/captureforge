# FaceForge — design (fase 1)

Extensão própria do Blender 5.2 para gerar blendshapes faciais (ARKit 52 e listas custom) a partir de um
rig temporário, sem comprar add-on. Nome de trabalho: **FaceForge**. Clean room: só conceitos públicos
(ver `RESEARCH.md`), API Python do Blender, Rigify embutido e a lista pública da Apple.

## 1. Escopo do MVP

Fluxo do artista (idêntico em espírito ao padrão FaceFlex / ARKit Blendshape Helper):

1. Rig facial temporário (Rigify face recomendado) na malha da cabeça; olhos, dentes e língua no mesmo
   rig.
2. `Create markers`: um marcador de timeline por shape (preset ARKit 52, ARKit simétrico 34, ou lista
   custom) + marcador `neutral`.
3. Pular de marcador em marcador, posar, `Key pose`.
4. `Make target` cria a cópia sem rig de cada malha; `Bake` grava uma shape key por marcador em cada alvo.
5. `Split L/R` nas keys simétricas.
6. `Import Live Link Face CSV` para testar com mocap real; `Render review sheet` para conferir tudo.
7. Export FBX para Unity (fora do add-on no MVP; checker na fase 3).

Fora do MVP: auto-rig, presets de pose, correctives, streaming ao vivo, cabeça/olhos do CSV, Wonder
Studio 90 (lista não pública de forma confiável).

## 2. Módulos do MVP

Pacote `faceforge/` (extensão Blender ≥ 4.4, Python puro, só `bpy`, `mathutils` e o numpy
embutido). Funções de núcleo recebem objetos/dados explícitos (sem `context`) para serem testáveis
headless; operadores são invólucros finos.

| Módulo | Responsabilidade | API principal |
|---|---|---|
| `presets.py` | `ARKIT_52` (ordem da Apple), `NOT_MIRROR = {jawLeft, jawRight, mouthLeft, mouthRight}`, `LIVELINK_ROTATION_COLUMNS`, `NEUTRAL_MARKER = "neutral"`, `mirror_base(name)`, `symmetric_names(names)` → `ARKIT_SYMMETRIC` (34). | puro Python |
| `markers.py` | Biblioteca de poses por marcadores. | `create_markers(scene, names, start_frame=1, neutral_frame=0, clear=True)`, `frames_from_markers(scene) -> [(name, frame)]`, `neutral_frame(scene)`, `key_pose(armature, frame)` (keyframe loc/rot/scale de todos os pose bones, respeitando `rotation_mode`) |
| `bake.py` | Bake de frames posados em shape keys. | `bake_shapes(scene, pairs, frames, neutral_frame, overwrite=True) -> [names]`, `make_target(source) -> obj`, `ensure_basis/ensure_key`, `reset_keys(obj)`, `DEFORM_ONLY` |
| `split.py` | Split L/R com falloff suave. | `left_weight(x, width)` (smoothstep), `split_lr(obj, key, width=0.02, suffix="ARKIT"/"BLENDER", delete_source=True) -> (left, right)`, `symmetric_keys(obj)` |
| `mocap.py` | CSV de mocap facial (Live Link Face ou genérico) → F-Curves. | `read_csv(path, csv_fps=60) -> (names, times, rows)` (alias `read_livelink_csv`), `apply_mocap(obj, names, times, rows, scene_fps, start_frame, mapping=None) -> (matched, unmatched)` |
| `sheet.py` | Review sheet em grade. | `render_sheet(scene, targets, out_path, names=None, tile=256, columns=8) -> path` |
| `ops.py` | Operadores `faceforge.*` (create_markers, key_pose, make_target, pair_add/remove, bake, split_lr, split_all, import_csv, render_sheet, reset_keys). | `bpy.types.Operator` |
| `ui.py` | `PropertyGroup` em `scene.faceforge` + painel `View3D > Sidebar > FaceForge`. | `bpy.types.Panel`, `UIList` |
| `__init__.py` | `register()/unregister()` (sem `bl_info`; o manifesto manda). | — |

### Algoritmos

**Bake** (`bake_shapes`):
1. Para cada Source, desligar `show_viewport` dos modificadores fora de `DEFORM_ONLY` (guardar para
   restaurar em `finally`, junto com o frame atual).
2. `frame_set(neutral)`; `depsgraph = context.evaluated_depsgraph_get()`; `N = coords_mundo(Source)`.
   Se `len(N) != len(Target.data.vertices)`: `ValueError` com mensagem clara (alvo deve ser duplicata da
   malha base).
3. Para cada `(nome, frame)`: `frame_set(frame)`, novo depsgraph, `P = coords_mundo(Source)`,
   `delta = P − N`; `key = ensure_key(Target, nome)` (cria ou sobrescreve, `relative_key = Basis`,
   `value = 0`); `key.co = Basis_target + delta @ inv(M_target)[:3,:3].T`.
4. Vários pares no mesmo laço (cabeça, olho.L, olho.R, dentes, língua): mesmo mapa de marcadores, cada
   alvo recebe só as keys com delta (opcional: pular keys com `max|delta| < 1e-6` para não poluir olhos
   com 52 keys vazias — decisão: **criar todas** por padrão, para o Unity ver a mesma lista em toda malha;
   checkbox `skip_empty`).
- Coordenadas em **espaço de mundo** porque Source e Target podem estar deslocados para comparação.
- Shape keys já existentes na Source entram no bake (o depsgraph as mistura): "o que você vê é o que
  baka". Delta contra o **neutro avaliado** evita bakar duas vezes o que modificador/key já faz (ideia
  do Pose Shape Keys).

**Split L/R** (`split_lr`): `delta = key − Basis`; `w = smoothstep(clamp((x/width + 1)/2))` com `x` =
X da Basis em espaço do objeto (`width == 0` → degrau, 0.5 em X=0); `Left = Basis + delta·w`,
`Right = Basis + delta·(1−w)`; remove a key simétrica por padrão. `split_all` percorre as keys cujo nome
é base de par ARKit (`mirror_base`), ignorando `NOT_MIRROR`. Convenção: Left = +X (Rigify `.L`).

**Mocap** (`apply_mocap`): casa colunas e keys por `lower()`; ignora `Timecode`, `BlendShapeCount` e
rotações (reporta); `t` do timecode `HH:MM:SS:FF.sub` com `FF.sub / csv_fps`, relativo à primeira linha,
fallback `índice / csv_fps`; `frame = start + round(t · fps_cena)`, última linha vence; uma F-Curve por
key via `action.fcurve_ensure_for_datablock(shape_keys, 'key_blocks["nome"].value')` (Blender 5.x não
tem mais `action.fcurves`), `keyframe_points.add/foreach_set`, interpolação LINEAR, `fc.update()`.

**Review sheet** (`render_sheet`): guarda e restaura engine/resolução/filepath/câmera/`hide_render`/
valores das keys; esconde tudo que não é alvo; câmera ortográfica em −Y olhando +Y, `ortho_scale` =
maior lado do bbox dos alvos × 1.15 (+ espaço para rótulo); objeto FONT com o nome da shape abaixo do
queixo; para `["neutral"] + nomes`: zera keys, liga a key em todo alvo que a tiver, renderiza Workbench
`tile×tile` em pasta temporária; monta a grade com numpy (`image.pixels.foreach_get/set`; linhas de
imagem crescem de baixo para cima no Blender) e salva PNG; remove câmera, rótulo, temporários.

## 3. Modelo de dados

- **Marcadores da timeline** = biblioteca de poses. Nome do marcador = nome da shape key; `neutral` =
  frame de referência. Vantagens sobre uma action por shape: visíveis na timeline, `Jump to marker`
  nativo, reordenáveis, sem NLA. Quem tiver actions pode bakar na timeline antes.
- **`scene.faceforge`** (`PropertyGroup`):
  - `preset: Enum {ARKIT_52, ARKIT_SYMMETRIC, CUSTOM}`, `custom_names: String` (nomes separados por
    vírgula/linha) — `CUSTOM` cobre Wonder Studio/A2F quando houver lista.
  - `start_frame: Int = 1`, `neutral_frame: Int = 0`.
  - `pairs: Collection[FFPair{source: Pointer(Object, mesh), target: Pointer(Object, mesh)}]`,
    `pairs_index: Int`.
  - `overwrite: Bool = True`, `skip_empty: Bool = False`.
  - `split_width: Float = 0.02` (unidades do objeto), `split_suffix: Enum {ARKIT, BLENDER}`,
    `split_delete_source: Bool = True`.
  - `csv_path: String(FILE_PATH)`, `csv_fps: Float = 60`, `mocap_start_frame: Int = 1`.
  - `sheet_path: String(FILE_PATH)`, `sheet_tile: Int = 256`, `sheet_columns: Int = 8`.
- **Shape keys** no alvo: `Basis` + uma key por marcador, `relative_key = Basis`, valor 0 após o bake.
- **Action de mocap**: `"<alvo>_facemocap"` no `shape_keys.animation_data`, um slot (API de slots).

## 4. Layout de arquivos

```
faceforge/                   a extensão (o que vai no zip)
  blender_manifest.toml      id="faceforge", type="add-on", blender_version_min="4.4.0",
                             license=["SPDX:GPL-3.0-or-later"]
  __init__.py                register/unregister
  presets.py  markers.py  bake.py  split.py  mocap.py  sheet.py  ops.py  ui.py
  helpers/video_to_csv.py    script externo (mediapipe), roda fora do Blender
tests/run_tests.py           runner headless (constrói a cena, roda tudo, asserts, exit code)
tests/sample_livelink.csv    amostra escrita por nós (cabeçalho de 61 colunas, ~12 linhas a 60 fps)
docs/pt-BR/                  pesquisa e design (este arquivo e RESEARCH.md)
README.md  README.pt-BR.md   instalação e uso
```

Instalação: `Edit > Preferences > Get Extensions > Install from Disk` com o zip de
`blender --command extension build --source-dir faceforge`.
Para os testes, `sys.path.insert(0, "<raiz do repositório>")` + `import faceforge; faceforge.register()` (imports
relativos dentro do pacote funcionam tanto como `faceforge` quanto como `bl_ext.<repo>.faceforge`).

## 5. Plano de testes

Comando: `timeout 300 "<blender.exe>" --background --factory-startup --python tests/run_tests.py`
(headless, sem GUI, sem Blender MCP, um processo por vez). O runner imprime `PASS/FAIL` por teste e
sai com código ≠ 0 em falha.

Cena procedural (sem ops dependentes de contexto): esfera UV (cabeça, ~500 verts) + armature com
`jaw` (pivô na altura da orelha), `brow.L/brow.R`, `lid.L/lid.R`; vertex groups por região com peso
suavizado (queixo = `z < 0 and y < 0`, sobrancelhas = topo frontal por lado, pálpebras = região dos
olhos); modificador Armature por `modifiers.new`; dois alvos extras: duas esferas pequenas (olhos) com
o mesmo rig; um modificador Subsurf na cabeça (para testar o desligamento) e uma shape key extra na
Source (para testar "o que você vê é o que baka").

| # | Teste | Assert |
|---|---|---|
| 1 | `create_markers(ARKIT_52)` | 53 marcadores, `neutral` em 0, `tongueOut` em 52; `ARKIT_SYMMETRIC` tem 34 nomes |
| 2 | `key_pose` + `bake_shapes` com marcadores `jawOpen` (jaw rotacionado), `eyeBlink` (lids para baixo), `browInnerUp` (brows para cima) | keys criadas com esses nomes em cabeça e olhos; em `jawOpen`, vértices do queixo descem > 0.05 e vértices do topo movem < 1e-5; Subsurf volta a `show_viewport=True`; `frame_current` restaurado |
| 3 | Bake com source cujo Subsurf foi **aplicado** (contagem diferente) | `ValueError` com mensagem citando os dois objetos |
| 4 | Bake com `overwrite=False` em key existente | `ValueError`; com `overwrite=True` sobrescreve sem duplicar |
| 5 | `split_lr("eyeBlink", width=0.1)` | cria `eyeBlinkLeft/Right`, remove `eyeBlink`; em `eyeBlinkLeft`, delta em vértices com `x < −0.1` é 0 e em `x > 0.1` igual ao original; em `x≈0` peso ≈ 0.5; `Left + Right − Basis == original` |
| 6 | `read_livelink_csv(sample)` | 52 nomes, rotações ignoradas, `times[0] == 0`, `times[-1] ≈ (n−1)/60` |
| 7 | `apply_mocap` em cena a 30 fps | F-Curve de `jawOpen` existe, nº de keyframes = frames únicos, valor no frame esperado bate com a linha, interpolação LINEAR, `unmatched` lista as colunas sem key |
| 8 | `render_sheet(tile=64, columns=3)` com 4 shapes | PNG existe, dimensões `192 × 128` (5 tiles → 2 linhas), câmera/rótulo removidos, `hide_render` e valores de key restaurados |
| 9 | Registro: `faceforge.register()`; `bpy.ops.faceforge.create_markers()` e `bpy.ops.faceforge.bake()` via `scene.faceforge` | operadores retornam `{'FINISHED'}` e produzem o mesmo resultado do núcleo |

Também: `blender --command extension validate faceforge` sem erros.

## 6. Roadmap "melhor que o FaceFlex"

1. **Auto-fit do Rigify face por landmarks.** O artista clica cantos dos olhos, cantos da boca, linha da
   sobrancelha e queixo numa imagem frontal (ou direto na malha) e o add-on posiciona o metarig facial do
   Rigify e gera o rig. Elimina a etapa mais lenta.
2. **Presets de pose.** Pose inicial por shape ARKit em cima do rig gerado (ex.: `jawOpen` = rotação do
   `jaw_master`, `eyeBlink` = pálpebras fechadas); o artista só ajusta o estilo.
3. **Alvos por imagem de referência.** Contorno 2D de boca/olhos numa foto ou concept guia a pose por
   matching de contorno projetado.
4. **Correctives e combinações.** Bake de pose combinada menos a soma das isoladas, driver `a*b`, export
   como shape extra (ou tabela para o engine).
5. **Checker de export para Unity.** 52 nomes exatos sem duplicatas em toda malha, ordem, normais de
   blendshape no FBX, escala/eixos, aviso de key não zerada.
6. **Cabeça e olhos do CSV** para ossos (`HeadYaw/Pitch/Roll`, `Left/RightEye*`) e **streaming UDP**
   (porta 11111) para preview ao vivo.
7. **Presets Wonder Studio 90 / Audio2Face** como listas carregáveis de arquivo.
8. **Mocap por webcam (sem iPhone).** Quem só tem Android não pode usar o Live Link Face (iPhone). O MediaPipe Face Landmarker (Google,
   gratuito, código aberto) devolve os mesmos 52 scores com nomes ARKit (`eyeBlinkLeft`, …, mais uma
   categoria `_neutral` que o importador ignora) a partir de qualquer webcam ou vídeo de celular. Plano:
   script externo pequeno (`faceforge/helpers/`, Python + `mediapipe`, fora do add-on para não
   trazer dependência ao Blender) que lê um arquivo de vídeo e grava o nosso CSV genérico
   (`time` em segundos + uma coluna por shape). O importador já aceita esse formato (ver nota abaixo).
   Construído: ver o README (51 shapes; `tongueOut` não existe no MediaPipe).

Nota (MVP já entregue): o importador de CSV é genérico, não só Live Link Face: casa colunas com shape
keys pelo nome (sem diferenciar maiúsculas), aceita um mapa opcional `coluna=key`, e lê o tempo de
`Timecode` (Live Link Face), de `time` (segundos) ou, sem nenhum dos dois, de `índice / FPS do CSV`.

## 7. Limites honestos

- Bake exige Source e Target com mesma contagem/ordem de vértices (duplicata). Modificador generativo
  desconhecido → aviso e abort, nunca lixo silencioso.
- Timecode do Live Link Face lido como `HH:MM:SS:FF.sub`; se mudar entre versões do app, fallback por
  índice de linha ÷ FPS.
- Review sheet no Workbench, sem materiais complexos; serve para conferir forma, não para apresentação.
- Split assume linha média em X = 0 do objeto; malha assimétrica precisa de ajuste manual.
- Sem Wonder Studio 90 enquanto não houver lista pública confiável (campo `CUSTOM` cobre).
