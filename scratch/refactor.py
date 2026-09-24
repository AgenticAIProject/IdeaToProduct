import os
import re
from pathlib import Path

base_dir = Path("/Users/shivarajchougala/python/Ai/CourseProject/IdeaToProduct/Agents")
prompts_dir = base_dir / "prompts"
skills_dir = base_dir / "skills"
prompts_dir.mkdir(exist_ok=True)
skills_dir.mkdir(exist_ok=True)

files_to_process = [
    ("DesignAgent.py", "design_prompt", "prompts/design_prompt.txt"),
    ("CodeAgent.py", "code_prompt", "prompts/code_prompt.txt"),
    ("TestAgent.py", "system_prompt", "prompts/test_prompt.txt"),
    ("ReviewAgent.py", "review_prompt", "prompts/review_prompt.txt"),
    ("ReviewAgent.py", "review_skill", "skills/review_skill.txt"),
    ("DocumentationAgent.py", "doc_prompt", "prompts/documentation_prompt.txt"),
    ("RequirementAgent.py", "clarification_prompt", "prompts/clarification_prompt.txt"),
    ("RequirementAgent.py", "requirement_prompt", "prompts/requirement_prompt.txt"),
    ("RequirementAgent.py", "requirement_skill", "skills/requirement_skill.txt"),
]

# Utility loader to put in imports.py
utils_code = """
import os
from pathlib import Path

def load_prompt(filename: str) -> str:
    path = Path(__file__).resolve().parent / filename
    with open(path, "r") as f:
        return f.read()
"""

imports_path = base_dir / "imports.py"
imports_content = imports_path.read_text()
if "def load_prompt" not in imports_content:
    with open(imports_path, "a") as f:
        f.write("\n" + utils_code)

for filename, var_name, out_path in files_to_process:
    filepath = base_dir / filename
    if not filepath.exists():
        continue
        
    content = filepath.read_text()
    
    # We look for:
    # var_name = imports.SystemMessage(
    #     content="""..."""
    # )
    
    # Regex to capture the content inside """..."""
    pattern1 = re.compile(rf"{var_name}\s*=\s*imports\.SystemMessage\(\s*content=\"\"\"(.*?)\"\"\"\s*\)", re.DOTALL)
    # For skills (which are AIMessages)
    pattern2 = re.compile(rf"{var_name}\s*=\s*imports\.AIMessage\(\s*content=\"\"\"(.*?)\"\"\"\s*\)", re.DOTALL)
    
    match1 = pattern1.search(content)
    match2 = pattern2.search(content)
    
    match = match1 or match2
    if match:
        extracted_text = match.group(1).strip()
        
        # Write to external file
        out_file = base_dir / out_path
        out_file.write_text(extracted_text)
        
        # Replace in original file
        if match1:
            replacement = f'{var_name} = imports.SystemMessage(content=imports.load_prompt("{out_path}"))'
        else:
            replacement = f'{var_name} = imports.AIMessage(content=imports.load_prompt("{out_path}"))'
            
        new_content = content[:match.start()] + replacement + content[match.end():]
        filepath.write_text(new_content)
        print(f"Successfully extracted {var_name} from {filename} to {out_path}")
    else:
        print(f"Could not find {var_name} in {filename}")

