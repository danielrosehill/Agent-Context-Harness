---
title: Agent Task Break Detector
emoji: ✂️
colorFrom: indigo
colorTo: green
sdk: gradio
sdk_version: 5.49.1
app_file: app.py
pinned: false
license: apache-2.0
short_description: Does this message need the session so far, or a fresh one?
models:
- danielrosehill/Agent-Task-Break-Detector-ModernBERT
datasets:
- danielrosehill/Agent-Task-Break-Detector
tags:
- agents
- context-management
- topic-shift
- onnx
---

# Agent Task Break Detector: explainer and demo

Interactive explainer for [danielrosehill/Agent-Task-Break-Detector-ModernBERT](https://huggingface.co/danielrosehill/Agent-Task-Break-Detector-ModernBERT).
It runs the int8 ONNX build on CPU, with the input format and threshold (0.76) the model expects; both come from the model's `new_task_split.json`.

Source: [Agent-Context-Harness/space](https://github.com/danielrosehill/Agent-Context-Harness/tree/main/space).
