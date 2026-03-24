import unittest

from src.pipeline.chunking import (
    DefaultLanguageRegistry,
    get_language_registry,
    reset_language_registry,
)


class _DummyStrategy:
    @property
    def name(self) -> str:
        return "dummy"

    def supports_language(self, language: str | None) -> bool:
        return language == "python"

    def chunk(
        self, request, language, config
    ):  # pragma: no cover - behavior not under test here
        return []


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

    def test_strategy_registration(self) -> None:
        strategy = _DummyStrategy()
        self.registry.register_strategy("python", strategy)
        self.assertIs(self.registry.get_strategy("python"), strategy)
        self.assertIs(self.registry.get_strategy("PYTHON"), strategy)
        self.assertIsNone(self.registry.get_strategy("rust"))

    def test_global_singleton_registry(self) -> None:
        reg1 = reset_language_registry()
        reg2 = get_language_registry()
        reg3 = get_language_registry()
        self.assertIs(reg1, reg2)
        self.assertIs(reg2, reg3)

        strategy = _DummyStrategy()
        reg1.register_strategy("python", strategy)
        self.assertIs(reg2.get_strategy("python"), strategy)


if __name__ == "__main__":
    unittest.main()
