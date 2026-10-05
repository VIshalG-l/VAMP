from modules.llm import ask_llm

report = """
ANR in com.demo.app

Reason:
Input dispatching timed out

MainActivity.java:53
"""

patch = ask_llm(report)

print("Old Code:")
print(patch.old_code)

print("\nNew Code:")
print(patch.new_code)

print("\nExplanation:")
print(patch.explanation)
