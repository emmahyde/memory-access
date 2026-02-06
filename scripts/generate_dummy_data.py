#!/usr/bin/env python3
"""Generate ~1000 realistic insights and insert them into the semantic memory database."""

import asyncio
import random
import sys
import time
from collections import Counter
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from semantic_memory.embeddings import EmbeddingEngine
from semantic_memory.models import Frame, Insight
from semantic_memory.storage import InsightStore


# Template components for generating realistic insights
CAUSAL_TEMPLATES = [
    ("When {condition}, {effect}", "IF {condition} THEN {effect}"),
    ("Using {tool} leads to {effect}", "USING {tool} CAUSES {effect}"),
    ("{action} causes {effect}", "{action} CAUSES {effect}"),
    ("If you {action}, it will {effect}", "IF {action} THEN {effect}"),
    ("{condition} results in {effect}", "{condition} RESULTS_IN {effect}"),
]

CONSTRAINT_TEMPLATES = [
    ("{tool} requires {requirement}", "{tool} REQUIRES {requirement}"),
    ("You must {action} before {other_action}", "MUST {action} BEFORE {other_action}"),
    ("{system} only works when {condition}", "{system} REQUIRES {condition}"),
    ("Cannot {action} without {requirement}", "CANNOT {action} WITHOUT {requirement}"),
    ("{feature} is not available in {context}", "{feature} UNAVAILABLE_IN {context}"),
]

PATTERN_TEMPLATES = [
    ("In {domain}, {pattern_desc}", "PATTERN: {pattern_desc} IN {domain}"),
    ("When debugging {issue}, check {solution}", "WHEN {issue} CHECK {solution}"),
    ("{system} typically exhibits {behavior}", "{system} EXHIBITS {behavior}"),
    ("Most {domain} problems involve {cause}", "{domain} PROBLEMS INVOLVE {cause}"),
    ("Common pattern: {pattern_desc}", "PATTERN: {pattern_desc}"),
]

PROCEDURE_TEMPLATES = [
    ("To {goal}, first {step1}, then {step2}", "TO {goal}: {step1} THEN {step2}"),
    ("Deploy by {step1}, followed by {step2}", "DEPLOY: {step1} THEN {step2}"),
    ("Fix {problem} by {solution}", "FIX {problem}: {solution}"),
    ("Standard process: {step1}, then {step2}", "PROCESS: {step1} THEN {step2}"),
    ("Recommended workflow: {step1} before {step2}", "WORKFLOW: {step1} BEFORE {step2}"),
]

TAXONOMY_TEMPLATES = [
    ("{item} is a type of {category}", "{item} IS_A {category}"),
    ("{concept} belongs to {category}", "{concept} BELONGS_TO {category}"),
    ("{tool} is classified as {category}", "{tool} IS_A {category}"),
    ("{pattern} is an instance of {category}", "{pattern} INSTANCE_OF {category}"),
]

EQUIVALENCE_TEMPLATES = [
    ("{term1} means the same as {term2}", "{term1} EQUIVALENT_TO {term2}"),
    ("{term1} and {term2} are interchangeable", "{term1} EQUIVALENT_TO {term2}"),
    ("In {context}, {term1} is equivalent to {term2}", "{term1} EQUIVALENT_TO {term2} IN {context}"),
]

# Content components
CONDITIONS = [
    "using async/await syntax",
    "working with large datasets",
    "deploying to production",
    "running tests in CI",
    "handling user input",
    "processing streaming data",
    "implementing authentication",
    "optimizing database queries",
    "dealing with concurrent requests",
    "working in a containerized environment",
]

EFFECTS = [
    "improved performance by 30%",
    "reduced memory usage significantly",
    "better error handling",
    "clearer stack traces",
    "faster debugging cycles",
    "more maintainable code",
    "easier testing",
    "better type safety",
    "reduced deployment time",
    "improved scalability",
]

TOOLS = [
    "Docker", "Kubernetes", "Git", "pytest", "TypeScript", "React", "PostgreSQL",
    "Redis", "Nginx", "Jenkins", "GitHub Actions", "Terraform", "Ansible",
    "Prometheus", "Grafana", "Elasticsearch", "RabbitMQ", "gRPC", "Jest", "Vim"
]

ACTIONS = [
    "add type annotations",
    "implement caching",
    "use connection pooling",
    "enable compression",
    "add logging",
    "implement retries",
    "use batch operations",
    "optimize indexes",
    "enable async processing",
    "implement circuit breakers",
]

