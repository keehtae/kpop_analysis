"""Load artist quality rules and flag rows using DuckDB.
The first matching condition supplies the quarantine reason.
"""

import yaml


def load_rules(path):
    with path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    if not isinstance(config, dict) or not isinstance(config.get("rules"), list):
        raise ValueError("The quality rules file must contain a rules list.")
    rules, labels = [], set()
    for rule in config["rules"]:
        if not isinstance(rule, dict) or set(rule) != {"label", "condition"}:
            raise ValueError("Each quality rule needs a label and condition.")
        label, condition = rule["label"], rule["condition"]
        if not all(isinstance(value, str) and value.strip() for value in (label, condition)):
            raise ValueError("Rule labels and conditions must be nonempty strings.")
        if label in labels:
            raise ValueError(f"Duplicate quality rule: {label}")
        labels.add(label)
        rules.append((label, condition))
    if not rules:
        raise ValueError("At least one quality rule is required.")
    return rules


def apply_quality_rules(connection, rules):
    cases = []
    for label, condition in rules:
        try:
            result = connection.execute(f"SELECT ({condition}) FROM source_rows LIMIT 0")
            if str(result.description[0][1]) != "BOOLEAN":
                raise ValueError("The condition must return a boolean.")
        except Exception as exc:
            raise ValueError(f"Cannot evaluate quality rule {label!r}: {exc}") from exc
        label = label.replace("'", "''")
        cases.append(f"WHEN coalesce(({condition}), true) THEN '{label}'")
    connection.execute(
        "CREATE OR REPLACE TEMP TABLE flagged_rows AS SELECT *, CASE "
        + " ".join(cases)
        + " ELSE NULL END AS quality_flag FROM source_rows"
    )
