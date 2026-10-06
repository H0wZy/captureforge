# T051: licença dos pesos dos modelos MediaPipe (pesquisa)

Verificado em 2026-10-04, nas fontes primárias (model cards em PDF do Google, páginas oficiais do MediaPipe, texto da
Apache-2.0, lista de licenças da FSF, termos do Blender Extensions). Nada foi baixado além dos PDFs lidos; nada foi
instalado.

## English summary

- Every model file CaptureForge uses (`pose_landmarker_{lite,full,heavy}.task`, `hand_landmarker.task`,
  `face_landmarker.task`, including the blendshapes model inside it) is covered by a Google model card whose
  "Licensed under" field reads **Apache License, Version 2.0**. There is no separate "model card license" and no
  non-commercial clause. The documentation pages themselves are CC BY 4.0 (text) and Apache-2.0 (code samples) and do
  not state the weight license; the model-card PDFs do.
- Apache-2.0 is GPLv3-compatible (FSF). A GPL-3.0-or-later add-on may download the weights at runtime from the
  official URLs with no obligation at all (nothing is redistributed), and may also bundle them if it ships the
  Apache-2.0 text plus an attribution note (Apache-2.0 section 4; the `.task` files carry no NOTICE file).
- Model output (landmarks, blendshape scores, the animation built from them) is not licensed material; using it on
  commercial game characters is fine. The cards state the models are not for surveillance or identity recognition and
  do not store any unique face representation.
- Recommendation: keep the current design (download at runtime, only after the user confirms, with sha256 checks),
  do not bundle; add one sentence to README, a small `THIRD_PARTY_NOTICES.md`, and two bullets to POLICY.md. Keep
  `FACEFORGE_MODEL` / `BODYFORGE_POSE_MODEL` as they are. The one caveat is extensions.blender.org, whose terms
  forbid non-CC0 binary assets inside the zip and discourage features that need components downloaded elsewhere;
  this only matters for a future listing there, not for the GitHub release.

## 1. Qual licença cobre os pesos

Cada arquivo `.task` é um pacote com um ou mais modelos TFLite. Os model cards (PDF) de cada modelo trazem um campo
"LICENSED UNDER" e todos dizem a mesma coisa:

| Modelo (arquivo `.task`) | Model card (fonte primária) | Campo "Licensed under" | Data no card |
|---|---|---|---|
| `pose_landmarker_lite/full/heavy.task` (BlazePose GHUM 3D, lite 3 MB, full 6 MB, heavy 26 MB) | [Model Card BlazePose GHUM 3D](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20BlazePose%20GHUM%203D.pdf) | Apache License, Version 2.0 | 16 abr 2021 |
| `hand_landmarker.task` (Hand Tracking lite/full) | [Model Card Hand Tracking (Lite/Full) with Fairness](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Hand%20Tracking%20(Lite_Full)%20with%20Fairness%20Oct%202021.pdf) | Apache License, Version 2.0 | out 2021 |
| `face_landmarker.task`, detector de rosto (BlazeFace short range) | [MediaPipe BlazeFace Model Card (Short Range)](https://storage.googleapis.com/mediapipe-assets/MediaPipe%20BlazeFace%20Model%20Card%20(Short%20Range).pdf) | Apache License, Version 2.0 | 9 jun 2021 |
| `face_landmarker.task`, malha de 478 pontos (Face Mesh V2) | [Model Card MediaPipe Face Mesh V2](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20MediaPipe%20Face%20Mesh%20V2.pdf) | Apache License, Version 2.0 | 15 set 2022 |
| `face_landmarker.task`, 52 blendshapes (Blendshape V2) | [Model Card Blendshape V2](https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Blendshape%20V2.pdf) | Apache License, Version 2.0 | 11 nov 2022 |

Os links dos cards são os que as páginas oficiais apontam: [Pose Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker)
("info" ao lado de cada variante lite/full/heavy, os três apontam para o mesmo card) e
[Face Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker) (FaceDetector,
FaceMesh-V2, Blendshape). O rodapé dessas páginas diz "the content of this page is licensed under the Creative Commons
Attribution 4.0 License, and code samples are licensed under the Apache 2.0 License"; isso cobre o texto e os exemplos
da página, não os pesos. A licença dos pesos está nos cards, e é Apache-2.0 em todos. O repositório
[google-ai-edge/mediapipe](https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE) (código) também é
Apache-2.0.

Como os PDFs foram lidos: `pdftotext` sobre os arquivos baixados dos links acima; o texto é extraível (a tentativa
anterior falhou por limitação da ferramenta, não do PDF). Trechos exatos, na ordem da tabela:

- BlazePose GHUM 3D, p. 1: "DOCUMENTATION ... LICENSED UNDER Apache License, Version 2.0"; p. 2, Out-of-scope:
  "Any form of surveillance or identity recognition is explicitly out of scope and not enabled by this technology".
- Hand Tracking, p. 2: "LICENSED UNDER Apache License, Version 2.0"; Out-of-scope: "Any form of surveillance or
  identity recognition is explicitly out of scope and not enabled by this technology."
- BlazeFace short range, p. 1: "LICENSED UNDER Apache License, Version 2.0"; Out-of-scope: "Any form of surveillance
  or identity recognition is explicitly out of scope and not enabled by this technology".
- Face Mesh V2, p. 1: "LICENSED UNDER Apache License, Version 2.0"; p. 2: "Predicted face landmarks do not provide
  facial recognition or identification and do not store any unique face representation."
- Blendshape V2, p. 1: "LICENSED UNDER Apache License, Version 2.0"; p. 2: "Predicted facial blendshapes do not
  provide facial recognition or identification and do not store any unique face representation."

Não existe "licença de model card" separada, nem cláusula de uso não comercial, nem termo de aceite para baixar os
arquivos de `storage.googleapis.com/mediapipe-models/`. O que os cards trazem além da licença são declarações de uso
pretendido e fora de escopo (seção 4), que são orientação do fabricante, não termos de licença.

Observação sobre as URLs: a documentação usa o sufixo `float16/latest/`; o README do FaceForge aponta
`face_landmarker/float16/1/face_landmarker.task`, que é a versão fixa 1 do mesmo arquivo. Ambas são oficiais. Para
quem confere sha256, a URL com número de versão é mais estável que `latest`.

## 2. Add-on GPL-3.0 pode baixar em runtime ou empacotar os pesos?

**Baixar em runtime (o que o CaptureForge faz hoje):** pode, sem nenhuma obrigação de licença. O add-on não
redistribui os pesos; quem baixa é o usuário, direto do Google. A Apache-2.0 só impõe condições a quem redistribui
(seção 4). A GPL não alcança os pesos: são dados que o programa lê, não código derivado do add-on, e o processo que os
usa roda num venv externo. Nada a mais na licença do add-on.

**Empacotar (bundle) no zip:** também é permitido. A FSF lista a Apache-2.0 como "a free software license, compatible
with version 3 of the GNU GPL" ([license-list](https://www.gnu.org/licenses/license-list.en.html#apache2); não é
compatível com a GPLv2, o que não nos afeta porque o CaptureForge é GPL-3.0-or-later). Empacotar vira
redistribuição, então valem as condições da seção 4 do texto da [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0):

