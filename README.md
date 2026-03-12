<pre>
.
├─ test_case # from QuixBugs(Only the executable `.py` files and corresponding `.txt` )
├─ results # some sample results
├─ cyto.json # Generated output (do not edit manually)
├─ index.html # Frontend visualization (Cytoscape)
├─ main.py # Calls OpenAI and generates cyto.json
├─ package-lock.json
├─ package.json 
└─ README.md
</pre>

---

## Requirements

- Python 3.10+
- OpenAI API key (API billing enabled)

---

## Setup

### 1. Install dependencies

```bash
pip3 install -r requirements.txt
```
### 2. Set your API key
### Windows(cmd):

```bash
setx OPENAI_API_KEY "YOUR_API_KEY"
```

### macOS / Linux:

```bash
export OPENAI_API_KEY="YOUR_API_KEY"
```

---

## Quick Start (recommended)

Run everything with a single command — installs deps, generates graphs, starts server, and opens the browser automatically:

```bash
python run.py
```

First run will prompt for your OpenAI API key and offer to save it to `.env` for future runs. It might take a while.

### Options

```bash
python run.py              # QuixBugs cases only (test_case/)
python run.py --swe        # Also fetch & process SWE-bench Lite cases
python run.py --no-pipeline  # Skip generation, just view existing output
python run.py --dir <path>   # Process a custom input directory if you want
```

---

### View visualization

```bash
python -m http.server 8000
# open http://localhost:8000/index.html
```

---

## Notes
Do not commit your API key. Use a `.env` file (added to `.gitignore`) instead.

