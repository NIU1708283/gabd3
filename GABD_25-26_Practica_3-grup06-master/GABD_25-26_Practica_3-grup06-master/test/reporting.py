# reporting.py
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Mapping, Iterable, Tuple, Callable
from collections import Counter
import datetime as dt
import json
import math
import pathlib

import os
import subprocess
from pathlib import Path
import re
import html as _html
import html





# Assume que ja tens ReportMeta definit tal com al teu mòdul reporting.py
# from reporting import ReportMeta


def ensure_output_path(path: pathlib.Path):
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run_git(args, cwd=None) -> Optional[str]:
    try:
        out = subprocess.check_output(["git"] + args, cwd=cwd, stderr=subprocess.DEVNULL, text=True)
        return out.strip()
    except Exception:
        return None

def _parse_repo_name_from_remote(url: str) -> Optional[str]:
    """
    Converteix remote URL -> 'owner/repo'
    Exemples:
      https://github.com/acme/vision-model.git -> acme/vision-model
      git@github.com:acme/vision-model.git -> acme/vision-model
      https://gitlab.com/org/proj -> org/proj
    """
    if not url:
        return None
    url = url.strip()
    # SSH: git@host:owner/repo(.git)
    m = re.match(r".*?:([^/]+/[^/]+?)(?:\.git)?$", url)
    if m:
        return m.group(1)
    # HTTPS: https://host/owner/repo(.git)
    m = re.match(r"https?://[^/]+/([^/]+/[^/]+?)(?:\.git)?$", url)
    if m:
        return m.group(1)
    return None

def _ci_context() -> Dict[str, Optional[str]]:
    """
    Detecta variables d'entorn comunes de CI/CD i retorna dict amb info.
    Suporta: GitHub Actions, GitLab CI, Jenkins, Azure DevOps.
    """
    env = os.environ
    ci = {}

    # GitHub Actions
    if env.get("GITHUB_ACTIONS") == "true":
        ci["provider"] = "github"
        ci["branch"] = env.get("GITHUB_REF_NAME") or env.get("GITHUB_HEAD_REF")
        ci["commit"] = env.get("GITHUB_SHA")
        repo = env.get("GITHUB_REPOSITORY")  # owner/repo
        if repo:
            ci["repo_name"] = repo
        ci["author"] = env.get("GITHUB_ACTOR")
        ci["email"] = None  # no la dóna GHA per defecte
        # environment: pots codificar per event/ref, o usar vars pròpies
        ci["environment"] = env.get("ENVIRONMENT") or env.get("ENV") or "ci"

    # GitLab CI
    if env.get("GITLAB_CI") == "true":
        ci["provider"] = "gitlab"
        ci["branch"] = env.get("CI_COMMIT_REF_NAME")
        ci["commit"] = env.get("CI_COMMIT_SHA")
        ci["repo_name"] = env.get("CI_PROJECT_PATH")  # group/project
        ci["author"] = env.get("GITLAB_USER_NAME")
        ci["email"] = env.get("GITLAB_USER_EMAIL")
        ci["environment"] = env.get("CI_ENVIRONMENT_NAME") or env.get("ENVIRONMENT") or env.get("ENV") or "ci"

    # Jenkins
    if env.get("JENKINS_URL"):
        ci["provider"] = "jenkins"
        ci["branch"] = env.get("GIT_BRANCH") or env.get("BRANCH_NAME")
        ci["commit"] = env.get("GIT_COMMIT")
        # REPO: a Jenkins depèn del plugin, difícil generalitzar; deixa-ho buit
        ci["repo_name"] = env.get("REPO_NAME")
        ci["author"] = env.get("CHANGE_AUTHOR") or env.get("GIT_AUTHOR_NAME")
        ci["email"] = env.get("GIT_AUTHOR_EMAIL")
        ci["environment"] = env.get("ENVIRONMENT") or env.get("ENV") or "ci"

    # Azure DevOps
    if env.get("TF_BUILD") == "True":
        ci["provider"] = "azure"
        ci["branch"] = env.get("BUILD_SOURCEBRANCHNAME")
        ci["commit"] = env.get("BUILD_SOURCEVERSION")
        proj = env.get("BUILD_REPOSITORY_NAME")  # owner/repo o només repo
        ci["repo_name"] = proj
        ci["author"] = env.get("BUILD_REQUESTEDFOR")
        ci["email"] = env.get("BUILD_REQUESTEDFOREMAIL")
        ci["environment"] = env.get("ENVIRONMENT") or env.get("ENV") or "ci"

    return {k: v for k, v in ci.items() if v}

def _best_environment_guess() -> Optional[str]:
    # ordre de preferència
    for key in ("ENVIRONMENT", "ENV", "STAGE", "APP_ENV"):
        if os.environ.get(key):
            return os.environ[key]
    # heurístiques simples
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"]) or ""
    if branch in {"main", "master"}:
        return "prod"
    if branch in {"develop", "dev"}:
        return "dev"
    if "staging" in branch:
        return "staging"
    return None

