"""
principal.py - loop do carro autonomo (reborn-autonomos).

    python3 principal.py --seco --ver     # 1o teste: NAO move nada, so mostra o que decidiria
    python3 principal.py --tempo 10       # anda 10 s e para sozinho
    python3 principal.py                  # anda ate Ctrl+C (ou 'q' na janela)

Opcoes:
    --seco        motores e servo parados (so visao e log)
    --ver         abre as janelas no PROPRIO Raspberry (terminal da area de trabalho)
    --tempo S     para sozinho depois de S segundos
    --camera N    numero da camera (ou caminho de um video, pra testar no PC)
    --maximo      SEMPRE 100% de potencia, sem nenhuma freada (so desta corrida)
    --vel V       velocidade base so desta corrida (ex.: --vel 0.4), sem mexer no config.py
    --sem-autocal nao autocalibra a escala ao ligar (padrao: autocalibra com o carro parado)
    --recalibrar  refaz a calibracao da DIRECAO (sentido do volante e puxao): o carro anda ~1,5 m.
                  Na 1a vez ela roda sozinha; depois fica salva em dados/direcao.json.
    --sem-log     nao grava a pasta logs/
    --simulado    GPIO de mentira (testa o programa sem o carro)

Este arquivo so faz entrada/saida: le a camera, entrega ao Piloto (piloto.py),
manda (turn, speed) pro servo e pros motores. Qualquer problema (quadro velho,
erro, Ctrl+C) para os motores e centraliza o servo.
"""

import argparse
import os
import time

import cv2

