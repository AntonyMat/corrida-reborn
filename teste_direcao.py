"""
teste_direcao.py - descobre se ESTERCO_INVERTER deve ser True ou False.

    python3 teste_direcao.py            # carro no chao, area livre a frente
    python3 teste_direcao.py --vel 0.65 --tempo 1.5

Anda pra frente 1,5 s com o volante virado AO MAXIMO num lado, so com o sinal
LOGICO +1 (direita no mundo do piloto). Voce diz pra onde o carro foi.

Resultado:
    carro foi pra DIREITA  -> ESTERCO_INVERTER = False (atualiza config.py)
    carro foi pra ESQUERDA -> ESTERCO_INVERTER = True  (atualiza config.py)
    reto                   -> servo nao esta virando: cheque mecanica/servo.
"""

import argparse
import os
import re
import time

import config
import hardware

CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")


def aplicar_config(inverter: bool):
    s = open(CFG, encoding="utf-8").read()
    s, n = re.subn(r"^ESTERCO_INVERTER    = (True|False).*$",
                   f"ESTERCO_INVERTER    = {inverter}    # ajustado por teste_direcao.py",
                   s, count=1, flags=re.M)
    if n:
        open(CFG, "w", encoding="utf-8").write(s)
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vel", type=float, default=0.70)
    ap.add_argument("--tempo", type=float, default=5.0)
    ap.add_argument("--simulado", action="store_true")
    a = ap.parse_args()
    vel = max(0.4, min(1.0, a.vel))

    # Para este teste a INVERSAO fica OFF na sessao: assim o comando logico vai cru pro servo,
    # e o usuario vê qual lado fisico o servo escolhe com o sinal logico=+1 ("direita logica").
    config.ESTERCO_INVERTER = False

    servo = hardware.Servo(simulado=a.simulado)
    motores = hardware.Motores(simulado=a.simulado)
    print("Carro RETO, em area livre, ~1,5 m a frente. Ctrl+C para na hora.")
    try:
        for i in (3, 2, 1):
            print(f"  largando em {i}...")
            time.sleep(1.0)
        servo.virar(+1.0)                   # +1 = direita logica (sem inverter: servo fisico pra direita)
        motores.andar_por(vel, a.tempo)
        motores.parar()
        servo.virar(0.0)
        r = input("\nPra onde o carro foi? (d=direita / e=esquerda / r=reto): ").strip().lower()
        if r == "d":
            print("-> Direcao NORMAL: volante vai pro lado certo. Vou gravar ESTERCO_INVERTER=False.")
            ok = aplicar_config(False)
        elif r == "e":
            print("-> Direcao INVERTIDA: volante vai pro lado oposto. Vou gravar ESTERCO_INVERTER=True.")
            ok = aplicar_config(True)
        else:
            print("-> Servo nao virou: cheque mecanica (servo preso? bracinho solto?) e teste_servo.py.")
            return
        if ok:
            print("Gravado em config.py. Faca git commit se quiser subir.")
        else:
            print("NAO consegui editar config.py: edite ESTERCO_INVERTER manualmente.")
    except KeyboardInterrupt:
        print("\nInterrompido.")
    finally:
        motores.fechar()
        servo.fechar()
        hardware.limpar()


if __name__ == "__main__":
    main()
