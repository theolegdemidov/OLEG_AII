import tempfile
import unittest
from pathlib import Path

from oleg_ai import launcher


def scripted(*answers):
    it = iter(answers)
    return lambda prompt="": next(it)


class TestLauncher(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_clean_path_strips_drag_and_drop_quotes(self):
        self.assertEqual(launcher.clean_path('  "C:\\Видео\\папка" '), Path("C:\\Видео\\папка"))

    def test_set_env_values_updates_and_appends_keeping_comments(self):
        env = self.d / ".env"
        env.write_text("# комментарий\nA=1\nB=\nGEMINI_API_KEY=\n", encoding="utf-8")
        launcher.set_env_values(env, {"B": "2", "NEW": "x"})
        lines = env.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[:3], ["# комментарий", "A=1", "B=2"])
        self.assertIn("NEW=x", lines)

    def test_first_run_wizard_creates_env_with_generated_token(self):
        example = self.d / ".env.example"
        example.write_text("API_TOKEN=\nLLM_PROVIDER=anthropic\nGEMINI_API_KEY=\nYOUTUBE_API_KEY=\n", encoding="utf-8")
        env = self.d / ".env"
        self.assertTrue(launcher.ensure_env(env, example, scripted("2", "gem-key", "", "https://t.me/x")))
        text = env.read_text(encoding="utf-8")
        self.assertIn("LLM_PROVIDER=gemini", text)
        self.assertIn("GEMINI_API_KEY=gem-key", text)
        self.assertIn("TELEGRAM_CHANNEL_URL=https://t.me/x", text)
        token = [l for l in text.splitlines() if l.startswith("API_TOKEN=")][0].split("=", 1)[1]
        self.assertGreaterEqual(len(token), 32)
        self.assertFalse(launcher.ensure_env(env, example, scripted()))  # второй раз ничего не спрашивает

    def test_wizard_all_skipped_still_works(self):
        env = self.d / ".env"
        launcher.ensure_env(env, self.d / "missing.example", scripted("", "", "", ""))
        self.assertIn("LLM_PROVIDER=anthropic", env.read_text(encoding="utf-8"))

    def test_scan_folder(self):
        vids = self.d / "v"
        vids.mkdir()
        for n in ["b_страх-растёт.MP4", "a.mov", "notes.txt", "c.webm"]:
            (vids / n).write_bytes(b"x")
        rows = launcher.scan_folder(vids, self.d / "videos.csv")
        self.assertEqual([r["file"] for r in rows], ["a.mov", "b_страх-растёт.MP4", "c.webm"])
        self.assertEqual(rows[1]["topic"], "b страх растёт")
        self.assertIn("a.mov", (self.d / "videos.csv").read_text(encoding="utf-8-sig"))

    def test_local_ip_is_an_address(self):
        self.assertRegex(launcher.local_ip(), r"^\d+\.\d+\.\d+\.\d+$")

    def test_menu_exit_and_bad_choice(self):
        # .env уже существует в ROOT или создаётся мастером: подставляем ответы мастера на случай первого запуска
        env = launcher.ROOT / ".env"
        existed = env.exists()
        try:
            answers = ["9", "5"] if existed else ["", "", "", "", "9", "5"]
            self.assertEqual(launcher.main(scripted(*answers)), 0)
        finally:
            if not existed and env.exists():
                env.unlink()


if __name__ == "__main__":
    unittest.main()
