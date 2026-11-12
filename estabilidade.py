"""
estabilidade.py - deixa a MEDIDA da faixa (erro lateral e proa) estavel antes de chegar ao volante.

Problema: a leitura da faixa as vezes pula de um quadro pro outro (linha identificada no lugar
errado, linha curta com inclinacao ruidosa). O controle (Stanley) obedece a medida na hora, e o
volante vai de um batente ao outro. Aqui a medida passa por 3 etapas:

  1. LIMITE      : a medida nunca passa de +-limite (a proa de 40 graus e quase sempre erro de leitura).
  2. MEDIANA DE 3: um quadro isolado muito diferente dos vizinhos e descartado.
  3. PORTAO DE PULO: se a medida muda mais que `pulo` entre um quadro e outro, SEGURA o valor
                     anterior. So aceita a mudanca se ela persistir por `quadros_pulo` quadros
                     seguidos (mudanca real, nao ruido).
  4. FILTRO EM TEMPO: media movel exponencial com constante de tempo tau_s (igual em qualquer FPS).

Tudo em tempo (segundos) e nao em quadros, pra se comportar igual a 10, 15 ou 30 FPS.
"""

import math
from collections import deque


def _mediana3(v):
    s = sorted(v)
    return s[len(s) // 2]


class MedidaEstavel:
    def __init__(self, tau_s, pulo, quadros_pulo=3, limite=None):
        self.tau_s = float(tau_s)
        self.pulo = float(pulo)
        self.quadros_pulo = int(quadros_pulo)
        self.limite = None if limite is None else float(limite)
        self.reset()

    def reset(self):
        self._hist = deque(maxlen=3)
        self.valor = None
        self._pulos = 0
        self._cand = None            # valor candidato (a 'nova posicao') que o portao esta testando
        self.rejeitadas = 0          # quadros segurados pelo portao (so estatistica/log)

    def atualizar(self, x, dt):
        x = float(x)
        if self.limite is not None:
            x = max(-self.limite, min(self.limite, x))
        self._hist.append(x)
        if len(self._hist) < 3:
            # aquecimento: com menos de 3 leituras nao da pra saber qual e o pulo. Devolve 0 (sem
            # correcao) em vez de seguir uma leitura que pode ser ruido - ex.: a 1a depois de achar a faixa.
            return 0.0 if self.valor is None else self.valor
        med = _mediana3(self._hist)
        if self.valor is None:
            self.valor = med
            return self.valor
        if abs(med - self.valor) > self.pulo:
            # Mudanca real e CONSISTENTE (os quadros concordam entre si); ruido muda de valor e de
            # sinal a cada quadro. So conta como 'persistiu' se o novo valor for parecido com o anterior.
            if self._cand is not None and abs(med - self._cand) <= 0.5 * self.pulo:
                self._pulos += 1
            else:
                self._pulos = 1
            self._cand = med
            if self._pulos < self.quadros_pulo:
                self.rejeitadas += 1
                return self.valor            # segura: pode ser so um pulo de leitura
        else:
            self._pulos = 0
            self._cand = None
        a = 1.0 - math.exp(-max(dt, 1e-3) / max(self.tau_s, 1e-3))
        self.valor += a * (med - self.valor)
        return self.valor
