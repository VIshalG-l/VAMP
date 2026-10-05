from config import MAX_RETRIES
from modules.analyzer import analyze
from modules.llm import ask_llm
from modules.patcher import backup_file, apply_patch
from modules.builder import build_project


class BugFixAgent:

    def __init__(self, workspace, log_file):
        self.workspace = workspace
        self.log_file = log_file

    def run(self):

    	for attempt in range(MAX_RETRIES):

    	    print(f"\nAttempt {attempt+1}")

    	    report = analyze(
    	        self.log_file,
    	        self.workspace
    	    )

    	    patch = ask_llm(report)

    	    backup_file(report["source"])

    	    apply_patch(
    	        report["source"],
    	        patch
    	    )

    	    success, logs = build_project(
    	        self.workspace
    	    )

    	    if success:
    	        print("\nBug Fixed")
    	        return True

    	    print("\nStill Failing")

    	print("\nMaximum retries reached.")

    	return False

"""    def run(self):

        print("=" * 60)
        print("Starting Bug Fix Agent")
        print("=" * 60)

        report = analyze(
            self.log_file,
            self.workspace
        )

        print("\nCrash:")
        print(report["crash"])

        patch = ask_llm(report)

        print("\nExplanation:")
        print(patch.explanation)

        backup_file(report["source"])

        ok = apply_patch(
            report["source"],
            patch
        )

        if not ok:
            print("\nPatch failed")
            return False

        print("\nPatch applied")

        success, logs = build_project(
            self.workspace
        )

        print("\nBuild Result:", success)

        if success:
            print("\nProject builds successfully.")
            return True

        print("\nBuild failed.")
        print(logs)

        return False
"""


