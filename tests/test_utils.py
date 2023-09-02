from unittest import TestCase

import pytest

from theflow import Composable
from theflow.utils.paths import is_name_matched, is_parent_of_child
from theflow.utils.modules import import_dotted_string, serialize, deserialize


class TestNameMatching(TestCase):
    def test_name_matching_exact(self):
        """Test if the name matching is correct"""
        self.assertTrue(is_name_matched("", ""))
        self.assertTrue(is_name_matched(".main", ".main"))
        self.assertTrue(is_name_matched(".main.pipeline_A1", ".main.pipeline_A1"))
        self.assertFalse(is_name_matched(".main.pipeline_A1", ".main.pipeline_A2"))

    def test_name_matching_wildcard(self):
        """Test for wildcard matching"""
        self.assertTrue(
            is_name_matched(
                ".main.pipeline_A1.pipeline_B2.pipeline_C2.step_a",
                ".main.*.pipeline_B2.*.step_a",
            )
        )

        self.assertTrue(
            is_name_matched(
                ".main.pipeline_A1.pipeline_B2.pipeline_C2.step_a",
                ".main.*.pipeline_B2.pipeline*.step_a",
            )
        )

        self.assertFalse(
            is_name_matched(
                ".main.pipeline_A1.pipeline_B2.pipeline_C2.step_a.some_step",
                ".main.*.pipeline_B2.pipeline*.step_a",
            )
        )


class TestParentChildMatching(TestCase):
    def test_parent_child_matching_exact(self):
        """Test if the parent-child matching is correct"""
        self.assertTrue(
            is_parent_of_child(".main.pipeline_A1", ".main.pipeline_A1.pipeline_B1")
        )

        self.assertFalse(is_parent_of_child(".main.pipeline_A1", ".main.pipeline_A2"))

    def test_parent_child_matching_wildcard(self):
        """Test for wildcard matching"""
        self.assertTrue(
            is_parent_of_child(
                ".main.pipeline_A1.pipeline_B2.pipeline_C2",
                ".main.*.pipeline_B2.*.step_a",
            )
        )

        self.assertTrue(
            is_parent_of_child(
                ".main.pipeline_A1.pipeline_B2.pipeline_C2",
                ".main.*.pipeline_B2.pipeline*.step_a",
            )
        )

        self.assertFalse(
            is_parent_of_child(
                ".main.pipeline_A1.pipeline_B2.pipeline_C2",
                ".main.*.pipeline_B2.pipeline*.step_a.some_step",
            )
        )


class TestImportDottedString(TestCase):
    def test_import_class(self):
        """Test it can import class"""
        from pathlib import Path

        self.assertEqual(import_dotted_string("pathlib.Path", safe=False), Path)

    def test_import_function(self):
        """Test it can import function"""
        self.assertEqual(
            import_dotted_string(
                "theflow.utils.modules.import_dotted_string", safe=False
            ),
            import_dotted_string,
        )

    def test_import_safe_no_allowed_modules_raise_error(self):
        """Test that safe import without modules will raise error"""
        with self.assertRaises(ValueError):
            import_dotted_string("pathlib.Path")

    def test_import_safe_missing_allowed_modules_raise_error(self):
        """Test that safe import with missing modules will raise error"""
        import re

        with self.assertRaises(ValueError):
            import_dotted_string("pathlib.Path", allowed_modules={"re": re})

    def test_import_safe_with_allowed_modules(self):
        """Test that safe import with allowed modules will not raise error"""
        import re
        from pathlib import Path

        self.assertEqual(
            import_dotted_string(
                "pathlib.Path", allowed_modules={"pathlib.Path": Path, "re": re}
            ),
            Path,
        )


