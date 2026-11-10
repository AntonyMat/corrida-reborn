"""
frente.py - anda SO pra frente, os dois motores juntos (sem testar um de cada vez).

    python3 frente.py                    # 80% por 5 s
    python3 frente.py --vel 1.0 --tempo 8
    python3 frente.py --simulado         # sem mexer em nada

Centraliza o servo, espera 3 s (pra voce sair da frente) e anda. Ctrl+C para na hora.
"""

import argparse
import time

import config
import hardware


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vel", type=float, default=0.8, help="potencia 0..1 (padrao 0.8)")
    ap.add_argument("--tempo", type=float, default=5.0, help="segundos andando (padrao 5)")
    ap.add_argument("--simulado", action="store_true")
    a = ap.parse_args()
    vel = max(0.0, min(1.0, a.vel))

    servo = None
    try:
        servo = hardware.Servo(simulado=a.simulado)      # roda reta
    except Exception as e:
        print(f"(servo nao abriu: {e}; segue so com os motores)")
    motores = hardware.Motores(simulado=a.simulado)
    print(f"Pinos (BCM): ENA {config.ENA} IN1 {config.IN1} IN2 {config.IN2} | "
          f"ENB {config.ENB} IN3 {config.IN3} IN4 {config.IN4}")
    print(f"Vai andar pra FRENTE a {vel:.0%} por {a.tempo:.1f} s. Ctrl+C para na hora.")
    try:
        for i in (3, 2, 1):
            print(f"  largando em {i}...")
            time.sleep(1.0)
        motores.andar_por(vel, a.tempo)
        print("Fim.")
    except KeyboardInterrupt:
        print("\nParado (Ctrl+C).")
    finally:
        motores.fechar()
        if servo is not None:
            servo.fechar()
        hardware.limpar()


if __name__ == "__main__":
    main()
