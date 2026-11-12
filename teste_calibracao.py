"""
teste_calibracao.py - valida calib_geom.py contra cameras SIMULADAS com erro conhecido.

    python3 teste_calibracao.py

Para cada caso: a camera "real" tem inclinacao/campo de visao/guinada diferentes dos supostos.
O ajuste recebe so os quadros e os valores supostos (os de fabrica) e tem que chegar perto dos reais.
Sai com codigo 1 se algum caso nao melhorar o custo ou errar muito.
"""

import os
import sys

import config
import sim
from calib_geom import ajustar, medir
from geometria import CameraChao, parametros_padrao

CASOS = (
    # nome, mudancas na camera REAL em relacao aos valores supostos (de fabrica)
    ("inclinacao +8",            {"inclinacao": +8.0}),
    ("inclinacao -8",            {"inclinacao": -8.0}),
    ("fov -8",                   {"fov_h": -8.0}),
    ("guinada +3",               {"guinada": +3.0}),
    ("inclinacao +6, fov -6, guinada +2", {"inclinacao": +6.0, "fov_h": -6.0, "guinada": +2.0}),
)
TOL = {"inclinacao": 2.5, "guinada": 1.0}      # so os parametros que a calibracao ajusta
TOL_POS_CM = 1.5                               # erro maximo da posicao das linhas na vista de cima


def quadros(real, n=5):
    pista = sim.Pista([(150.0, 0.0), (250.0, 0.0)])
    rend = sim.Renderizador(CameraChao(real, config.CAMERA_RES), config.CAMERA_RES)
    carro = sim.Carro(pista)
    return [rend.quadro(pista, carro) for _ in range(n)], pista.W


def erro_posicao(params, frames, W):
    """Maior erro (cm) entre onde as 2 linhas APARECEM na vista de cima e onde estao de verdade
    (-W/2 e +W/2, carro centrado e reto), perto e longe. E isso que o controle usa."""
    _, det = medir(params, frames, W)
    pts = next((p for p in reversed(det) if len(p) == 2), None)
    if pts is None:
        return 99.0
    alvo = (-W / 2.0, +W / 2.0)
    return max(abs(x - a) for (xn, xf), a in zip(pts, alvo) for x in (xn, xf))


def main():
    base = parametros_padrao()
    ok_geral = True
    for nome, delta in CASOS:
        real = dict(base)
        for k, v in delta.items():
            real[k] += v
        frames, W = quadros(real)
        c0, _ = medir(base, frames, W)
        novo, antes, depois = ajustar(base, frames, W)
        e0, e1 = erro_posicao(base, frames, W), erro_posicao(novo, frames, W)
        # parametros so sao cobrados quando o caso nao mexe no fov (o fov e ambiguo com a inclinacao)
        recupera = "fov_h" in delta or all(abs(novo[k] - real[k]) <= TOL[k] for k in TOL)
        ok = depois < antes and e1 <= TOL_POS_CM and recupera
        ok_geral &= ok
        print(f"[{'OK ' if ok else 'FALHA'}] {nome:36s} custo {antes:.3f} -> {depois:.3f} | "
              f"erro de posicao das linhas {e0:4.1f} -> {e1:3.1f} cm | "
              + " ".join(f"{k} real {real[k]:.1f} achei {novo[k]:.1f}" for k in TOL))
    print("\nTodos os casos recuperaram a camera." if ok_geral else "\nAlgum caso falhou.")
    sys.exit(0 if ok_geral else 1)


if __name__ == "__main__":
    main()
