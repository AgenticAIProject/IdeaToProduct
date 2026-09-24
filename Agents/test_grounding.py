"""
test_grounding.py - Standalone test for Kaggle Startup Success and GH Archive Grounding tools.
"""

from tools import market_check, github_issues_check

test_ideas = [
    "internship portal for university students to apply with resumes",
    "daily schedule planner and habit calendar",
    "expense sharing wallet and budget splitter for roommates"
]

print("============================================================")
print("  TESTING GROUNDING TOOLS & DATASETS")
print("============================================================")

for idea in test_ideas:
    print(f"\n[IDEA]: {idea}")
    
    # 1. Test Kaggle Startup Success dataset
    market = market_check.invoke({"idea": idea})
    print(f"   [Kaggle Dataset Match]")
    print(f"     Sector: {market.get('category')}")
    print(f"     Viability Score: {market.get('viability_score')}/10 (Verdict: {market.get('verdict')})")
    print(f"     Historical V1 Survival Rate: {market.get('success_rate', 0) * 100:.0f}%")
    print(f"     Top Incumbents: {', '.join(market.get('similar_products', []))}")
    print(f"     Key Failure Risks: {'; '.join(market.get('risks', [])[:2])}")

    # 2. Test GH Archive / GitHub Issues dataset
    keywords = [w for w in idea.split() if len(w) > 3][:4]
    gh = github_issues_check.invoke({"keywords": keywords})
    print(f"   [GH Archive Issue Grounding] (Source: {gh.get('source')})")
    print(f"     Retrieved {gh.get('issue_count')} developer issues:")
    for iss in gh.get("issues", [])[:2]:
        print(f"       * [{iss.get('repo')}] {iss.get('title')}")

print("\n============================================================")
print("  ALL GROUNDING TESTS COMPLETED")
print("============================================================")
