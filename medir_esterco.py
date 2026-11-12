"""
medir_esterco.py - mede quanto a roda REALMENTE vira (com o carro andando, no seu piso) e grava no config.py.

    python3 medir_esterco.py --entre-eixos 20
    python3 medir_esterco.py --entre-eixos 20 --vel 0.6 --tempo 6

Por que: o controle calcula o angulo de roda certo pra fazer a curva, mas converte isso em comando de servo
supondo que o volante todo vira a roda ESTERCO_MAX_GRAUS. Se a roda vira menos (folga, servo fraco, piso que
escorrega), toda curva sai ABERTA. Aqui o carro mostra o esterco real.

COMO:
  1. Meca a distancia entre o eixo da frente e o de tras (centro das rodas), em cm: --entre-eixos.
  2. Carro no chao, com uns 2,5 m livres em volta. Marque no chao onde ele esta (fita).
  3. O carro anda em CIRCULO com o volante todo pra DIREITA. Observe o circulo que ele faz.
  4. Meca o DIAMETRO do circulo (de um lado ao outro do trajeto do centro do carro), em cm, e digite.
  5. Repete pra ESQUERDA.
O script calcula o esterco real (raio = diametro/2, angulo = atan(entre-eixos / raio)) e grava
ESTERCO_MAX_GRAUS, CARRO_ENTREEIXOS_CM e SEG_GANHO = 1.0 no config.py.
"""

import argparse
import math
import os
import re
import time

import config
import hardware

CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")


def gravar(chave, valor, comentario):
    s = open(CFG, encoding="utf-8").read()
    s, n = re.subn(rf"^{chave}\s*=\s*[-\d.]+.*$", f"{chave} = {valor}    # {comentario}", s, count=1, flags=re.M)
    if n:
        open(CFG, "w", encoding="utf-8").write(s)
    return bool(n)


def volta(servo, motores, turn, vel, tempo):
    for i in (3, 2, 1):
        print(f"  largando em {i}...")
        time.sleep(1.0)
    servo.virar(turn)
    time.sleep(0.4)                       # servo chega na posicao antes de andar
    motores.andar_por(vel, tempo)
    motores.parar()
    servo.virar(0.0)


def ler_diametro(lado):
    while True:
        r = input(f"Diametro do circulo pra {lado} (cm; 'r' = repetir; 'x' = nao virou/pular): ").strip().lower()
        if r in ("r", "x"):
            return r
        try:
            d = float(r.replace(",", "."))
            if d > 0:
                return d
        except ValueError:
            pass
        print("  digite um numero em cm, 'r' ou 'x'.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entre-eixos", type=float, required=True, help="eixo da frente ao de tras (cm)")
    ap.add_argument("--vel", type=float, default=config.VELOCIDADE_BASE, help="potencia (use a de corrida)")
    ap.add_argument("--tempo", type=float, default=6.0, help="segundos andando em circulo")
    ap.add_argument("--simulado", action="store_true")
    a = ap.parse_args()
    L = a.entre_eixos
    vel = max(config.PISO_MOTOR_MIN, min(1.0, a.vel))

    servo = hardware.Servo(simulado=a.simulado)
    motores = hardware.Motores(simulado=a.simulado)
    angulos = {}
    try:
        for lado, turn in (("DIREITA", 1.0), ("ESQUERDA", -1.0)):
            while True:
                input(f"\nCarro no chao, area livre de ~2,5 m. Enter pra andar {a.tempo:.0f} s em circulo pra {lado}...")
                volta(servo, motores, turn, vel, a.tempo)
                d = ler_diametro(lado.lower())
                if d == "r":
                    continue
                if d == "x":
                    print("  (pulei este lado)")
                    break
                raio = d / 2.0
                ang = math.degrees(math.atan(L / raio))
                angulos[lado] = ang
                print(f"  -> raio {raio:.0f} cm: a roda vira de verdade {ang:.1f} graus pra {lado.lower()}")
                break
    except KeyboardInterrupt:
        print("\nInterrompido.")
    finally:
        motores.fechar()
        servo.fechar()
        hardware.limpar()

    if not angulos:
        print("\nNada medido. Se o carro NAO faz circulo com o volante todo virado, o problema e mecanico: "
              "bracinho do servo solto, tirante com folga, ou o piso escorrega demais.")
        return 1
    real = sum(angulos.values()) / len(angulos)
    print(f"\nEsterco real medio: {real:.1f} graus (o config supunha {config.ESTERCO_MAX_GRAUS:.0f}).")
    if len(angulos) == 2 and abs(angulos["DIREITA"] - angulos["ESQUERDA"]) > 4:
        print(f"  Aviso: direita {angulos['DIREITA']:.0f} e esquerda {angulos['ESQUERDA']:.0f} graus diferem bastante; "
              "uso a media. Curvas pro lado mais fraco saem um pouco mais abertas.")
    if real < 10:
        print(f"  Aviso: so {real:.0f} graus. Raio minimo do carro ~{L / math.tan(math.radians(real)):.0f} cm: "
              "curvas mais fechadas que isso sao IMPOSSIVEIS pra ele, nenhum ajuste de software resolve.")
    ok = gravar("ESTERCO_MAX_GRAUS", f"{real:.1f}", "medido por medir_esterco.py (roda real, andando)")
    ok &= gravar("CARRO_ENTREEIXOS_CM", f"{L:.1f}", "medido")
    ok &= gravar("SEG_GANHO", "1.0", "esterco real medido: ganho 1 = geometria pura")
    print("Gravado no config.py." if ok else "NAO consegui gravar tudo no config.py: edite ESTERCO_MAX_GRAUS, "
          "CARRO_ENTREEIXOS_CM e SEG_GANHO na mao.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