def autofill_meta(
    suite_name: str = "Test Suite",
    overrides: Optional[Dict[str, Optional[str]]] = None,
    repo_cwd: Optional[Path] = None,
) -> "ReportMeta":
    """
    Construeix un ReportMeta amb dades de Git/CI/entorn i permet sobreescriure camps.
    Camps suportats a overrides: repo_name, suite_name, author, environment, branch, commit,
                               header_note, footer_note
    """
    overrides = overrides or {}
    cwd = str(repo_cwd or Path.cwd())

    # 1) CI context
    ci = _ci_context()

    # 2) Git data
    branch = ci.get("branch") or _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd)
    commit = ci.get("commit") or _run_git(["rev-parse", "--short", "HEAD"], cwd=cwd)
    remote = _run_git(["config", "--get", "remote.origin.url"], cwd=cwd)
    repo_name = ci.get("repo_name") or (remote and _parse_repo_name_from_remote(remote))

    # fallback repo_name: nom del directori actual
    if not repo_name:
        repo_name = Path(cwd).resolve().name

    # 3) Author / email
    author = overrides.get("author") or ci.get("author") or _run_git(["config", "--get", "user.name"], cwd=cwd)
    email = os.environ.get("GIT_AUTHOR_EMAIL") or ci.get("email") or _run_git(["config", "--get", "user.email"], cwd=cwd)

    # 4) Environment
    environment = overrides.get("environment") or ci.get("environment") or _best_environment_guess()

    # 5) Altres camps (notes, suite)
    meta = ReportMeta(
        repo_name = overrides.get("repo_name") or repo_name or "unknown-repo",
        suite_name = overrides.get("suite_name") or suite_name,
        author = author or None,
        environment = environment or None,
        branch = overrides.get("branch") or branch or None,
        commit = overrides.get("commit") or commit or None,
        header_note = overrides.get("header_note"),
        footer_note = overrides.get("footer_note") or (email and f"Contacte: {email}") or None,
    )
    return meta


def normalize_images(images: Optional[Dict[str, Any]]) -> List[ImageItem]:
    """
    Accepta:
      - {"lab": "path.png"}
      - {"lab": {"path": "path.png", "caption": "..." , "alt":"..."}}
    Retorna List[ImageItem] preservant l'ordre d'inserció (Python 3.7+ dict és ordered).
    """
    out: List[ImageItem] = []
    if not images:
        return out
    for label, spec in images.items():
        if isinstance(spec, str):
            out.append(ImageItem(label=label, path=spec))
        elif isinstance(spec, dict):
            out.append(ImageItem(
                label=label,
                path=spec.get("path"),
                caption=spec.get("caption"),
                alt=spec.get("alt"),
            ))
        else:
            raise TypeError(f"Format d’imatge no suportat per a label='{label}': {type(spec)}")
    return out

def build_figure_index(tests: List["TestEntry"], fig_opts: FigureOptions):
    """
    Recorre tots els tests en ordre i assigna números de figura globals.
    Retorna:
      idx: dict[label] = {"num": n, "anchor": "fig-n"}
      seq: llista de tuples (test_index, ImageItem, num, anchor)
    """
    idx: Dict[str, Dict[str, Any]] = {}
    seq: List[Dict[str, Any]] = []
    n = fig_opts.start_number
    for ti, t in enumerate(tests):
        for img in t.images:
            if img.label in idx:
                # Si es repeteix la label, mantenim el primer número (LaTeX-style)
                assigned = idx[img.label]
            else:
                assigned = {"num": n, "anchor": fig_opts.anchor_template.format(num=n)}
                idx[img.label] = assigned
                n += 1
            seq.append({"test_i": ti, "image": img, "num": assigned["num"], "anchor": assigned["anchor"]})
    return idx, seq

# Reemplaça \ref{label} per "Figura n" amb enllaç intern (MD/HTML)
_REF_RX = re.compile(r"\\ref\{([^\}]+)\}")

def replace_refs_md(text: str, fig_index: Dict[str, Dict[str, Any]], prefix: str = "Figura") -> str:
    def repl(m):
        lab = m.group(1)
        if lab in fig_index:
            n = fig_index[lab]["num"]; anchor = fig_index[lab]["anchor"]
            return f"#{anchor}"
        return f"{prefix} ?"  # label desconeguda
    return _REF_RX.sub(repl, text)

def replace_refs_html(text: str, fig_index: Dict[str, Dict[str, Any]], prefix: str = "Figura") -> str:
    def repl(m):
        lab = m.group(1)
        if lab in fig_index:
            n = fig_index[lab]["num"]; anchor = fig_index[lab]["anchor"]
            return f'#{_html.escape(anchor)}{_html.escape(prefix)} {n}</a>'
        return _html.escape(f"{prefix} ?")
    # Escapem el text però preservem \ref{...} substituint en dos passos
    # 1) Marquem refs
    marked = []
    last = 0
    for mm in _REF_RX.finditer(text):
        marked.append(_html.escape(text[last:mm.start()]))
        marked.append(repl(mm))  # ja és HTML-safe
        last = mm.end()
    marked.append(_html.escape(text[last:]))
    return "".join(marked)

