from unittest import TestCase

from finestflow.utils import is_name_matched, is_parent_of_child


class TestNameMatching(TestCase):

    def test_name_matching_exact(self):
        """Test if the name matching is correct"""
        self.assertTrue(is_name_matched("", ""))
        self.assertTrue(is_name_matched(".main", ".main"))
        self.assertTrue(is_name_matched(".main.pipeline_A1", ".main.pipeline_A1"))
        self.assertFalse(is_name_matched(".main.pipeline_A1", ".main.pipeline_A2"))

    def test_name_matching_wildcard(self):
        """Test for wildcard matching"""
        self.assertTrue(is_name_matched(
            ".main.pipeline_A1.pipeline_B2.pipeline_C2.step_a",
            ".main.*.pipeline_B2.*.step_a"
        ))

        self.assertTrue(is_name_matched(
            ".main.pipeline_A1.pipeline_B2.pipeline_C2.step_a",
            ".main.*.pipeline_B2.pipeline*.step_a"
        ))

        self.assertFalse(is_name_matched(
            ".main.pipeline_A1.pipeline_B2.pipeline_C2.step_a.some_step",
            ".main.*.pipeline_B2.pipeline*.step_a"
        ))


class TestParentChildMatching(TestCase):
    
        def test_parent_child_matching_exact(self):
            """Test if the parent-child matching is correct"""    
            self.assertTrue(is_parent_of_child(
                ".main.pipeline_A1",
                ".main.pipeline_A1.pipeline_B1"
            ))
    
            self.assertFalse(is_parent_of_child(
                ".main.pipeline_A1",
                ".main.pipeline_A2"
            ))
    
        def test_parent_child_matching_wildcard(self):
            """Test for wildcard matching"""
            self.assertTrue(is_parent_of_child(
                ".main.pipeline_A1.pipeline_B2.pipeline_C2",
                ".main.*.pipeline_B2.*.step_a"
            ))
    
            self.assertTrue(is_parent_of_child(
                ".main.pipeline_A1.pipeline_B2.pipeline_C2",
                ".main.*.pipeline_B2.pipeline*.step_a"
            ))
    
            self.assertFalse(is_parent_of_child(
                ".main.pipeline_A1.pipeline_B2.pipeline_C2",
                ".main.*.pipeline_B2.pipeline*.step_a.some_step"
            ))