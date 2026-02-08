---
name: using-semantic-memory
description: This skill should be used when the user asks to "store a memory", "remember this", "save this insight", "search memories", "find related insights", "what do I know about", "connect these concepts", "add a relationship", "traverse the knowledge graph", or when working with the sem-mem MCP tools. Also activates when storing learnings, debugging knowledge, or building on prior insights.
---

# Using Sem-Mem

Sem-Mem is a persistent knowledge graph MCP server that stores insights as normalized semantic frames with embeddings and typed subject relations. Use it to build durable knowledge that survives context compaction and spans sessions.

## When to Use

- **Storing knowledge**: Lessons learned, debugging discoveries, architectural decisions, code patterns
- **Retrieving knowledge**: "What do I know about X?", finding prior solutions to similar problems
- **Building connections**: Linking problems to resolutions, people to projects, tasks to PRs
- **Preserving context**: Before compaction, store critical insights from the current conversation

## Available MCP Tools (9 total)

### Writing Tools

**`store_insight`** — Primary entry point for storing knowledge.
```
store_insight(text, domain?, source?, repo?, pr?, author?, project?, task?)
```
- `text`: Raw knowledge to store (decomposed into atomic insights automatically)
- `domain`: Comma-separated knowledge areas (e.g., "react,typescript")
- `source`: Where this knowledge came from
- Git context params (`repo`, `pr`, `author`, `project`, `task`): Creates subjects and typed relations in the knowledge graph

The server automatically: decomposes text into atomic insights, classifies semantic frame, extracts entities/problems/resolutions/contexts, generates embeddings, creates subjects and relations.

**`update_insight`** — Adjust confidence on an existing insight.
```
update_insight(insight_id, confidence)
```

**`forget`** — Remove an insight from memory.
```
forget(insight_id)
```

**`add_subject_relation`** — Manually create typed edges between subjects.
```
add_subject_relation(from_name, from_kind, to_name, to_kind, relation_type)
```
Valid relation types: contains, scopes, frames, solved_by, implemented_in, applies_to, involves, has_problem, addresses, produces, works_on, authors, resolves.

### Reading Tools

**`search_insights`** — Semantic similarity search using embeddings.
```
search_insights(query, domain?, limit?)
```
Best for: finding insights by meaning/intent, exploring "what do I know about X?"

**`search_by_subject`** — Indexed lookup by subject name and kind.
```
search_by_subject(name, kind?, limit?)
```
Best for: precise retrieval when the subject is known. Faster than embedding search. Subject kinds: domain, entity, problem, resolution, context, person, project, task, pr, repo.

**`list_insights`** — Browse stored insights with optional filters.
```
list_insights(domain?, frame?, limit?)
```
Frame types: causal, constraint, pattern, equivalence, taxonomy, procedure.

**`related_insights`** — Find insights connected via shared subjects.
```
related_insights(insight_id, limit?)
```
Traverses the knowledge graph — finds insights that share domains, entities, problems, etc.

**`get_subject_relations`** — Traverse the subject hierarchy.
```
get_subject_relations(name, kind?, relation_type?, limit?)
```
Follow typed edges: repo→contains→project, problem→solved_by→resolution, etc.

## Search Strategy Guide

| Goal | Tool | Example |
|------|------|---------|
| Find by meaning | `search_insights` | "how to fix race conditions in asyncio" |
| Find by exact subject | `search_by_subject` | name="asyncio", kind="entity" |
| Browse a domain | `list_insights` | domain="python", frame="pattern" |
| Explore connections | `related_insights` | Starting from a known insight ID |
| Follow hierarchy | `get_subject_relations` | name="sem-mem", kind="repo" |

**Combine tools for deep retrieval:**
1. `search_insights` to find a relevant insight
2. `related_insights` on the result to discover connected knowledge
3. `get_subject_relations` to traverse the hierarchy

## Subject Kinds and Relations

10 subject kinds with 16 typed relation types. Auto-created on insert when subjects co-occur:

| From | Relation | To |
|------|----------|----|
| context | frames | problem |
| context | applies_to | domain |
| context | involves | entity |
| entity | has_problem | problem |
| problem | solved_by | resolution |
| resolution | implemented_in | pr |
| resolution | applies_to | entity |
| domain | scopes | entity |
| domain | contains | domain (sub) |
| repo | contains | project |
| project | contains | task |
| task | produces | pr |
| task | addresses | problem |
| person | works_on | project |
| person | authors | pr |
| person | resolves | problem |

## Best Practices

### Storing Insights Effectively

- **Include git context** when the insight relates to code work — pass `repo`, `pr`, `author`, `project`, `task` to create the full traceability chain
- **Specify domains** to enable filtered retrieval later
- **Let the normalizer work** — pass raw natural language, the LLM decomposer handles atomization and classification
- **Store at decision points** — when a non-obvious choice is made, store why

### Retrieving Insights

- **Start broad, narrow down** — use `search_insights` first, then `search_by_subject` for precision
- **Check related insights** — a single insight often connects to a cluster of related knowledge
- **Use subject relations** to understand the broader context of an insight

## Additional Resources

### Reference Files

For the complete subject hierarchy and schema details:
- **`references/schema.md`** — Full database schema, migration history, and measured statistics