import adaptacao
import calibracao_direcao
import config
import hardware
from camera import abrir_camera, ajustar, CameraThread
from autocal import autocalibrar
from geometria import carregar_parametros
from piloto import Piloto
from registro import Registro
import visual
import web_ver


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seco", action="store_true")
    ap.add_argument("--ver", action="store_true")
    ap.add_argument("--tempo", type=float, default=0.0)
    ap.add_argument("--camera", default=None)
    ap.add_argument("--sem-log", action="store_true")
    ap.add_argument("--simulado", action="store_true")
    ap.add_argument("--sem-autocal", action="store_true",
                    help="nao autocalibra a escala ao ligar")
    ap.add_argument("--maximo", action="store_true",
                    help="SEMPRE 100%% de potencia, sem nenhuma freada (curvas, torto, perdido)")
    ap.add_argument("--recalibrar", action="store_true",
                    help="refaz a calibracao da direcao (o carro anda ~1,5 m)")
    ap.add_argument("--autocal", action="store_true",
                    help="faz a autocalibracao da escala ANTES de largar (padrao: larga na hora)")
    ap.add_argument("--esquecer", action="store_true",
                    help="ignora o que foi aprendido antes (dados/auto.json) e aprende do zero")
    ap.add_argument("--web", type=int, nargs="?", const=8080, default=0, metavar="PORTA",
                    help="mostra a camera e o que o carro le no NAVEGADOR (http://ip-do-pi:PORTA, padrao 8080)")
    ap.add_argument("--status-cada", type=float, default=2.0,
                    help="segundos entre as linhas de status (use 0.3 pra ver a proa/erro em detalhe)")
    ap.add_argument("--vel", type=float, default=None,
                    help="velocidade base desta corrida (0..1), sem mexer no config.py")
    a = ap.parse_args()
    if a.maximo:
        config.VELOCIDADE_BASE = config.VELOCIDADE_MIN = config.VELOCIDADE_PERDIDO = 1.0
        print("MODO MAXIMO: 100% de potencia o tempo todo, sem freada em curva. Mao no Ctrl+C!")
    if a.vel is not None:
        config.VELOCIDADE_BASE = max(config.PISO_MOTOR_MIN, min(1.0, a.vel))   # nunca abaixo do piso do motor
        config.VELOCIDADE_MIN = min(config.VELOCIDADE_MIN, config.VELOCIDADE_BASE)
        if a.vel < config.PISO_MOTOR_MIN:
            print(f"(--vel {a.vel:.2f} esta abaixo do piso {config.PISO_MOTOR_MIN:.2f}: usando o piso)")
        print(f"Velocidade base desta corrida: {config.VELOCIDADE_BASE:.2f}")

    ver = a.ver
    if ver and not _achar_tela():
        print("Nao achei a tela do Pi (nenhuma area de trabalho aberta?). Ligue o Pi a um monitor com a area de "
              "trabalho aberta, ou use --web pra ver no navegador. Janela desligada.")
        ver = False
    elif ver:
        print(f"Janela na tela do Pi (DISPLAY={os.environ.get('DISPLAY', '-')}). 'q' na janela para parar.")

    params, origem = carregar_parametros()
    piso_salvo = hardware.carregar_piso() if config.MOTOR_PISO_APRENDER else None
    piloto = Piloto(params, config.CAMERA_RES, piso=piso_salvo)
    print(f"Potencia minima pra andar: {piloto.gov.piso:.2f} "
          f"({'aprendida em dados/motor.json' if piso_salvo is not None else 'padrao do config; o carro aprende sozinho'})")
    print(f"Geometria da camera ({origem}):\n  {piloto.cam.resumo()}")

    cap = abrir_camera(a.camera)
    if not cap.isOpened():
        print("Erro: a camera nao abriu (v4l2-ctl --list-devices).")
        return
    thread = CameraThread(cap, reabrir=lambda: abrir_camera(a.camera))
    t_espera = time.monotonic()
    while thread.read()[0] is None and time.monotonic() - t_espera < 6.0:
        time.sleep(0.05)
    if thread.read()[0] is None:
        print("\nERRO: a camera abriu mas NAO entrega quadros. Nao vou andar as cegas.\n"
              "  1) Outro programa usando a camera?  ->  pkill -f principal.py ; pkill -f calibrar_camera.py\n"
              "  2) Falta de energia (aviso de baixa tensao)?  ->  vcgencmd get_throttled  (0x0 = ok)\n"
              "  3) Cabo/porta USB: troque a porta, use uma USB 3 (azul) e um cabo curto.")
        thread.release()
        return

    if (config.AUTOCALIBRAR or a.autocal) and not a.sem_autocal:
        print("Autocalibracao (alguns segundos): deixe o carro PARADO, reto, dentro da faixa, "
              "com a pontilhada e a continua visiveis...")

        def _ler():
            f, _, idade = thread.read()
            return None if f is None or idade > config.QUADRO_VELHO_S else ajustar(f)
        params, info = autocalibrar(params, _ler)
        print("  autocalibracao: " + info["motivo"])
        if info["aplicada"]:
            piloto = Piloto(params, config.CAMERA_RES, piso=piso_salvo)
            print(f"  {piloto.cam.resumo()}")
        piloto.gov.ruido = max(0.3, info.get("ruido", 0.6))
        lado_continuo = info.get("lado_continuo", "direita")
    else:
        lado_continuo = config.LADO_CONTINUO if config.LADO_CONTINUO in ("direita", "esquerda") else "direita"
    piloto.espelhar = (lado_continuo == "esquerda")
    print(f"Faixa continua a {lado_continuo.upper()}" +
          (" (imagem espelhada pro processamento)" if piloto.espelhar else ""))

    servo = motores = None
    if not a.seco:
        servo = hardware.Servo(simulado=a.simulado)
        motores = hardware.Motores(simulado=a.simulado)
        print(f"Servo ({servo.modo}): centro {servo.cal['centro']:.0f} "
              f"esq {servo.cal['esquerda']:.0f} dir {servo.cal['direita']:.0f}  [{servo.origem}]")
        if not hardware.hardware_real():
            print("(hardware simulado: nada vai se mexer)")
    else:
        print("MODO SECO: motores e servo desligados.")

    # ---- calibracao da direcao: o carro descobre sozinho pra que lado o volante vira e
    # se puxa pra um lado (1a vez, ou --recalibrar). O resultado fica em dados/direcao.json.
    dir_cal = calibracao_direcao.carregar(servo.cal if servo is not None else None)
    if dir_cal is None and calibracao_direcao.existe() and servo is not None:
        print("A calibracao da direcao salva (dados/direcao.json) e de OUTRO servo/calibracao de servo: "
              "vou refazer.")
    if servo is not None and (a.recalibrar or (config.AUTOCAL_DIRECAO and dir_cal is None)):
        print("\nCALIBRACAO DA DIRECAO (so na 1a vez ou com --recalibrar): o carro vai andar uns "
              "1,5 m e virar um pouco pros dois lados.\nCarro RETO, DENTRO da faixa, num trecho RETO "
              "da pista, com espaco livre na frente. SAIA DA FRENTE!")
        for i in (3, 2, 1):
            print(f"  comecando em {i}...")
            time.sleep(1.0)
        ultimo = {"idx": -1}

        def passo(turn_raw, speed):
            servo.virar(turn_raw)
            motores.andar(speed)
            while True:
                f, idx, idade = thread.read()
                if f is not None and idx != ultimo["idx"] and idade < 0.3:
                    ultimo["idx"] = idx
                    return ajustar(f), time.monotonic()
                time.sleep(0.002)

        try:
            cal_piloto = Piloto(params, config.CAMERA_RES, piso=piso_salvo)
            cal_piloto.espelhar = piloto.espelhar
            r = calibracao_direcao.calibrar(cal_piloto, passo)
        except KeyboardInterrupt:
            r = {"ok": False, "motivo": "interrompida (Ctrl+C)"}
        finally:
            motores.parar()
            servo.virar(0.0)
            time.sleep(0.6)
        if r["ok"]:
            calibracao_direcao.salvar(r, servo.cal)
            dir_cal = calibracao_direcao.carregar(servo.cal)
            print("  calibracao da direcao: " + r["motivo"] + "  [salva em dados/direcao.json]")
        else:
            print("  calibracao da direcao NAO concluida: " + r["motivo"] +
                  "\n  (segue com os padroes do config.py; tente de novo com --recalibrar)")
        if os.isatty(0):
            try:
                input("\nRecoloque o carro NO INICIO da pista, reto, e aperte Enter pra largar... ")
            except (EOFError, KeyboardInterrupt):
                pass
    if dir_cal is not None:
        piloto.direcao.inverter = dir_cal["inverter"]
        piloto.direcao.trim = dir_cal["trim"]
        print(f"Direcao: volante {'INVERTIDO' if dir_cal['inverter'] else 'normal'}, "
              f"compensacao {dir_cal['trim']:+.2f} (dados/direcao.json)")
    else:
        print(f"Direcao: padrao do config.py (inverter={config.ESTERCO_INVERTER}); o carro se ajusta ANDANDO")

    # ---- o que foi aprendido ANDANDO nas corridas anteriores (sentido do volante, puxao, largura, lado)
    auto = None if a.esquecer else adaptacao.carregar_auto(servo.cal if servo is not None else None)
    if auto:
        piloto.adapt.aplicar(auto)
        print(f"Aprendido antes (dados/auto.json): volante {'INVERTIDO' if piloto.direcao.inverter else 'normal'}"
              f"{' (confirmado)' if piloto.adapt.confirmada else ' (a confirmar)'}, compensacao "
              f"{piloto.direcao.trim:+.2f}, faixa {piloto.faixas.W:.1f} cm")
    print("LARGA NA HORA: o carro se calibra enquanto anda (devagar ate confirmar o sentido do volante).")

    registro = None if a.sem_log else Registro()
    if registro:
        print(f"Log em {registro.pasta}")

    janela_ok = False
    tx = None
    if a.web:
        try:
            tx = web_ver.Transmissor(a.web)
            print(f"VISAO NO NAVEGADOR: http://{web_ver.ip_local()}:{tx.porta}   (PC/celular na mesma rede do Pi)")
        except OSError as e:
            print(f"(nao consegui abrir a porta {a.web} pro navegador: {e}; sigo sem a transmissao)")
    ultimo_idx = -1
    avisou_velho = False
    t_ini = time.monotonic()
    n, fps_medido = 0, 15.0
    t_fps, frames = time.monotonic(), 0
    print("Rodando. Ctrl+C (ou 'q' na janela) para parar.")
    try:
        while True:
            frame, idx, idade = thread.read()
            if frame is None or idx == ultimo_idx:
                time.sleep(0.003)
                continue
            ultimo_idx = idx
            if idade > config.QUADRO_VELHO_S:
                if motores:
                    motores.parar()
                if not avisou_velho:
                    print(f"  [camera] sem quadro novo ha {idade:.1f}s: motores parados (aguardando a camera)")
                    avisou_velho = True
                continue
            avisou_velho = False
            frame = ajustar(frame)

            # instante em que o quadro foi CAPTURADO (nao o de agora): o dt do controle e a
            # pose consideram a latencia da camera/USB
            agora = time.monotonic() - idade
            n += 1
            mostrar = ver and (n % config.DEBUG_CADA == 0)
            # BEV/mascara de debug custam copias: so quando ha janela ou no log, a cada N quadros
            web_vez = tx is not None and tx.clientes > 0 and n % config.WEB_CADA == 0     # so desenha com alguem vendo
            debug = mostrar or web_vez or (registro is not None and n % config.DEBUG_LOG_CADA == 0)
            try:
                turn, speed = piloto.step(agora, frame, fps=fps_medido, debug=debug)
            except Exception as e:      # um quadro ruim nao derruba a corrida: trata como faixa perdida
                msg = f"[erro] quadro descartado: {e!r}"
                print("  " + msg)
                if registro:
                    registro.evento(msg)
                turn, speed = piloto.direcao.decair(0.8), 0.0
                piloto.turn, piloto.speed = turn, speed
            if servo:
                servo.virar(turn)
                motores.andar(speed)

            if web_vez and piloto.res is not None and piloto.res.bev is not None:
                tx.publicar(visual.compor(piloto, frame))

            for linha in piloto.eventos:
                print("  " + linha)
                if registro:
                    registro.evento(linha)
                    registro.foto(linha.split("]")[0].strip("[ ") if "]" in linha else "ev",
                                  visual.compor(piloto, frame) if piloto.res.bev is not None else frame)   # sem BEV de debug: ao menos o quadro cru
            if registro:
                registro.telemetria(piloto, fps_medido)

            frames += 1
            if time.monotonic() - t_fps >= max(0.1, a.status_cada):
                fps_medido = frames / (time.monotonic() - t_fps)
                frames, t_fps = 0, time.monotonic()
                _resumo(piloto, fps_medido, servo)

            if mostrar:
                try:
                    img = visual.compor(piloto, frame)
                    if config.VER_ESCALA != 1.0:
                        img = cv2.resize(img, None, fx=config.VER_ESCALA, fy=config.VER_ESCALA,
                                         interpolation=cv2.INTER_NEAREST)
                    if not janela_ok:
                        cv2.namedWindow("reborn-autonomos", cv2.WINDOW_NORMAL)
                        janela_ok = True
                    cv2.imshow("reborn-autonomos", img)
                    if (cv2.waitKey(1) & 0xFF) == ord('q'):
                        break
                except cv2.error as e:     # janela nao abre: avisa e SEGUE a corrida (so sem a janela)
                    print("  (nao consegui abrir a janela na tela do Pi: "
                          f"{str(e).splitlines()[0][:110]}). Sigo sem ela. Dica: DISPLAY=:0 python3 principal.py --ver, "
                          "com a area de trabalho aberta no Pi; ou use --web.")
                    ver = False
            if a.tempo and time.monotonic() - t_ini >= a.tempo:
                print(f"Tempo de {a.tempo:.0f}s acabou.")
                break
    except KeyboardInterrupt:
        print("\nParada de emergencia (Ctrl+C).")
    finally:
        if motores:
            motores.fechar()
        if servo:
            servo.fechar()
        hardware.limpar()
        if a.seco:
            print("(modo seco: nao gravei nada em dados/ - o carro nao andou, entao nao ha o que aprender)")
        elif config.MOTOR_PISO_APRENDER and piloto.gov.piso > piloto.gov.piso_inicial + 0.005:
            salvo = min(piloto.gov.piso, config.PISO_SALVAR_MAX)
            hardware.salvar_piso(salvo)
            print(f"Potencia minima aprendida: {piloto.gov.piso:.2f} (salva {salvo:.2f} em dados/motor.json)")
            if piloto.gov.piso > config.PISO_SALVAR_MAX:
                print(f"  ATENCAO: o carro quis mais que {config.PISO_SALVAR_MAX:.2f} pra andar: confira a bateria "
                      f"dos motores, o jumper do ENA/ENB e a camera (imagem congelada engana o aprendizado).")
        if not a.seco:
            try:
                adaptacao.salvar_auto(piloto.adapt.estado(), servo.cal if servo is not None else None)
            except Exception as e:
                print(f"(nao consegui salvar o aprendizado: {e})")
        thread.release()
        if tx is not None:
            tx.parar()
        if registro:
            registro.fechar()
        try:
            cv2.destroyAllWindows()
        except cv2.error:
            pass
        print("Desligado com seguranca.")


