import sys
from pathlib import Path
import json

# Add Agents to path
sys.path.append(str(Path(__file__).parent / "Agents"))

from Agents.CodeAgent import Code_Agent
from Agents.State_definition import AgentState

def run_individual_test():
    print("=================================================================")
    print("TESTING Code_Agent INDIVIDUALLY WITH FRONTEND INPUT STATE")
    print("=================================================================")

    # Prepare a realistic input state coming from Requirement & Design Agents
    state: AgentState = {
        "project_id": "stockmarket_viz_v1",
        "user_id": "user_001",
        "idea": "Build a frontend for stock market visualization",
        "requirements": {
            "problem_statement": "Users need an interactive frontend dashboard to visualize stock market trends, search ticker symbols, and monitor stock performance.",
            "target_audience": "Retail investors and market analysts",
            "scope": {
                "in_scope": [
                    "Interactive stock price charts",
                    "Ticker search and selection",
                    "Watchlist management in local storage",
                    "Summary statistics (Open, High, Low, Close, Volume)"
                ],
                "out_of_scope": ["Broker integration", "Real money trading", "Backend database"]
            },
            "functional_requirements": [
                {
                    "id": "FR-01",
                    "title": "Interactive Stock Chart",
                    "description": "Render interactive price history charts for selected tickers",
                    "acceptance_criteria": [
                        "Display price history charts with timeframe selection (1D, 1W, 1M, 1Y)",
                        "Render tooltip with price, date, and volume on hover"
                    ],
                    "priority": "HIGH"
                },
                {
                    "id": "FR-02",
                    "title": "Ticker Search and Filter",
                    "description": "Search and select stock tickers from a list",
                    "acceptance_criteria": [
                        "Real-time search filtering of stock symbols and names",
                        "Selecting a ticker updates the main chart view"
                    ],
                    "priority": "HIGH"
                },
                {
                    "id": "FR-03",
                    "title": "Watchlist Management",
                    "description": "Save favorite tickers to personal watchlist",
                    "acceptance_criteria": [
                        "Users can toggle star/favorite to save stocks to browser localStorage",
                        "Watchlist displays current price and percentage change"
                    ],
                    "priority": "MEDIUM"
                }
            ],
            "non_functional_requirements": [
                {
                    "id": "NFR-01",
                    "category": "Performance",
                    "requirement": "Chart re-render in under 50ms upon ticker switch",
                    "target_metric": "< 50ms"
                },
                {
                    "id": "NFR-02",
                    "category": "Responsiveness",
                    "requirement": "Responsive dark mode financial dashboard layout",
                    "target_metric": "Responsive"
                }
            ]
        },
        "requirements_version": 1,
        "design": {
            "system_type": "Frontend Web Application",
            "architecture_pattern": "Single Page Application (SPA)",
            "technology_choices": {
                "frontend": "HTML/CSS/JS",
                "backend": None,
                "database": None,
                "testing": "jest"
            },
            "components": [
                {
                    "name": "MarketDashboard",
                    "responsibility": "Main container UI with navigation, search bar, and active ticker summary",
                    "interfaces": ["renderDashboard()", "handleTickerSelect(symbol)"]
                },
                {
                    "name": "ChartVisualizer",
                    "responsibility": "Canvas/SVG chart renderer for stock price trends and timeframes",
                    "interfaces": ["renderChart(data, timeframe)", "updateHoverTooltip(point)"]
                },
                {
                    "name": "WatchlistManager",
                    "responsibility": "Manages starred symbols with localStorage persistence",
                    "interfaces": ["getWatchlist()", "addToWatchlist(symbol)", "removeFromWatchlist(symbol)"]
                }
            ],
            "api_endpoints": [],
            "data_entities": [],
            "security_considerations": ["Sanitize search inputs", "Safe local storage key namespacing"]
        },
        "design_version": 1,
        "code": {},
        "code_version": 0,
        "test_results": {},
        "test_version": 0,
        "review": {},
        "review_version": 0,
        "documentation": {},
        "documentation_version": 0,
        "clarification_questions": [],
        "user_answers": [],
        "clarification_round": 0,
        "current_stage": "code",
        "workflow_status": "running",
        "retry_count": {"requirements": 0, "design": 0, "code": 0, "test": 0, "review": 0},
        "approval_status": "approved"
    }

    print("\n[1] Input State Prepared:")
    print(f"  - Project ID: {state['project_id']}")
    print(f"  - Idea: {state['idea']}")
    print(f"  - System Type: {state['design']['system_type']}")
    print(f"  - Frontend: {state['design']['technology_choices']['frontend']} | Backend: {state['design']['technology_choices']['backend']} | DB: {state['design']['technology_choices']['database']}")
    print(f"  - Components: {[c['name'] for c in state['design']['components']]}")

    print("\n[2] Executing Code_Agent(state)...\n")
    new_state = Code_Agent(state)

    print("\n[3] Execution Completed! Inspecting Output State:")
    print(f"  - Code Version: {new_state.get('code_version')}")
    print(f"  - Current Stage: {new_state.get('current_stage')}")
    
    code_artifact = new_state.get("code", {})
    files = code_artifact.get("files", [])
    print(f"  - Total Generated Files: {len(files)}")
    for idx, f in enumerate(files, 1):
        print(f"    {idx}. {f['path']} ({len(f['content'].splitlines())} lines) -> Req IDs: {f.get('requirement_ids')}, Comp IDs: {f.get('design_component_ids')}")

    print("\n[4] Dependencies:")
    print(f"  {code_artifact.get('dependencies', [])}")

    print("\n[5] Test Command:")
    print(f"  {code_artifact.get('test_command')}")

    print("\n[6] Setup Instructions:")
    print(f"  {code_artifact.get('setup_instructions')}")

    print("\n[7] Sample Code Preview (index.html):")
    html_file = next((f for f in files if f['path'] == 'index.html'), None)
    if html_file:
        print("-----------------------------------------------------------------")
        print(html_file['content'])
        print("-----------------------------------------------------------------")
    
    print("\n✓ CodeAgent standalone execution completed successfully!")

if __name__ == "__main__":
    run_individual_test()
