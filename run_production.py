import os
import sys

def main():
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    threads = int(os.environ.get("THREADS", 6))

    print("=" * 60)
    print("   SISTEMA DE GESTÃO DE ALMOÇO ESTUDANTIL - PRODUÇÃO")
    print("=" * 60)
    print(f"[*] Escutando em: http://{host}:{port}")
    print(f"[*] Threads de atendimento: {threads}")

    try:
        from waitress import serve
        from app import app
        print("[*] Servidor WSGI: Waitress (Multi-threaded Production)")
        print("[*] Pressione Ctrl+C para encerrar o servidor.")
        serve(app, host=host, port=port, threads=threads)
    except ImportError:
        print("[!] Waitress não encontrado. Carregando servidor padrão...")
        from app import app
        app.run(host=host, port=port, threaded=True)

if __name__ == "__main__":
    main()
