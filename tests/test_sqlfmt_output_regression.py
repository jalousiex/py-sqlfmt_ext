import unittest

from tests.sqlfmt_test_helpers import case_expected, format_with_entry_defaults, selected_cases


class TestSqlfmtOutputRegression(unittest.TestCase):
    def test_sqlfmt_entry_output_should_match_expected(self):
        for case in selected_cases():
            with self.subTest(case=case.name):
                actual_output = format_with_entry_defaults(case.input_sql)
                self.assertEqual(actual_output, case_expected(case), "格式化输出与期望不一致")


if __name__ == "__main__":
    unittest.main()
