"""
teste_camera.py - confere a CAMERA e a leitura da faixa, SEM tela e SEM mover nada.

    python3 teste_camera.py                  # camera do config (CAMERA_ID)
    python3 teste_camera.py --camera 2       # outra camera
    python3 teste_camera.py --camera foto.jpg

Faz: abre a camera, mede o FPS por 3 s, roda o detector de faixas em ~10 quadros e
salva em teste_camera_saida/:
    quadro.jpg  = o que a camera ve (ja ajustada: giro/espelho do config)
    bev.jpg     = vista de cima com a mascara das linhas (verde) e as linhas achadas
Abra os dois (scp pro PC, ou pelo desktop do Pi) e confira se as linhas da pista aparecem.
"""

import argparse
import os
import time

import cv2

import config
from camera import abrir_camera, ajustar, CameraThread
from geometria import carregar_parametros
from piloto import Piloto
import visual

PASTA = "teste_camera_saida"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", default=None)
    a = ap.parse_args()

    cap = abrir_camera(a.camera)
    if not cap.isOpened():
        print("ERRO: a camera nao abriu. Veja:  v4l2-ctl --list-devices   (e CAMERA_ID no config.py)")
        return
    th = CameraThread(cap, reabrir=None)
    try:
        t0 = time.monotonic()
        while th.read()[0] is None and time.monotonic() - t0 < 6.0:
            time.sleep(0.05)
        if th.read()[0] is None:
            print("ERRO: a camera abriu mas NAO entrega quadros.\n"
                  "  - outro programa usando?  pkill -f principal.py\n"
                  "  - falta de energia?       vcgencmd get_throttled   (0x0 = ok)\n"
                  "  - troque a porta/cabo USB (USB 3 azul, cabo curto)")
            return

        # FPS real de captura
        idx0, t0 = th.read()[1], time.monotonic()
        time.sleep(3.0)
        _, idx1, idade = th.read()
        fps = (idx1 - idx0) / (time.monotonic() - t0)
        print(f"Captura: {fps:.1f} FPS, quadro mais novo tem {idade * 1000:.0f} ms")
        if fps < 5:
            print("  AVISO: FPS muito baixo (USB lento, pouca luz ou falta de energia).")

        params, origem = carregar_parametros()
        piloto = Piloto(params, config.CAMERA_RES)
        print(f"Geometria ({origem}): {piloto.cam.resumo()}")

        ok = 0
        motivos = {}
        ultimo = -1
        t = time.monotonic()
        for _ in range(10):
            while True:
                f, idx, _ = th.read()
                if idx != ultimo:
                    ultimo = idx
                    break
                time.sleep(0.01)
            frame = ajustar(f)
            t = time.monotonic()
            piloto.step(t, frame, fps=fps, debug=True)
            if piloto.motivo == "ok":
                ok += 1
            else:
                motivos[piloto.motivo] = motivos.get(piloto.motivo, 0) + 1

        os.makedirs(PASTA, exist_ok=True)
        cv2.imwrite(os.path.join(PASTA, "quadro.jpg"), piloto.frame_proc)
        cv2.imwrite(os.path.join(PASTA, "bev.jpg"), visual.desenhar_bev(piloto))
        print(f"Faixa lida em {ok}/10 quadros", end="")
        if motivos:
            print("  (falhas: " + ", ".join(f"{m} x{n}" for m, n in motivos.items()) + ")")
        else:
            print()
        r = piloto.res
        if r is not None and r.linhas:
            print("Linhas: " + " ".join(f"{l.ident or '?'}:{l.x_ref:+.0f}cm({l.classe or '?'})" for l in r.linhas))
        print(f"Imagens salvas em {os.path.abspath(PASTA)}/ (quadro.jpg e bev.jpg)")
        if ok == 0:
            print("Nao achou a faixa: confira se a camera aponta pra pista, a luz, e a altura/inclinacao "
                  "(CAM_ALTURA_CM / CAM_INCLINACAO no config.py).")
    finally:
        th.release()


if __name__ == "__main__":
    main()
