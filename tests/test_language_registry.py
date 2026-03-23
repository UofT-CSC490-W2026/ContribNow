import unittest

from src.pipeline.chunking import DefaultLanguageRegistry


class TestLanguageRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = DefaultLanguageRegistry()

    def test_detect_by_extension(self) -> None:
        self.assertEqual(self.registry.detect("src/main.py"), "python")
        self.assertEqual(self.registry.detect("lib/index.ts"), "typescript")
        self.assertEqual(self.registry.detect("infra/main.tf"), "hcl")

    def test_detect_by_special_filename(self) -> None:
        self.assertEqual(self.registry.detect("Dockerfile"), "dockerfile")
        self.assertEqual(self.registry.detect("Makefile"), "makefile")
        self.assertEqual(self.registry.detect("CMakeLists.txt"), "cmake")

    def test_detect_by_shebang(self) -> None:
        self.assertEqual(
            self.registry.detect("scripts/tool", "#!/usr/bin/env python3\nprint(1)\n"),
            "python",
        )
        self.assertEqual(
            self.registry.detect("scripts/run", "#!/usr/bin/env bash\necho hi\n"),
            "shell",
        )
        self.assertEqual(
            self.registry.detect(
                "scripts/dev", "#!/usr/bin/env node\nconsole.log(1)\n"
            ),
            "javascript",
        )

    def test_unknown_language(self) -> None:
        self.assertIsNone(self.registry.detect("docs/notes.custom"))
        self.assertIsNone(
            self.registry.detect("scripts/runner", "#!/usr/bin/env perl\nprint 'x';\n")
        )


if __name__ == "__main__":
    unittest.main()
