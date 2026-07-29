import json
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "economic_data.json"


def period_kind(period):
    text = str(period)
    if re.fullmatch(r"\d{4}", text):
        return "annual"
    if re.fullmatch(r"\d{4}-Q[1-4]", text):
        return "quarterly"
    if re.fullmatch(r"\d{4}-\d{2}", text):
        return "monthly"
    return "other"


def numeric_values(values):
    return [value for value in values if isinstance(value, (int, float))]


def run():
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    countries = [country["code"] for country in payload.get("countries", [])]
    report = []
    report.append(f"Updated: {payload.get('updated')}")
    report.append(f"Countries: {len(countries)} ({', '.join(countries)})")
    report.append("")

    for indicator in payload.get("indicators", []):
        if indicator.get("kind") == "rating":
            continue
        labels = indicator.get("dates") or indicator.get("years") or []
        kinds = {}
        for label in labels:
            kinds[period_kind(label)] = kinds.get(period_kind(label), 0) + 1
        mixed = sum(1 for key in ("annual", "quarterly", "monthly") if kinds.get(key, 0)) > 1
        report.append(f"{indicator.get('key')} | {indicator.get('label')}")
        report.append(f"  periods={len(labels)} kinds={kinds} mixed_frequency={mixed}")

        if mixed:
            report.append("  WARNING: mixed annual/monthly/quarterly periods caused by country-level fallback data.")

        for code in countries:
            values = indicator.get("series", {}).get(code, [])
            if len(values) != len(labels):
                report.append(f"  ERROR {code}: length mismatch values={len(values)} labels={len(labels)}")
            nums = numeric_values(values)
            null_count = sum(value is None for value in values)
            coverage = len(nums) / len(labels) if labels else 0
            zero_periods = [labels[index] for index, value in enumerate(values) if value == 0]
            if nums:
                min_value = min(nums)
                max_value = max(nums)
                latest = next((values[index] for index in range(len(values) - 1, -1, -1) if isinstance(values[index], (int, float))), None)
                latest_period = next((labels[index] for index in range(len(values) - 1, -1, -1) if isinstance(values[index], (int, float))), None)
            else:
                min_value = max_value = latest = latest_period = None
            flags = []
            if coverage < 0.15:
                flags.append("low_coverage")
            if zero_periods and indicator.get("key") in {"inflation", "unemployment", "interest_rate"}:
                flags.append(f"zero_values={len(zero_periods)}")
            if indicator.get("key") == "inflation" and nums and max_value > 100:
                flags.append("very_high_inflation_history")
            if flags:
                report.append(
                    f"  {code}: coverage={coverage:.0%} nulls={null_count} min={min_value} max={max_value} "
                    f"latest={latest}@{latest_period} flags={', '.join(flags)}"
                )

        report.append("")

    (BASE_DIR / "economic_data_audit.txt").write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    run()
