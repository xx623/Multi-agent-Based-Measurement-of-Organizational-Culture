PYTHON ?= python

.PHONY: demo test schemas replay windows-demo pilot-summary manifest

# Runs the five-role pipeline on demo/inputs with the pinned local model (config/model_pins.json)
# and writes new logs under runs/. Needs an OpenAI-compatible server for the pinned model,
# e.g. Ollama with `ollama create culture-qwen2.5-14b-20k -f config/Modelfile`.
demo:
	$(PYTHON) run_workflow.py demo

# Offline: replays the recorded constructed-passage run through controller and validators.
replay:
	$(PYTHON) run_workflow.py replay --recorded demo/recorded/DEMO-C_001

test:
	$(PYTHON) -m unittest discover -s tests -v

schemas:
	$(PYTHON) run_workflow.py export-schemas

windows-demo:
	$(PYTHON) run_workflow.py windows --transcript demo/inputs/synthetic_transcript_lseg.txt --out-dir work/demo --keep-ids --license synthetic --mask-terms demo/inputs/synthetic_mask_terms.json

pilot-summary:
	$(PYTHON) run_workflow.py pilot-summary --runs logs/pilot_2026-10-31_qwen2.5-14b

manifest:
	$(PYTHON) tools/make_manifest.py
