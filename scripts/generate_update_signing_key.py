from __future__ import annotations

import argparse
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def generate_key_pair(private_path: Path, public_path: Path) -> None:
    private_path = private_path.resolve()
    public_path = public_path.resolve()
    if private_path.exists() or public_path.exists():
        raise FileExistsError("Refusing to overwrite an existing update signing key.")
    private_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    private_key = Ed25519PrivateKey.generate()
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    try:
        os.chmod(private_path, 0o600)
    except OSError:
        pass
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )


def main() -> int:
    local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    parser = argparse.ArgumentParser(description="Generate the offline Ed25519 update signing key.")
    parser.add_argument(
        "--private-key",
        type=Path,
        default=local_app_data / "VisionTrainingStudio" / "release_keys" / "update_private_key.pem",
    )
    parser.add_argument(
        "--public-key",
        type=Path,
        default=Path("updates/keys/update_public_key.pem"),
    )
    args = parser.parse_args()
    generate_key_pair(args.private_key, args.public_key)
    print(f"Private key: {args.private_key.resolve()}")
    print(f"Public key:  {args.public_key.resolve()}")
    print("Keep the private key offline. Never commit or upload it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
