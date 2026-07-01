"""Scope-boundary smoke test for the orchestration engine.

# Feature: orchestration-engine-completion, Task 32.2 (scope boundaries)

Requirement 21 defines the feature's scope and its safety invariants. This
module statically/structurally asserts two of those boundaries over the
Control_Plane source trees (``core/``, ``cp/`` and ``adapters/``):

* **Out-of-scope features are absent (Req 21.3).** Voice mode, vision/image
  input, browser automation, Kubernetes backends, and distributed swarm
  execution are explicitly out of scope. This module scans the source for
  tell-tale *import statements* of the libraries that would implement those
  capabilities and for *class/def definitions* whose names encode them, and
  asserts none are present.

* **No host execution path exists (Req 21.1).** All code and command execution
  must route through the kernel-backed Sandbox
  (:class:`adapters.rust_infra.RustInfraExecutionManager`). No orchestration
  module may spawn processes on the host. This module scans for host-execution
  primitives (``subprocess``, ``os.system``/``os.popen``/``os.exec*``,
  ``pty.spawn``, ``commands.getoutput``, and builtin ``eval(``/``exec(`` calls)
  and asserts none appear in the orchestration source, with particular focus on
  the step/tool/code execution modules
  (``core/code_executor.py``, ``core/tool_registry.py``,
  ``core/dag_executor.py``, ``adapters/rust_infra.py``).

Robustness notes:

* Scanning ignores string literals, docstrings, and comments. The source
  deliberately *names* the excluded features in prose (e.g. "there is no host
  path", "WorkloadControl.Exec") — those mentions must not trip a violation.
  We reconstruct a "code-only" view of each file with :mod:`tokenize`, blanking
  every STRING/COMMENT (and f-string literal) token while preserving line
  numbers, then match with :mod:`re` line by line.
* Generated protobuf/gRPC stubs (``core/generated/``) are excluded: they are
  machine-generated kernel transport code (which legitimately contains a
  ``WorkloadControl.Exec`` RPC), not orchestration logic.
* Every failure names the offending ``file:line`` and the matched snippet.

**Validates: Requirements 21.3, 21.1**
"""

from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# Source tree discovery
# ---------------------------------------------------------------------------

_CP_ROOT = Path(__file__).resolve().parent.parent
_SOURCE_ROOTS = (_CP_ROOT / "core", _CP_ROOT / "cp", _CP_ROOT / "adapters")

# Directories excluded from scanning: generated kernel transport stubs and
# bytecode caches are not orchestration source.
_EXCLUDED_DIR_PARTS = frozenset({"generated", "__pycache__"})

# The production execution modules that must have no host-execution path.
_EXECUTION_MODULES = (
    _CP_ROOT / "core" / "code_executor.py",
    _CP_ROOT / "core" / "tool_registry.py",
    _CP_ROOT / "core" / "dag_executor.py",
    _CP_ROOT / "adapters" / "rust_infra.py",
)


def _iter_source_files() -> list[Path]:
    """Return every orchestration ``.py`` file, excluding generated/cache dirs."""
    files: list[Path] = []
    for root in _SOURCE_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            if _EXCLUDED_DIR_PARTS.intersection(path.parts):
                continue
            files.append(path)
    return files


# ---------------------------------------------------------------------------
# Code-only view (strip strings/docstrings/comments, preserve line numbers)
# ---------------------------------------------------------------------------

# Token types whose text we blank out so prose never trips a match. f-string
# literal token types only exist on newer Pythons, so resolve them defensively.
_BLANK_TOKEN_TYPES = {tokenize.STRING, tokenize.COMMENT}
for _name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END"):
    _tok = getattr(tokenize, _name, None)
    if _tok is not None:
        _BLANK_TOKEN_TYPES.add(_tok)


