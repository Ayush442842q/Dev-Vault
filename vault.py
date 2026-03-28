"""
Dev Vault - AI-Powered Code Backup System
Uses HuggingFace Inference API to understand your projects
and automatically organizes them to your external hard disk.
"""

import os
import stat
import time
import shutil
import hashlib
import json
from pathlib import Path
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from huggingface_hub import InferenceClient
from rich.console import Console
from rich.panel import Panel
import threading

# ─── CONFIG ────────────────────────────────────────────────────────────────────

CONFIG_FILE = Path.home() / ".dev_vault_config.json"

DEFAULT_CONFIG = {
    "hf_api_key": "Your-HuggingFace-API-Key",
    "watch_paths": [str(Path.home() / "Documents"), str(Path.home() / "Desktop")],
    "backup_root": "H:/DevVault",
    "model": "mistralai/Mistral-7B-Instruct-v0.3",
    "min_file_size_bytes": 50,
    "debounce_seconds": 10,
    "ignored_dirs": [
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        "env", ".env", "dist", "build", ".idea", ".vscode",
        "*.egg-info", ".mypy_cache", ".pytest_cache"
    ],
    "code_extensions": [
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c",
        ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".r",
        ".html", ".css", ".scss", ".sql", ".sh", ".bat", ".ps1",
        ".yaml", ".yml", ".json", ".toml", ".xml"
    ]
}

CATEGORY_FOLDERS = {
    "machine_learning": "01_MachineLearning",
    "web_development": "02_WebDevelopment",
    "automation": "03_Automation",
    "data_science": "04_DataScience",
    "game_development": "05_GameDevelopment",
    "cli_tool": "06_CLITools",
    "api_backend": "07_APIBackend",
    "database": "08_Database",
    "hardware_iot": "09_Hardware_IoT",
    "utility": "10_Utilities",
    "other": "11_Other"
}

console = Console()

# ─── HELPERS ───────────────────────────────────────────────────────────────────

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def is_project_root(path: Path) -> bool:
    markers = [
        "requirements.txt", "package.json", "setup.py", "pyproject.toml",
        "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "Makefile",
        ".git", "main.py", "index.js", "main.js", "app.py", "index.html"
    ]
    return any((path / m).exists() for m in markers)

def find_project_root(file_path: Path, watch_paths: list) -> Path:
    current = file_path.parent
    watch_roots = [Path(p) for p in watch_paths]
    while current not in watch_roots and current != current.parent:
        if is_project_root(current):
            return current
        current = current.parent
    return file_path.parent

def collect_project_code(project_path: Path, extensions: list, max_chars=3000) -> str:
    code_snippets = []
    total_chars = 0
    priority_files = ["main.py", "app.py", "index.js", "main.js",
                      "README.md", "requirements.txt", "package.json"]

    for pf in priority_files:
        fp = project_path / pf
        if fp.exists() and total_chars < max_chars:
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")[:800]
                code_snippets.append(f"--- {pf} ---\n{content}")
                total_chars += len(content)
            except Exception:
                pass

    for ext in extensions:
        if total_chars >= max_chars:
            break
        for fp in project_path.rglob(f"*{ext}"):
            if total_chars >= max_chars:
                break
            if any(ig in fp.parts for ig in ["node_modules", "__pycache__", ".git", "venv"]):
                continue
            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")[:400]
                code_snippets.append(f"--- {fp.name} ---\n{content}")
                total_chars += len(content)
            except Exception:
                pass

    return "\n\n".join(code_snippets)

def normalize_category(raw) -> str:
    """Safely convert AI category output (may be list or string) to a valid key."""
    if isinstance(raw, list):
        raw = raw[0] if raw else "other"
    return str(raw).strip().lower()