REQUIREMENTS = [
    "proper error handling",
    "valid credentials",
    "sufficient permissions",
    "network connectivity",
    "compatible versions",
    "environment variables set",
    "database migrations run",
    "SSL certificates configured",
    "resource limits defined",
    "health checks configured",
]

SYSTEMS = [
    "Kubernetes pods",
    "Docker containers",
    "PostgreSQL connections",
    "Redis cache",
    "API rate limiting",
    "WebSocket connections",
    "message queues",
    "load balancers",
    "database replicas",
    "microservices",
]

ISSUES = [
    "memory leaks",
    "race conditions",
    "deadlocks",
    "connection timeouts",
    "cache misses",
    "authentication failures",
    "permission errors",
    "slow queries",
    "high CPU usage",
    "network latency",
]

SOLUTIONS = [
    "connection pool settings",
    "resource cleanup",
    "lock ordering",
    "timeout configuration",
    "cache warming strategies",
    "token refresh logic",
    "IAM policies",
    "query execution plans",
    "profiler output",
    "network traces",
]

DOMAINS_LIST = [
    "backend", "frontend", "devops", "database", "networking", "security",
    "testing", "monitoring", "deployment", "architecture", "performance",
    "cloud", "distributed-systems", "containers", "api-design"
]

ENTITIES_POOL = [
    "HTTP", "TCP", "SQL", "NoSQL", "REST", "GraphQL", "gRPC", "WebSocket",
    "OAuth", "JWT", "TLS", "DNS", "CDN", "API", "CLI", "SDK", "ORM",
    "CRUD", "ACID", "CAP", "CI/CD", "SLA", "SLO", "pod", "service",
    "deployment", "ingress", "volume", "namespace"
]

SOURCES = [
    "debugging_session",
    "code_review",
    "documentation",
    "pair_programming",
    "incident_response",
    "architecture_review",
]

PROBLEMS = [
    "memory leak", "race condition", "deadlock", "connection timeout",
    "cache miss", "authentication failure", "permission denied", "slow query",
    "high CPU usage", "network latency", "data corruption", "schema drift",
    "dependency conflict", "certificate expiry", "rate limiting hit",
    "disk full", "OOM kill", "DNS resolution failure", "port conflict",
    "session fixation", "CORS error", "N+1 query", "thread starvation",
]

RESOLUTIONS = [
    "added connection pooling", "implemented retry with backoff",
    "increased timeout to 30s", "added circuit breaker", "switched to async",
    "added index on created_at", "upgraded to v2 API", "rotated credentials",
    "added rate limiter", "implemented cache warming", "fixed lock ordering",
    "added health checks", "enabled compression", "switched to streaming",
    "added graceful shutdown", "implemented bulkhead pattern",
    "added request deduplication", "migrated to connection-per-request",
    "enabled query plan caching", "added resource limits",
]

CONTEXTS = [
    "production deploy", "staging test", "CI pipeline", "code review",
    "pair programming", "incident response", "load testing", "migration",
    "canary release", "blue-green deploy", "hotfix", "sprint planning",
    "post-mortem", "capacity planning", "security audit", "dependency update",
    "performance profiling", "chaos engineering", "on-call shift",
]


