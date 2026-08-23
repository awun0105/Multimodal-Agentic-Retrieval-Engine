"""
TRINH KHOI DONG & DIEU KHIEN TOAN DIEN (ALL-IN-ONE LAUNCHER).
Quan ly vong doi Web App: Khoi dong, Tat tien trinh, Reset cong mang, Hot Reload.
"""

from __future__ import annotations
import os
import sys
import time
import subprocess
from pathlib import Path

# Dam bao UTF-8 cho Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_SCRIPT = PROJECT_ROOT / "interactive-test-app" / "app.py"


def is_port_in_use(port: int = 7860) -> bool:
    """Kiem tra xem cong port co dang mo khong."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def get_pids_on_ports(ports=(7860, 7861, 7862)) -> list[int]:
    """Tim danh sach cac PID dang chiem cong."""
    pids = set()
    try:
        output = subprocess.check_output(["netstat", "-ano", "-p", "tcp"], encoding="utf-8", errors="ignore")
        for line in output.splitlines():
            for p in ports:
                if f":{p} " in line and "LISTENING" in line:
                    parts = line.strip().split()
                    try:
                        pids.add(int(parts[-1]))
                    except ValueError:
                        pass
    except Exception:
        pass
    return list(pids)


def stop_running_app(silent: bool = False):
    """Tat cac tien trinh dang chiem cong 7860/7861."""
    if not silent:
        print("\n" + "=" * 72)
        print("  [DUNG UNG DUNG] Dang tim va giai phong cac cong mang 7860/7861...")
        print("=" * 72)
    pids = get_pids_on_ports()
    if not pids:
        if not silent:
            print("[THONG BAO] Khong co tien trinh nao dang chiem cong 7860/7861.")
    else:
        for pid in pids:
            try:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if not silent:
                    print(f"  -> Da tat tien trinh PID: {pid}")
            except Exception as e:
                if not silent:
                    print(f"  -> Loi khi tat PID {pid}: {e}")
        time.sleep(0.5)
        if not silent:
            print("[THANH CONG] Da giai phong hoan toan cong mang 7860/7861!")


def start_web_app():
    """Khoi chay may chu Web App kem tinh nang ngat phim Ctrl+C de Reset/Cap nhat code tuc thi."""
    stop_running_app(silent=True)
    time.sleep(0.5)

    print("\n" + "=" * 72)
    print("  [KHOI CHAY] MAY CHU RETRIEVAL COCKPIT: http://127.0.0.1:7860")
    print("=" * 72)
    print("  -> Mo trinh duyet va truy cap: http://127.0.0.1:7860")
    print("  -> [QUAN TRONG] Nhan phim Ctrl + C bat ky luc nao de DUNG & RESET CAP NHAT CODE!")
    print("=" * 72 + "\n")

    proc = None
    try:
        proc = subprocess.Popen([sys.executable, str(APP_SCRIPT)])
        proc.wait()
    except KeyboardInterrupt:
        print("\n" + "=" * 72)
        print("  [DA NHAN LENH DUNG] Dang ngat ung dung de cap nhat code moi...")
        print("=" * 72)
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except Exception:
                proc.kill()
        stop_running_app(silent=True)
        print("  -> Da giai phong cong 7860 va bo nho RAM!")
        print("\n  -> Ban muon lam gi tiep theo?")
        print("     [1] Khoi Dong Lai Ngay Lap Tuc (Restart & Cap nhat code moi)")
        print("     [2] Quay Lai Menu Chinh")
        print("     [3] Thoat")
        try:
            sub_choice = input("\nNhap lua chon [1-3] (Mac dinh: 1): ").strip()
        except (KeyboardInterrupt, EOFError):
            sub_choice = "3"

        if sub_choice in ("", "1"):
            start_web_app()
        elif sub_choice == "2":
            return
        elif sub_choice == "3":
            sys.exit(0)


def reset_web_app():
    """Tat phien cu va khoi chay lai phien moi tren cong 7860."""
    print("\n" + "=" * 72)
    print("  [RESET UNG DUNG] Dang giai phong cong mang va khoi dong lai...")
    print("=" * 72)
    stop_running_app()
    time.sleep(0.5)
    start_web_app()


def show_menu():
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print("=" * 72)
        print("   BANG DIEU KHIEN AIC 2026 RETRIEVAL & BENCHMARK STUDIO (ALL-IN-ONE)")
        print("=" * 72)
        print("   [1] Khoi Dong Web App (Mac dinh: Nhan Enter)")
        print("   [2] Tat Ung Dung (Stop App - Giai phong Port 7860/7861)")
        print("   [3] Reset & Khoi Dong Lai Tu Dau (Restart App tren Port 7860)")
        print("   [4] Thoat")
        print("=" * 72)
        print("   Luu y: Khi Web App dang chay, nhan Ctrl+C de dung & reset ngay!")
        print("=" * 72)

        try:
            choice = input("\nNhap lua chon cua ban [1-4] (Mac dinh: 1): ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nThoat chuong trinh.")
            break

        if choice in ("", "1"):
            start_web_app()
            input("\nNhan Enter de quay lai menu chinh...")
        elif choice == "2":
            stop_running_app()
            input("\nNhan Enter de quay lai menu chinh...")
        elif choice == "3":
            reset_web_app()
            input("\nNhan Enter de quay lai menu chinh...")
        elif choice == "4":
            print("\nThoat chuong trinh.")
            break


if __name__ == "__main__":
    show_menu()
