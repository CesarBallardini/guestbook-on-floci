"""The one architecture rule that import-linter can't state: the domain is standard library only.

The rules between the layers are import-linter contracts, in pyproject.toml, run by
"make architecture". A contract can forbid the libraries it names; this test forbids every
library, named or not.
"""

import ast
import sys
from pathlib import Path

import pytest

import guestbook.domain

pytestmark = pytest.mark.unit

DOMAIN_DIR = Path(guestbook.domain.__file__).parent


def imported_modules() -> set[str]:
    """Every module imported anywhere in the domain, type-checking imports included."""
    modules: set[str] = set()
    for source_file in DOMAIN_DIR.rglob('*.py'):
        for node in ast.walk(ast.parse(source_file.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert node.level == 0, f'{source_file}: relative import'
                assert node.module is not None
                modules.add(node.module)
    return modules


def test_the_domain_has_imports_to_check() -> None:
    assert imported_modules()


def test_the_domain_imports_the_standard_library_and_itself_only() -> None:
    foreign = {
        module
        for module in imported_modules()
        if module.split('.')[0] not in sys.stdlib_module_names and not module.startswith('guestbook.domain')
    }

    assert foreign == set()