def generate_insight(frame: Frame, idx: int) -> Insight:
    """Generate a single realistic insight for the given frame type."""

    if frame == Frame.CAUSAL:
        template, norm_template = random.choice(CAUSAL_TEMPLATES)
        params = {
            "condition": random.choice(CONDITIONS),
            "effect": random.choice(EFFECTS),
            "tool": random.choice(TOOLS),
            "action": random.choice(ACTIONS),
        }
        text = template.format(**{k: v for k, v in params.items() if k in template})
        normalized = norm_template.format(**{k: v.upper() for k, v in params.items() if k in norm_template})
        domains = random.sample(["backend", "performance", "architecture", "devops"], k=random.randint(1, 3))
        entities = random.sample(ENTITIES_POOL[:15], k=random.randint(2, 4))
        problems = random.sample(PROBLEMS, k=random.randint(1, 2))
        resolutions = random.sample(RESOLUTIONS, k=random.randint(0, 1))
        contexts = random.sample(CONTEXTS, k=random.randint(0, 1))

    elif frame == Frame.CONSTRAINT:
        template, norm_template = random.choice(CONSTRAINT_TEMPLATES)
        params = {
            "tool": random.choice(TOOLS),
            "requirement": random.choice(REQUIREMENTS),
            "action": random.choice(ACTIONS),
            "other_action": random.choice(ACTIONS),
            "system": random.choice(SYSTEMS),
            "condition": random.choice(CONDITIONS),
            "feature": random.choice(["feature X", "async mode", "clustering", "sharding"]),
            "context": random.choice(["development", "production", "v1.x", "legacy systems"]),
        }
        text = template.format(**{k: v for k, v in params.items() if k in template})
        normalized = norm_template.format(**{k: v.upper() for k, v in params.items() if k in norm_template})
        domains = random.sample(["devops", "deployment", "security", "architecture"], k=random.randint(1, 2))
        entities = random.sample(ENTITIES_POOL, k=random.randint(1, 3))
        problems = random.sample(PROBLEMS, k=random.randint(0, 1))
        resolutions = []
        contexts = random.sample(CONTEXTS, k=random.randint(0, 1))

    elif frame == Frame.PATTERN:
        template, norm_template = random.choice(PATTERN_TEMPLATES)
        params = {
            "domain": random.choice(["microservices", "REST APIs", "database design", "testing", "CI/CD"]),
            "pattern_desc": random.choice([
                "retry with exponential backoff",
                "circuit breaker on third failure",
                "graceful degradation under load",
                "eventual consistency in distributed systems",
                "command query responsibility segregation",
            ]),
            "issue": random.choice(ISSUES),
            "solution": random.choice(SOLUTIONS),
            "system": random.choice(SYSTEMS),
            "behavior": random.choice(["predictable failure modes", "exponential resource growth", "bursty traffic patterns"]),
            "cause": random.choice(["configuration errors", "resource contention", "network issues", "state synchronization"]),
        }
        text = template.format(**{k: v for k, v in params.items() if k in template})
        normalized = norm_template.format(**{k: v.upper() for k, v in params.items() if k in norm_template})
        domains = random.sample(["distributed-systems", "architecture", "debugging", "monitoring"], k=random.randint(2, 3))
        entities = random.sample(ENTITIES_POOL, k=random.randint(2, 4))
        problems = random.sample(PROBLEMS, k=random.randint(1, 2))
        resolutions = random.sample(RESOLUTIONS, k=random.randint(1, 2))
        contexts = random.sample(CONTEXTS, k=random.randint(1, 2))

    elif frame == Frame.PROCEDURE:
        template, norm_template = random.choice(PROCEDURE_TEMPLATES)
        params = {
            "goal": random.choice(["deploy safely", "optimize performance", "debug connection issues", "setup monitoring"]),
            "step1": random.choice(["run tests", "check logs", "verify config", "backup database", "scale replicas"]),
            "step2": random.choice(["deploy to staging", "analyze metrics", "restart services", "update DNS", "verify health"]),
            "problem": random.choice(["memory leak", "slow queries", "connection timeout", "auth failure"]),
            "solution": random.choice(["restart with larger heap", "add indexes", "increase timeout", "refresh tokens"]),
        }
        text = template.format(**{k: v for k, v in params.items() if k in template})
        normalized = norm_template.format(**{k: v.upper() for k, v in params.items() if k in norm_template})
        domains = random.sample(["devops", "deployment", "debugging", "operations"], k=random.randint(1, 2))
        entities = random.sample(ENTITIES_POOL[:12], k=random.randint(1, 3))
        problems = random.sample(PROBLEMS, k=random.randint(1, 1))
        resolutions = random.sample(RESOLUTIONS, k=random.randint(1, 2))
        contexts = random.sample(CONTEXTS, k=random.randint(0, 1))

    elif frame == Frame.TAXONOMY:
        template, norm_template = random.choice(TAXONOMY_TEMPLATES)
        items = ["Redis", "MongoDB", "REST", "gRPC", "OAuth", "JWT", "Prometheus", "Grafana"]
        categories = ["NoSQL database", "API protocol", "authentication scheme", "monitoring tool"]
        params = {
            "item": random.choice(items),
            "category": random.choice(categories),
            "concept": random.choice(["circuit breaker", "load balancer", "service mesh"]),
            "tool": random.choice(TOOLS),
            "pattern": random.choice(["singleton", "factory", "observer", "adapter"]),
        }
        text = template.format(**{k: v for k, v in params.items() if k in template})
        normalized = norm_template.format(**{k: v.upper() for k, v in params.items() if k in norm_template})
        domains = random.sample(["architecture", "api-design", "database"], k=random.randint(1, 2))
        entities = random.sample(ENTITIES_POOL[:10], k=random.randint(1, 2))
        problems = []
        resolutions = []
        contexts = random.sample(CONTEXTS, k=random.randint(0, 1))

    else:  # EQUIVALENCE
        template, norm_template = random.choice(EQUIVALENCE_TEMPLATES)
        equiv_pairs = [
            ("pod restart", "container recreation"),
            ("horizontal scaling", "adding more instances"),
            ("cache invalidation", "cache clearing"),
            ("rolling update", "phased deployment"),
            ("blue-green deployment", "zero-downtime deployment"),
        ]
        pair = random.choice(equiv_pairs)
        params = {
            "term1": pair[0],
            "term2": pair[1],
            "context": random.choice(["Kubernetes", "Docker Swarm", "cloud environments", "microservices"]),
        }
        text = template.format(**{k: v for k, v in params.items() if k in template})
        normalized = norm_template.format(**{k: v.upper() for k, v in params.items() if k in norm_template})
        domains = random.sample(["devops", "containers", "deployment"], k=random.randint(1, 2))
        entities = random.sample(ENTITIES_POOL[:8], k=random.randint(1, 2))
        problems = []
        resolutions = []
        contexts = random.sample(CONTEXTS, k=random.randint(1, 1))

    return Insight(
        text=text,
        normalized_text=normalized,
        frame=frame,
        domains=domains,
        entities=entities,
        problems=problems,
        resolutions=resolutions,
        contexts=contexts,
        confidence=round(random.uniform(0.6, 1.0), 2),
        source=random.choice(SOURCES),
    )


