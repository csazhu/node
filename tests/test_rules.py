"""tools/rule.py 与项目 AGENTS.md 规则清单的完整性测试。"""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("agents_rule", ROOT / "tools" / "rule.py")
rule = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rule)


def empty_agents(text="# head\n\n## 6. 规则清单\n"):
    return f"{text}{rule.START}\n{rule.END}\n\n## tail\n"


class TestRuleTool(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "AGENTS.md"
        self.path.write_text(empty_agents(), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_numbers_and_preserves_document(self):
        status, line = rule.add_rule("  规则  一  ", path=self.path, today="2026-11-11")
        self.assertEqual(status, "added")
        self.assertEqual(line, "- R001 [2026-11-11] 规则 一")
        status, line = rule.add_rule("规则二", path=self.path, tag="流程", today="2026-11-11")
        self.assertEqual(status, "added")
        self.assertTrue(line.startswith("- R002 [2026-11-11] `流程` "))

        text = self.path.read_text(encoding="utf-8")
        self.assertIn("# head", text)
        self.assertIn("## tail", text)
        self.assertEqual(text.count(rule.START), 1)
        self.assertEqual(text.count(rule.END), 1)
        self.assertEqual(len(rule.list_rules(self.path)), 2)

    def test_duplicate_is_skipped(self):
        rule.add_rule("同一条规则", path=self.path)
        status, _ = rule.add_rule("  同一条  规则 ", path=self.path)
        self.assertEqual(status, "duplicate")
        self.assertEqual(len(rule.list_rules(self.path)), 1)

    def test_numbering_continues_from_existing(self):
        self.path.write_text(
            empty_agents().replace(
                f"{rule.START}\n{rule.END}",
                f"{rule.START}\n- R007 [2026-01-01] `x` 手写规则\n{rule.END}",
            ),
            encoding="utf-8",
        )
        status, line = rule.add_rule("新规则", path=self.path, today="2026-11-11")
        self.assertEqual(status, "added")
        self.assertTrue(line.startswith("- R008 "))

    def test_missing_markers_raise(self):
        self.path.write_text("没有标记的文件\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            rule.add_rule("x", path=self.path)

    def test_empty_rule_raises(self):
        with self.assertRaises(ValueError):
            rule.add_rule("   ", path=self.path)

    def test_project_agents_rules_are_well_formed(self):
        lines = rule.list_rules(rule.AGENTS_PATH)
        self.assertGreaterEqual(len(lines), 8)
        nums = []
        for line in lines:
            m = rule.LINE_RE.match(line)
            self.assertIsNotNone(m, f"规则行格式错误: {line}")
            nums.append(int(m.group(1)))
        self.assertEqual(nums, list(range(1, len(nums) + 1)), "规则编号应连续")
        self.assertEqual(len(set(rule._body(l) for l in lines)), len(lines), "规则不应重复")

    def test_project_agents_is_concise(self):
        text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertLessEqual(len(text.splitlines()), 130, "AGENTS.md 应保持精简")
        self.assertIn("自测", text)
        self.assertIn("自动刷新", text)


if __name__ == "__main__":
    unittest.main()
