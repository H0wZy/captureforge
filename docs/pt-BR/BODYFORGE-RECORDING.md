# BodyForge: como filmar um clipe

A qualidade do clipe é decidida na câmera. O BodyForge rastreia uma pessoa com uma câmera de celular parada, usando o
MediaPipe Pose; ele vai bem em gestos lentos e no lugar, e vai pior em movimentos rápidos, escondidos ou com muita gente.
Qualquer celular Android (ou outro) serve, e uma webcam também. Não precisa de iPhone, sensor de profundidade nem LiDAR.

O BodyForge avisa dos problemas mais comuns antes de resolver o movimento (taxa de quadros baixa, corpo fora do
enquadramento, pouca confiança, várias pessoas), e o relatório de qualidade mostra quais trechos ficaram fracos.

> **Uso responsável.** Filme você mesmo, ou alguém que concordou com isso. Não capture nem anime uma pessoa real sem o
> consentimento explícito dela. Leia o [POLICY.md](../../POLICY.md). Guarde os vídeos fora do repositório.

## O básico (todo clipe)

- **Câmera**: celular em tripé ou apoiado em algo estável, em paisagem ou retrato, **sem se mexer**. Lente na altura do
  peito, apontando direto para a pessoa. Um ângulo leve (até uns 30 graus) tudo bem; de lado perde profundidade.
- **Enquadramento**: o corpo inteiro, da cabeça aos pés, durante a gravação toda, com folga ao redor das mãos quando
  sobem ou abrem. Não corte os pés.
- **Taxa de quadros**: **30 fps ou mais**; use **60 fps** em movimentos rápidos (dança). Trave a exposição e desligue
  filtros de beleza e estabilização, se o celular tiver.
- **Luz**: clara e uniforme (janela ou sombra ao ar livre); evite contraluz. Movimento rápido pede luz forte, para o
  obturador ser rápido e a imagem ficar nítida.
- **Fundo e roupa**: fundo liso e roupa que contraste com ele. Roupa justa, não larga; mangas que não escondam os
  cotovelos; sapato de cor diferente do chão. Evite um pôster de pessoa atrás de você.
- **Começo neutro**: comece toda gravação **parado por 1,5 a 2 segundos**, braços soltos ao lado do corpo, de frente
  para a câmera. O BodyForge mede suas proporções, a direção de "cima" e o chão a partir dessa pose (o tempo está em
  "Neutral s"). Sem isso ele usa as proporções padrão do rig e mostra um aviso.
- **Uma pessoa** no quadro. Se uma segunda pessoa aparecer, a mais proeminente é rastreada e você recebe um aviso.
- Guarde o arquivo fora do repositório; o BodyForge grava os pontos, o relatório e o filmstrip ao lado dele.

## Os quatro clipes

### 1. Mãos ao alto (rendição), obrigatório, o mais fácil

Fique parado, depois levante as duas mãos devagar acima da cabeça, com as palmas abertas para a câmera, e segure por um
segundo. Mantenha os cotovelos visíveis. Bom para testar a cadeia toda. Dica: deixe uma palma de folga no quadro acima
das mãos levantadas.

### 2. Revista (com as mãos), obrigatório

Ligue o rastreio de mãos (**Hands and fingers**; precisa do modelo de mãos do **Install helper**). De frente para a
câmera, braços abertos para os lados, palmas para baixo, e deixe ser apalpado. Mantenha as mãos **na frente do corpo, não
atrás**, e evite sobrepor as duas mãos no tronco por muito tempo: o modelo de mãos perde uma mão coberta, e os dedos então
ficam parados ou relaxam para o repouso. Filme o ator e quem faz a revista em duas gravações separadas; o BodyForge
rastreia uma pessoa.

### 3. Andando de moto, melhor esforço

Sente numa moto parada (ou numa cadeira) na mesma pose, câmera de lado e meio de frente, com **os dois braços e pelo menos
uma perna totalmente visíveis**. A perna escondida e o banco deixam os pés pouco confiáveis: **desligue o foot lock**
(por pé ou por trecho) e, se precisar, ajuste os pés à mão depois. A altura do quadril fica aproximada na pose sentada.

### 4. Dança, melhor esforço

Use **60 fps**, luz forte, roupa justa e chão livre; fique no lugar e dentro do quadro durante todo o movimento. Ligue
**Keep video frame rate** para animar em 60 fps. Braços rápidos borram: o relatório lista os trechos de pouca confiança,
que você pode cortar ou consertar à mão. Para uma dança em loop, termine perto da pose inicial e use **Close loop**.

## Limites conhecidos

- Uma pessoa, uma câmera parada, quase tudo no lugar. Deslocamento no mundo, movimento de câmera e pulos não são
  recuperados.
- Profundidade é o ponto fraco de uma câmera só: braços apontando para a câmera ficam ruidosos. Filme de frente, ou faça
  o movimento atravessar o quadro quando der.
- O foot lock é uma heurística. Pulos, agachamentos fundos e poses sentadas pedem que ele fique desligado.
- Dedos são só curvatura e giro do punho, não pose de mão precisa.
- Partes escondidas ou cortadas são seguradas ou interpoladas a partir dos bons quadros ao redor e aparecem no relatório.

## Depois da gravação

1. **Video to body** (ou carregue um arquivo de pontos), depois **Clean up**, depois **Report**, e olhe o filmstrip.
2. Corrija o que o relatório apontar: corte pontas ruins, desligue o foot lock onde atrapalhou, espelhe se filmou ao
   contrário.
3. **Export for Unity**, e importe como clipe Humanoid com o avatar do próprio personagem (veja o quickstart em
   `specs/001-bodyforge-v1/quickstart.md`).
