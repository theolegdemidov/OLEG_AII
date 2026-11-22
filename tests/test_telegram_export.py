import json
import tempfile
import unittest
from pathlib import Path

from oleg_ai import telegram_export as tg


def export(n=12, views=False):
    msgs = [{"id": 0, "type": "service", "date": "2026-11-01T10:00:00", "text": ""}]
    for i in range(n):
        m = {"id": i + 1, "type": "message", "date": f"2026-11-{i + 1:02d}T{(9 if i % 2 else 19):02d}:30:00",
             "text": [{"type": "bold", "text": "Дисциплина"}, " важнее мотивации #дисциплина " + "x" * (i * 80)],
             "reactions": [{"emoji": "🔥", "count": 5 * (i + 1)}]}
        if views:
            m["views"] = 100 * (i + 1)
        msgs.append(m)
    return {"name": "Канал", "messages": msgs}


class TestTelegramExport(unittest.TestCase):
    def load(self, data):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "result.json"
            p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return tg.load_posts(p)

    def test_parsing_text_entities_and_service_skipped(self):
        posts = self.load(export())
        self.assertEqual(len(posts), 12)
        self.assertTrue(posts[0]["text"].startswith("Дисциплина важнее"))
        self.assertEqual(posts[0]["reactions"], 5)

    def test_metric_choice(self):
        self.assertEqual(tg.choose_metric(self.load(export())), "reactions")
        self.assertEqual(tg.choose_metric(self.load(export(views=True))), "views")

    def test_report_honest_about_small_groups(self):
        rep = tg.build_report(self.load(export()))
        self.assertIn("постов: 6", rep)
        self.assertIn("мало данных", rep)      # ночь/утро/вечер без 3 постов
        self.assertIn("#дисциплина", rep)
        self.assertIn("не причины", rep)

    def test_too_few_posts(self):
        self.assertIn("Слишком мало", tg.build_report(self.load(export(3))))

    def test_account_wide_export_and_broken_dates(self):
        data = {"chats": {"list": [{"messages": export(6)["messages"] + [{"type": "message", "date": "bad", "text": "x"}]}]}}
        self.assertEqual(len(self.load(data)), 6)


if __name__ == "__main__":
    unittest.main()
