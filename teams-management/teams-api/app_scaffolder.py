"""Application source-code scaffolder.

Reads template files from templates/{language}/{workload_type}/, performs
placeholder substitution, and returns a Dict[str, str] mapping repo-relative
paths to rendered content.  Pure data transformation — no side effects.
"""

from pathlib import Path
from typing import Dict

from builders import Language, WorkloadType

TEMPLATE_ROOT = Path(__file__).parent / "templates"

GITHUB_OWNER = "rodmhgl"

# Mapping of shared language-level templates to their repo-relative output paths
_SHARED_TEMPLATES = {
    "build.yml.tmpl": ".github/workflows/build.yml",
    ".releaserc.json.tmpl": ".releaserc.json",
}


def _build_placeholders(
    workload_name: str,
    language: Language,
    port: int,
) -> Dict[str, str]:
    """Build the placeholder substitution map."""
    if language == Language.python:
        module_name = workload_name.replace("-", "_")
    else:
        module_name = workload_name

    return {
        "{{GITHUB_OWNER}}": GITHUB_OWNER,
        "{{MODULE_NAME}}": module_name,
        "{{PORT}}": str(port),
        "{{WORKLOAD_NAME}}": workload_name,
    }


def _substitute(content: str, placeholders: Dict[str, str]) -> str:
    """Replace all placeholders in content."""
    for key, value in placeholders.items():
        content = content.replace(key, value)
    return content


def scaffold_app_source(
    workload_name: str,
    language: Language,
    workload_type: WorkloadType,
    port: int = 8080,
) -> Dict[str, str]:
    """Generate application source files from templates.

    Returns a dict of {repo_relative_path: rendered_content} ready to be
    committed to a new GitHub repository.
    """
    placeholders = _build_placeholders(workload_name, language, port)
    files: Dict[str, str] = {}

    # Walk workload-type-specific templates
    type_dir = TEMPLATE_ROOT / language.value / workload_type.value
    if type_dir.is_dir():
        for tmpl_path in sorted(type_dir.rglob("*.tmpl")):
            relative = tmpl_path.relative_to(type_dir)
            # Strip .tmpl suffix for the output path
            output_path = str(relative).removesuffix(".tmpl")
            content = tmpl_path.read_text()
            files[output_path] = _substitute(content, placeholders)

    # Load shared language-level templates
    lang_dir = TEMPLATE_ROOT / language.value
    for tmpl_name, output_path in _SHARED_TEMPLATES.items():
        tmpl_path = lang_dir / tmpl_name
        if tmpl_path.is_file():
            content = tmpl_path.read_text()
            files[output_path] = _substitute(content, placeholders)

    return files
