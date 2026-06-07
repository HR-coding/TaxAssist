import json


def retrieve_tax_rules():

    with open(
        "data/tax_rules.json",
        "r"
    ) as f:

        rules = json.load(f)

    return rules["old_regime"]