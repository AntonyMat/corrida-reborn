"""
calibrar_geometria.py - calibra a camera SEM TELA, com o carro PARADO na faixa.

    python3 calibrar_geometria.py --altura 31.5 --largura 28.5            # so mostra antes/depois
    python3 calibrar_geometria.py --altura 31.5 --largura 28.5 --salvar   # grava dados/camera.json

MEDIDAS (com regua):
  --altura   altura da LENTE ate o chao, em cm        (fixa a escala: o programa NAO mexe nela)
  --largura  distancia entre duas linhas vizinhas da pista, de CENTRO a CENTRO da tinta, em cm

COMO POSICIONAR O CARRO: parado, na faixa do carro, com a continua de um lado e a pontilhada do outro,
ALINHADO com as linhas (a distancia do lado do carro ate a linha tem que ser a mesma na frente e atras).
A guinada da camera e ajustada assumindo que o carro esta alinhado: carro torto = guinada errada.

O programa ajusta INCLINACAO e GUINADA pra as linhas ficarem paralelas e na largura certa (ver calib_geom.py).
O campo de visao fica o do config.py (CAM_FOV_H): com altura fixa e pista reta ele e ambiguo com a inclinacao.
"""

import argparse
import time

import config
import geometria
from calib_geom import ajustar, descrever, medir
from camera import abrir_camera, ajustar as ajustar_quadro, CameraThread

CUSTO_MAX_PRA_SALVAR = 0.05


def capturar(th, n=8, intervalo=0.15):
    quadros, ultimo = [], -1
    t0 = time.monotonic()
    while len(quadros) < n and time.monotonic() - t0 < 15.0:
        f, idx, idade = th.read()
        if f is not None and idx != ultimo and idade < 0.5:
            ultimo = idx
            quadros.append(ajustar_quadro(f).copy())
            time.sleep(intervalo)
        else:
            time.sleep(0.01)
    return quadros


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--altura", type=float, default=None, help="altura da lente ao chao (cm). Medida com regua")
    ap.add_argument("--largura", type=float, default=None, help="distancia entre linhas vizinhas, centro a centro (cm)")
    ap.add_argument("--camera", default=None, help="numero da camera ou caminho de uma foto/video")
    ap.add_argument("--salvar", action="store_true", help="grava dados/camera.json se o resultado for bom")
    ap.add_argument("--ajustar-fov", action="store_true", help="tambem ajusta o campo de visao (ambiguo, nao recomendado)")
    a = ap.parse_args()

    params, origem = geometria.carregar_parametros()
    if a.altura is not None:
        params["altura_cm"] = a.altura
    W = a.largura if a.largura is not None else config.FAIXA_LARGURA_CM
    print(f"Geometria inicial ({origem}): altura {params['altura_cm']:.1f}cm inclinacao {params['inclinacao']:.1f} "
          f"fov {params['fov_h']:.1f} guinada {params['guinada']:.1f}  | largura da faixa: {W:.1f}cm")
    if a.altura is None:
        print("AVISO: sem --altura o programa usa a do config.py. Meca a lente ao chao com regua: a escala depende disso.")
    if a.largura is None:
        print("AVISO: sem --largura uso FAIXA_LARGURA_CM do config.py. Meca de centro a centro das linhas.")

    cap = abrir_camera(a.camera)
    if not cap.isOpened():
        print("ERRO: a camera nao abriu.")
        return 1
    th = CameraThread(cap, reabrir=None)
    try:
        t0 = time.monotonic()
        while th.read()[0] is None and time.monotonic() - t0 < 6.0:
            time.sleep(0.05)
        quadros = capturar(th)
    finally:
        th.release()
    if len(quadros) < 4:
        print("ERRO: poucos quadros da camera. Confira o cabo/energia (teste_camera.py).")
        return 1

    print("\nANTES : " + descrever(params, quadros, W))
    custo0, det = medir(params, quadros, W)
    if all(len(p) < 2 for p in det):
        print("\nNao achei 2 linhas bem medidas. Confira se o carro esta na faixa, com a continua e a pontilhada "
              "visiveis (rode teste_camera.py).")
        return 1

    livres = ("inclinacao", "guinada") + (("fov_h",) if a.ajustar_fov else ())
    print("\nAjustando " + ", ".join(livres) + " ...")
    novo, antes, depois = ajustar(params, quadros, W, livres=livres, log=print)
    print("\nDEPOIS: " + descrever(novo, quadros, W))
    print(f"\nInclinacao {params['inclinacao']:.1f} -> {novo['inclinacao']:.1f} graus | "
          f"guinada {params['guinada']:.1f} -> {novo['guinada']:.1f} graus"
          + (f" | fov {params['fov_h']:.1f} -> {novo['fov_h']:.1f}" if a.ajustar_fov else ""))
    print(f"Custo {antes:.4f} -> {depois:.4f}  (0 = linhas paralelas e na largura exata)")

    bom = depois < antes and depois <= CUSTO_MAX_PRA_SALVAR
    if not bom:
        print("\nNAO salvei: o ajuste nao ficou bom o bastante. Possiveis causas: carro torto na faixa, largura/altura "
              "medidas erradas, ou poucas linhas visiveis.")
        return 1
    if a.salvar:
        geometria.salvar_parametros(novo)
        print(f"\nSALVO em {geometria.ARQ_CAMERA}. O principal.py ja usa esse arquivo.")
    else:
        print("\n(nao salvei; rode de novo com --salvar para gravar)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
