"""
teste_pinos.py - isola defeito de fiacao/driver do L298N, SEM PWM.

    python3 teste_pinos.py          # carro SUSPENSO (rodas fora do chao!)

Para cada canal (A e B): liga o ENABLE em nivel ALTO fixo (100%, sem PWM) e aciona
IN1/IN2 (ou IN3/IN4) nos dois sentidos, 2 s cada. Voce diz se a roda girou.

Leitura do resultado:
  * gira SEM PWM mas nao gira no teste_motores.py -> problema no PWM (software) daquele pino
  * nao gira nem sem PWM                          -> fiacao, jumper do ENA/ENB, driver ou motor
  * o canal B gira e o A nao, mesmo trocando os motores de lugar nos bornes
                                                  -> canal A do L298N queimado
"""

import time

import config

try:
    import RPi.GPIO as G
except (ImportError, RuntimeError):
    raise SystemExit("RPi.GPIO indisponivel: rode no Raspberry Pi (no Pi 5 use rpi-lgpio).")

CANAIS = (("A", config.ENA, config.IN1, config.IN2),
          ("B", config.ENB, config.IN3, config.IN4))


def main():
    if input("Rodas FORA DO CHAO? (s/n) ").strip().lower() != "s":
        return
    G.setmode(G.BCM)
    G.setwarnings(False)
    print("Pinos (BCM): " + " | ".join(f"{n}: EN {en} IN {a}/{b}" for n, en, a, b in CANAIS))
    try:
        for nome, en, a, b in CANAIS:
            for p in (en, a, b):
                G.setup(p, G.OUT, initial=G.LOW)
            for rotulo, va, vb in (("sentido 1", G.HIGH, G.LOW), ("sentido 2", G.LOW, G.HIGH)):
                input(f"\nEnter: canal {nome}, {rotulo} (EN fixo em ALTO, sem PWM) por 2 s...")
                G.output(a, va)
                G.output(b, vb)
                G.output(en, G.HIGH)
                time.sleep(2.0)
                G.output(en, G.LOW)
                G.output(a, G.LOW)
                G.output(b, G.LOW)
                r = input(f"  A roda do canal {nome} girou? (s/n) ").strip().lower()
                print("  ok" if r == "s" else "  -> NAO girou")
    except KeyboardInterrupt:
        print("\nInterrompido.")
    finally:
        for _, en, a, b in CANAIS:
            for p in (en, a, b):
                G.output(p, G.LOW)
        G.cleanup()


if __name__ == "__main__":
    main()
