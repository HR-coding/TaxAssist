import json
import os


def retrieve_tax_rules():

    file_path = os.path.join(
        os.path.dirname(
            os.path.dirname(__file__)
        ),
        "data",
        "tax_rules.json"
    )

    with open(
        file_path,
        "r"
    ) as f:

        rules = json.load(
            f
        )

    return rules[
        "old_regime"
    ]