async def main():
    """Generate insights and insert them into the database."""

    print("Starting insight generation...")
    start_time = time.time()

    # Initialize storage and embedding engine
    db_path = "/tmp/semantic-memory-test.db"
    store = InsightStore(db_path)
    await store.initialize()
    print(f"Database initialized at {db_path}")

    embedding_engine = EmbeddingEngine()
    print("Embedding engine initialized")

    # Generate insights with target distribution
    target_counts = {
        Frame.CAUSAL: 250,
        Frame.CONSTRAINT: 200,
        Frame.PATTERN: 250,
        Frame.PROCEDURE: 150,
        Frame.TAXONOMY: 100,
        Frame.EQUIVALENCE: 50,
    }

    all_insights = []
    for frame, count in target_counts.items():
        for i in range(count):
            insight = generate_insight(frame, i)
            all_insights.append(insight)

    print(f"Generated {len(all_insights)} insights")

    # Shuffle to mix frames
    random.shuffle(all_insights)

    # Process in batches
    batch_size = 50
    total_inserted = 0
    frame_counts = Counter()
    domain_counts = Counter()
    problem_counts = Counter()
    resolution_counts = Counter()
    context_counts = Counter()

    for i in range(0, len(all_insights), batch_size):
        batch = all_insights[i:i + batch_size]
        texts = [insight.normalized_text for insight in batch]

        # Generate embeddings for batch
        embeddings = embedding_engine.embed_batch(texts)

        # Insert each insight with its embedding
        for insight, embedding in zip(batch, embeddings):
            await store.insert(insight, embedding)
            frame_counts[insight.frame] += 1
            for domain in insight.domains:
                domain_counts[domain] += 1
            for p in insight.problems:
                problem_counts[p] += 1
            for r in insight.resolutions:
                resolution_counts[r] += 1
            for c in insight.contexts:
                context_counts[c] += 1
            total_inserted += 1

        print(f"Inserted batch {i // batch_size + 1}/{(len(all_insights) + batch_size - 1) // batch_size}")

    elapsed = time.time() - start_time

    # Print summary
    print("\n" + "=" * 60)
    print("GENERATION COMPLETE")
    print("=" * 60)
    print(f"Total insights inserted: {total_inserted}")
    print(f"Time elapsed: {elapsed:.2f} seconds")
    print(f"\nFrame distribution:")
    for frame in Frame:
        print(f"  {frame.value:12s}: {frame_counts[frame]:4d}")
    print(f"\nTop 10 domains:")
    for domain, count in domain_counts.most_common(10):
        print(f"  {domain:20s}: {count:4d}")
    print(f"\nTop 10 problems:")
    for problem, count in problem_counts.most_common(10):
        print(f"  {problem:25s}: {count:4d}")
    print(f"\nTop 10 resolutions:")
    for resolution, count in resolution_counts.most_common(10):
        print(f"  {resolution:35s}: {count:4d}")
    print(f"\nTop 10 contexts:")
    for context, count in context_counts.most_common(10):
        print(f"  {context:25s}: {count:4d}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