def _code_only_lines(path: Path) -> list[str]:
    """Return the file's lines with strings/docstrings/comments blanked out.

    Line numbers are preserved (index ``i`` is source line ``i + 1``) so failure
    messages point at the real location. If a file cannot be tokenized we fall
    back to the raw text, which fails safe (a real violation would still match).
    """
    text = path.read_text(encoding="utf-8")
    buffer = [list(line) for line in text.splitlines()]

    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return text.splitlines()

    for tok in tokens:
        if tok.type not in _BLANK_TOKEN_TYPES:
            continue
        (srow, scol), (erow, ecol) = tok.start, tok.end
        for row in range(srow, erow + 1):
            if row - 1 >= len(buffer):
                continue
            chars = buffer[row - 1]
            start = scol if row == srow else 0
            end = ecol if row == erow else len(chars)
            for col in range(start, min(end, len(chars))):
                chars[col] = " "

    return ["".join(chars) for chars in buffer]


# ---------------------------------------------------------------------------
# Out-of-scope feature detection (Req 21.3)
# ---------------------------------------------------------------------------

# Excluded-capability libraries, grouped by the out-of-scope feature they would
# implement. Matched only as real ``import``/``from ... import`` module names.
_EXCLUDED_IMPORT_MODULES = {
    # Voice mode / audio
    "whisper": "voice mode",
    "faster_whisper": "voice mode",
    "speech_recognition": "voice mode",
    "sounddevice": "voice mode",
    "pyaudio": "voice mode",
    "vosk": "voice mode",
    # Vision / image input
    "cv2": "vision/image input",
    "opencv": "vision/image input",
    "PIL": "vision/image input",
    "pytesseract": "vision/image input",
    "easyocr": "vision/image input",
    "torchvision": "vision/image input",
    "face_recognition": "vision/image input",
    # Browser automation
    "selenium": "browser automation",
    "playwright": "browser automation",
    "puppeteer": "browser automation",
    "pyppeteer": "browser automation",
    "pyautogui": "browser automation",
    "mss": "browser automation",
    # Kubernetes backends
    "kubernetes": "Kubernetes backend",
    "kubernetes_asyncio": "Kubernetes backend",
    "kubectl": "Kubernetes backend",
    "kubernetes_client": "Kubernetes backend",
}

_IMPORT_RE = re.compile(
    r"^\s*(?:import|from)\s+([A-Za-z_][\w.]*)",
)

# Unambiguous identifier tokens that, if they appear in a class/def name, encode
# an out-of-scope capability. Deliberately excludes ambiguous words like
# "vision"/"voice"/"image"/"audio"/"browser" (they collide with benign words
# such as "provision"/"revision"); those capabilities are covered by the
# library-import scan above instead.
_EXCLUDED_SYMBOL_TOKENS = {
    "swarm": "distributed swarm execution",
    "kubernetes": "Kubernetes backend",
    "k8s": "Kubernetes backend",
    "kubectl": "Kubernetes backend",
    "selenium": "browser automation",
    "playwright": "browser automation",
    "puppeteer": "browser automation",
    "pyppeteer": "browser automation",
    "webdriver": "browser automation",
    "opencv": "vision/image input",
    "tesseract": "vision/image input",
    "whisper": "voice mode",
}

_DEF_RE = re.compile(r"^\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_]\w*)")

_IDENT_PART_RE = re.compile(r"[A-Za-z][a-z0-9]*|[A-Z]+(?=[A-Z]|$)|\d+")


def _identifier_tokens(name: str) -> set[str]:
    """Split an identifier into lowercase word tokens.

    Handles both ``snake_case`` and ``camelCase``/``PascalCase`` so that names
    like ``KubernetesBackend`` or ``start_k8s_backend`` decompose into the words
    they contain (``{kubernetes, backend}`` / ``{start, k8s, backend}``).
    """
    tokens: set[str] = set()
    for chunk in re.split(r"_+", name):
        for part in _IDENT_PART_RE.findall(chunk):
            tokens.add(part.lower())
    return tokens


def _scan_excluded_imports(path: Path, lines: list[str]) -> list[str]:
    violations: list[str] = []
    for lineno, line in enumerate(lines, start=1):
        match = _IMPORT_RE.match(line)
        if not match:
            continue
        top_module = match.group(1).split(".")[0]
        feature = _EXCLUDED_IMPORT_MODULES.get(top_module)
        if feature is not None:
            violations.append(
                f"{path}:{lineno}: out-of-scope {feature} import "
                f"({top_module!r}) -> {line.strip()!r}"
            )
    return violations


