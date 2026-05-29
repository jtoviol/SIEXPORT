"""Verifica la conexion a SQL Server y muestra el estado."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from efdi.config import settings

def main():
    print("  Host    : {}:{}".format(settings.db_host, settings.db_port))
    print("  Base    : {}".format(settings.db_name))
    print("  Usuario : {}".format(settings.db_user))
    print("  Mock    : {}".format("SI (datos falsos)" if settings.use_mock else "NO (BD real)"))
    print()

    if settings.use_mock:
        print("[!] USE_MOCK=true en .env -- no conecta a SQL Server.")
        return

    try:
        import pyodbc
    except ImportError:
        print("[x] pyodbc no instalado.")
        print("    Instala con: pip install pyodbc")
        print("    (asegurate de usar el mismo Python/venv del proyecto)")
        sys.exit(1)

    print("Conectando...", end=" ", flush=True)
    try:
        with pyodbc.connect(settings.db_dsn, timeout=10) as conn:
            cur = conn.cursor()
            cur.execute("SELECT @@VERSION")
            version = cur.fetchone()[0].split("\n")[0].strip()
            cur.execute(
                "SELECT COUNT(1) FROM AVS_REGISTRO_SERAGIL WHERE FLG_REGIND_DEMIND = 'SI'"
            )
            total = cur.fetchone()[0]
        print("OK")
        print("[OK] Conectado a SQL Server")
        print("     Version  : {}".format(version))
        print("     Registros SERAGIL (FLG_REGIND_DEMIND=SI): {:,}".format(total))
    except Exception as e:
        print("FALLO")
        msg = str(e).lower()
        print("[x] {}".format(e))
        print()
        if "timeout" in msg or "timed out" in msg:
            print("    --> Host no alcanzable. Estas en la VPN/red corporativa?")
        elif "login failed" in msg or "password" in msg:
            print("    --> Credenciales incorrectas. Verifica DB_USER y DB_PASSWORD en .env")
        elif "data source" in msg or "driver" in msg:
            print("    --> Driver ODBC no instalado.")
            print("        Instala: ODBC Driver 17 for SQL Server")
        sys.exit(1)

if __name__ == "__main__":
    main()