# Per LaTeX: escapem text però preservem \ref{...} literal
def escape_latex_preserving_refs(text: str) -> str:
    parts = []
    last = 0
    for m in _REF_RX.finditer(text):
        # text abans -> escapar LaTeX
        parts.append(_latex_escape(text[last:m.start()]))
        # la referència -> tal qual
        parts.append(text[m.start():m.end()])
        last = m.end()
    parts.append(_latex_escape(text[last:]))
    return "".join(parts)

def _latex_escape(s: str) -> str:
    repl = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "$": r"\$",
        "&": r"\&",
        "#": r"\#",
        "_": r"\_",
        "%": r"\%",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    return s


@dataclass
class FigureOptions:
    prefix: str = "Figura"
    start_number: int = 1
    anchor_template: str = "fig-{num}"   # per Markdown/HTML

@dataclass
class ImageItem:
    label: str
    path: str
    caption: Optional[str] = None
    alt: Optional[str] = None  # per HTML/MD



class TestStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARN = "WARN"
    SKIP = "SKIP"
    ERROR = "ERROR"

_STATUS_ICON = {
    TestStatus.PASS: "✅",
    TestStatus.FAIL: "❌",
    TestStatus.WARN: "⚠️",
    TestStatus.SKIP: "⏭️",
    TestStatus.ERROR: "🛑",
}

@dataclass
class ReportMeta:
    repo_name: str
    suite_name: str = "Test Suite"
    run_at: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    file_name : Optional[str] = "Avaluacio"
    author: Optional[str] = None
    environment: Optional[str] = None
    branch: Optional[str] = None
    commit: Optional[str] = None
    ci_build_id: Optional[str] = None
    header_note: Optional[str] = None
    footer_note: Optional[str] = None
    output_path: pathlib.Path = field(
        default_factory=lambda: pathlib.Path(__file__).resolve().parent.parent / "Avaluacio")

@dataclass
class TestEntry:
    id: str
    title: str
    general_text: str
    status: TestStatus
    status_note: Optional[str] = None
    duration_s: Optional[float] = None
    tags: List[str] = field(default_factory=list)
    links: Dict[str, str] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)
    report: Optional[Dict[str, Any]] = None
    priority: Optional[int] = None
    images: List[ImageItem] = field(default_factory=list)
    level: int = 1  # ← valor per defecte

@dataclass
class DictRenderOptions:
    mode: str = "auto"     # "auto" | "table" | "json"
    flatten: bool = True
    sep: str = "."
    max_value_len: int = 120
    collapse_section: bool = True



@dataclass
class BuilderOptions:
    dict_render: DictRenderOptions = field(default_factory=DictRenderOptions)
    status_texts: Dict[TestStatus, str] = field(default_factory=lambda: {
        TestStatus.PASS: "El test ha passat correctament.",
        TestStatus.FAIL: "El test ha fallat.",
        TestStatus.WARN: "El test ha generat advertències.",
        TestStatus.SKIP: "El test s'ha omès.",
        TestStatus.ERROR: "S'ha produït un error durant l'execució del test.",
    })
    show_toc: bool = True
    show_summary: bool = True
    show_metrics: bool = True
    show_links: bool = True
    show_tags: bool = False
    overall_status_policy: str = "worst"  # "worst" | "by-fail" | "by-error-priority"
    order_mode: str = "insertion"  # "insertion" | "by_id" | "by_title" | "by_status" | "by_duration" | "by_priority" | "custom"
    order_reverse: bool = False
    explicit_order: List[str] = field(default_factory=list)  # si vols forçar ordre d'IDs
    custom_order_key: Optional[Callable[["TestEntry"], Any]] = None
    figure: FigureOptions = field(default_factory=FigureOptions)
    toc_max_level: int = 1  # ← per defecte 1
    toc_indent: bool = True  # ← indentar segons el nivell (2 espais per nivell)



def human_duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    if seconds < 1:
        return f"{seconds*1000:.0f} ms"
    if seconds < 60:
        return f"{seconds:.2f} s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{int(m)}m {s:.0f}s"
    h, m = divmod(m, 60)
    return f"{int(h)}h {int(m)}m {s:.0f}s"

def truncate_value(v: Any, max_len: int) -> str:
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    if len(s) <= max_len:
        return s
    return s[:max_len - 1] + "…"