def _scan_excluded_symbols(path: Path, lines: list[str]) -> list[str]:
    violations: list[str] = []
    for lineno, line in enumerate(lines, start=1):
        match = _DEF_RE.match(line)
        if not match:
            continue
        name = match.group(1)
        name_tokens = _identifier_tokens(name)
        for token, feature in _EXCLUDED_SYMBOL_TOKENS.items():
            if token in name_tokens:
                violations.append(
                    f"{path}:{lineno}: out-of-scope {feature} definition "
                    f"({name!r} contains {token!r}) -> {line.strip()!r}"
                )
    return violations


# ---------------------------------------------------------------------------
# Host-execution path detection (Req 21.1)
# ---------------------------------------------------------------------------

# Each pattern matches a way to run code/commands on the host directly. Matched
# against the code-only view so docstrings/comments/strings never trip them.
_HOST_EXEC_PATTERNS = (
    (re.compile(r"\bsubprocess\b"), "subprocess module"),
    (re.compile(r"\bos\.system\s*\("), "os.system()"),
    (re.compile(r"\bos\.popen\s*\("), "os.popen()"),
    (re.compile(r"\bos\.exec[lv]\w*\s*\("), "os.exec*()"),
    (re.compile(r"\bos\.spawn\w*\s*\("), "os.spawn*()"),
    (re.compile(r"\bpty\.spawn\s*\("), "pty.spawn()"),
    (re.compile(r"\bcommands\.get(?:status)?output\s*\("), "commands.getoutput()"),
    # Builtin eval()/exec() of code, but not attribute calls like `.Exec(`.
    (re.compile(r"(?<![\w.])eval\s*\("), "builtin eval()"),
    (re.compile(r"(?<![\w.])exec\s*\("), "builtin exec()"),
)


def _scan_host_exec(path: Path, lines: list[str]) -> list[str]:
    violations: list[str] = []
    for lineno, line in enumerate(lines, start=1):
        for pattern, label in _HOST_EXEC_PATTERNS:
            if pattern.search(line):
                violations.append(
                    f"{path}:{lineno}: host execution path via {label} "
                    f"-> {line.strip()!r}"
                )
    return violations


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_source_tree_is_discoverable() -> None:
    """Sanity check: the scan actually covers the orchestration source.

    Guards against the scan silently passing because it found no files (e.g. a
    path typo), which would make the boundary assertions vacuous.
    """
    files = _iter_source_files()
    assert files, "no orchestration source files were discovered to scan"
    names = {f.name for f in files}
    for module in _EXECUTION_MODULES:
        assert module.exists(), f"expected execution module missing: {module}"
        assert module.name in names


def test_no_out_of_scope_feature_imports() -> None:
    """Req 21.3: no imports of voice/vision/browser/Kubernetes/swarm libraries."""
    violations: list[str] = []
    for path in _iter_source_files():
        violations.extend(_scan_excluded_imports(path, _code_only_lines(path)))

    assert not violations, "out-of-scope feature imports found:\n" + "\n".join(
        violations
    )


def test_no_out_of_scope_feature_symbols() -> None:
    """Req 21.3: no class/def encodes an out-of-scope capability by name."""
    violations: list[str] = []
    for path in _iter_source_files():
        violations.extend(_scan_excluded_symbols(path, _code_only_lines(path)))

    assert not violations, "out-of-scope feature definitions found:\n" + "\n".join(
        violations
    )


def test_no_host_execution_path_in_orchestration_source() -> None:
    """Req 21.1: no orchestration module runs code/commands on the host."""
    violations: list[str] = []
    for path in _iter_source_files():
        violations.extend(_scan_host_exec(path, _code_only_lines(path)))

    assert not violations, (
        "host execution paths found (all execution must route through the "
        "kernel-backed Sandbox):\n" + "\n".join(violations)
    )


