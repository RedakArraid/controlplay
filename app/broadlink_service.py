import os
from typing import Optional


def send_ir_command(ip: str, ir_code: Optional[str]) -> None:
    dry_run = os.getenv("BROADLINK_DRY_RUN", "true").lower() == "true"
    if not ir_code:
        raise ValueError("Code IR manquant pour cette action.")
    if dry_run:
        print(f"[BROADLINK-DRY-RUN] ip={ip} code={ir_code[:20]}...")
        return

    # Activation reelle possible quand tu auras l'appareil.
    import broadlink  # type: ignore

    devices = broadlink.hello(ip_address=ip)
    if not devices:
        raise RuntimeError(f"Broadlink introuvable a l'IP {ip}")
    device = devices[0]
    device.auth()
    device.send_data(bytes.fromhex(ir_code))
