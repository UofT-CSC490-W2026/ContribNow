def build_prompt(user_prompt: str | None, context: str) -> str:
    user_request_section = ""
    if user_prompt and user_prompt.strip():
        user_request_section = f"""

Additional user request:
{user_prompt.strip()}
"""

    return f"""
You are generating a markdown onboarding guide for a new contributor.

Write only markdown.

Use exactly these sections:
1. Project Overview
2. Tech Stack
3. Repository Structure
4. Setup Instructions
5. How to Run Locally
6. Development Workflow
7. First Contribution Tips
8. Known Gaps / Things to Confirm

Rules:
- Be concrete and practical.
- Do not invent facts not supported by the context.
- If information is missing, explicitly say it should be confirmed.
- Keep the guide readable for a new team member.{user_request_section}

Repository context:
{context}
""".strip()