class TestSerialize(TestCase):
    def test_serialize_simple_builtin_types(self):
        """Simple built-in types will be returned as is"""
        self.assertEqual(serialize(0.5), 0.5)
        self.assertEqual(serialize(None), None)
        self.assertEqual(serialize(True), True)
        self.assertEqual(serialize(1), 1)
        self.assertEqual(serialize("1"), "1")
        self.assertEqual(serialize([1, 2, 3]), [1, 2, 3])
        self.assertEqual(serialize((1, 2, 3)), (1, 2, 3))
        self.assertEqual(serialize({"a": 1, "b": 2}), {"a": 1, "b": 2})

    def test_serialize_complex_python_object(self):
        """Complex objects should become dotted string wrapped by double curly braces"""
        from pathlib import Path

        self.assertEqual(serialize(Path), "{{ pathlib.Path }}")
        self.assertEqual(serialize(serialize), "{{ theflow.utils.modules.serialize }}")

    def test_serialize_composite_list(self):
        """Composite type should be serialized as dotted string wrapped by double curly braces"""
        from theflow.base import Composable
        from pathlib import Path

        self.assertEqual(
            serialize([Composable, 6]), ["{{ theflow.base.Composable }}", 6]
        )
        self.assertEqual(
            serialize([Composable, 6, [Path, "hello"]]),
            ["{{ theflow.base.Composable }}", 6, ["{{ pathlib.Path }}", "hello"]],
        )

    def test_serialize_composite_dict(self):
        """Composite type should be serialized as dotted string wrapped by double curly braces"""
        from theflow.base import Composable
        from pathlib import Path

        self.assertEqual(
            serialize({"a": Composable, "b": 6}),
            {"a": "{{ theflow.base.Composable }}", "b": 6},
        )
        self.assertEqual(
            serialize({"a": Composable, "b": 6, "c": {"hello": Path}}),
            {
                "a": "{{ theflow.base.Composable }}",
                "b": 6,
                "c": {"hello": "{{ pathlib.Path }}"},
            },
        )

    @pytest.mark.skip(reason="TODO: not work yet")
    def test_serialize_type_annotation(self):
        """Type will be serialized mostly as is, except object will be dotted string"""
        from typing import Any, Union

        self.assertEqual(serialize(Any), "{{ typing.Any }}")
        self.assertEqual(serialize(Union[str, int]), "{{ typing.Union[str, int] }}")
        self.assertEqual(
            serialize(list[Composable]), "{{ list[theflow.base.Composable] }}"
        )


class TestDeserialize(TestCase):
    def test_deserialize_simple_builtin_types(self):
        """Simple built-in types will be returned as is"""
        self.assertEqual(deserialize(0.5), 0.5)
        self.assertEqual(deserialize(None), None)
        self.assertEqual(deserialize(True), True)
        self.assertEqual(deserialize(1), 1)
        self.assertEqual(deserialize("1"), "1")
        self.assertEqual(deserialize([1, 2, 3]), [1, 2, 3])
        self.assertEqual(deserialize((1, 2, 3)), (1, 2, 3))
        self.assertEqual(deserialize({"a": 1, "b": 2}), {"a": 1, "b": 2})

    def test_deserialize_complex_python_object_unsafe(self):
        """Complex Python object with dotted string will be imported"""
        from pathlib import Path

        self.assertEqual(deserialize("{{ pathlib.Path }}", safe=False), Path)
        self.assertEqual(
            deserialize("{{ theflow.utils.modules.serialize }}", safe=False), serialize
        )

    def test_deserialize_composite_list_unsafe(self):
        """Complex Python object within list"""
        from theflow.base import Composable
        from pathlib import Path

        self.assertEqual(
            deserialize(["{{ theflow.base.Composable }}", 6], safe=False),
            [Composable, 6],
        )
        self.assertEqual(
            deserialize(
                ["{{ theflow.base.Composable }}", 6, ["{{ pathlib.Path }}", "hello"]],
                safe=False,
            ),
            [Composable, 6, [Path, "hello"]],
        )

    def test_deserialize_composite_dict_unsafe(self):
        """Composite type should be serialized as dotted string wrapped by double curly braces"""
        from theflow.base import Composable
        from pathlib import Path

        self.assertEqual(
            deserialize({"a": "{{ theflow.base.Composable }}", "b": 6}, safe=False),
            {"a": Composable, "b": 6},
        )
        self.assertEqual(
            deserialize(
                {
                    "a": "{{ theflow.base.Composable }}",
                    "b": 6,
                    "c": {"hello": "{{ pathlib.Path }}"},
                },
                safe=False,
            ),
            {"a": Composable, "b": 6, "c": {"hello": Path}},
        )

    @pytest.mark.skip(reason="TODO: not work yet")
    def test_serialize_type_annotation(self):
        """Type will be serialized mostly as is, except object will be dotted string"""
        from typing import Any, Union

        self.assertEqual(serialize(Any), "{{ typing.Any }}")
        self.assertEqual(serialize(Union[str, int]), "{{ typing.Union[str, int] }}")
        self.assertEqual(
            serialize(list[Composable]), "{{ list[theflow.base.Composable] }}"
        )
