# Agent Usage Report

**Project:** Project Assistant - Document-to-Action AI Workflow  
**Date:** 2026-08-02

---

## 1. Overview

This report covers how GitHub Copilot's agentic features were used during development. It describes the tools invoked, the kinds of prompts that were effective, any work offloaded to sub-agents, mistakes that were caught and corrected, and the approach taken to verify generated code.

The project is a full-stack application (FastAPI + React + PostgreSQL with pgvector) orchestrated with Docker Compose. Copilot was used primarily for file scaffolding, context gathering, and iterative refinement of documentation.

---

## 2. How Copilot Was Used

Copilot was used across the entire development lifecycle, from initial scaffolding through to late-stage refinements. It acted as an interactive assistant rather than an autonomous code generator. Every change was initiated by the user, and output was always reviewed before acceptance.

The workflow followed a deliberate pattern. For any change touching application code, Copilot was run in **plan mode** so the generated plan could be reviewed and approved before a single line was written. For ambiguous requirements or unclear existing behaviour, **ask mode** was used first to gather clarifications without generating code prematurely. Once the path was clear, the actual implementation was done by reading relevant source files with `read_file` to understand existing patterns, producing output with `create_file` and `replace_string_in_file`, and refining iteratively as the user reviewed and requested adjustments.

No terminal commands were issued directly by Copilot. Docker operations, test runs, and environment management were handled by the user. No sub-agents were dispatched; all work was done in the primary conversation.

### Tools invoked across the project

| Tool                     | Purpose                                                             |
| ------------------------ | ------------------------------------------------------------------- |
| `read_file`              | Context gathering before every change. Source files, config, README |
| `create_file`            | Scaffolding new modules, routes, schemas, components, and tests     |
| `replace_string_in_file` | Targeted edits to existing code                                     |

---

## 3. Prompts That Worked Well

The following rules were applied to keep output efficient and consistent with the codebase:

1. Use comments extensively throughout all code.
2. Analyse the existing codebase to ensure every implementation is consistent with surrounding patterns.
3. Before fixing a bug or implementing a feature, trace the full cycle from frontend to backend. For example, when fixing a JWT issue, analyse the entire authentication flow first.
4. Prefer the most optimised and efficient approach using the least code possible; avoid simplistic or naive solutions.
5. Maintain consistent data formatting across the entire flow.
6. Do not create markdown files unless explicitly asked.
7. Remove backward-compatible code when an implementation changes, do not leave dead branches behind.
8. Make the least number of changes needed to accomplish the goal.

---

## 4. Agent Delegation

No sub-agents were used. If the project grows in complexity, useful delegation targets would be:

- Cross-file symbol search (e.g. "find all callers of `extract_findings`")
- Library documentation lookups via Context7 (FastAPI, SQLAlchemy, Tailwind)
- Pylance-powered refactoring (`source.unusedImports`, `source.addTypeAnnotation`)

---

## 5. Mistakes & Rejected Output

Three design decisions were originally made by the assistant that were rejected as suboptimal for this project:

| #   | What it generated                                                                                                                                                                                                                          | Why it was wrong                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | What was done instead                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | **Field aliases in the LLM output schema**: The assistant added Pydantic `Field(alias=...)` mappings so the LLM could use keys like `statement`, `decision`, `description` and they'd be silently mapped to the canonical `content` field. | This is a probabilistic band-aid. Adding aliases treats the symptom (inconsistent LLM key names) rather than the cause. The LLM would still sometimes pick the wrong key, aliases would silently swallow the mismatch, and the mapping logic grew fragile as more entity types were added. Every new alias increased the chance of collisions and made debugging harder.                                                                                                            | **Forced the LLM to output the exact JSON schema via Ollama's native `with_structured_output` mode.** This constrains token sampling at the model level so the LLM _cannot_ emit keys that don't exist in the Pydantic schema. Instead of catching mistakes post-hoc, the approach eliminates the entire class of key-naming errors. No aliases, no regex fallbacks, no synonym maps.                                                                                         |
| 2   | **A single monolithic LLM invocation for the entire analysis**: One big prompt that asked the LLM to retrieve documents, extract entities, detect conflicts, check policies, and produce a summary all in one call.                        | Context-window overload. A single prompt packed with retrieval results, extraction instructions, conflict rules, policy references, and summary formatting pushed the LLM past its effective reasoning limits. The output was inconsistent: entities were missed, conflicts went undetected, and the summary was shallow. Worse, when the model hallucinated a field name or missed a step, there was no way to isolate and retry just that part, the entire call had to be re-run. | **Split into a 4-phase structured pipeline** (Phase 1: per-document extraction, Phase 2: cross-document conflict detection, Phase 3: policy-gap analysis, Phase 4: executive summary). Each phase has a single, narrow responsibility with its own focused prompt and its own `with_structured_output` schema. If one phase produces a bad result, only that phase needs to be retried. Context windows stay manageable, and each phase's output is independently verifiable. |
| 3   | **Local Ollama with `qwen2.5:32b` or `qwen2.5:3b`**: The assistant set up the project to use locally-hosted models, choosing between the heavy 32B variant for quality or the lightweight 3B variant for speed.                            | The 32B model was too large to run on consumer hardware with acceptable latency, inference times were measured in minutes per document. The 3B model ran fast but lacked the reasoning depth needed for structured extraction, conflict detection, and policy analysis; it would hallucinate field names, skip entire entity categories, and produce garbled JSON. Neither model hit the sweet spot of quality + speed for this use case.                                           | **Switched to the Ollama Cloud API with `ollama-gpt-oss:120b`.** This model runs on Ollama's cloud infrastructure so there's no local hardware burden, and at 120B parameters it has more than enough capacity for multi-document reasoning, structured JSON output, and the full 4-phase pipeline, all with sub-minute inference times.                                                                                                                                      |

---

## 6. Verification Approach

Copilot was always run in **plan mode** for any change touching application code, the generated plan was reviewed and approved before a single line was written. For ambiguous requirements or unclear existing behaviour, **ask mode** was used first to gather clarifications without generating code prematurely. This kept the workflow deliberate: clarify in ask mode, plan in plan mode, then execute.

Early in the project, when the codebase was small and the surface area limited, verification was manual spot-checking API responses in the browser and eyeballing database state. As complexity grew with the addition of the multi-phase extraction pipeline, pgvector chunking, FAISS indexing, and the review workspace, a proper test suite was added. The backend now has pytest coverage across auth, knowledge CRUD, project CRUD, extraction schemas, the extraction pipeline, and the FAISS service (`docker compose exec backend pytest`). The frontend type-checks with `tsc --noEmit`. Every significant change after that point was verified by running the relevant test suite before considering the work done.

---

## 7. Summary

Copilot was effective for documentation scaffolding and iterative editing. The session was low-risk (no production code was modified), so verification was limited to manual review. For future sessions that touch application code, the full test-and-lint pipeline should be run after each change.
