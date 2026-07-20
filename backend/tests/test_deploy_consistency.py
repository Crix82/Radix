"""Guards against config drifting between the app and the files that provision it.

The M6 fix for the 404 model tag (`qwen3.5:9b-instruct-q4_K_M` does not exist on the Ollama
registry) updated `.env.example`, `config.py`, the install guide and the spec — but missed
`deploy/install.sh`, which is precisely the file that writes a *new* customer's `.env`. A fresh
install kept defaulting to the dead tag, `ollama pull` failed, and the installer only warned:
the stack came up with no model. Nothing caught it because the deploy scripts sit outside the
ruff/mypy gate and no test read them.
"""

import re
from pathlib import Path

from app.core.config import get_settings

REPO = Path(__file__).resolve().parents[2]
INSTALL_SH = REPO / "deploy" / "install.sh"
ENV_EXAMPLE = REPO / ".env.example"
DOCKERFILE = REPO / "backend" / "Dockerfile"

_TAG_RE = re.compile(r"qwen[\w.]*:[\w.\-]+")


def _default_model() -> str:
    get_settings.cache_clear()
    model = get_settings().llm_model
    get_settings.cache_clear()
    return model


def test_install_sh_offers_the_same_default_model_as_the_app() -> None:
    tags = set(_TAG_RE.findall(INSTALL_SH.read_text()))
    assert tags, "no model tag found in install.sh — did the wizard change shape?"
    assert tags == {_default_model()}, (
        f"install.sh offers {sorted(tags)} but the app defaults to {_default_model()!r}; "
        "a wizard default that disagrees with the app ships a broken .env"
    )


def test_env_example_matches_the_app_default() -> None:
    tags = set(_TAG_RE.findall(ENV_EXAMPLE.read_text()))
    assert tags == {_default_model()}


def test_image_bakes_models_through_the_runtime_path() -> None:
    """`docling-tools models download` populates a cache the runtime never reads.

    Docling's LayoutModel resolves through snapshot_download into the HuggingFace cache, while
    the CLI writes to /root/.cache/docling/models. The M6 image shipped 1.3 GB there and still
    fetched the layout model from the Hub on the first document — verified by parsing a fixture
    under `docker run --network none`, which failed on the M6 image and passes on this one.
    That breaks SPEC §9 ("nessuna chiamata esterna a runtime") on an air-gapped install.

    Warming the service's own converters downloads exactly what the runtime resolves.
    """
    dockerfile = DOCKERFILE.read_text()
    assert "warm_models" in dockerfile, "the image must warm models via the service's own path"
    assert "docling-tools models download" not in dockerfile, (
        "docling-tools writes to a cache the runtime does not read — see SPEC §9 and ADR 0009"
    )


def test_dependencies_are_installed_from_the_lockfile() -> None:
    """An unpinned `pip install .` resolves whatever is newest on build day (ADR 0009)."""
    dockerfile = DOCKERFILE.read_text()
    assert "requirements.lock" in dockerfile
    assert (REPO / "backend" / "requirements.lock").exists()
