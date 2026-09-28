"""Initialize local Django secrets without printing them or overwriting existing values."""
import argparse
import secrets
from pathlib import Path
from dotenv import dotenv_values, set_key

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    path = Path(__file__).resolve().parents[1] / ".env"
    values = dotenv_values(path)
    additions = {"DJANGO_SECRET_KEY": secrets.token_urlsafe(64), "DJANGO_DEBUG": "true", "DATABASE_NAME": "reading_map_django"}
    for key, value in additions.items():
        if not values.get(key):
            if args.apply:
                set_key(str(path), key, value)
            print(f"{'Configured' if args.apply else 'Would configure'} {key}")

if __name__ == "__main__":
    main()
