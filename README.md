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

## Auto-Pipeline Work:

```bash
python pipeline.py # run this first
python -m http.server 8000
```

---

## Generate Graph JSON

```bash
python main.py
```

##  View Visualization
start a local server:

```bash
python -m http.server 8000
```

open:

```bash
http://localhost:8000/index.html
```
then u can see the graph

## Notes
Do not commit your API key.

