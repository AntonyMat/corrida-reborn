"""
web_ver.py - mostra no NAVEGADOR o que o carro esta lendo, enquanto o principal.py roda (sem tela no Pi).

    python3 principal.py --web            # porta 8080
    python3 principal.py --web 9000

Abra no PC/celular (na MESMA rede do Pi):   http://<ip-do-pi>:8080
Mostra: a camera com a linha-alvo | a vista de cima (BEV) com as linhas achadas (A/D/B) e o centro da faixa,
mais o erro, a proa, o volante e a velocidade.

So gasta CPU com alguem vendo: sem navegador aberto o carro nem desenha nada. Qualquer pessoa na rede local que
abrir o endereco ve o video (somente leitura; nao ha como controlar o carro por aqui).
"""

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2

PAGINA = b"""<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>reborn - visao</title>
<style>html,body{margin:0;background:#111;color:#ddd;font:14px sans-serif}
img{display:block;width:100%;max-width:1400px;margin:0 auto}p{text-align:center;margin:6px}</style></head>
<body><p>Esquerda: camera (amarelo = alvo) | Direita: vista de cima (verde = centro da faixa, A/D/B = linhas)</p>
<img src="/video" alt="aguardando o carro..."></body></html>"""


class Transmissor:
    def __init__(self, porta=8080, qualidade=60):
        self.qualidade = int(qualidade)
        self._cond = threading.Condition()
        self._img = None
        self._seq = 0
        self._jpg = (None, -1)            # (bytes, seq a que se refere): evita codificar uma vez por cliente
        self._parado = False
        self._clientes = 0
        self._foto_ate = 0.0              # um GET /foto.jpg recente tambem conta como 'alguem vendo'
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):    # silencia o log de cada requisicao
                pass

            def do_GET(self):
                if self.path in ("/", "/index.html"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(PAGINA)))
                    self.end_headers()
                    self.wfile.write(PAGINA)
                elif self.path.startswith("/foto.jpg"):
                    outer._foto_ate = time.monotonic() + 3.0      # liga o desenho; espera o primeiro quadro
                    with outer._cond:
                        outer._cond.wait_for(lambda: outer._img is not None or outer._parado, timeout=2.0)
                    jpg = outer._jpeg_atual()
                    if jpg is None:
                        self.send_response(503)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(jpg)))
                    self.end_headers()
                    self.wfile.write(jpg)
                elif self.path.startswith("/video"):
                    outer._stream(self)
                else:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()

        self.srv = ThreadingHTTPServer(("0.0.0.0", int(porta)), Handler)
        self.srv.daemon_threads = True
        self.porta = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    # ---- usado pelo laco do carro
    @property
    def clientes(self):
        return self._clientes + (1 if time.monotonic() < self._foto_ate else 0)

    def publicar(self, img):
        with self._cond:
            self._img = img
            self._seq += 1
            self._cond.notify_all()

    def parar(self):
        with self._cond:
            self._parado = True
            self._cond.notify_all()
        try:
            self.srv.shutdown()
            self.srv.server_close()
        except Exception:
            pass

    # ---- internos
    def _jpeg_atual(self):
        with self._cond:
            img, seq = self._img, self._seq
            if img is None:
                return None
            if self._jpg[1] == seq:
                return self._jpg[0]
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, self.qualidade])
        if not ok:
            return None
        jpg = buf.tobytes()
        with self._cond:
            if seq >= self._jpg[1]:
                self._jpg = (jpg, seq)
        return jpg

    def _stream(self, h):
        h.send_response(200)
        h.send_header("Content-Type", "multipart/x-mixed-replace; boundary=quadro")
        h.send_header("Cache-Control", "no-cache, no-store")
        h.send_header("Connection", "close")
        h.end_headers()
        with self._cond:
            self._clientes += 1
        ultimo = -1
        try:
            while not self._parado:
                with self._cond:
                    self._cond.wait_for(lambda: self._seq != ultimo or self._parado, timeout=1.0)
                    ultimo = self._seq
                jpg = self._jpeg_atual()      # se nao veio quadro novo, reenvia o ultimo (detecta cliente que saiu)
                if jpg is None:
                    continue
                h.wfile.write(b"--quadro\r\nContent-Type: image/jpeg\r\nContent-Length: "
                              + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                h.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass
        finally:
            with self._cond:
                self._clientes -= 1


def ip_local():
    """IP do Pi na rede local (sem mandar nenhum pacote de verdade)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return socket.gethostname()
