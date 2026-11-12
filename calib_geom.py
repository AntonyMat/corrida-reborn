"""
calib_geom.py - ajusta a GEOMETRIA da camera (inclinacao, campo de visao, guinada) a partir de quadros
do carro PARADO, ALINHADO com a faixa.

Principio: com a geometria certa, na vista de cima as linhas da pista ficam
  * PARALELAS ao eixo do carro (inclinacao ~ 0 se o carro esta alinhado), e
  * IGUALMENTE ESPACADAS: a distancia entre linhas vizinhas e a LARGURA REAL da faixa, tanto perto
    quanto longe (se a inclinacao esta errada, o espacamento muda com a distancia: o "V").

A ALTURA da lente NAO e ajustada: e uma medida fisica (regua) e fixa a escala. O CAMPO DE VISAO tambem fica
fixo por padrao: numa pista reta ele e ambiguo com a inclinacao (um erro de fov e absorvido pela inclinacao
sem mudar onde as linhas aparecem, que e o que o controle usa). Para ajustar fov: livres=(..., "fov_h").

Custo (menor = melhor):  media por quadro de
    soma_pares [ ((esp_perto - W)/W)^2 + ((esp_longe - W)/W)^2 ]   +   soma_linhas (inclinacao_da_linha / 0.5)^2
Busca: descida por coordenadas com passo que diminui (so numpy, roda no Raspberry).
"""

import math

import numpy as np

import config
from faixas import DetectorFaixas
from geometria import CameraChao

# fov_h NAO entra por padrao: com altura fixa e pista reta, campo de visao e inclinacao se COMPENSAM (o custo
# fica ~igual dos dois jeitos), entao os quadros nao tem informacao pra separar. Fica o valor da ficha da camera.
LIVRES_PADRAO = ("inclinacao", "guinada")
LIMITES = {"inclinacao": (12.0, 60.0), "fov_h": (45.0, 100.0), "guinada": (-10.0, 10.0),
           "rolagem": (-6.0, 6.0)}
PASSO0 = {"inclinacao": 4.0, "fov_h": 6.0, "guinada": 2.0, "rolagem": 1.5}
PENALIDADE = 5.0            # custo de um quadro em que nao deu pra medir (menos de 2 linhas boas)


def medir(params, frames, W):
    """Devolve (custo, detalhe). detalhe = lista por quadro de [(x_perto, x_longe)] ordenado."""
    try:
        cam = CameraChao(params, config.CAMERA_RES)
    except ValueError:
        return PENALIDADE, []
    det = DetectorFaixas(cam)
    span = cam.y_max - cam.y_min
    y_p, y_l = cam.y_min + 10.0, cam.y_max - 10.0
    total, detalhe = 0.0, []
    for fr in frames:
        res = det.processar(fr)
        ls = [l for l in res.linhas if (l.y1 - l.y0) >= 0.4 * span]
        pts = sorted(((float(l.x(y_p)), float(l.x(y_l))) for l in ls), key=lambda t: t[0])
        detalhe.append(pts)
        if len(pts) < 2:
            total += PENALIDADE
            continue
        c, n_pares = 0.0, 0
        for (a_n, a_f), (b_n, b_f) in zip(pts, pts[1:]):
            sp_n, sp_f = b_n - a_n, b_f - a_f
            if not (0.6 * W <= sp_n <= 1.5 * W):          # par que nao e vizinho (faltou uma linha): ignora
                continue
            c += ((sp_n - W) / W) ** 2 + ((sp_f - W) / W) ** 2
            n_pares += 1
        if n_pares == 0:
            total += PENALIDADE
            continue
        for (xn, xf) in pts:
            c += (((xf - xn) / (y_l - y_p)) / 0.5) ** 2
        total += c
    return total / max(1, len(frames)), detalhe


def ajustar(params, frames, W, livres=LIVRES_PADRAO, rodadas=7, log=None):
    """Descida por coordenadas. Devolve (novos_params, custo_antes, custo_depois)."""
    p = dict(params)
    melhor, _ = medir(p, frames, W)
    antes = melhor
    passo = {k: PASSO0[k] for k in livres}
    for r in range(rodadas):
        mudou = False
        for k in livres:
            lo, hi = LIMITES[k]
            for sinal in (+1.0, -1.0):
                while True:
                    cand = dict(p)
                    cand[k] = min(hi, max(lo, p[k] + sinal * passo[k]))
                    if cand[k] == p[k]:
                        break
                    c, _ = medir(cand, frames, W)
                    if c < melhor - 1e-9:
                        p, melhor, mudou = cand, c, True      # continua andando nesse sentido
                    else:
                        break
        if log:
            log(f"  rodada {r + 1}: custo {melhor:.4f}  " +
                " ".join(f"{k} {p[k]:.1f}" for k in livres))
        for k in livres:
            passo[k] *= 0.5
    return p, antes, melhor


def descrever(params, frames, W):
    """Texto com as linhas medidas (perto/longe) e inclinacao de cada uma, no ultimo quadro bom."""
    custo, det = medir(params, frames, W)
    cam = CameraChao(params, config.CAMERA_RES)
    y_p, y_l = cam.y_min + 10.0, cam.y_max - 10.0
    for pts in reversed(det):
        if len(pts) >= 2:
            partes = []
            for xn, xf in pts:
                ang = math.degrees(math.atan((xf - xn) / (y_l - y_p)))
                partes.append(f"x {xn:+5.1f}cm (inclin. {ang:+4.1f}deg)")
            esp = [f"{b[0] - a[0]:.1f}/{b[1] - a[1]:.1f}" for a, b in zip(pts, pts[1:])]
            return (f"custo {custo:.4f} | linhas: " + " ; ".join(partes) +
                    f" | espacamento perto/longe: {' , '.join(esp)} cm (alvo {W:.1f})")
    return f"custo {custo:.4f} | nao achei 2 linhas boas"
