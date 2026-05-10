import unittest

from tests.sqlfmt_test_helpers import case_expected, case_input, selected_cases


class TestSqlfmtCaseIntegrity(unittest.TestCase):
    def test_cases_should_be_defined_and_unique(self):
        cases = selected_cases()
        self.assertGreater(len(cases), 0, "筛选后无可用 SQL 用例")
        names = [case.name for case in cases]
        self.assertEqual(len(names), len(set(names)), "用例名称必须唯一")

    def test_case_fields_should_not_be_empty(self):
        for case in selected_cases():
            with self.subTest(case=case.name):
                self.assertTrue(case.name.strip(), "用例名称不能为空")
                self.assertTrue(case.note.strip(), "用例说明不能为空")
                self.assertTrue(case_input(case), "输入 SQL 不能为空")
                self.assertTrue(case_expected(case), "期望 SQL 不能为空")
                self.assertGreater(len(case.tags), 0, "用例至少应包含一个标签")


if __name__ == "__main__":
    unittest.main()