def force_remove_tree(path: Path):
    """Reliably delete a directory tree even with read-only files (Windows)."""
    def on_error(func, p, exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass
    shutil.rmtree(str(path), onerror=on_error)

# ─── AI ANALYSIS ───────────────────────────────────────────────────────────────

class AIAnalyzer:
    def __init__(self, api_key: str, model: str):
        self.client = InferenceClient(token=api_key)
        self.model = model

    def analyze_project(self, project_name: str, code_sample: str) -> dict:
        prompt = f"""You are a code analyzer. Analyze this project and respond ONLY with a valid JSON object.

Project name: {project_name}

Code sample:
{code_sample}

Respond with EXACTLY this JSON format (no extra text):
{{
  "description": "one sentence describing what this project does",
  "category": "one of: machine_learning, web_development, automation, data_science, game_development, cli_tool, api_backend, database, hardware_iot, utility, other",
  "languages": ["list", "of", "languages", "used"],
  "tags": ["3", "to", "5", "relevant", "tags"],
  "readme_summary": "2-3 sentence summary for README"
}}"""

        try:
            response = self.client.chat_completion(
                messages=[{"role": "user", "content": prompt}],
                model=self.model,
                max_tokens=400,
                temperature=0.3,
            )
            text = response.choices[0].message.content.strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(text[start:end])
        except Exception as e:
            console.print(f"[yellow]AI analysis fallback for {project_name}: {e}[/yellow]")

        return {
            "description": f"Code project: {project_name}",
            "category": "other",
            "languages": [],
            "tags": [],
            "readme_summary": f"Project {project_name} backed up by Dev Vault."
        }

# ─── BACKUP ENGINE ─────────────────────────────────────────────────────────────

class BackupEngine:
    def __init__(self, config: dict):
        self.config = config
        self.backup_root = Path(config["backup_root"])
        self.analyzer = AIAnalyzer(config["hf_api_key"], config["model"])
        self.state_file = self.backup_root / ".vault_state.json"
        self.state = self._load_state()
        self.lock = threading.Lock()

    def _load_state(self) -> dict:
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_state(self):
        self.backup_root.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, "w") as f:
            json.dump(self.state, f, indent=2)

    def _generate_readme(self, project_name: str, analysis: dict, project_path: Path, category: str) -> str:
        langs = ", ".join(analysis.get("languages", [])) or "Various"
        tags_raw = analysis.get("tags", [])
        tags = " ".join(f"`{t}`" for t in tags_raw) if isinstance(tags_raw, list) else f"`{tags_raw}`"
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        return f"""# {project_name}

{analysis.get('description', '')}

## Summary
{analysis.get('readme_summary', '')}

## Details
- **Languages:** {langs}
- **Category:** {category.replace('_', ' ').title()}
- **Tags:** {tags}
- **Original Path:** `{project_path}`
- **Backed up:** {now}

---
*Auto-generated by Dev Vault 🔒*
"""

    def backup_project(self, project_path: Path):
        with self.lock:
            project_name = project_path.name
            state_key = str(project_path)

            # BUG FIX 2: Bail out early if the source path no longer exists
            if not project_path.exists():
                console.print(f"[dim]⚠  Skipping {project_name}: source path no longer exists[/dim]")
                return

            try:
                dir_hash = hashlib.md5(
                    str(sorted([
                        str(f) + str(f.stat().st_mtime)
                        for f in project_path.rglob("*")
                        if f.is_file() and not any(
                            ig in f.parts for ig in self.config["ignored_dirs"]
                        )
                    ])).encode()
                ).hexdigest()
            except Exception:
                dir_hash = str(time.time())

            if self.state.get(state_key, {}).get("hash") == dir_hash:
                console.print(f"[dim]⏭  No changes in {project_name}, skipping[/dim]")
                return

            console.print(f"\n[bold cyan]🔍 Analyzing:[/bold cyan] {project_name}")

            code_sample = collect_project_code(project_path, self.config["code_extensions"])
            analysis = self.analyzer.analyze_project(project_name, code_sample)

            # Normalize category — AI can return a list or unexpected type
            category = normalize_category(analysis.get("category", "other"))
            if category not in CATEGORY_FOLDERS:
                category = "other"

            category_folder = CATEGORY_FOLDERS[category]
            dest = self.backup_root / category_folder / project_name

            console.print(f"[bold green]💾 Backing up:[/bold green] {project_name} → {category_folder}/")

            # Delete old backup if exists (handles category changes between runs)
            if dest.exists():
                force_remove_tree(dest)

            # Also clean up any old backup in a different category folder
            for folder in CATEGORY_FOLDERS.values():
                old = self.backup_root / folder / project_name
                if old != dest and old.exists():
                    force_remove_tree(old)

            def ignore_func(d, contents):
                return [
                    c for c in contents
                    if c in self.config["ignored_dirs"] or c.startswith(".")
                ]

            def safe_copy(src, dst):
                try:
                    shutil.copy2(src, dst)
                except (OSError, PermissionError) as e:
                    console.print(f"[dim]⚠ Skipping file {Path(src).name}: {e}[/dim]")

            # Create dest folder fresh, then copy into it
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copytree(str(project_path), str(dest), ignore=ignore_func,
                            copy_function=safe_copy, dirs_exist_ok=True)

            readme_content = self._generate_readme(project_name, analysis, project_path, category)
            (dest / "VAULT_README.md").write_text(readme_content, encoding="utf-8")

            meta = {
                "project_name": project_name,
                "original_path": str(project_path),
                "backed_up_at": datetime.now().isoformat(),
                "category": category,
                "description": analysis.get("description", ""),
                "languages": analysis.get("languages", []),
                "tags": analysis.get("tags", []),
                "readme_summary": analysis.get("readme_summary", "")
            }
            (dest / "vault_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

            self.state[state_key] = {
                "hash": dir_hash,
                "last_backup": datetime.now().isoformat(),
                "category": category,
                "description": analysis.get("description", ""),
                "dest": str(dest)
            }
            self._save_state()

            console.print(f"[bold green]✅ Done:[/bold green] [italic]{analysis.get('description', '')}[/italic]")

# ─── FILE WATCHER ──────────────────────────────────────────────────────────────

class CodeChangeHandler(FileSystemEventHandler):
    def __init__(self, engine: BackupEngine, config: dict):
        self.engine = engine
        self.config = config
        self.pending = {}
        self.timer_lock = threading.Lock()

    def _is_code_file(self, path: str) -> bool:
        return any(path.endswith(ext) for ext in self.config["code_extensions"])

    def _is_ignored(self, path: str) -> bool:
        return any(ig in Path(path).parts for ig in self.config["ignored_dirs"])

    def _schedule_backup(self, project_path: Path):
        key = str(project_path)
        debounce = self.config["debounce_seconds"]
        with self.timer_lock:
            if key in self.pending:
                self.pending[key].cancel()
            t = threading.Timer(debounce, self.engine.backup_project, args=[project_path])
            self.pending[key] = t
            t.start()

    def on_modified(self, event):
        if event.is_directory or self._is_ignored(event.src_path):
            return
        if self._is_code_file(event.src_path):
            project_root = find_project_root(Path(event.src_path), self.config["watch_paths"])
            console.print(f"[dim]📝 Change detected in {Path(event.src_path).name}[/dim]")
            self._schedule_backup(project_root)

    def on_created(self, event):
        self.on_modified(event)

# ─── INITIAL SCAN ──────────────────────────────────────────────────────────────

def initial_scan(engine: BackupEngine, config: dict):
    console.print("\n[bold yellow]🔎 Running initial scan of all projects...[/bold yellow]\n")
    found = []
    ignored = set(config.get("ignored_dirs", []))

    # Resolve backup_root so we never scan inside the vault itself
    backup_root_resolved = Path(config["backup_root"]).resolve()

    for watch_path in config["watch_paths"]:
        wp = Path(watch_path)
        if not wp.exists():
            console.print(f"[dim]⚠ Skipping {watch_path} (not found)[/dim]")
            continue

        dirs_to_visit = [wp]
        while dirs_to_visit:
            current = dirs_to_visit.pop()

            # BUG FIX 1: Skip any directory that lives inside the backup vault
            try:
                current_resolved = current.resolve()
                if current_resolved == backup_root_resolved or \
                   backup_root_resolved in current_resolved.parents:
                    continue
            except (OSError, ValueError):
                pass

            if current.name in ignored:
                continue

            try:
                children = list(current.iterdir())
            except (PermissionError, OSError) as e:
                console.print(f"[dim]⚠ Skipping {current.name}: {e}[/dim]")
                continue

            try:
                if is_project_root(current):
                    if not any(str(current).startswith(str(f) + os.sep) for f in found):
                        found.append(current)
                    continue
            except (PermissionError, OSError):
                continue

            for child in children:
                try:
                    if child.is_symlink():
                        continue
                    if child.is_dir():
                        dirs_to_visit.append(child)
                except (PermissionError, OSError):
                    continue

    console.print(f"[bold]Found {len(found)} projects.[/bold]\n")

    # BUG FIX 3: Deduplicate by resolved path so the same folder isn't backed up twice
    seen = set()
    unique_found = []
    for proj in found:
        try:
            key = str(proj.resolve())
        except OSError:
            key = str(proj)
        if key not in seen:
            seen.add(key)
            unique_found.append(proj)

    for proj in unique_found:
        engine.backup_project(proj)

# ─── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    console.print(Panel.fit(
        "[bold cyan]Dev Vault[/bold cyan] 🔒\n"
        "[dim]AI-powered automatic code backup[/dim]",
        border_style="cyan"
    ))

    config = load_config()

    hf_key = config.get("hf_api_key", "")
    if hf_key in ("YOUR_HF_API_KEY_HERE", "", None) or not str(hf_key).startswith("hf_"):
        console.print("\n[bold yellow]⚙️  HuggingFace API key required![/bold yellow]")
        console.print("[dim]Get a free key at: huggingface.co/settings/tokens[/dim]\n")
        config["hf_api_key"] = console.input("[cyan]Enter your HuggingFace API key: [/cyan]").strip()
        current_root = config.get("backup_root", "H:/DevVault")
        new_root = console.input(
            f"[cyan]Enter your HDD backup path (press Enter to keep '{current_root}'): [/cyan]"
        ).strip()
        if new_root:
            config["backup_root"] = new_root
        watch = console.input(
            "[cyan]Enter folders to watch (comma-separated, press Enter to keep current): [/cyan]"
        ).strip()
        if watch:
            config["watch_paths"] = [w.strip() for w in watch.split(",")]
        save_config(config)
        console.print(f"\n[green]✅ Config saved to {CONFIG_FILE}[/green]")

    engine = BackupEngine(config)
    initial_scan(engine, config)

    handler = CodeChangeHandler(engine, config)
    observer = Observer()
    for watch_path in config["watch_paths"]:
        if Path(watch_path).exists():
            observer.schedule(handler, watch_path, recursive=True)
            console.print(f"[green]👁  Watching:[/green] {watch_path}")

    observer.start()
    console.print(f"\n[bold green]🚀 Dev Vault is running! Watching for changes 24/7...[/bold green]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        console.print("\n[yellow]Dev Vault stopped.[/yellow]")
    observer.join()

if __name__ == "__main__":
    main()