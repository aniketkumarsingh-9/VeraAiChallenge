"""Regenerate submission.jsonl from the official test_pairs.json dataset."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Make sure we run from the project root
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

DATASET = PROJECT_ROOT / "magicpin-ai-challenge" / "dataset"
TRIGGERS_DIR = DATASET / "triggers"
MERCHANTS_DIR = DATASET / "merchants"
CUSTOMERS_DIR = DATASET / "customers"
CATEGORIES_DIR = DATASET / "categories"
TEST_PAIRS = DATASET / "test_pairs.json"
OUTPUT = PROJECT_ROOT / "submission.jsonl"


def load_json(path: Path) -> dict:
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


def find_file(directory: Path, prefix: str) -> Path | None:
    """Find the first JSON file in directory whose stem starts with prefix."""
    for p in directory.glob("*.json"):
        if p.stem == prefix or p.stem.startswith(prefix):
            return p
    return None


def load_merchant(merchant_id: str) -> dict:
    path = find_file(MERCHANTS_DIR, merchant_id)
    return load_json(path) if path else {}


def load_customer(customer_id: str) -> dict | None:
    if not customer_id:
        return None
    path = find_file(CUSTOMERS_DIR, customer_id)
    return load_json(path) if path else None


def load_trigger(trigger_id: str) -> dict:
    path = find_file(TRIGGERS_DIR, trigger_id)
    return load_json(path) if path else {}


def load_category_for_merchant(merchant: dict) -> dict:
    """Try to load category JSON by merchant's category field."""
    cat_name = (
        merchant.get("category_slug")
        or merchant.get("category")
        or merchant.get("vertical")
        or merchant.get("segment")
        or ""
    )
    if not cat_name:
        return {}
    safe = cat_name.lower().replace(" ", "_").replace("/", "_")
    path = find_file(CATEGORIES_DIR, safe)
    if path:
        return load_json(path)
    # Try partial match
    for p in CATEGORIES_DIR.glob("*.json"):
        if safe in p.stem or p.stem in safe:
            return load_json(p)
    return {}


def main() -> None:
    from bot import compose  # import after sys.path set

    pairs_data = load_json(TEST_PAIRS)
    pairs = pairs_data.get("pairs", [])

    lines: list[str] = []
    errors: list[str] = []

    for pair in pairs:
        test_id = pair["test_id"]
        trigger_id = pair["trigger_id"]
        merchant_id = pair["merchant_id"]
        customer_id = pair.get("customer_id")

        trigger = load_trigger(trigger_id)
        merchant = load_merchant(merchant_id)
        customer = load_customer(customer_id) if customer_id else None
        category = load_category_for_merchant(merchant)

        if not trigger:
            errors.append(f"{test_id}: trigger file not found for {trigger_id!r}")
        if not merchant:
            errors.append(f"{test_id}: merchant file not found for {merchant_id!r}")

        try:
            result = compose(category, merchant, trigger, customer)
            out = {"test_id": test_id, **result}
            lines.append(json.dumps(out, ensure_ascii=False))
            print(f"  [{test_id}] {result['body'][:100]}")
        except Exception as exc:
            errors.append(f"{test_id}: compose() raised {exc!r}")
            print(f"  [{test_id}] ERROR: {exc}", file=sys.stderr)

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nWrote {len(lines)} lines to {OUTPUT}")
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")


if __name__ == "__main__":
    main()
