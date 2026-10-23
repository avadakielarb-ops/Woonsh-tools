"""
Deterministic checks for Google Ads CSV + SHA-256 review signature.
From X-File ads_validation.py, adapted for woonsh_tools.
"""

import hashlib
import json
from urllib.parse import urlparse

HEADERS = {
    "Amenities", "Brands", "Courses", "Degree programs", "Destinations",
    "Featured hotels", "Insurance coverage", "Models", "Neighborhoods",
    "Service catalog", "Shows", "Styles", "Types",
}


def check(rows, settings, policy_issue):
    errors, warnings = [], []
    campaigns = [r for r in rows if r.get("Row Type") == "Campaign"]
    groups = [r for r in rows if r.get("Row Type") == "Ad group"]

    if not campaigns:
        errors.append("Нет кампании.")

    for c in campaigns:
        name = c.get("Campaign")
        cg = [r for r in groups if r.get("Campaign") == name]
        if len(cg) != settings["ad_groups"]:
            errors.append(
                f"{name}: групп {len(cg)}, нужно {settings['ad_groups']}.")
        if not c.get("Location"):
            warnings.append(
                f"{name}: география не задана, проверьте перед запуском.")
        if not c.get("Language"):
            errors.append(f"{name}: не задан язык.")

        campaign_rows = [r for r in rows if r.get("Campaign") == name]
        for asset, field in [("callouts", "Callout text"),
                             ("sitelinks", "Sitelink text")]:
            need = settings.get("ext", {}).get(asset, 0)
            actual = sum(bool(r.get(field)) for r in campaign_rows)
            if actual < need:
                warnings.append(
                    f"{name}: {asset} — {actual} из {need}.")
        if (settings.get("ext", {}).get("snippets")
                and not any(r.get("Asset type") == "Structured snippet"
                            for r in campaign_rows)):
            errors.append(
                f"{name}: нет структурированного описания.")

        for g in cg:
            label = g.get("Ad group")
            children = [r for r in rows
                        if r.get("Campaign") == name
                        and r.get("Ad group") == label]
            keywords = [r.get("Keyword", "") for r in children
                        if r.get("Row Type") == "Keyword"]
            if len(set(keywords)) != settings["keywords"]:
                errors.append(
                    f"{label}: ключей {len(set(keywords))}, "
                    f"нужно {settings['keywords']}.")
            ads = [r for r in children if r.get("Row Type") == "Ad"]
            if len(ads) != settings["ads"]:
                errors.append(
                    f"{label}: объявлений {len(ads)}, "
                    f"нужно {settings['ads']}.")

    for n, r in enumerate(rows, 1):
        kind = r.get("Row Type")
        if kind == "Ad":
            for prefix, count, limit in [
                ("Headline", settings["headlines"], 30),
                ("Description", settings["descriptions"], 90),
            ]:
                texts = [r.get(f"{prefix} {i}", "").strip()
                         for i in range(1, 16 if prefix == "Headline" else 5)]
                texts = [t for t in texts if t]
                if len(texts) != count:
                    errors.append(
                        f"Строка {n}: {prefix} — {len(texts)}, "
                        f"нужно {count}.")
                if len({t.casefold() for t in texts}) != len(texts):
                    errors.append(f"Строка {n}: повторяющиеся {prefix}.")
                for t in texts:
                    if len(t) > limit:
                        errors.append(
                            f"Строка {n}: {prefix} длиннее {limit}: {t}")
                    issue = (policy_issue(t, set())
                             if settings.get("policy", True) else None)
                    if issue:
                        errors.append(f"Строка {n}: {issue}: {t}")

        if kind in ("Ad", "Sitelink"):
            u = urlparse(r.get("Final URL", ""))
            if u.scheme not in ("http", "https") or not u.hostname:
                errors.append(f"Строка {n}: неверный URL.")

        for field, limit in [("Callout text", 25), ("Sitelink text", 25),
                             ("Sitelink description 1", 35),
                             ("Sitelink description 2", 35)]:
            if len(r.get(field, "")) > limit:
                errors.append(f"Строка {n}: {field} длиннее {limit}.")

        if r.get("Asset type") == "Structured snippet":
            vals = r.get("Structured snippet values", "").split(";")
            if (r.get("Structured snippet header") not in HEADERS
                    or len(vals) < 3
                    or any(not v.strip() or len(v) > 25 for v in vals)):
                errors.append(
                    f"Строка {n}: неверное структурированное описание.")

    return list(dict.fromkeys(errors)), list(dict.fromkeys(warnings))


def review_signature(state):
    content = {"s": state["s"], "sites": state["sites"]}
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, ensure_ascii=False)
        .encode("utf-8")).hexdigest()


def manually_approved(state):
    return (state.get("manual_review", {}).get("signature")
            == review_signature(state))