def flatten_dict(d: Mapping[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    items: List[Tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
        if isinstance(v, Mapping):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            for i, elem in enumerate(v):
                list_key = f"{new_key}[{i}]"
                if isinstance(elem, Mapping):
                    items.extend(flatten_dict(elem, list_key, sep=sep).items())
                else:
                    items.append((list_key, elem))
        else:
            items.append((new_key, v))
    return dict(items)

def dict_to_md_table(d: Mapping[str, Any], max_value_len: int = 120) -> str:
    lines = ["| Indicador | Valor |", "|---|---|"]
    for k, v in d.items():
        val = truncate_value(v, max_value_len).replace("\n", "<br>")
        lines.append(f"| `{k}` | {val} |")
    return "\n".join(lines)

def dict_to_json_md(d: Mapping[str, Any]) -> str:
    return "```json\n" + json.dumps(d, ensure_ascii=False, indent=2) + "\n```"

def compute_overall_status(statuses: Iterable[TestStatus], policy: str = "worst") -> TestStatus:
    priority = {
        TestStatus.ERROR: 5,
        TestStatus.FAIL: 4,
        TestStatus.WARN: 3,
        TestStatus.SKIP: 2,
        TestStatus.PASS: 1,
    }
    if policy == "worst":
        worst = None
        worst_p = -math.inf
        for s in statuses:
            p = priority.get(s, 0)
            if p > worst_p:
                worst, worst_p = s, p
        return worst or TestStatus.PASS
    elif policy == "by-fail":
        if any(s == TestStatus.ERROR for s in statuses):
            return TestStatus.ERROR
        if any(s == TestStatus.FAIL for s in statuses):
            return TestStatus.FAIL
        if any(s == TestStatus.WARN for s in statuses):
            return TestStatus.WARN
        if all(s == TestStatus.SKIP for s in statuses):
            return TestStatus.SKIP
        return TestStatus.PASS
    return compute_overall_status(statuses, "worst")

class BaseRenderer:
    def render(self, meta: ReportMeta, tests: List[TestEntry], opts: BuilderOptions) -> str:
        raise NotImplementedError

import re
import json
from collections import Counter
from typing import List, Dict, Any

class MarkdownRenderer(BaseRenderer):
    _REF_RX = re.compile(r"\\?ref\{([^\}]+)\}")  # suporta \ref{...} i ref{...}

    def _anchor(self, t: TestEntry) -> tuple[str,str]:
        nom = t.title.strip()
        a = nom.lower()
        a = "".join(ch if ch.isalnum() or ch.isspace() else "-" for ch in a)
        return nom, "-".join(a.split())

    def _build_figure_index(self, tests: List[TestEntry], fig_opts: "FigureOptions") -> Dict[str, Dict[str, Any]]:
        """
        Construeix un índex global de figures per label: label -> {"num": n, "anchor": "fig-n"}.
        Prioritza la primera aparició de cada label (estil LaTeX).
        """
        idx: Dict[str, Dict[str, Any]] = {}
        n = fig_opts.start_number
        for t in tests:
            # si no existeix el camp images (per compatibilitat), ho tractem com llista buida
            for img in getattr(t, "images", []) or []:
                if img.label not in idx:
                    idx[img.label] = {"num": n, "anchor": fig_opts.anchor_template.format(num=n)}
                    n += 1
        return idx

    def _replace_refs_md(self, text: str, fig_index: Dict[str, Dict[str, Any]], prefix: str = "Figura") -> str:
        def repl(m):
            lab = m.group(1)
            if lab in fig_index:
                n = fig_index[lab]["num"]; anchor = fig_index[lab]["anchor"]
                return f"#{anchor}"
            return f"{prefix} ?"
        return self._REF_RX.sub(repl, text)

    def _render_report_dict(self, report, opts: DictRenderOptions) -> str:
        if not report:
            return ""
        if opts.mode == "json":
            content = dict_to_json_md(report)
        else:
            flat = flatten_dict(report, sep=opts.sep) if opts.flatten else report
            if opts.mode == "table":
                content = dict_to_md_table(flat, max_value_len=opts.max_value_len)
            else:
                long_vals = sum(1 for v in flat.values()
                                if isinstance(v, (dict, list)) or len(json.dumps(v, ensure_ascii=False)) > opts.max_value_len)
                content = dict_to_json_md(report) if long_vals > max(3, len(flat) * 0.3) \
                         else dict_to_md_table(flat, max_value_len=opts.max_value_len)
        if opts.collapse_section:
            return "<details><summary><strong>Detall report</strong></summary>\n\n" + content + "\n\n</details>"
        return "**Detall report**\n\n" + content

    def render(self, meta: ReportMeta, tests: List[TestEntry], opts: BuilderOptions) -> str:
        counts = Counter(t.status for t in tests)
        for s in TestStatus:
            counts.setdefault(s, 0)
        overall = compute_overall_status((t.status for t in tests), policy=opts.overall_status_policy)
        when = meta.run_at.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

        # Índex de figures global (un sol cop)
        fig_index = self._build_figure_index(tests, opts.figure)

        parts: List[str] = []
        # Header
        parts += [
            f"# Informe de Resultats — {meta.suite_name}",
            "",
            f"- **Repositori:** `{meta.repo_name}`",
            f"- **Execució:** {when}",
        ]
        if meta.author: parts.append(f"- **Autor:** {meta.author}")
        if meta.environment: parts.append(f"- **Entorn:** {meta.environment}")
        if meta.branch: parts.append(f"- **Branca:** `{meta.branch}`")
        if meta.commit: parts.append(f"- **Commit:** `{meta.commit}`")
        if meta.ci_build_id: parts.append(f"- **Build:** `{meta.ci_build_id}`")
        parts.append("")
        icon = _STATUS_ICON.get(overall, "ℹ️")
        parts.append(f"> **Estat global:** {icon} **{overall.value}**  "
                     f"(PASS: {counts[TestStatus.PASS]}, FAIL: {counts[TestStatus.FAIL]}, "
                     f"WARN: {counts[TestStatus.WARN]}, SKIP: {counts[TestStatus.SKIP]}, ERROR: {counts[TestStatus.ERROR]})")
        parts.append("")
        if meta.header_note:
            parts += [meta.header_note, ""]

        # TOC
        if opts.show_toc:
            parts += ["## Taula de continguts", ""]
            max_level = max(1, int(getattr(opts, "toc_max_level", 1) or 1))
            indent_enabled = bool(getattr(opts, "toc_indent", True))
            filename = meta.file_name + ".md" if meta else "report.md"

            # Ordena perquè el TOC sigui estable i “natural”
            def _sort_key(t):
                # Assegura un nivell vàlid (>=1) per si algun test no porta level
                try:
                    lvl = int(getattr(t, "level", 1) or 1)
                except Exception:
                    lvl = 1
                return (lvl, t.id)

            for t in sorted(tests, key=_sort_key):
                # Normalitza el nivell
                try:
                    lvl = int(getattr(t, "level", 1) or 1)
                except Exception:
                    lvl = 1

                if lvl <= max_level:
                    indent = ("  " * (max(lvl, 1) - 1)) if indent_enabled else ""
                    # Mostra el títol com a enllaç (més clar que només l'àncora)
                    # Si vols conservar el teu format antic, canvia la línia següent a f"{indent}- #{self._anchor(t)}"
                    nom,enllaç = self._anchor(t)
                    parts.append(f"{indent}- [{nom}]({filename}#-{enllaç})")
                    parts.append("")

        # Resum
        if opts.show_summary:
            parts += [
                "## Resum", "",
                f"- Total tests: **{sum(counts.values())}**",
                f"- PASS: **{counts[TestStatus.PASS]}**, FAIL: **{counts[TestStatus.FAIL]}**, "
                f"WARN: **{counts[TestStatus.WARN]}**, SKIP: **{counts[TestStatus.SKIP]}**, "
                f"ERROR: **{counts[TestStatus.ERROR]}**",
                ""
            ]

        # Detall
        for t in tests:
            icon = _STATUS_ICON.get(t.status, "")
            parts += [f"## {icon} {t.title}", ""]
            parts += [f"*Estat:* **{t.status.value}**  •  *Durada:* {human_duration(t.duration_s)}"]
            if opts.show_links and t.links:
                parts += ["", " • ".join(v for v in t.links.values())]
            parts.append("")

            # general_text amb referències a figures
            if t.general_text:
                txt = self._replace_refs_md(t.general_text, fig_index, prefix=opts.figure.prefix)
                parts += [txt, ""]

            parts.append(f"> {t.status_note or opts.status_texts.get(t.status, '')}")
            parts.append("")

            if opts.show_metrics and t.metrics:
                parts += ["**Indicadors**", "", dict_to_md_table(t.metrics), ""]
            if t.report:
                parts += [self._render_report_dict(t.report, opts.dict_render), ""]

            # Figures d'aquest test
            # for img in getattr(t, "images", []) or []:
            #     info = fig_index.get(img.label)
            #     if not info:
            #         continue
            #     n = info["num"]; anchor = info["anchor"]
            #     alt = img.alt or (img.caption or img.label or "")
            #     caption = img.caption or img.label or ""
            #     parts += [
            #         f'<a id="{anchor}"></a>',
            #         f'{img.path}',
            #         f"*{opts.figure.prefix} {n}: {caption}*",
            #         ""
            #     ]


            # Figures d'aquest test (assumim List[ImageItem])
            for img in (getattr(t, "images", []) or []):
                label = getattr(img, "label", None)
                if not label:
                    continue
                info = fig_index.get(label)
                if not info:
                    continue

                n = info["num"]
                anchor = info["anchor"]
                path = (getattr(img, "path", "") or "").strip()
                if not path:
                    continue

                alt = (getattr(img, "alt", None) or getattr(img, "caption", None) or label or "").strip()
                caption = (getattr(img, "caption", None) or label or "").strip()
                # ![Fig-1](esquema_GestorUCI.png)
                parts += [
                    f'![{anchor}"]({path})',
                    f"*{opts.figure.prefix} {n}: {caption}*",
                    ""
                ]

        # Footer
        parts += ["---", ""]
        if meta.footer_note:
            parts += [meta.footer_note, ""]
        parts.append("_Generat automàticament._")
        return "\n".join(parts)




class HTMLRenderer(BaseRenderer):
    _REF_RX = re.compile(r"\\?ref\{([^\}]+)\}")  # \ref{...} i ref{...}

    def _esc(self, s: Any) -> str:
        return html.escape(s if isinstance(s, str) else json.dumps(s, ensure_ascii=False))

    def _status_badge(self, st: TestStatus) -> str:
        color = {
            TestStatus.PASS: "#2e7d32",
            TestStatus.FAIL: "#c62828",
            TestStatus.WARN: "#f9a825",
            TestStatus.SKIP: "#6d6d6d",
            TestStatus.ERROR: "#ad1457",
        }[st]
        return f'<span class="badge" style="background:{color}">{_STATUS_ICON[st]} {st.value}</span>'

    def _human_dt(self, d: "datetime") -> str:
        return d.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    def _anchor(self, title: str) -> str:
        a = title.strip().lower()
        a = "".join(ch if ch.isalnum() or ch.isspace() else "-" for ch in a)
        return "-".join(a.split())

    def _build_figure_index(self, tests: List[TestEntry], fig_opts: "FigureOptions") -> Dict[str, Dict[str, Any]]:
        idx: Dict[str, Dict[str, Any]] = {}
        n = fig_opts.start_number
        for t in tests:
            for img in getattr(t, "images", []) or []:
                if img.label not in idx:
                    idx[img.label] = {"num": n, "anchor": fig_opts.anchor_template.format(num=n)}
                    n += 1
        return idx

    def _replace_refs_html(self, text: str, fig_index: Dict[str, Dict[str, Any]], prefix: str = "Figura") -> str:
        # escapem tot el text, però substituïm les referències amb enllaç
        out = []
        last = 0
        for m in self._REF_RX.finditer(text):
            out.append(html.escape(text[last:m.start()]))
            lab = m.group(1)
            if lab in fig_index:
                n = fig_index[lab]["num"]; anchor = fig_index[lab]["anchor"]
                out.append(f'<a href="#{html.escape(anchor)}ape(prefix) {n}</a>')
                # out.append(f'&lt;a href="#{html.escape(anchor)}ape(prefix)} {n}&lt;/a&gt;')


            else:
                out.append(html.escape(f"{prefix} ?"))
            last = m.end()
        out.append(html.escape(text[last:]))
        return "".join(out)

    def _table_from_mapping(self, m: Dict[str, Any]) -> str:
        rows = []
        for k, v in m.items():
            vk = html.escape(str(k))
            vv = html.escape(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
            vv = vv.replace("\n", "\\n")
            rows.append(f"<tr><td><code>{vk}</code></td><td>{vv}</td></tr>")
        return "<table class='kv'><thead><tr><th>Clau</th><th>Valor</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"

    def _render_report_block(self, report: Dict[str, Any], opts: DictRenderOptions) -> str:
        if not report:
            return ""
        if opts.mode == "json":
            content = "<pre><code class='json'>" + html.escape(json.dumps(report, ensure_ascii=False, indent=2)) + "</code></pre>"
        else:
            flat = flatten_dict(report, sep=opts.sep) if opts.flatten else report
            if opts.mode == "table":
                content = self._table_from_mapping(flat)
            else:
                long_vals = sum(1 for v in flat.values()
                                if isinstance(v, (dict, list)) or len(json.dumps(v, ensure_ascii=False)) > opts.max_value_len)
                content = ("<pre><code class='json'>" + html.escape(json.dumps(report, ensure_ascii=False, indent=2)) + "</code></pre>"
                           if long_vals > max(3, len(flat) * 0.3) else self._table_from_mapping(flat))
        if opts.collapse_section:
            return f"<details><summary><strong>Detall report</strong></summary>{content}</details>"
        return f"<section><h4>Detall report</h4>{content}</section>"

    def render(self, meta: ReportMeta, tests: List[TestEntry], opts: BuilderOptions) -> str:
        counts = Counter(t.status for t in tests)
        for s in TestStatus:
            counts.setdefault(s, 0)
        overall = compute_overall_status((t.status for t in tests), policy=opts.overall_status_policy)
        fig_index = self._build_figure_index(tests, opts.figure)

        head = f"""<!doctype html>
<html lang="ca">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Informe — {html.escape(meta.suite_name)}</title>
<style>
:root {{
  --fg:#1f2937; --muted:#555; --bg:#fff; --card:#f8fafc; --border:#e5e7eb;
}}
body {{ font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; color:var(--fg); background:var(--bg); margin:2rem; }}
h1,h2,h3 {{ line-height:1.2; }}
header, section.card {{ background:var(--card); border:1px solid var(--border); border-radius:8px; padding:1rem 1.25rem; margin-bottom:1rem; }}
.badge {{ color:#fff; border-radius:999px; padding:0.2rem 0.6rem; font-weight:600; font-size:0.9rem; }}
.kv {{ width:100%; border-collapse: collapse; }}
.kv th, .kv td {{ border:1px solid var(--border); padding:0.4rem 0.6rem; vertical-align:top; }}
.meta ul {{ list-style:none; padding-left:0; margin:0; }}
.meta li {{ margin:0.2rem 0; }}
.toc ul {{ margin:0.2rem 0 0.4rem 1.25rem; }}
footer {{ color:var(--muted); margin-top:2rem; }}
.summary-kpis span {{ margin-right:0.8rem; }}
figure {{ margin: 1rem 0; }}
figcaption {{ color: var(--muted); font-size: 0.95rem; }}
img {{ max-width: 100%; height: auto; }}
</style>
</head>
<body>
"""
        header = f"""
<header>
  <h1>Informe de Resultats — {html.escape(meta.suite_name)}</h1>
  <div class="meta">
    <ul>
      <li><strong>Repositori:</strong> <code>{html.escape(meta.repo_name)}</code></li>
      <li><strong>Execució:</strong> {self._human_dt(meta.run_at)}</li>
      {"<li><strong>Autor:</strong> " + self._esc(meta.author) + "</li>" if meta.author else ""}
      {"<li><strong>Entorn:</strong> " + self._esc(meta.environment) + "</li>" if meta.environment else ""}
      {"<li><strong>Branca:</strong> <code>" + self._esc(meta.branch) + "</code></li>" if meta.branch else ""}
      {"<li><strong>Commit:</strong> <code>" + self._esc(meta.commit) + "</code></li>" if meta.commit else ""}
      {"<li><strong>Build:</strong> <code>" + self._esc(meta.ci_build_id) + "</code></li>" if meta.ci_build_id else ""}
    </ul>
  </div>
  <p><strong>Estat global:</strong> {self._status_badge(overall)}
    <span class="summary-kpis"> (PASS: {counts[TestStatus.PASS]}, FAIL: {counts[TestStatus.FAIL]},
    WARN: {counts[TestStatus.WARN]}, SKIP: {counts[TestStatus.SKIP]}, ERROR: {counts[TestStatus.ERROR]})</span></p>
  {("<p>" + self._esc(meta.header_note) + "</p>") if meta.header_note else ""}
</header>
"""
        toc = ""
        if opts.show_toc:
            toc_items = "\n".join(f"<li>#{self._anchor(t.title)}{html.escape(t.title)}</a></li>" for t in tests)
            toc = f"<section class='card toc'><h2>Taula de continguts</h2><ul>{toc_items}</ul></section>"

        summary = ""
        if opts.show_summary:
            total = sum(counts.values())
            summary = f"""
<section class="card">
  <h2>Resum</h2>
  <ul>
    <li>Total tests: <strong>{total}</strong></li>
    <li>PASS: <strong>{counts[TestStatus.PASS]}</strong>, FAIL: <strong>{counts[TestStatus.FAIL]}</strong>,
        WARN: <strong>{counts[TestStatus.WARN]}</strong>, SKIP: <strong>{counts[TestStatus.SKIP]}</strong>,
        ERROR: <strong>{counts[TestStatus.ERROR]}</strong></li>
  </ul>
</section>
"""

        details_parts: List[str] = []
        for t in tests:
            aid = self._anchor(t.title)
            links_html = ""
            if opts.show_links and t.links:
                links_html = "<p>" + " • ".join(f"{self._esc(url)}{self._esc(name)}</a>"
                                                 for name, url in t.links.items()) + "</p>"
            metrics_html = ""
            if opts.show_metrics and t.metrics:
                metrics_html = "<h4>Indicadors</h4>" + self._table_from_mapping(t.metrics)

            report_html = self._render_report_block(t.report, opts.dict_render) if t.report else ""

            general_html = ""
            if t.general_text:
                general_html = "<p>" + self._replace_refs_html(t.general_text, fig_index, prefix=opts.figure.prefix) + "</p>"

            # Figures d'aquest test
            figs_html = []
            for img in getattr(t, "images", []) or []:
                info = fig_index.get(img.label)
                if not info:
                    continue
                n = info["num"]; anchor = info["anchor"]
                alt = html.escape(img.alt or img.caption or img.label or "")
                cap = html.escape(img.caption or img.label or "")
                figs_html.append(
                    f'<figure id="{html.escape(anchor)}">'
                    f'{html.escape(img.path)}'
                    f'<figcaption>{html.escape(opts.figure.prefix)} {n}: {cap}</figcaption>'
                    f"</figure>"
                )

            details_parts.append(f"""
<section class="card" id="{aid}">
  <h2>{_STATUS_ICON[t.status]} {html.escape(t.title)}</h2>
  <p><code>{html.escape(t.id)}</code> • {self._status_badge(t.status)} • Durada: {html.escape(human_duration(t.duration_s))}</p>
  {links_html}
  {general_html}
  <blockquote>{html.escape(t.status_note or opts.status_texts.get(t.status, ""))}</blockquote>
  {metrics_html}
  {report_html}
  {"".join(figs_html)}
</section>
""")

        footer = f"""
<footer>
  <hr>
  {("<p>" + self._esc(meta.footer_note) + "</p>") if meta.footer_note else ""}
  <p><em>Generat automàticament.</em></p>
</footer>
</body></html>
"""

        return head + header + toc + summary + "\n".join(details_parts) + footer

class ReportBuilder:
    def __init__(self, meta: ReportMeta, options: Optional[BuilderOptions] = None, renderer: Optional[BaseRenderer] = None):
        self.meta = meta
        self.options = options or BuilderOptions()
        self.renderer = renderer or MarkdownRenderer()
        self._tests: List[TestEntry] = []

    def add_test(self, id: str, title: str, general_text: str, status: TestStatus,
                 status_note: Optional[str] = None, duration_s: Optional[float] = None,
                 tags: Optional[List[str]] = None, links: Optional[Dict[str, str]] = None,
                 metrics: Optional[Dict[str, Any]] = None, report: Optional[Dict[str, Any]] = None,
                 priority: Optional[int] = None, images: Optional[Dict[str, Any]] = None, level: int=1) -> "ReportBuilder":
        self._tests.append(TestEntry(
            id=id, title=title, general_text=general_text, status=status,
            status_note=status_note, duration_s=duration_s, tags=tags or [],
            links=links or {}, metrics=metrics or {}, report=report, priority=priority,
            images=normalize_images(images),
            level=level
        ))
        return self

    def add_test_from_result(self, result: Dict[str, Any]) -> "ReportBuilder":
        status = TestStatus(result.get("status", "PASS"))
        return self.add_test(
            id=result["id"], title=result.get("title", result["id"]),
            general_text=result.get("general_text", ""), status=status,
            status_note=result.get("status_note"), duration_s=result.get("duration_s"),
            tags=result.get("tags"), links=result.get("links"), metrics=result.get("metrics"),
            report=result.get("report"), priority=result.get("priority"),
            images=result.get("images")
        )

    def get_report_path(self):
        """Obté el path complet on es desarà el report."""

        return self.meta.output_path

    # --- ORDRE ---

    def set_order_by_ids(self, order: List[str], reverse: bool = False) -> None:
        """
        Defineix un ordre explícit per IDs. Els IDs no presents conserven l'ordre d'inserció al final.
        """
        self.options.explicit_order = list(order)
        self.options.order_mode = "by_id"
        self.options.order_reverse = reverse

    def sort_tests(self, key: Callable[[TestEntry], Any], reverse: bool = False) -> None:
        """
        Aplica ordenació immediata sobre els tests actuals i, a més, configura el mode 'custom'
        per mantenir coherència en futures renderitzacions.
        """
        self._tests.sort(key=key, reverse=reverse)
        self.options.custom_order_key = key
        self.options.order_mode = "custom"
        self.options.order_reverse = reverse

    def _clean_filename(self) -> str:
        name = (self.meta.file_name or "").strip()
        if name:
            p = Path( name)
            # Elimina totes les extensions (p.ex. "informe.v1.md.zip" -> "informe")
            while p.suffix:
                p = p.with_suffix('')
            base = p.name
        else:
            base = "report"
        return base

    def _apply_order(self, tests: List[TestEntry]) -> List[TestEntry]:
        """
        Retorna una llista de tests ordenada segons 'options'.
        No muta self._tests per evitar sorpreses.
        """
        mode = self.options.order_mode
        reverse = self.options.order_reverse
        out = list(tests)

        if mode == "insertion":
            return out  # ja preservem l'ordre d'afegit

        if mode == "by_id":
            if self.options.explicit_order:
                order_index = {tid: i for i, tid in enumerate(self.options.explicit_order)}
                # Els que no hi són, posició gran per mantenir-los al final en ordre d'inserció
                out.sort(key=lambda t: (order_index.get(t.id, 10**9),))
                if reverse:
                    out.reverse()
                return out
            else:
                out.sort(key=lambda t: t.id, reverse=reverse)
                return out

        if mode == "by_title":
            out.sort(key=lambda t: t.title.lower(), reverse=reverse)
            return out

        if mode == "by_status":
            # Ordre de prioritat de pitjor a millor (ERROR>FAIL>WARN>SKIP>PASS) si reverse=False.
            prio = {TestStatus.ERROR: 5, TestStatus.FAIL: 4, TestStatus.WARN: 3, TestStatus.SKIP: 2, TestStatus.PASS: 1}
            out.sort(key=lambda t: prio.get(t.status, 0), reverse=reverse)
            return out

        if mode == "by_duration":
            out.sort(key=lambda t: (t.duration_s is None, t.duration_s if t.duration_s is not None else float("inf")), reverse=reverse)
            return out

        if mode == "by_priority":
            # Si priority és None, el deixem al final
            out.sort(key=lambda t: (t.priority is None, t.priority if t.priority is not None else float("inf")), reverse=reverse)
            return out

        if mode == "custom" and self.options.custom_order_key:
            out.sort(key=self.options.custom_order_key, reverse=reverse)
            return out

        # fallback
        return out

    # --- RENDER/SAVE ---

    def render(self) -> str:
        tests_ordered = self._apply_order(self._tests)
        return self.renderer.render(self.meta, tests_ordered, self.options)

    def to_markdown(self) -> str:
        # Alias per compatibilitat, respecta l'ordre
        self._clean_filename()
        return self.render()


    def save(self) -> None:
        # Obté el nom net del fitxer i li afegeix l'extensió .md
        filename = self._clean_filename() + ".md"

        # Construeix el path complet dins del directori de sortida
        full_path = self.meta.output_path / filename  # assumint que self.meta és ReportMeta

        # Crea la carpeta si no existeix
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Escriu el contingut renderitzat al fitxer
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(self.render())
