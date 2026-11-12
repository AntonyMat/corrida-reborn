"""
seguidor.py - MODO SIMPLES: o carro fica SEMPRE entre a linha pontilhada (esquerda) e a continua (direita).

Por quadro:
  1. Pega as linhas achadas pelo detector (faixas.py) e mede onde cada uma esta perto do carro (Y_PERTO).
  2. Cada linha vai pro lado (ESQUERDA = pontilhada, DIREITA = continua) cuja posicao esperada (centro do
     quadro anterior -+ meia faixa) esta mais perto: continuidade. Linhas longe das duas sao ignoradas.
  3. Centro da faixa = meio das duas, ao longo de toda a vista. Se so uma aparece, usa ela +- meia faixa.
  4. Ponto-alvo = centro da faixa a SEG_OLHAR_CM a frente. Filtrado (mediana + portao de pulo + tempo).
  5. Volante por PURE PURSUIT: aponta as rodas pra passar pelo ponto-alvo. Uma medida so, sem termos
     brigando (erro x proa), por isso nao oscila. Mais longe o alvo = mais suave.
"""

import math

import config
from estabilidade import MedidaEstavel


class SeguidorFaixa:
    def __init__(self, cam):
        self.cam = cam
        self.W = float(config.FAIXA_LARGURA_CM)
        self.c_prev = 0.0                 # centro da faixa (X, cm) em Y_PERTO no quadro anterior
        self.f_alvo = MedidaEstavel(config.SEG_ALVO_TAU_S, config.SEG_PULO_CM, config.MEDIDA_PULO_QUADROS)
        self.esq = self.dir = None        # linhas escolhidas (debug/HUD)
        self.lados = ""                   # "E+D", "so E", "so D"
        self.cx = None                    # funcao X(Y) do centro no ultimo quadro bom (HUD)
        self.alvo = None                  # (x, y) do ponto-alvo (HUD)

    def reset(self):
        self.c_prev = 0.0
        self.f_alvo.reset()

    def _y(self):
        cam = self.cam
        y_perto = cam.y_min + 6.0
        y_alvo = min(cam.y_max - 4.0, max(y_perto + 10.0, config.SEG_OLHAR_CM))
        return y_perto, y_alvo

    def centro(self, linhas):
        """Devolve uma funcao X(Y) do centro da faixa, ou None. Atualiza self.esq/self.dir/self.lados.

        Cada linha vai pro lado cuja posicao ESPERADA (centro anterior -+ meia faixa) esta mais perto dela:
        uma linha nao pula meia faixa de um quadro pro outro. A classe (continua/pontilhada) so desempata,
        porque numa curva fechada a continua sai em parte da vista e parece pontilhada."""
        W = self.W
        y_p, _ = self._y()
        esp_e, esp_d = self.c_prev - 0.5 * W, self.c_prev + 0.5 * W
        cand_e, cand_d = [], []
        for l in linhas:
            x = float(l.x(y_p))
            de, dd = abs(x - esp_e), abs(x - esp_d)
            if min(de, dd) > 0.5 * W:                 # nao e nenhuma das duas linhas da faixa atual
                continue
            if abs(de - dd) < 0.25 * W and l.classe in ("continua", "pontilhada"):
                lado = "D" if l.classe == "continua" else "E"     # ambiguo: a classe decide
            else:
                lado = "E" if de < dd else "D"
            (cand_e if lado == "E" else cand_d).append((de if lado == "E" else dd, x, l))
        e = min(cand_e, key=lambda t: t[0]) if cand_e else None
        d = min(cand_d, key=lambda t: t[0]) if cand_d else None
        if e is not None and d is not None:
            larg = d[1] - e[1]
            if not (0.6 * W <= larg <= 1.5 * W):           # par incoerente: fica com a que esta mais no lugar
                if d[0] <= e[0]:
                    e = None
                else:
                    d = None
            else:
                self.W += 0.05 * (min(1.3 * config.FAIXA_LARGURA_CM, max(0.75 * config.FAIXA_LARGURA_CM, larg)) - self.W)
        self.esq = e[2] if e else None
        self.dir = d[2] if d else None
        W = self.W
        le, ld = self.esq, self.dir
        if le is not None and ld is not None:
            self.lados = "E+D"
            return lambda Y: 0.5 * (float(le.x(Y)) + float(ld.x(Y)))
        if le is not None:
            self.lados = "so E"
            return lambda Y: float(le.x(Y)) + 0.5 * W
        if ld is not None:
            self.lados = "so D"
            return lambda Y: float(ld.x(Y)) - 0.5 * W
        self.lados = ""
        return None

    def passo(self, linhas, dt):
        """Devolve (turn, erro_cm, proa_graus) ou None se nao achou a faixa."""
        cx = self.centro(linhas)
        if cx is None:
            return None
        y_p, y_a = self._y()
        self.c_prev = cx(y_p)
        self.cx = cx
        x_a = self.f_alvo.atualizar(cx(y_a) + config.SEG_DESLOCAMENTO_CM, dt)   # ponto-alvo filtrado
        self.alvo = (x_a, y_a)
        # pure pursuit a partir do eixo TRASEIRO (Y = -entre-eixos)
        L = config.CARRO_ENTREEIXOS_CM
        dy = y_a + L
        ld2 = x_a * x_a + dy * dy
        delta = math.degrees(math.atan2(2.0 * L * x_a, ld2))
        turn = max(-1.0, min(1.0, config.SEG_GANHO * delta / config.ESTERCO_MAX_GRAUS))
        erro = cx(0.0)
        proa = math.degrees(math.atan((cx(y_a) - cx(y_p)) / max(1.0, y_a - y_p)))
        return turn, erro, proa
