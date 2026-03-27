def retrieve_context(repo_url: str) -> str:
    # TODO: call RAG endpoint here
    return f"""
Repository URL: {repo_url}
Main purpose: Web app for contributor onboarding
Possible stack: React frontend, backend API, cloud deployment
Important note: Exact setup steps are not confirmed yet
"""