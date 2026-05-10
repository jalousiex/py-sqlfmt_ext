import unittest

from tests.sqlfmt_test_helpers import format_with_entry_defaults, selected_cases


class TestSqlfmtIdempotency(unittest.TestCase):
    def test_sqlfmt_entry_should_be_idempotent(self):
        for case in selected_cases():
            with self.subTest(case=case.name):
                first_pass = format_with_entry_defaults(case.input_sql)
                second_pass = format_with_entry_defaults(first_pass)
                self.assertEqual(second_pass, first_pass, "二次格式化结果发生变化")


if __name__ == "__main__":
    unittest.main()
