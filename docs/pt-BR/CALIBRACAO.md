# Calibração do ator: passo a passo

Para que serve: deixar a captura facial do FaceForge mais fiel ao **seu** rosto. Você grava um roteiro curto uma vez;
depois disso todo `Video to face` e toda `Live webcam` sua saem corrigidos, em qualquer personagem. Detalhes técnicos:
`specs/005-actor-calibration/` (em inglês).

## 1. Prepare a gravação

- Celular **em pé**, num tripé ou suporte, **na altura dos olhos** (não de baixo para cima).
- O rosto inteiro aparecendo, da testa ao queixo, com um pouco de folga.
- Luz de frente e estável. Câmera traseira ou frontal, tanto faz (se a gravação sair espelhada, o FaceForge percebe e
  corrige).

## 2. Grave o roteiro (uns 40 s)

Comece com **3 s de rosto neutro**. Depois faça cada expressão, segure **~1 s** e volte ao neutro por **~1 s**:

1. Boca aberta
2. Sorriso
3. Sorriso só do lado esquerdo
4. Bico
5. Boca em "O"
6. Piscar os dois olhos
7. Piscar só o olho esquerdo
8. Piscar só o olho direito
9. Sobrancelhas pra cima
10. Sobrancelhas franzidas
11. Boca triste (cantos pra baixo)
12. Esticar a boca pros lados
13. Boca pra esquerda
14. Boca pra direita
15. Bochecha inflada
16. Nariz franzido
17. Olhos arregalados
18. Sorriso de boca fechada, apertando os lábios

"Esquerda" e "direita" são as **suas**. Se errar, grave de novo: é rápido.

## 3. Calibre no Blender

1. Painel FaceForge, seção `4d. Actor calibration`.
2. `Calibration video`: o vídeo que você gravou. `Label`: um apelido qualquer.
3. `Calibrate`. Se aparecer "found N expressions, the script has 18", o FaceForge não conseguiu separar as expressões:
   a mensagem mostra os trechos que ele achou; grave de novo com pausas neutras mais claras.
4. Pronto: o perfil `<apelido>.faceprofile.json` fica ao lado do vídeo e já vem escolhido em `Actor profile`.

## 4. Leia o relatório

- **Target key strongest**: em quantas das 18 expressões a key certa é a mais forte, antes e depois.
- **Median target peak**: até onde as expressões chegam (o ideal é perto de 1.0).
- **Weight on other keys**: quanto vaza para keys erradas (quanto menor, melhor).
- **Not detected**: keys que o rastreador não enxerga no seu rosto. Elas ficam como estão.
- **Head pitch**: o ângulo da cabeça na calibração. Grave as próximas cenas num ângulo parecido.

## 5. Use

Com `Actor profile` preenchido, `Video to face` e `Live webcam` já usam a correção. Para CSVs antigos do FaceForge,
ligue `Apply actor profile` antes do `Import CSV`. Para desligar, apague o `Actor profile`.

## Privacidade

O vídeo é dado do seu rosto e fica com você. O arquivo de captura temporário é apagado depois da calibração. O perfil
guarda só números e o seu apelido; o git ignora `*.faceprofile.json` e `*.capture.npz`.