- (a) entregar uma cópia da licença Apache-2.0 junto;
- (b) marcar arquivos modificados (não se aplica: os `.task` iriam intactos);
- (c) manter avisos de copyright e atribuição (os `.task` não carregam aviso legível; basta um arquivo de notas
  dizendo de onde vêm, de quem são e sob qual licença);
- (d) reproduzir o NOTICE se a obra tiver um. Os `.task` não têm NOTICE; o repositório MediaPipe não publica NOTICE
  para os modelos. Logo, não há texto de NOTICE a copiar; um `THIRD_PARTY_NOTICES.md` nosso resolve (a)+(c).

Não há exigência de atribuição para o caso de download em runtime; mesmo assim, citar origem e licença no README é boa
prática e já é feito em `docs/BODYFORGE-MODELS.md`.

**Caveat do Blender Extensions (só para uma futura listagem em extensions.blender.org):** os
[termos de serviço](https://extensions.blender.org/terms-of-service/) dizem (1) "Binary files or other types of assets
included in the extension (images, SVG files, fonts, etc.) must be licensed as Public Domain (CC0)", o que impede
empacotar `.task` Apache-2.0 no zip enviado lá; e (5) "Extension should not require any external functional components
(other than Blender itself) that need to be downloaded from elsewhere to access any of its features, even if those
features are considered optional", o que tensiona com o venv + modelos baixados. O venv já é um componente externo
hoje (FaceForge sempre foi assim), então o status da listagem não muda por causa dos pesos; é um item a levantar com
os revisores da plataforma quando a listagem for tentada (item já no roadmap do README). Para o zip distribuído no
GitHub Releases nada disso se aplica. O manifesto já declara `permissions.network` com o motivo ("model download only
after you confirm"), como os termos pedem.

## 3. Uso da saída em personagens comerciais

Não há restrição. A Apache-2.0 não impõe condições sobre a saída de um programa ou modelo (só sobre a redistribuição
da obra licenciada). Os model cards listam "AR entertainment", "controlling an avatar's face", "3D pose and gesture
recognition", "fitness" como usos pretendidos; animar um personagem de jogo é exatamente isso. Landmarks, scores de
blendshape e a animação baked em shape keys ou bones são dados criados pelo usuário a partir do próprio vídeo. Nenhuma
atribuição ao Google é exigida no jogo final. Vale lembrar a diferença: isso é sobre usar a saída; redistribuir os
pesos (seção 2) é outra pergunta.

## 4. Biometria, consentimento, dados de rosto

O que os cards dizem, textualmente (seção 1): vigilância e reconhecimento de identidade estão "explicitly out of scope
and not enabled by this technology"; os modelos de rosto "do not store any unique face representation"; não são para
"human life-critical decisions"; foram treinados "on consented images". Isso é declaração de escopo, não termo de
licença: a Apache-2.0 não proíbe uso algum, então descumprir o escopo não quebra a licença, mas contradiz o fabricante
e pode quebrar a lei.

O que vale de verdade é a lei de dados pessoais e biométricos de cada país (LGPD no Brasil, GDPR na UE, BIPA em
Illinois, por exemplo), e nelas um vídeo de rosto ou corpo é dado pessoal, e dados usados para identificar alguém são
biométricos sensíveis. O CaptureForge não identifica ninguém e processa tudo localmente, o que ajuda, mas o usuário
que filma outra pessoa continua responsável pelo consentimento.

O `POLICY.md` já cobre o essencial (consentimento explícito, celebridades, leis de imagem e privacidade, "vídeo ou
scan de rosto é dado pessoal em muitos países"). Faltam dois pontos que valem acrescentar, e uma correção:

- dizer que os modelos de rosto e corpo não fazem reconhecimento ou identificação e que a ferramenta não deve ser
  usada para isso (alinha com o escopo declarado pelo fabricante);
- dizer que nenhum vídeo, landmark ou resultado sai da máquina do usuário (sem telemetria; o único acesso à rede é o
  download dos modelos, com confirmação), o que é o argumento de privacidade mais forte da ferramenta;
- a primeira frase fala em "animate a human face"; com o BodyForge disponível, estender para "face or body".

## 5. Recomendação para o CaptureForge

**Decisão: download em runtime da URL oficial, como já está. Não empacotar.** Motivos: zero obrigação de licença,
zip pequeno (os pesos somam mais de 40 MB), mantém a porta aberta para o Blender Extensions (que exige CC0 para
binários no zip), e a verificação de sha256 já protege contra troca silenciosa de arquivo atrás do `latest`.

O que mudar nos textos (sem mexer em código):

1. **`docs/BODYFORGE-MODELS.md`**: trocar o bloco "Open verification item (research item 1)" por: "Verified
   2026-10-04: the model cards for BlazePose GHUM 3D (pose lite/full/heavy) and Hand Tracking (hand landmarker) state
   'Licensed under Apache License, Version 2.0'. The face landmarker bundle (BlazeFace short range, Face Mesh V2,
   Blendshape V2) has the same wording on its three model cards." Acrescentar `face_landmarker.task` à tabela de
   URLs (link, 3,6 MB, sha256 a registrar na próxima vez que o helper o baixar) para que o FaceForge e o BodyForge
   tenham a mesma fonte de verdade. Fechar o T051 em `tasks.md` apontando para este documento.

2. **`README.md` e `README.pt-BR.md`**, na seção do BodyForge, uma frase: "The MediaPipe models are downloaded from
   Google's storage on your confirmation and never bundled; they are Apache-2.0 (see their model cards, linked in
   `docs/BODYFORGE-MODELS.md`). The output (landmarks, shape-key and bone animation) is yours; there is no restriction
   on using it in commercial projects." No passo 2 do FaceForge ("Download the MediaPipe Face Landmarker model"),
   acrescentar "(Apache-2.0)".

3. **`THIRD_PARTY_NOTICES.md`** (novo, na raiz, curto): lista `mediapipe`, `opencv-python` e os cinco modelos com
   origem, licença Apache-2.0 e link do card, e a frase "These are installed or downloaded by the user into the helper
   environment; none of them is part of the CaptureForge distribution." Não é exigido pela Apache-2.0 no modo download;
   é a trilha de auditoria para quem for verificar, e vira obrigatório se algum dia os pesos forem empacotados (aí
   adicionar também o texto da Apache-2.0 ao lado do `LICENSE`).

4. **`POLICY.md`**: os três ajustes da seção 4 (sem identificação ou reconhecimento; tudo local, sem telemetria;
   "face or body").

5. **`FACEFORGE_MODEL` e `BODYFORGE_POSE_MODEL` (e `BODYFORGE_HAND_MODEL`)**: manter como estão. São caminhos para
   arquivos `.task` que o usuário já tem; servem aos testes e como fallback das preferências vazias. Não há nada de
   licença neles. Única sugestão: no `--help` ou no docstring dos testes, dizer "any pose_landmarker .task from
   Google's MediaPipe storage (Apache-2.0)" para que quem roda os testes saiba de onde pegar o arquivo.

6. **Não fazer**: não adicionar cláusula sobre os modelos ao `LICENSE` (GPL fica puro); não pedir aceite de termos no
   botão de instalação (não existe termo a aceitar); não bloquear por país ou uso.

## Fontes

- Pose Landmarker (página oficial): <https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker>
- Face Landmarker (página oficial): <https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker>
- Model cards (PDF): links na tabela da seção 1.
- Código MediaPipe, LICENSE: <https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE>
- Apache License 2.0, texto: <https://www.apache.org/licenses/LICENSE-2.0>
- FSF, compatibilidade Apache-2.0 e GPLv3: <https://www.gnu.org/licenses/license-list.en.html#apache2>
- Blender Extensions, termos de serviço: <https://extensions.blender.org/terms-of-service/>
- Política do site Google Developers (CC BY 4.0 texto, Apache-2.0 exemplos): <https://developers.google.com/terms/site-policies>
