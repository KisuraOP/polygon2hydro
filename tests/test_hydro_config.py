"""Validate generated configs against Hydro's own problem-config JSON schema.

`fixtures/hydro_problemconfig.schema.json` is extracted verbatim from
``@hydrooj/ui-default/components/monaco/schema/problemconfig.ts`` (the schema
Hydro's 评测设置 form validates against).  If Hydro changes the schema, extract
it again: the validator below implements exactly the JSON-schema keywords that
schema uses.
"""

import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from p2h.hydro.package import build_config
from p2h.kinds import COMMUNICATION, INTERACTIVE, TRADITIONAL


SCHEMA = json.loads((Path(__file__).parent / "fixtures" / "hydro_problemconfig.schema.json").read_text(encoding="utf-8"))


def _validate(instance: object, schema: dict, root: dict, path: str = "") -> list[str]:
    """Validate the JSON-schema subset Hydro's problem config schema uses.

    Hydro validates the 评测设置 form with this exact schema; generating a config
    that fails it makes the problem page show red errors (the bug this test
    guards against), so the check has to happen before packaging.
    """
    errors: list[str] = []

    if "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/definitions/"):
            raise AssertionError(f"unsupported $ref: {ref}")
        target = root["definitions"][ref.split("/")[-1]]
        return _validate(instance, target, root, path)

    if "oneOf" in schema:
        matches = [branch for branch in schema["oneOf"] if not _validate(instance, branch, root, path)]
        if len(matches) != 1:
            errors.append(f"{path or '/'}: must match exactly one schema in oneOf")
        return errors

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path or '/'}: must be equal to one of the allowed values")

    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(instance, dict):
            errors.append(f"{path or '/'}: must be object")
            return errors
        properties = schema.get("properties", {})
        for required in schema.get("required", []):
            if required not in instance:
                errors.append(f"{path or '/'}: must have required property '{required}'")
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties and not any(
                    re.fullmatch(pattern, key) for pattern in schema.get("patternProperties", {})
                ):
                    errors.append(f"{path or '/'}: must NOT have additional properties ({key})")
        for key, value in instance.items():
            if key in properties:
                errors.extend(_validate(value, properties[key], root, f"{path}/{key}"))
            else:
                for pattern, subschema in schema.get("patternProperties", {}).items():
                    if re.fullmatch(pattern, key):
                        errors.extend(_validate(value, subschema, root, f"{path}/{key}"))
    elif expected_type == "array":
        if not isinstance(instance, list):
            errors.append(f"{path or '/'}: must be array")
            return errors
        if "items" in schema:
            for index, item in enumerate(instance):
                errors.extend(_validate(item, schema["items"], root, f"{path}/{index}"))
    elif expected_type == "string":
        if not isinstance(instance, str):
            errors.append(f"{path or '/'}: must be string")
            return errors
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path or '/'}: must match pattern {schema['pattern']!r}")
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path or '/'}: too short")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path or '/'}: too long")
    elif expected_type == "integer":
        if not isinstance(instance, int) or isinstance(instance, bool):
            errors.append(f"{path or '/'}: must be integer")
            return errors
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path or '/'}: must be >= {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path or '/'}: must be <= {schema['maximum']}")
    elif expected_type == "number":
        if not isinstance(instance, (int, float)) or isinstance(instance, bool):
            errors.append(f"{path or '/'}: must be number")
    return errors


def validate_config(config: dict) -> list[str]:
    return _validate(config, SCHEMA, SCHEMA)


class TestHydroProblemConfigSchema(unittest.TestCase):
    def test_traditional_config_is_valid(self) -> None:
        config = build_config(
            1000, 256, [("01.in", "01.out")],
            kind=TRADITIONAL, interactor_name=None, checker_name="check.cpp",
        )
        self.assertEqual(validate_config(config), [])

    def test_interactive_config_is_valid(self) -> None:
        config = build_config(
            1000, 256, [("01.in", "01.out")],
            kind=INTERACTIVE, interactor_name="interactor.cpp", checker_name=None,
        )
        self.assertEqual(validate_config(config), [])

    def test_communication_config_is_valid(self) -> None:
        # Run-twice problems use Hydro's native multi_pass option on the
        # interactive type; the expected answer is the normal case output.
        config = build_config(
            1000, 1024, [("01.in", "01.out")],
            kind=COMMUNICATION, interactor_name="p2h_interactor.cc.cc17o2", checker_name="check.cpp",
            run_count=2,
        )
        self.assertEqual(validate_config(config), [])
        self.assertEqual(config["type"], "interactive")
        self.assertEqual(config["multi_pass"], 2)
        self.assertEqual(config["interactor"], "p2h_interactor.cc.cc17o2")
        self.assertNotIn("manager", config)
        self.assertNotIn("num_processes", config)
        self.assertNotIn("judge_extra_files", config)
        self.assertNotIn("checker", config)
        self.assertEqual(config["subtasks"][0]["cases"][0]["output"], "01.out")

    def test_checker_without_lang_is_rejected(self) -> None:
        # This is exactly the bug users saw in 评测设置: a checker object without
        # `lang` fails Hydro's oneOf schema ("must have required property 'lang'"
        # is one of the branch errors).
        config = {
            "type": "default",
            "checker_type": "testlib",
            "checker": {"file": "check.cpp"},
        }
        errors = validate_config(config)
        self.assertTrue(errors)
        self.assertTrue(any("oneOf" in error for error in errors), errors)

    def test_unknown_problem_type_is_rejected(self) -> None:
        config = build_config(
            1000, 256, [("01.in", "01.out")],
            kind=TRADITIONAL, interactor_name=None, checker_name="check.cpp",
        )
        config["type"] = "run-twice"
        errors = validate_config(config)
        self.assertTrue(any("allowed values" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
