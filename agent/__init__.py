"""Genuine agentic loop: a DeepSeek LLM drives the whole task by calling tools.

Unlike the deterministic pipeline, here the model plans, calls tools (PDBe
retrieval, residue mapping, per-tool predictions), observes results, and reasons
its way to the adjudication itself. The deterministic functions are demoted to
*tools the agent calls*; the decisions are the model's, not hardcoded if/else.
"""
