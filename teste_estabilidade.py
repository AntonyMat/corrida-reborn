"""
teste_estabilidade.py - confere que a estabilizacao da medida acalma o volante (sem carro, sem camera).

    python3 teste_estabilidade.py

Cenario: o carro esta REALMENTE reto e centrado (erro 0, proa 0), mas a leitura da faixa pula de vez em
quando, como no log real (proa +-20..40 graus, erro +-10..40 cm em quadros isolados ou em pares).
Compara o volante com a medida CRUA (como era) e com a medida ESTABILIZADA (como e agora).
Tambem confere que uma mudanca REAL (curva: erro cresce de verdade) ainda passa.
Sai com codigo 1 se a estabilizacao nao melhorar o suficiente.
"""

import math
import random
import sys

import config
from controle import Direcao
from estabilidade import MedidaEstavel

FPS = 15.0
DT = 1.0 / FPS
V_CMS = 0.58 * config.V_CMS_NA_VEL_1


def medida_ruidosa(n, seed=1):
    """(erro_cm, proa_graus) por quadro: verdade = 0, com pulos de leitura."""
    r = random.Random(seed)
    out, i = [], 0
    while i < n:
        if r.random() < 0.18:                       # pulo de 1 ou 2 quadros
            dur = r.choice((1, 1, 2))
            e = r.choice((-1, 1)) * r.uniform(10, 40)
            p = r.choice((-1, 1)) * r.uniform(15, 42)
            out += [(e, p)] * dur
            i += dur
        else:
            out.append((r.gauss(0, 0.6), r.gauss(0, 1.5)))
            i += 1
    return out[:n]


def rodar(medidas, estabilizar):
    d = Direcao()
    fe = MedidaEstavel(config.ERRO_TAU_S, config.MEDIDA_PULO_ERRO_CM, config.MEDIDA_PULO_QUADROS)
    fp = MedidaEstavel(config.PROA_TAU_S, config.MEDIDA_PULO_PROA_GRAUS, config.MEDIDA_PULO_QUADROS,
                       limite=config.PROA_MAX_GRAUS)
    turns = []
    for e, p in medidas:
        if estabilizar:
            e, p = fe.atualizar(e, DT), fp.atualizar(p, DT)
        d.atualizar(DT, e, math.radians(p), V_CMS)
        turns.append(d.turn)
    pico = max(abs(t) for t in turns)
    curso = sum(abs(b - a) for a, b in zip(turns, turns[1:]))          # quanto o volante andou no total
    fora = sum(1 for t in turns if abs(t) > 0.3) / len(turns)          # fracao do tempo com volante bem virado
    return pico, curso / (len(turns) * DT), fora


def resposta_a_curva(estabilizar):
    """Erro cresce de verdade (0 -> 20 cm em 1 s) e fica la: o volante precisa reagir e chegar perto do alvo."""
    d = Direcao()
    fe = MedidaEstavel(config.ERRO_TAU_S, config.MEDIDA_PULO_ERRO_CM, config.MEDIDA_PULO_QUADROS)
    fp = MedidaEstavel(config.PROA_TAU_S, config.MEDIDA_PULO_PROA_GRAUS, config.MEDIDA_PULO_QUADROS,
                       limite=config.PROA_MAX_GRAUS)
    t_reage = None
    for k in range(int(3.0 * FPS)):
        t = k * DT
        e = min(20.0, 20.0 * t)
        p = 0.0
        if estabilizar:
            e, p = fe.atualizar(e, DT), fp.atualizar(p, DT)
        d.atualizar(DT, e, math.radians(p), V_CMS)
        if t_reage is None and d.turn >= 0.3:
            t_reage = t
    return t_reage, d.turn


def main():
    n = int(60 * FPS)
    m = medida_ruidosa(n)
    pico0, curso0, fora0 = rodar(m, False)
    pico1, curso1, fora1 = rodar(m, True)
    print("Carro RETO e centrado, leitura da faixa com pulos (60 s a %.0f FPS):" % FPS)
    print(f"  medida CRUA        : volante anda {curso0:.2f} do curso por segundo, fica >0.3 em {fora0:.0%} do tempo (pico {pico0:.2f})")
    print(f"  medida ESTABILIZADA: volante anda {curso1:.2f} do curso por segundo, fica >0.3 em {fora1:.0%} do tempo (pico {pico1:.2f})")
    print("  (o gerador corrompe ~24% dos quadros; rajadas de 3+ quadros iguais passam de proposito: sao indistinguiveis de uma mudanca real)")
    r0, f0 = resposta_a_curva(False)
    r1, f1 = resposta_a_curva(True)
    print("Curva REAL (erro 0 -> 20 cm em 1 s):")
    print(f"  crua         : volante passa de 0.3 em {r0:.2f} s, termina em {f0:.2f}")
    print(f"  estabilizada : volante passa de 0.3 em {r1:.2f} s, termina em {f1:.2f}")

    ok = True
    # M2 (config.py): escolhido por varredura no simulador pra NAO perder margem de estabilidade nas curvas.
    # O custo e filtrar menos: o curso do volante cai ~3x, o tempo bem virado cai ~1/3 (nao pela metade).
    if fora1 > 0.8 * fora0:
        print("FALHOU: o volante continua muito tempo virado.");  ok = False
    if curso1 > 0.4 * curso0:
        print("FALHOU: o volante continua andando demais."); ok = False
    if r1 is None or r1 > 1.5 or f1 < 0.4:
        print("FALHOU: a estabilizacao deixou o volante lento demais pra uma curva real."); ok = False
    print("OK: volante mais calmo e ainda reage a curva real." if ok else "")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