def _achar_tela():
    """True se da pra abrir janela. Vindo de terminal remoto (DISPLAY vazio) tenta a tela do PROPRIO Pi:
    se ha uma area de trabalho aberta nele, existe o socket do X em /tmp/.X11-unix."""
    if os.name == "nt":
        return True
    if os.environ.get("DISPLAY"):
        return True
    for n in ("0", "1"):
        if os.path.exists(f"/tmp/.X11-unix/X{n}"):
            os.environ["DISPLAY"] = f":{n}"
            return True
    return False


def _resumo(p, fps, servo=None):
    r = p.res
    linhas = ""
    if r is not None and r.linhas:
        linhas = " ".join(f"{l.ident or '?'}:{l.x_ref:+.0f}" for l in r.linhas)
    d = p.direcao
    auto = (f"volante {'INV' if d.inverter != d.espelho else 'normal'}{'+' if p.adapt.confirmada else '?'} "
            f"trim {d.trim:+.2f} W {p.faixas.W:.0f}cm{' ESPELHADO' if p.espelhar else ''}")
    # angulo FISICO do servo (graus), medido a partir da saida logica + calibracao
    srv = ""
    if servo is not None:
        c = servo.cal["centro"]
        alvo = servo.cal["esquerda"] if d.saida() < 0 else servo.cal["direita"]
        curso = max(-config.SERVO_CURSO_USO_MAX, min(config.SERVO_CURSO_USO_MAX, alvo - c))
        ang = c + abs(d.saida()) * curso
        srv = f" | servo {ang:5.1f}deg (saida {d.saida():+.2f})"
    print(f"FPS {fps:4.1f} | {'OK' if p.motivo == 'ok' else 'PERDIDO: ' + p.motivo:<24s} | "
          f"erro {p.erro_cm:+6.1f}cm proa {p.proa_graus:+5.1f} | turn {p.turn:+.2f} vel {p.speed:.2f}{srv} "
          f"| auto: {auto} | linhas {linhas or '-'}")


if __name__ == "__main__":
    main()
