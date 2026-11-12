"""
balanco.py - ajusta MOTOR_A_FATOR / MOTOR_B_FATOR pra o carro andar RETO.

    python3 balanco.py                  # carro no chao, area livre a frente
    python3 balanco.py --vel 0.6

Anda 2 s pra frente com o volante centrado. Voce diz pra onde o carro foi:
    e = esquerda  -> o motor DIREITO esta mais forte, baixa B_FATOR 0.05
    d = direita   -> o motor ESQUERDO esta mais forte, baixa A_FATOR 0.05
    r = reto      -> fim, grava em dados/balanco.json e no config.py
Repita ate ir reto. Ctrl+C para na hora.
"""

import argparse
import json
import os
import time

import config
import hardware

ARQ = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados", "balanco.json")


def carregar():
    try:
        with open(ARQ, encoding="utf-8") as f:
            d = json.load(f)
        return float(d["a"]), float(d["b"])
    except (OSError, ValueError, KeyError):
        return 1.0, 1.0


def salvar(a, b):
    os.makedirs(os.path.dirname(ARQ), exist_ok=True)
    with open(ARQ, "w", encoding="utf-8") as f:
        json.dump({"a": round(a, 3), "b": round(b, 3)}, f, indent=2)


def aplicar_no_config(a, b):
    """Reescreve as duas linhas MOTOR_*_FATOR no config.py pra persistir entre corridas."""
    cfg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")
    s = open(cfg, encoding="utf-8").read()
    import re
    s, nA = re.subn(r"^MOTOR_A_FATOR = [\d.]+.*$",
                    f"MOTOR_A_FATOR = {a:.3f}         # ajustado por balanco.py",
                    s, count=1, flags=re.M)
    s, nB = re.subn(r"^MOTOR_B_FATOR = [\d.]+.*$",
                    f"MOTOR_B_FATOR = {b:.3f}         # ajustado por balanco.py",
                    s, count=1, flags=re.M)
    if nA and nB:
        open(cfg, "w", encoding="utf-8").write(s)
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vel", type=float, default=0.65)
    ap.add_argument("--tempo", type=float, default=2.0)
    ap.add_argument("--simulado", action="store_true")
    a = ap.parse_args()
    vel = max(0.3, min(1.0, a.vel))

    fa, fb = carregar()
    # relê para pegar valores atuais do config.py (caso o balanco.json nao exista)
    fa = config.MOTOR_A_FATOR if (fa, fb) == (1.0, 1.0) else fa
    fb = config.MOTOR_B_FATOR if (fa, fb) == (1.0, 1.0) else fb
    print(f"Comecando com A={fa:.2f}  B={fb:.2f}  (esquerdo/direito)")

    servo = None
    try:
        servo = hardware.Servo(simulado=a.simulado)
    except Exception as e:
        print(f"(servo nao abriu: {e}; segue sem servo)")
    motores = hardware.Motores(simulado=a.simulado)
    print("Carro RETO, na pista ou em area livre. Ctrl+C para na hora.")
    try:
        while True:
            config.MOTOR_A_FATOR, config.MOTOR_B_FATOR = fa, fb
            try:
                input(f"\nEnter pra andar {a.tempo:.1f}s a {vel:.0%}  [A={fa:.2f}  B={fb:.2f}]... ")
            except EOFError:
                break
            for i in (3, 2, 1):
                print(f"  {i}...")
                time.sleep(1.0)
            motores.andar_por(vel, a.tempo)
            motores.parar()
            r = input("Pra onde foi? (e=esquerda / d=direita / r=reto / q=sair) ").strip().lower()
            if r == "q":
                break
            if r == "r":
                salvar(fa, fb)
                if aplicar_no_config(fa, fb):
                    print(f"Gravei A={fa:.3f}  B={fb:.3f} no config.py e em dados/balanco.json")
                else:
                    print(f"Gravei em dados/balanco.json. Edite MOTOR_A_FATOR/MOTOR_B_FATOR no config.py.")
                break
            if r == "e":
                fb = max(0.3, fb - 0.05)   # desviou pra esquerda: direito mais forte, abaixa B
            elif r == "d":
                fa = max(0.3, fa - 0.05)   # desviou pra direita: esquerdo mais forte, abaixa A
    except KeyboardInterrupt:
        print("\nInterrompido.")
    finally:
        motores.fechar()
        if servo is not None:
            servo.fechar()
        hardware.limpar()


if __name__ == "__main__":
    main()
