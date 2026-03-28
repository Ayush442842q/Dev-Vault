# 🔒 Dev Vault — AI-Powered Code Backup

Automatically watches your laptop for code projects, uses HuggingFace AI to **understand** what each project does, and backs them up to your external HDD — organized, labeled, and with auto-generated READMEs.

---

## ✨ What it does

- **Watches** your folders 24/7 for any code changes
- **Understands** your project using HuggingFace AI (Mistral-7B)
- **Organizes** projects into smart categories automatically:
  ```
  DevVault/
  ├── 01_MachineLearning/
  ├── 02_WebDevelopment/
  ├── 03_Automation/
  ├── 04_DataScience/
  ├── 05_GameDevelopment/
  ├── 06_CLITools/
  ├── 07_APIBackend/
  ├── 08_Database/
  ├── 09_Hardware_IoT/
  ├── 10_Utilities/
  └── 11_Other/
  ```
- **Generates** a `VAULT_README.md` for every project with description, languages, tags
- **Saves** a `vault_meta.json` with full AI analysis metadata
- **Debounces** changes — waits 10 seconds after last change before backing up (no spam)
- **Skips** unchanged projects using directory hashing

---

## 🚀 Installation

```bash
# 1. Clone or download this folder
cd dev_vault

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run it
python vault.py
```

On first run it will ask you for:
- Your **HuggingFace API key** (free at huggingface.co/settings/tokens)
- Your **HDD backup path** (e.g. `D:/DevVault` or `/media/myHDD/DevVault`)
- Which **folders to watch** (defaults to Documents + Desktop)

---

## ⚙️ Config

Config is saved at `~/.dev_vault_config.json`. You can edit it directly:

```json
{
  "hf_api_key": "hf_xxxx",
  "watch_paths": ["C:/Users/You/Documents", "C:/Users/You/Desktop"],
  "backup_root": "D:/DevVault",
  "model": "mistralai/Mistral-7B-Instruct-v0.3",
  "debounce_seconds": 10,
  "ignored_dirs": ["node_modules", ".git", "__pycache__", "venv"]
}
```

---

## 🏃 Run on startup (Windows)

1. Press `Win + R` → type `shell:startup`
2. Create a file `devvault.bat`:
```bat
@echo off
cd C:\path\to\dev_vault
python vault.py
```

## 🏃 Run on startup (Linux/Mac)

Add to crontab:
```bash
@reboot cd /path/to/dev_vault && python vault.py >> ~/vault.log 2>&1
```

---

## 📁 Output example

For your `weather_predictor` project, Dev Vault creates:

```
DevVault/
└── 01_MachineLearning/
    └── weather_predictor/
        ├── [all your original files]
        ├── VAULT_README.md       ← AI-generated description
        └── vault_meta.json       ← full metadata
```

**VAULT_README.md preview:**
```markdown
# weather_predictor

A machine learning model that predicts rainfall using historical 
weather data and scikit-learn regression algorithms.

## Details
- Languages: Python
- Category: Machine Learning
- Tags: `ml` `weather` `regression` `scikit-learn` `prediction`
- Backed up: 2024-03-28 14:32
```

---

Built with ❤️ — your personal dev archive, forever organized.


Copyright (C) 2026 Ayush Singh
Licensed under GNU GPL v3
