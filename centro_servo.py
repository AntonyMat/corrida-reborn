"""
centro_servo.py - acha o angulo em que as rodas da frente apontam RETO e grava no config.py.

    python3 centro_servo.py            # rodas fora do chao ou carro parado: so olhe as rodas da frente

Por que importa: se o centro configurado (SERVO_CENTRO_PADRAO) nao e o centro real, o volante fica torto
de fabrica: o carro puxa pra um lado e o controle oscila tentando compensar.

Comandos (digite e Enter):
    +  / -        sobe / desce 1 grau
    ++ / --       sobe / desce 5 graus
    um numero     vai direto pra esse angulo (ex.: 31)
    s             SALVA este angulo como o centro (reto) no config.py e sai
    q             sai sem salvar
Olhe a roda da frente de cima: o angulo certo e aquele em que ela fica paralela ao corpo do carro.
"""

import argparse
import os
import re

import config
import hardware

CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")
LIM = (config.SERVO_LIMITE_ABS[0], config.SERVO_LIMITE_ABS[1])


def gravar(angulo):
    s = open(CFG, encoding="utf-8").read()
    s, n = re.subn(r"^SERVO_CENTRO_PADRAO\s*=\s*[\d.]+.*$",
                   f"SERVO_CENTRO_PADRAO   = {angulo:.1f}    # ajustado por centro_servo.py (rodas retas)",
                   s, count=1, flags=re.M)
    if n:
        open(CFG, "w", encoding="utf-8").write(s)
    return bool(n)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--simulado", action="store_true")
    a = ap.parse_args()

    servo = hardware.Servo(simulado=a.simulado)
    ang = float(config.SERVO_CENTRO_PADRAO)
    print(__doc__)
    print(f"Centro configurado agora: {ang:.1f} graus (esquerda {config.SERVO_ESQ_PADRAO:.0f}, "
          f"direita {config.SERVO_DIR_PADRAO:.0f}).")
    try:
        while True:
            ang = max(LIM[0], min(LIM[1], ang))
            servo.angulo(ang, forcar=True)
            cmd = input(f"\nservo em {ang:.1f} graus. (+ - ++ -- numero / s salva / q sai): ").strip().lower()
            if cmd == "+":
                ang += 1.0
            elif cmd == "-":
                ang -= 1.0
            elif cmd == "++":
                ang += 5.0
            elif cmd == "--":
                ang -= 5.0
            elif cmd == "s":
                if gravar(ang):
                    print(f"Gravei SERVO_CENTRO_PADRAO = {ang:.1f} no config.py. "
                          f"Curso: esquerda {ang - config.SERVO_ESQ_PADRAO:.0f}, direita {config.SERVO_DIR_PADRAO - ang:.0f} graus.")
                else:
                    print(f"NAO consegui editar o config.py. Edite SERVO_CENTRO_PADRAO = {ang:.1f} na mao.")
                break
            elif cmd == "q":
                print("Saiu sem salvar.")
                break
            else:
                try:
                    ang = float(cmd.replace(",", "."))
                except ValueError:
                    print("  nao entendi.")
    except (KeyboardInterrupt, EOFError):
        print("\nInterrompido (nao salvei).")
    finally:
        servo.fechar()
        hardware.limpar()


if __name__ == "__main__":
    main()