def test_execution_modules_have_no_host_execution_path() -> None:
    """Req 21.1: the step/tool/code execution modules are host-exec free.

    A focused, explicit assertion on the four modules responsible for running
    steps, tools, and code — the modules where a host-execution regression is
    most likely and most dangerous.
    """
    violations: list[str] = []
    for path in _EXECUTION_MODULES:
        violations.extend(_scan_host_exec(path, _code_only_lines(path)))

    assert not violations, (
        "host execution path in a core execution module (must route through "
        "RustInfraExecutionManager only):\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Detector robustness (property-based)
# ---------------------------------------------------------------------------

# Benign words that superficially resemble excluded capabilities but must NOT be
# flagged (they encode no out-of-scope feature).
_BENIGN_WORDS = [
    "provision",
    "revision",
    "envision",
    "provisional",
    "image",
    "images",
    "audio",
    "voice",
    "vision",
    "browser",
    "browse",
    "command",
    "commander",
    "executor",
    "execute",
    "evaluate",
    "evaluation",
    "swarming",  # substring only; token is "swarming", not "swarm"
    "framework",
    "manager",
    "registry",
    "workflow",
    "handler",
    "sandbox",
    "kernel",
]


@settings(max_examples=200, deadline=None)
@given(
    st.lists(st.sampled_from(_BENIGN_WORDS), min_size=1, max_size=4),
    st.sampled_from(["snake", "pascal"]),
)
def test_symbol_detector_has_no_false_positives(words: list[str], style: str) -> None:
    """The symbol detector never flags identifiers built from benign words.

    Guards the ``_identifier_tokens`` / ``_EXCLUDED_SYMBOL_TOKENS`` matcher
    against false positives so the Req 21.3 assertion stays trustworthy.

    **Validates: Requirements 21.3**
    """
    if style == "snake":
        name = "_".join(words)
        line = f"def {name}(self):"
    else:
        name = "".join(w.capitalize() for w in words)
        line = f"class {name}:"

    violations = _scan_excluded_symbols(Path("synthetic.py"), [line])
    assert violations == [], f"false positive on benign identifier {name!r}: {violations}"


@settings(max_examples=200, deadline=None)
@given(
    st.sampled_from(sorted(_EXCLUDED_SYMBOL_TOKENS)),
    st.sampled_from(_BENIGN_WORDS),
    st.sampled_from(["prefix", "suffix"]),
)
def test_symbol_detector_flags_excluded_tokens(
    token: str, benign: str, position: str
) -> None:
    """The symbol detector flags identifiers that embed an excluded token.

    Confirms the matcher actually catches an out-of-scope capability name in
    both ``snake_case`` and mixed contexts, so the assertion is not vacuous.

    **Validates: Requirements 21.3**
    """
    parts = [token, benign] if position == "prefix" else [benign, token]
    name = "_".join(parts)
    line = f"class {name}:"

    violations = _scan_excluded_symbols(Path("synthetic.py"), [line])
    assert violations, f"missed excluded token {token!r} in identifier {name!r}"


@pytest.mark.parametrize(
    "line",
    [
        "    response = self._call(self._stub.Exec, request)",  # gRPC attr, not builtin
        '    """there is no host path; execution is blocked."""',  # prose
        "    command = list(request.command)",  # benign 'command' variable
        "from core.orchestration_types import GrantContext",  # benign import
    ],
)
def test_host_exec_detector_ignores_benign_lines(line: str) -> None:
    """The host-exec detector does not flag benign attribute calls or prose."""
    # Feed through the code-only path is unnecessary here; the regexes alone
    # must already avoid these false positives on raw code lines.
    assert _scan_host_exec(Path("synthetic.py"), [line]) == []


@pytest.mark.parametrize(
    "line",
    [
        "    subprocess.run(['ls'])",
        "    os.system('rm -rf /')",
        "    result = eval(user_code)",
        "    exec(payload)",
        "    pty.spawn(['/bin/sh'])",
    ],
)
def test_host_exec_detector_flags_real_host_exec(line: str) -> None:
    """The host-exec detector catches genuine host-execution primitives."""
    assert _scan_host_exec(Path("synthetic.py"), [line])
